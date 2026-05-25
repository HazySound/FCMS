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

# ─────────────────────────────────────────────
# v0.2.0 — 기간 / 자동 단위 / 다차원 집계
# ─────────────────────────────────────────────

def get_matches_for_period(start_date_kst: _dt.date, end_date_kst: _dt.date) -> list[dict]:
    """KST 날짜 구간 [start, end]의 매치들. end 날짜 포함."""
    start = _dt.datetime.combine(start_date_kst, _dt.time(0, 0, 0), tzinfo=KST)
    end = _dt.datetime.combine(end_date_kst + _dt.timedelta(days=1), _dt.time(0, 0, 0), tzinfo=KST)
    return db.get_matches_between(_kst_to_utc_iso(start), _kst_to_utc_iso(end))


def _stat_matches(matches: list[dict]) -> list[dict]:
    """집계 대상 필터링 — 챔/슈챔 + 승/패만. 모든 breakdown 함수의 공통 전처리."""
    return [
        m for m in matches
        if m["division"] in (800, 900) and m["match_result"] in ("승", "패")
    ]


def summarize_matches(matches: list[dict]) -> dict:
    """기본 통계 + 활동일·평균 — 임의 매치 집합에 대해."""
    s = _summarize(matches)
    daily = daily_breakdown(matches)
    active_days = len(daily)
    s["active_days"] = active_days
    s["fc_per_day"] = (s["fc"] / active_days) if active_days > 0 else 0.0
    s["fc_per_match"] = (s["fc"] / s["total"]) if s["total"] > 0 else 0.0
    return s


def determine_unit(start_date: _dt.date, end_date: _dt.date) -> str:
    """기간 길이에 따라 차트 단위 자동 결정.

    반환:
        'hour'  — 단일 일자 (24시간대별)
        'day'   — 32일 미만
        'week'  — 32~120일
        'month' — 121일~700일
        'year'  — 700일 초과
    """
    if start_date == end_date:
        return "hour"
    days = (end_date - start_date).days + 1
    if days <= 31:
        return "day"
    if days <= 120:
        return "week"
    if days <= 700:
        return "month"
    return "year"


# ─────────────────────────────────────────────
# 그룹별 집계
# ─────────────────────────────────────────────

def hourly_breakdown(matches: list[dict]) -> list[dict]:
    """24시간대별 집계. KST 기준 0~23시."""
    buckets = [
        {"hour": h, "label": f"{h:02d}시",
         "total": 0, "wins": 0, "losses": 0, "fc": 0,
         "sc_wins": 0, "ch_wins": 0}
        for h in range(24)
    ]
    for m in _stat_matches(matches):
        kst = _utc_iso_to_kst(m["match_date"])
        b = buckets[kst.hour]
        _accumulate(b, m)
    for b in buckets:
        b["win_rate"] = (b["wins"] / b["total"]) if b["total"] > 0 else 0.0
    return buckets


# 시간대 4그룹 정의 (새벽/오전/오후/저녁) — 분포 탭에서 24segment 대신 사용
TIME_GROUPS = [
    ("새벽", "00~06시", range(0, 6)),
    ("오전", "06~12시", range(6, 12)),
    ("오후", "12~18시", range(12, 18)),
    ("저녁", "18~24시", range(18, 24)),
]


def time_group_breakdown(matches: list[dict]) -> list[dict]:
    """시간대를 4개 그룹(새벽/오전/오후/저녁)으로 묶어 집계.
    24개 segment를 직접 표시하기 어려운 도넛/요약용."""
    hourly = hourly_breakdown(matches)
    groups: list[dict] = []
    for name, sub, hours in TIME_GROUPS:
        g = {
            "label": name, "sub_label": sub,
            "total": 0, "wins": 0, "losses": 0, "fc": 0,
            "sc_wins": 0, "ch_wins": 0,
        }
        for h in hours:
            b = hourly[h]
            for k in ("total", "wins", "losses", "fc", "sc_wins", "ch_wins"):
                g[k] += b[k]
        g["win_rate"] = (g["wins"] / g["total"]) if g["total"] > 0 else 0.0
        groups.append(g)
    return groups


def weekday_breakdown(matches: list[dict]) -> list[dict]:
    """요일별 집계. 0=월 ~ 6=일."""
    buckets = [
        {"weekday": w, "label": WEEKDAYS_KR[w],
         "total": 0, "wins": 0, "losses": 0, "fc": 0,
         "sc_wins": 0, "ch_wins": 0}
        for w in range(7)
    ]
    for m in _stat_matches(matches):
        kst = _utc_iso_to_kst(m["match_date"])
        _accumulate(buckets[kst.weekday()], m)
    for b in buckets:
        b["win_rate"] = (b["wins"] / b["total"]) if b["total"] > 0 else 0.0
    return buckets


