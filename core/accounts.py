"""다계정 메타 관리.

data/fc_stats_meta.json:
    {
      "active_ouid": "<ouid>",
      "accounts": [
        {"ouid": ..., "nickname": ..., "first_added_at": ..., "last_synced_at": ...},
        ...
      ]
    }

DB 파일 네이밍: data/fc_stats_<ouid>.db (계정별 독립)

기존 ImageReactor 통합본에서 옮겨온 단일 fc_stats.db가 있으면 첫 실행 시
자동으로 fc_stats_<ouid>.db로 rename + meta.json 등록한다 (§5.5).
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import Optional

from path_manager import DATA_DIR

META_PATH = DATA_DIR / "fc_stats_meta.json"
LEGACY_DB_PATH = DATA_DIR / "fc_stats.db"  # ImageReactor 통합본 단일 DB


def _now_iso() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _load() -> dict:
    if not META_PATH.exists():
        return {"active_ouid": None, "accounts": []}
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"active_ouid": None, "accounts": []}
    data.setdefault("active_ouid", None)
    data.setdefault("accounts", [])
    return data


def _save(meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = META_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    tmp.replace(META_PATH)


def db_path_for(ouid: str) -> Path:
    return DATA_DIR / f"fc_stats_{ouid}.db"


# ─────────────────────────────────────────────
# 초기화 + 마이그레이션
# ─────────────────────────────────────────────

def init_accounts() -> None:
    """첫 실행 시 meta.json 없으면 빈 구조로 생성.
    기존 단일 fc_stats.db가 있으면 그 안의 nickname/ouid를 읽어
    fc_stats_<ouid>.db로 rename + meta.json에 등록."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if META_PATH.exists():
        return  # 이미 초기화됨

    if LEGACY_DB_PATH.exists():
        try:
            _migrate_legacy_db()
            return
        except Exception:
            # 마이그레이션 실패해도 빈 meta로 시작 — 사용자는 새로 계정 추가 가능
            pass

    _save({"active_ouid": None, "accounts": []})


def _migrate_legacy_db() -> None:
    """data/fc_stats.db → data/fc_stats_<ouid>.db + meta.json 생성.
    legacy DB의 sync_state에서 ouid/nickname을 추출 후 키 제거."""
    ouid, nickname = _read_legacy_account(LEGACY_DB_PATH)
    if not ouid:
        # ouid 없는 legacy DB는 정체 불명 — meta만 비워두고 legacy 파일은 그대로 둠
        _save({"active_ouid": None, "accounts": []})
        return

    new_db = db_path_for(ouid)
    if new_db.exists():
        # 같은 ouid의 새 형식 DB가 이미 있으면 legacy는 .bak으로 백업
        LEGACY_DB_PATH.rename(LEGACY_DB_PATH.with_suffix(".db.bak"))
    else:
        LEGACY_DB_PATH.rename(new_db)
        _purge_legacy_keys(new_db)

    now = _now_iso()
    _save({
        "active_ouid": ouid,
        "accounts": [{
            "ouid": ouid,
            "nickname": nickname or "(unknown)",
            "first_added_at": now,
            "last_synced_at": None,
        }],
    })


def _read_legacy_account(db_path: Path) -> tuple[Optional[str], Optional[str]]:
    c = sqlite3.connect(db_path, timeout=5.0)
    try:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT key, value FROM sync_state").fetchall()
        kv = {r["key"]: r["value"] for r in rows}
        return kv.get("ouid"), kv.get("nickname")
    except sqlite3.DatabaseError:
        return None, None
    finally:
        c.close()


def _purge_legacy_keys(db_path: Path) -> None:
    """legacy DB의 sync_state에서 nickname/ouid/first_synced_at 제거 (meta로 이관됨)."""
    c = sqlite3.connect(db_path, timeout=5.0)
    try:
        c.execute("DELETE FROM sync_state WHERE key IN ('nickname', 'ouid', 'first_synced_at')")
        c.commit()
    finally:
        c.close()


# ─────────────────────────────────────────────
# 활성 계정 + 리스트
# ─────────────────────────────────────────────

def get_active_ouid() -> Optional[str]:
    return _load().get("active_ouid")


def set_active_ouid(ouid: Optional[str]) -> None:
    meta = _load()
    if ouid is not None and not any(a["ouid"] == ouid for a in meta["accounts"]):
        raise ValueError(f"등록되지 않은 ouid: {ouid}")
    meta["active_ouid"] = ouid
    _save(meta)


def list_accounts() -> list[dict]:
    return list(_load()["accounts"])


def get_account(ouid: str) -> Optional[dict]:
    for a in _load()["accounts"]:
        if a["ouid"] == ouid:
            return a
    return None


def get_active_account() -> Optional[dict]:
    ouid = get_active_ouid()
    return get_account(ouid) if ouid else None


# ─────────────────────────────────────────────
# 추가 / 삭제 / 닉네임 변경
# ─────────────────────────────────────────────

def add_account(ouid: str, nickname: str, make_active: bool = True) -> dict:
    """meta.json에 계정 추가. 이미 있으면 nickname만 갱신."""
    meta = _load()
    existing = next((a for a in meta["accounts"] if a["ouid"] == ouid), None)
    if existing:
        existing["nickname"] = nickname
    else:
        existing = {
            "ouid": ouid,
            "nickname": nickname,
            "first_added_at": _now_iso(),
            "last_synced_at": None,
        }
        meta["accounts"].append(existing)
    if make_active:
        meta["active_ouid"] = ouid
    _save(meta)
    return existing


def remove_account(ouid: str, delete_db: bool = True) -> None:
    """meta.json에서 제거. delete_db=True면 fc_stats_<ouid>.db 파일도 삭제.

    delete_db=False면 DB는 그대로 유지되어, 나중에 같은 닉네임으로 다시 계정을
    추가하면 자동으로 기존 데이터를 인식한다 (ouid가 같으므로 파일명 동일).
    """
    meta = _load()
    meta["accounts"] = [a for a in meta["accounts"] if a["ouid"] != ouid]
    if meta.get("active_ouid") == ouid:
        meta["active_ouid"] = meta["accounts"][0]["ouid"] if meta["accounts"] else None
    _save(meta)

    if delete_db:
        db_path = db_path_for(ouid)
        if db_path.exists():
            try:
                db_path.unlink()
            except OSError:
                pass


def update_nickname(ouid: str, new_nickname: str) -> None:
    """닉네임 변경. ouid는 그대로, nickname만 갱신."""
    meta = _load()
    for a in meta["accounts"]:
        if a["ouid"] == ouid:
            a["nickname"] = new_nickname
            _save(meta)
            return
    raise ValueError(f"등록되지 않은 ouid: {ouid}")


def touch_last_synced(ouid: str, when: Optional[str] = None) -> None:
    """sync 완료 시 meta의 last_synced_at 갱신."""
    meta = _load()
    for a in meta["accounts"]:
        if a["ouid"] == ouid:
            a["last_synced_at"] = when or _now_iso()
            _save(meta)
            return
