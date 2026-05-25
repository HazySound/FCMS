"""업데이트 다운로드 진행률 모달.

알림 UI는 main_window의 상단 배너에서 처리하고, 사용자가 [업데이트] 버튼을
누르면 이 모달을 띄워 다운로드 진행과 재시작 트리거를 담당한다.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from core import updater
from path_manager import BASE_DIR
from ui.theme import THEME
from version import APP_VERSION


class UpdateProgressDialog(ctk.CTkToplevel):
    """다운로드 진행률 + 재시작 모달.

    사용:
        dlg = UpdateProgressDialog(parent, release_info)
        dlg.start()  # 자동으로 다운로드 시작 + 진행률 표시
    """

    def __init__(self, parent, release_info: dict):
        super().__init__(parent)
        self.release_info = release_info
        self._parent = parent
        self._new_exe_path: Optional[Path] = None
        self._downloading = False

        tag = release_info.get("tag_name", "")
        exe_asset = release_info.get("exe_asset") or {}

        self.title("업데이트")
        self.geometry("440x200")
        self.minsize(440, 200)
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=THEME["APP_BG"])

        # 닫기는 다운로드 중 차단
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        ctk.CTkLabel(
            self, text=f"새 버전 {tag} 다운로드 중",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=THEME["TEXT"], anchor="w",
        ).pack(fill="x", padx=20, pady=(20, 4))

        ctk.CTkLabel(
            self, text=f"현재 버전 v{APP_VERSION} → {tag}",
            text_color=THEME["TEXT_MUTED"], anchor="w",
        ).pack(fill="x", padx=20)

        self._progress = ctk.CTkProgressBar(self, width=400)
        self._progress.set(0)
        self._progress.pack(fill="x", padx=20, pady=(16, 4))

        self._progress_label = ctk.CTkLabel(
            self, text="시작 중...", text_color=THEME["TEXT_MUTED"],
        )
        self._progress_label.pack(padx=20, anchor="w")

        # 하단 버튼 영역
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=20, pady=12)

        self._btn_action = ctk.CTkButton(
            btns, text="다운로드 중...", state="disabled",
            fg_color="#2563eb",
            command=self._apply_and_restart,
        )
        self._btn_action.pack(side="right")

        self._btn_close = ctk.CTkButton(
            btns, text="취소", width=80,
            fg_color="transparent", border_width=1,
            command=self._on_close_request,
            state="disabled",  # 다운로드 중 취소 비활성화 (손상 위험)
        )
        self._btn_close.pack(side="right", padx=(0, 8))

        # 정중앙 배치
        if hasattr(parent, "_center_child"):
            parent._center_child(self)
        self.grab_set()
        self.focus()

        # 다운로드 자동 시작
        exe_asset_url = exe_asset.get("url")
        if not exe_asset_url:
            self._on_download_error("exe 자산이 없습니다.")
            return

        # 자산 이름과 무관하게 다운로드 임시 파일은 항상 별도 이름으로.
        # 자산명이 FCMS.exe인 경우 실행 중인 exe와 충돌해 PermissionError 발생.
        # 배치파일이 이 임시 파일을 현재 exe 이름으로 rename한다.
        dest = BASE_DIR / "FCMS_new.exe"
        self._new_exe_path = dest
        self._downloading = True

        def _worker():
            try:
                updater.download_exe(
                    exe_asset_url, dest,
                    progress_cb=self._on_progress,
                    expected_size=int(exe_asset.get("size") or 0),
                )
                self.after(0, self._on_download_complete)
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: self._on_download_error(msg))

        threading.Thread(target=_worker, daemon=True).start()

    # ──────────────────────────────────────────
    # 진행률 콜백 / UI 갱신
    # ──────────────────────────────────────────

    def _on_progress(self, downloaded: int, total: int):
        if total > 0:
            ratio = downloaded / total
            mb_done = downloaded / 1_048_576
            mb_total = total / 1_048_576
            label = f"{mb_done:.1f} / {mb_total:.1f} MB"
        else:
            ratio = 0
            label = f"{downloaded / 1_048_576:.1f} MB"
        self.after(0, lambda r=ratio, l=label: self._update_progress_ui(r, l))

    def _update_progress_ui(self, ratio: float, label: str):
        try:
            self._progress.set(ratio)
            self._progress_label.configure(text=label)
        except Exception:
            pass

    # ──────────────────────────────────────────
    # 완료/오류 처리
    # ──────────────────────────────────────────

    def _on_download_complete(self):
        try:
            self._downloading = False
            self._progress.set(1.0)
            self._progress_label.configure(
                text="다운로드 완료. [재시작]을 눌러 적용해 주세요.",
                text_color=THEME["OK"],
            )
            self._btn_action.configure(
                text="재시작", state="normal", fg_color=THEME["OK"],
            )
            self._btn_close.configure(state="normal", text="나중에")
        except Exception:
            pass

    def _on_download_error(self, msg: str):
        try:
            self._downloading = False
            self._progress_label.configure(
                text=f"오류: {msg}", text_color=THEME["ERR"],
            )
            self._btn_action.configure(
                text="다시 시도", state="normal", fg_color="#2563eb",
                command=self._retry,
            )
            self._btn_close.configure(state="normal", text="닫기")
        except Exception:
            pass

    def _retry(self):
        # 가장 간단한 retry: 모달 새로 띄우고 자기 destroy.
        try:
            new = UpdateProgressDialog(self._parent, self.release_info)
            self.destroy()
        except Exception:
            pass

    # ──────────────────────────────────────────
    # 재시작 / 닫기
    # ──────────────────────────────────────────

    def _apply_and_restart(self):
        if self._new_exe_path is None:
            return
        try:
            updater.apply_update(self._new_exe_path)
        except RuntimeError as e:
            messagebox.showinfo(
                "안내",
                f"{e}\n\n다운로드된 파일:\n{self._new_exe_path}\n\n"
                "현재 exe와 수동으로 교체해 주세요.",
                parent=self,
            )

    def _on_close_request(self):
        if self._downloading:
            return  # 다운로드 중 닫기 차단
        self.destroy()