def daily_breakdown(matches: list[dict]) -> list[dict]:
    """일별 집계. key='YYYY-MM-DD'."""
    return _group_by(matches, lambda kst: (kst.strftime("%Y-%m-%d"), kst.strftime("%m-%d")))


def weekly_breakdown(matches: list[dict]) -> list[dict]:
    """주별 집계 (월요일 시작). key='YYYY-Www', label='M/D~D' (같은 달) 또는 'M/D~M/D'."""
    def key_label(kst):
        year, week, _ = kst.isocalendar()
        monday = kst.date() - _dt.timedelta(days=kst.weekday())
        sunday = monday + _dt.timedelta(days=6)
        if monday.month == sunday.month:
            label = f"{monday.month}/{monday.day}~{sunday.day}"
        else:
            label = f"{monday.month}/{monday.day}~{sunday.month}/{sunday.day}"
        return f"{year}-W{week:02d}", label
    return _group_by(matches, key_label)


def monthly_breakdown(matches: list[dict]) -> list[dict]:
    """월별 집계. key='YYYY-MM', label='MM월'."""
    return _group_by(matches, lambda kst: (kst.strftime("%Y-%m"), kst.strftime("%m월")))


def yearly_breakdown(matches: list[dict]) -> list[dict]:
    """연도별 집계. key='YYYY', label='YYYY년'."""
    return _group_by(matches, lambda kst: (kst.strftime("%Y"), kst.strftime("%Y년")))


def _group_by(matches, key_label_fn) -> list[dict]:
    """공통 그루핑 헬퍼. key_label_fn(kst) → (key, label) 튜플 반환."""
    buckets: dict[str, dict] = {}
    for m in _stat_matches(matches):
        kst = _utc_iso_to_kst(m["match_date"])
        key, label = key_label_fn(kst)
        if key not in buckets:
            buckets[key] = {
                "key": key, "label": label,
                "total": 0, "wins": 0, "losses": 0, "fc": 0,
                "sc_wins": 0, "ch_wins": 0,
            }
        _accumulate(buckets[key], m)
    for b in buckets.values():
        b["win_rate"] = (b["wins"] / b["total"]) if b["total"] > 0 else 0.0
    return sorted(buckets.values(), key=lambda d: d["key"])


def _accumulate(bucket: dict, m: dict) -> None:
    """단일 매치를 bucket에 누적. _stat_matches 필터 통과한 매치만 인자로."""
    bucket["total"] += 1
    bucket["fc"] += m["fc_earned"]
    if m["match_result"] == "승":
        bucket["wins"] += 1
        if m["division"] == 800:
            bucket["sc_wins"] += 1
        elif m["division"] == 900:
            bucket["ch_wins"] += 1
    else:
        bucket["losses"] += 1


def breakdown_for_unit(matches: list[dict], unit: str) -> list[dict]:
    """단위 문자열에 따라 적합한 breakdown 함수 호출."""
    if unit == "hour":  return hourly_breakdown(matches)
    if unit == "day":   return daily_breakdown(matches)
    if unit == "week":  return weekly_breakdown(matches)
    if unit == "month": return monthly_breakdown(matches)
    if unit == "year":  return yearly_breakdown(matches)
    return daily_breakdown(matches)


# ─────────────────────────────────────────────
# 분포 (도넛 차트용)
# ─────────────────────────────────────────────

def division_distribution(matches: list[dict]) -> dict:
    """디비전별 분포. 챔/슈챔 외 매치도 표시 (참고용)."""
    counts = {"슈퍼챔피언스": 0, "챔피언스": 0, "기타": 0}
    for m in matches:
        if m["match_result"] not in ("승", "패"):
            continue
        if m["division"] == 800:
            counts["슈퍼챔피언스"] += 1
        elif m["division"] == 900:
            counts["챔피언스"] += 1
        else:
            counts["기타"] += 1
    return counts


def result_distribution(matches: list[dict]) -> dict:
    """승/패 분포 (집계 대상 챔/슈챔 기준)."""
    filtered = _stat_matches(matches)
    return {
        "승": sum(1 for m in filtered if m["match_result"] == "승"),
        "패": sum(1 for m in filtered if m["match_result"] == "패"),
    }


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
