"""FC 채굴 통계용 SQLite 저장소.

스키마:
    matches     - 매치 단위 raw 데이터 (UPSERT). fc_earned는 derive 캐시.
    sync_state  - watermark 등 key/value (계정 식별 정보는 meta.json이 보유).

DB 파일: data/fc_stats_<ouid>.db (활성 계정별로 별도)
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

from path_manager import DATA_DIR
from core.accounts import db_path_for, get_active_ouid

_lock = threading.Lock()  # 단일 프로세스 내 sync 워커 + UI 동시 접근 직렬화


_SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id        TEXT PRIMARY KEY,
    match_date      TEXT NOT NULL,    -- ISO 8601 UTC, 예: 2026-05-24T09:29:27
    match_type      INTEGER NOT NULL, -- 52 (감독모드)
    season_id       INTEGER NOT NULL,
    division        INTEGER NOT NULL, -- 800(슈챔)/900(챔)/...
    match_result    TEXT NOT NULL,    -- 승/무/패
    match_end_type  INTEGER NOT NULL, -- 0 정상, 1 몰수승, 2 몰수패
    fc_earned       INTEGER NOT NULL,
    fetched_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_matches_date   ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_season ON matches(season_id);

CREATE TABLE IF NOT EXISTS sync_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class NoActiveAccountError(RuntimeError):
    """활성 계정이 설정되지 않은 상태에서 DB 접근 시도."""


def _db_path() -> Path:
    ouid = get_active_ouid()
    if not ouid:
        raise NoActiveAccountError("활성 계정이 없습니다. 먼저 계정을 추가하세요.")
    return db_path_for(ouid)


@contextmanager
def _conn():
    """짧은 트랜잭션 단위 connection. with 블록 종료 시 commit/close."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_db_path(), timeout=10.0)
    c.row_factory = sqlite3.Row
    try:
        with _lock:
            yield c
            c.commit()
    finally:
        c.close()


def init_db() -> None:
    """활성 계정 DB의 테이블/인덱스 멱등 생성. 활성 계정 없으면 no-op.
    WAL 모드로 동시 read/write 경합 완화."""
    if not get_active_ouid():
        return
    with _conn() as c:
        c.executescript(_SCHEMA)
        # WAL은 파일별 영구 설정이므로 한 번 켜두면 유지된다.
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")


# ─────────────────────────────────────────────
# sync_state (key/value)
# ─────────────────────────────────────────────

def get_state(key: str) -> Optional[str]:
    with _conn() as c:
        row = c.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_state(key: str, value: Optional[str]) -> None:
    with _conn() as c:
        if value is None:
            c.execute("DELETE FROM sync_state WHERE key = ?", (key,))
        else:
            c.execute(
                "INSERT INTO sync_state(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def clear_all() -> None:
    """매치/sync_state 전체 초기화. 일반적으로 호출할 일 없음 (계정 삭제는 accounts.remove_account)."""
    with _conn() as c:
        c.execute("DELETE FROM matches")
        c.execute("DELETE FROM sync_state")


# ─────────────────────────────────────────────
# matches
# ─────────────────────────────────────────────

def match_exists(match_id: str) -> bool:
    with _conn() as c:
        row = c.execute("SELECT 1 FROM matches WHERE match_id = ?", (match_id,)).fetchone()
        return row is not None


def get_existing_match_ids(match_ids: Iterable[str]) -> set[str]:
    ids = list(match_ids)
    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    with _conn() as c:
        rows = c.execute(
            f"SELECT match_id FROM matches WHERE match_id IN ({placeholders})", ids
        ).fetchall()
        return {r["match_id"] for r in rows}


def get_season_ids_for(match_ids: Iterable[str]) -> dict[str, int]:
    ids = list(match_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with _conn() as c:
        rows = c.execute(
            f"SELECT match_id, season_id FROM matches WHERE match_id IN ({placeholders})", ids
        ).fetchall()
        return {r["match_id"]: r["season_id"] for r in rows}


def get_known_season_ids() -> list[int]:
    """DB에 한 번이라도 적재된 unique season_id 목록 (내림차순)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT season_id FROM matches ORDER BY season_id DESC"
        ).fetchall()
        return [r["season_id"] for r in rows]


def recalculate_fc_earned() -> int:
    """모든 매치의 fc_earned를 현재 calc_fc 정책으로 재계산. idempotent."""
    from core.fc_api import calc_fc
    with _conn() as c:
        rows = c.execute(
            "SELECT match_id, division, match_result, match_end_type FROM matches"
        ).fetchall()
        updates = [
            (calc_fc(r["division"], r["match_result"], r["match_end_type"]),
             r["match_id"])
            for r in rows
        ]
        if updates:
            c.executemany(
                "UPDATE matches SET fc_earned = ? WHERE match_id = ?",
                updates,
            )
        return len(updates)


def upsert_match(record: dict) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO matches
                 (match_id, match_date, match_type, season_id, division,
                  match_result, match_end_type, fc_earned, fetched_at)
               VALUES
                 (:match_id, :match_date, :match_type, :season_id, :division,
                  :match_result, :match_end_type, :fc_earned, :fetched_at)
               ON CONFLICT(match_id) DO UPDATE SET
                  match_date     = excluded.match_date,
                  match_type     = excluded.match_type,
                  season_id      = excluded.season_id,
                  division       = excluded.division,
                  match_result   = excluded.match_result,
                  match_end_type = excluded.match_end_type,
                  fc_earned      = excluded.fc_earned,
                  fetched_at     = excluded.fetched_at""",
            record,
        )


def upsert_matches(records: list[dict]) -> int:
    if not records:
        return 0
    with _conn() as c:
        c.executemany(
            """INSERT INTO matches
                 (match_id, match_date, match_type, season_id, division,
                  match_result, match_end_type, fc_earned, fetched_at)
               VALUES
                 (:match_id, :match_date, :match_type, :season_id, :division,
                  :match_result, :match_end_type, :fc_earned, :fetched_at)
               ON CONFLICT(match_id) DO UPDATE SET
                  match_date     = excluded.match_date,
                  match_type     = excluded.match_type,
                  season_id      = excluded.season_id,
                  division       = excluded.division,
                  match_result   = excluded.match_result,
                  match_end_type = excluded.match_end_type,
                  fc_earned      = excluded.fc_earned,
                  fetched_at     = excluded.fetched_at""",
            records,
        )
    return len(records)


def get_match_count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]


def get_latest_match_date() -> Optional[str]:
    with _conn() as c:
        row = c.execute("SELECT MAX(match_date) AS d FROM matches").fetchone()
        return row["d"] if row and row["d"] else None


def get_matches_between(start_utc: str, end_utc: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM matches WHERE match_date >= ? AND match_date < ? "
            "ORDER BY match_date ASC",
            (start_utc, end_utc),
        ).fetchall()
        return [dict(r) for r in rows]


def get_matches_by_season(season_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM matches WHERE season_id = ? ORDER BY match_date ASC",
            (season_id,),
        ).fetchall()
        return [dict(r) for r in rows]
