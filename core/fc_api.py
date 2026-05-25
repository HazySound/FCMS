"""FC Online API 클라이언트.

CF Worker 프록시(nexon-api-proxy.cemigs1.workers.dev)를 경유한다.

urllib3 PoolManager로 HTTP keep-alive connection을 재활용한다:
- 매 호출마다 TCP/TLS handshake를 새로 하지 않아 응답 latency 큰 절감
- 다수의 동시 호출 시 TLS handshake가 GIL을 묶어 메인 UI를 멈추게 하는
  문제를 근본적으로 해결 (handshake가 connection 수만큼만 발생)

호출 흐름:
    nickname -> get_ouid() -> ouid
    ouid -> get_match_ids() -> [matchId, ...]
    matchId -> get_match_detail() -> dict
"""

from __future__ import annotations

import json
import time
from typing import Optional
from urllib.parse import urlencode

import urllib3
from urllib3.exceptions import HTTPError as Urllib3HTTPError

API_BASE = "https://nexon-api-proxy.cemigs1.workers.dev"

MATCHTYPE_MANAGER = 52       # 감독모드 (FC 채굴 추적 대상)
DIVISION_SUPER_CHAMPIONS = 800
DIVISION_CHAMPIONS = 900

_TIMEOUT = urllib3.Timeout(connect=5.0, read=15.0)
_MAX_RETRIES = 3
_INITIAL_BACKOFF_SEC = 1.0
_RETRY_STATUS = {429, 500, 502, 503, 504}
_HEADERS = {
    "User-Agent": "FCStats/1.0",
    "Accept": "application/json",
    "Connection": "keep-alive",
}

# 단일 PoolManager 인스턴스 — thread-safe하며 같은 host로 가는 connection을
# 재활용한다. maxsize는 동시 idle keep-alive connection 수.
# block=False: maxsize 초과 시 일시적 connection을 추가 생성 (queue 대신).
_POOL = urllib3.PoolManager(
    num_pools=2,
    maxsize=128,
    block=False,
    retries=False,       # 재시도/backoff는 우리가 직접 관리
    timeout=_TIMEOUT,
    headers=_HEADERS,
)


class FcApiError(Exception):
    """FC API 호출 실패. 호출부에서 사용자 메시지로 변환 가능."""


def _http_get_json(path: str, params: dict):
    """GET + JSON parse. 429/5xx/네트워크 오류는 exponential backoff."""
    url = f"{API_BASE}{path}?{urlencode(params)}"

    backoff = _INITIAL_BACKOFF_SEC
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = _POOL.request("GET", url)
        except Urllib3HTTPError as e:
            if attempt < _MAX_RETRIES:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise FcApiError(f"통신 오류 {path}: {e}") from e

        status = resp.status
        if status in _RETRY_STATUS and attempt < _MAX_RETRIES:
            time.sleep(backoff)
            backoff *= 2
            continue
        if status >= 400:
            body = ""
            try:
                body = resp.data[:200].decode("utf-8", errors="replace")
            except Exception:
                pass
            raise FcApiError(f"HTTP {status} {path}: {body}")

        try:
            return json.loads(resp.data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise FcApiError(f"JSON 파싱 실패 {path}: {resp.data[:200]!r}") from e

    raise FcApiError(f"최대 재시도 초과: {path}")


def get_ouid(nickname: str) -> str:
    """닉네임 -> ouid. 존재하지 않으면 FcApiError."""
    data = _http_get_json("/fconline/v1/id", {"nickname": nickname})
    if not isinstance(data, dict):
        raise FcApiError(f"닉네임 응답 형식 예외: {type(data).__name__}")
    ouid = data.get("ouid")
    if not ouid:
        raise FcApiError(f"존재하지 않는 닉네임이거나 응답에 ouid 없음: {data}")
    return ouid


def get_match_ids(
    ouid: str,
    matchtype: int = MATCHTYPE_MANAGER,
    offset: int = 0,
    limit: int = 100,
    orderby: str = "desc",
) -> list[str]:
    """매치 ID 목록을 최신순으로 반환. 최대 100개씩 페이징."""
    data = _http_get_json(
        "/fconline/v1/user/match",
        {
            "ouid": ouid,
            "matchtype": matchtype,
            "offset": offset,
            "limit": limit,
            "orderby": orderby,
        },
    )
    if not isinstance(data, list):
        raise FcApiError(f"매치 목록 응답 형식 예외: {type(data).__name__} (예상: list)")
    return data


def get_match_detail(match_id: str) -> dict:
    """매치 상세 dict. matchDate, matchType, matchInfo[] 등 포함."""
    data = _http_get_json("/fconline/v1/match-detail", {"matchid": match_id})
    if not isinstance(data, dict):
        raise FcApiError(f"매치 상세 응답 형식 예외: {type(data).__name__} (예상: dict)")
    return data


def extract_user_match_info(detail: dict, user_ouid: str) -> Optional[dict]:
    """매치 상세 응답에서 user_ouid 본인 정보만 추출.

    division/seasonId가 null인 매치(통계 미완성)는 skip해 다음 sync에서
    retry되게 한다.
    """
    participants = detail.get("matchInfo") or []
    for p in participants:
        if p.get("ouid") == user_ouid:
            md = p.get("matchDetail", {})
            division = p.get("division")
            season_id = md.get("seasonId")
            match_result = md.get("matchResult")
            if division is None or season_id is None or not match_result:
                return None
            return {
                "ouid": p.get("ouid"),
                "nickname": p.get("nickname"),
                "division": division,
                "seasonId": season_id,
                "matchResult": match_result,
                "matchEndType": md.get("matchEndType") or 0,
            }
    return None


def calc_fc(division: int, match_result: str, match_end_type: int = 0) -> int:
    """매치별 FC 획득량.

    챔피언스(900) 승: +15  (정상승/몰수승 모두 동일)
    슈퍼챔피언스(800) 승: +20
    그 외 division / 무 / 패: 0
    """
    if match_result != "승":
        return 0
    if division == DIVISION_SUPER_CHAMPIONS:
        return 20
    if division == DIVISION_CHAMPIONS:
        return 15
    return 0
