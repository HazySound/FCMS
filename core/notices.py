"""공지사항 조회 + 필터링.

GitHub raw 컨텐츠에서 notices.json을 fetch해 표시할 공지 목록을 반환한다.
신규 공지를 띄우려면 repo 루트의 notices.json만 수정해서 push하면 됨 — 빌드 불필요.

JSON 스키마 (한 항목):
    {
      "id":         "2026-06-15-thing",      # 필수, 사용자별 dismiss 추적 키
      "date":       "2026-06-15",             # 선택, 표시용
      "title":      "공지 제목",
      "body":       "본문 텍스트 (줄바꿈 보존)",
      "urgent":     false,                    # 선택, true면 ⚠️ 강조 + 색 자동 빨강
      "color":      "#3b82f6",                # 선택, 직접 지정 시 urgent 자동색보다 우선
      "link_url":   "https://...",            # 선택, 있을 때만 링크 버튼 표시
      "link_label": "자세히 보기",            # 선택, 없으면 "<링크>"
      "expires_at": "2026-07-30"              # 선택 (YYYY-MM-DD), 그 날짜 지나면 표시 안 함
    }

네트워크 실패는 조용히 [] 반환 — 공지가 앱 시작을 지연/중단시키면 안 됨.
"""

from __future__ import annotations

import datetime as _dt
import json
import ssl
from urllib.request import Request, urlopen

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

from core import app_state
from version import GITHUB_REPO

NOTICES_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/notices.json"
_USER_AGENT = "FCMS-Notices/1.0"
_TIMEOUT = 10


def fetch_unseen_notices() -> list[dict]:
    """안 본 + 만료 안 된 공지만 반환. 표시 순서는 JSON 기재 순.

    네트워크 / JSON 오류는 silent — 빈 리스트 반환. 사용자 경험에 영향 없음.
    """
    raw = _fetch_json()
    if raw is None:
        return []
    items = raw.get("notices") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []

    seen = app_state.get_seen_notice_ids()
    today = _dt.date.today()
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        nid = it.get("id")
        if not nid or str(nid) in seen:
            continue
        if _is_expired(it.get("expires_at"), today):
            continue
        out.append(it)
    return out


def mark_seen(notice_id: str) -> None:
    app_state.mark_notice_seen(notice_id)


# ─────────────────────────────────────────────
# 내부 helpers
# ─────────────────────────────────────────────

def _fetch_json():
    # cache buster — push 직후도 빠르게 반영. CDN이 query string 다르면 캐시 미스.
    url = f"{NOTICES_URL}?t={int(_dt.datetime.utcnow().timestamp() // 60)}"
    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=_TIMEOUT, context=_SSL_CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _is_expired(expires_at, today: _dt.date) -> bool:
    if not expires_at:
        return False
    try:
        exp = _dt.datetime.strptime(str(expires_at), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return today > exp
