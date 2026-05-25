"""FC 채굴 통계 집계.

DB의 raw 매치 데이터를 사용자 관점의 요약으로 집계한다.

UTC <-> KST 변환은 이 모듈 내부에서만 처리한다. 외부 인터페이스는
KST 기준 date/datetime을 받고, DB 조회 시 UTC ISO 8601로 변환한다.

용어:
    오늘 = 한국 자정 00:00 ~ 다음날 00:00
    이번 시즌 = DB의 가장 큰 season_id (서비스 정책상 매치는 항상 최신순 적재)
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from core import fc_stats_db as db

KST = _dt.timezone(_dt.timedelta(hours=9))
_UTC = _dt.timezone.utc
_ISO_FMT = "%Y-%m-%dT%H:%M:%S"

WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]


def format_season_id(season_id: int) -> str:
    """202602 -> '2026년 시즌2'"""
    year = season_id // 100
    num = season_id % 100
    return f"{year}년 시즌{num}"


def format_date_with_weekday(date_str: str) -> str:
    """'2026-05-24' -> '2026-05-24 (일)'"""
    dt = _dt.datetime.strptime(date_str, "%Y-%m-%d")
    return f"{date_str} ({WEEKDAYS_KR[dt.weekday()]})"


# ─────────────────────────────────────────────
# 시간 변환 유틸 (내부)
# ─────────────────────────────────────────────

def _kst_now() -> _dt.datetime:
    return _dt.datetime.now(KST)


def _kst_to_utc_iso(dt_kst: _dt.datetime) -> str:
    return dt_kst.astimezone(_UTC).strftime(_ISO_FMT)


def _utc_iso_to_kst(s: str) -> _dt.datetime:
    return _dt.datetime.strptime(s, _ISO_FMT).replace(tzinfo=_UTC).astimezone(KST)


def _kst_date_to_utc_range(date_kst: _dt.date) -> tuple[str, str]:
    """KST 하루(자정~자정)에 해당하는 UTC ISO 8601 범위."""
    start = _dt.datetime.combine(date_kst, _dt.time(0, 0, 0), tzinfo=KST)
    end = start + _dt.timedelta(days=1)
    return _kst_to_utc_iso(start), _kst_to_utc_iso(end)


# ─────────────────────────────────────────────
# 요약 집계 (공통)
# ─────────────────────────────────────────────

def _summarize(matches: list[dict]) -> dict:
    """챔(900)/슈챔(800) 승·패 매치만 집계.
    그 외 division과 무승부 매치는 통계에서 완전 제외 → total = wins + losses 보장.
    """
    matches = [
        m for m in matches
        if m["division"] in (800, 900) and m["match_result"] in ("승", "패")
    ]
    total = len(matches)
    wins = losses = 0
    fc = sc_wins = ch_wins = 0
    for m in matches:
        if m["match_result"] == "승":
            wins += 1
            if m["division"] == 800:
                sc_wins += 1
            elif m["division"] == 900:
                ch_wins += 1
        else:  # "패"
            losses += 1
        fc += m["fc_earned"]

    return {
        "total":    total,
        "wins":     wins,
        "losses":   losses,
        "fc":       fc,
        "sc_wins":  sc_wins,
        "ch_wins":  ch_wins,
        "win_rate": (wins / total) if total > 0 else 0.0,
    }


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def get_today_summary() -> dict:
    """오늘(KST 자정~자정) 통계."""
    start, end = _kst_date_to_utc_range(_kst_now().date())
    return _summarize(db.get_matches_between(start, end))


def get_season_summary(season_id: int) -> dict:
    """특정 시즌 통계."""
    return _summarize(db.get_matches_by_season(season_id))


def get_period_summary(start_date_kst: _dt.date, end_date_kst: _dt.date) -> dict:
    """KST 날짜 구간 [start, end] 통계. end 날짜 포함."""
    start = _dt.datetime.combine(start_date_kst, _dt.time(0, 0, 0), tzinfo=KST)
    end = _dt.datetime.combine(end_date_kst + _dt.timedelta(days=1), _dt.time(0, 0, 0), tzinfo=KST)
    matches = db.get_matches_between(_kst_to_utc_iso(start), _kst_to_utc_iso(end))
    return _summarize(matches)


def get_daily_fc_chart(season_id: int) -> list[tuple[str, int]]:
    """시즌의 일별 FC 채굴량 시계열 (간단 차트용)."""
    return [(d["date"], d["fc"]) for d in get_daily_summary(season_id)]


def get_daily_summary(season_id: int) -> list[dict]:
    """일별 상세 (차트 호버 툴팁용). 챔/슈챔 승·패 매치만 집계 (무승부 제외)."""
    daily: dict[str, dict] = {}
    for m in db.get_matches_by_season(season_id):
        if m["division"] not in (800, 900):
            continue
        if m["match_result"] not in ("승", "패"):
            continue
        kst_dt = _utc_iso_to_kst(m["match_date"])
        key = kst_dt.strftime("%Y-%m-%d")
        if key not in daily:
            daily[key] = {
                "date": key, "fc": 0,
                "total": 0, "wins": 0, "losses": 0,
                "sc_wins": 0, "ch_wins": 0,
            }
        d = daily[key]
        d["total"] += 1
        d["fc"] += m["fc_earned"]
        if m["match_result"] == "승":
            d["wins"] += 1
            div = m["division"]
            if div == 800:
                d["sc_wins"] += 1
            elif div == 900:
                d["ch_wins"] += 1
        else:  # "패"
            d["losses"] += 1
    return sorted(daily.values(), key=lambda d: d["date"])


def get_season_summary_extended(season_id: int) -> dict:
    """기본 summary + 활동일 / 일평균 FC / 판수당 평균 FC."""
    s = get_season_summary(season_id)
    daily = get_daily_summary(season_id)
    active_days = len(daily)
    s["active_days"]   = active_days
    s["fc_per_day"]    = (s["fc"] / active_days) if active_days > 0 else 0.0
    s["fc_per_match"]  = (s["fc"] / s["total"]) if s["total"] > 0 else 0.0
    return s


def get_current_season_id() -> Optional[int]:
    """DB에 적재된 가장 큰 season_id = 현재 시즌. 없으면 None."""
    seasons = db.get_known_season_ids()
    return seasons[0] if seasons else None


def get_known_seasons() -> list[int]:
    """DB에 적재된 모든 시즌 ID (내림차순)."""
    return db.get_known_season_ids()


# ─────────────────────────────────────────────
# 신뢰도 도트 (🟢/🔴 인디케이터)
# ─────────────────────────────────────────────

def get_today_freshness() -> dict:
    """오늘 데이터의 신뢰도 상태.

    반환:
        state: 'empty' / 'red' (2h↑ 경과, 수동 sync 권장) / 'green' (2h 이내)
        last_synced_at: 마지막 sync UTC ISO 8601 (또는 None)
    """
    last_synced = db.get_state("last_synced_at")

    if not last_synced:
        return {"state": "empty", "last_synced_at": None}

    last_kst = _utc_iso_to_kst(last_synced)
    elapsed_hours = (_kst_now() - last_kst).total_seconds() / 3600
    state = "green" if elapsed_hours < 2 else "red"

    return {"state": state, "last_synced_at": last_synced}
