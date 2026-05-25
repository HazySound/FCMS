"""앱 전용 폰트 등록 + customtkinter 기본 패밀리 적용.

Windows의 AddFontResourceExW(FR_PRIVATE)로 프로세스 lifetime 동안만 폰트를
등록한다. 시스템에 영구 설치하지 않고, 프로세스 종료 시 자동 해제.

CTkFont는 default family를 모듈 로드 시점에 한 번 박아두므로 ThemeManager
갱신만으로는 안 바뀐다. CTkFont.__init__을 wrap해 family 미지정 시
Pretendard를 강제하는 식으로 처리.

빌드본에서는 assets/ 안의 TTF가 PyInstaller _MEIPASS로 풀려 있으므로
path_manager.get_resource_path()가 그 경로를 찾아준다.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from path_manager import get_resource_path

FONT_FILES = [
    "assets/Pretendard-Regular.ttf",
    "assets/Pretendard-Bold.ttf",
]
APP_FONT_FAMILY = "Pretendard"

_FR_PRIVATE = 0x10


def register_app_fonts() -> int:
    """앱 시작 시 호출. 폰트 OS 등록 + CTkFont 기본 패밀리 강제 적용."""
    added = _register_windows_fonts()
    _patch_ctkfont_default_family(APP_FONT_FAMILY)
    return added


def _register_windows_fonts() -> int:
    if sys.platform != "win32":
        return 0
    try:
        gdi32 = ctypes.WinDLL("gdi32")
    except OSError:
        return 0
    added = 0
    for rel in FONT_FILES:
        path = Path(get_resource_path(rel))
        if not path.exists():
            continue
        try:
            n = gdi32.AddFontResourceExW(str(path), _FR_PRIVATE, 0)
            if n > 0:
                added += 1
        except Exception:
            pass
    return added


def _patch_ctkfont_default_family(family: str) -> None:
    """customtkinter의 CTkFont 기본 family를 family로 강제.
    이미 import된 customtkinter의 CTkFont를 monkey-patch한다.
    """
    try:
        import customtkinter as ctk
        from customtkinter.windows.widgets.theme import ThemeManager
    except ImportError:
        return

    # ThemeManager 갱신 — 일부 위젯이 이걸 직접 참조
    try:
        ThemeManager.theme["CTkFont"]["family"] = family
    except Exception:
        pass

    # CTkFont.__init__ wrap — family 미지정(인자 없음) 시 family를 주입
    orig_init = ctk.CTkFont.__init__

    def patched_init(self, *args, **kwargs):
        if not args and "family" not in kwargs:
            kwargs["family"] = family
        orig_init(self, *args, **kwargs)

    ctk.CTkFont.__init__ = patched_init
