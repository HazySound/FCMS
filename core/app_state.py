"""앱 UI 상태 영속화 (창 위치/크기 등).

계정 데이터와 분리. 단순 JSON.
"""

from __future__ import annotations

import json
from typing import Optional

from path_manager import DATA_DIR

STATE_PATH = DATA_DIR / "window_state.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_PATH)


def get_geometry() -> Optional[str]:
    return load_state().get("geometry")


def set_geometry(geom: str) -> None:
    state = load_state()
    state["geometry"] = geom
    save_state(state)
