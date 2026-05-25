"""앱 기준 경로 관리.

스탠드얼론 빌드용 단순화 버전:
- BASE_DIR: 개발 시 이 파일 폴더, 빌드 시 exe 옆 폴더
- DATA_DIR: BASE_DIR/data (DB 파일 + meta.json 위치)
- chdir_to_base: 시작 시 CWD를 BASE_DIR로 고정해 상대경로 일관 유지
- get_resource_path: PyInstaller --onefile에서 _MEIPASS 분기
"""

import os
import sys
from pathlib import Path


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "executable"):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _app_base_dir()
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def chdir_to_base() -> None:
    os.chdir(BASE_DIR)


def get_resource_path(rel_path: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / rel_path)
    return str(BASE_DIR / rel_path)
