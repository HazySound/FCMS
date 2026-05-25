"""FC 채굴 통계 — 스탠드얼론 엔트리 포인트."""

import ctypes
import sys
import threading

import customtkinter as ctk

from core import accounts, fc_stats_db, fc_sync
from core.font_loader import register_app_fonts
from path_manager import chdir_to_base, ensure_dirs
from ui.main_window import MainWindow


def _set_app_user_model_id():
    """Windows 작업표시줄이 우리 exe를 자체 그룹으로 인식하게 한다.
    이게 없으면 PyInstaller 빌드본도 Python.exe로 그룹화돼 exe 아이콘이
    작업표시줄에 안 보인다."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.fcms.fcms")
    except Exception:
        pass


def main():
    _set_app_user_model_id()
    chdir_to_base()
    ensure_dirs()
    register_app_fonts()        # Pretendard process-private 등록 (CTk init 전에)
    accounts.init_accounts()    # meta.json 초기화 + 단일 DB 자동 마이그레이션
    fc_stats_db.init_db()       # 활성 계정 DB 스키마 보장 (없으면 no-op)
    ctk.set_appearance_mode("dark")

    # 백그라운드에서 detail fetch pool을 미리 워밍업.
    # 첫 sync 시작 시점에는 이미 모든 worker가 idle 상태로 대기 중이라
    # spawn 비용으로 인한 UI 멈춤이 발생하지 않는다.
    threading.Thread(target=fc_sync.warmup_pool, daemon=True).start()

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
