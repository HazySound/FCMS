"""API 키 등록 팝오버.

기준 위젯(예: 열쇠 버튼) 아래에 말풍선처럼 표시되는 작은 창.
overrideredirect로 데코레이션을 없애고, 바깥 클릭 시 자동 닫힘.

UI:
    [● 인디케이터] Nexon Open API 키
    [입력 필드 (마스킹)]
    ⚠ 키는 외부에 공유하지 마세요
    [도움말]               [저장] [닫기]

인디케이터 색:
    회색 = 미설정 / 노랑 = 검증 중 / 초록 = 유효 / 빨강 = 무효
"""

from __future__ import annotations

import threading
from typing import Optional

import customtkinter as ctk

from core import app_state, fc_api
from ui.theme import THEME
from ui.widgets.api_key_help_dialog import ApiKeyHelpDialog

PAD = 12
PAD_SMALL = 6
POPOVER_W = 460
POPOVER_H = 260

# 본문 글씨 크기 — 가독성 위해 한 단계 키움
TITLE_SIZE = 15
BODY_SIZE = 14
NOTE_SIZE = 12
STATUS_SIZE = 13

# 인디케이터 색
DOT_NONE   = THEME["TEXT_MUTED"]
DOT_CHECK  = THEME["WARN"]
DOT_OK     = THEME["OK"]
DOT_ERR    = THEME["ERR"]


class ApiKeyPopover(ctk.CTkToplevel):
    """기준 위젯 근처에 띄우는 키 등록 팝오버.

    사용:
        ApiKeyPopover.toggle(anchor_widget)  # 열려있으면 닫고, 닫혀있으면 연다
    """

    _open_instance: Optional["ApiKeyPopover"] = None

    @classmethod
    def toggle(cls, anchor) -> None:
        if cls._open_instance is not None and cls._open_instance.winfo_exists():
            cls._open_instance.destroy()
            cls._open_instance = None
            return
        cls._open_instance = cls(anchor)

    def __init__(self, anchor):
        # parent는 anchor의 toplevel
        parent = anchor.winfo_toplevel()
        super().__init__(parent)
        self._anchor = anchor
        self._parent = parent
        self._closing = False
        self._content_frame = None
        self._button_frame = None
        self._entry = None      # 편집 모드에서만 존재

        self.overrideredirect(True)
        self.configure(fg_color=THEME["PANEL_BG"])
        # 외곽선 효과: 1px 테두리 색 frame을 감싸기
        outer = ctk.CTkFrame(
            self, fg_color=THEME["PANEL_BG"],
            border_color=THEME["BORDER"], border_width=1, corner_radius=8,
        )
        outer.pack(fill="both", expand=True)
        self._outer = outer

        self._build_static(outer)
        # 저장된 키가 있으면 라벨 모드, 없으면 편집 모드로 시작
        # (편집 모드 진입은 최초 등록이라 fill/cancel 둘 다 false)
        if app_state.get_api_key():
            self._show_label_mode()
        else:
            self._show_edit_mode(focus=True, fill_current=False)

        self._position(anchor)

        # 외부 클릭 / Esc 시 닫기
        self.bind("<Escape>", lambda _e: self._close())
        self._global_click_id = parent.bind(
            "<Button-1>", self._on_global_click, add="+"
        )
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ─────────────────────────────────────────
    # UI 구축 (공통 부분)
    # ─────────────────────────────────────────

    def _build_static(self, host):
        # 헤더: 인디케이터 + 제목 + 상태
        header = ctk.CTkFrame(host, fg_color="transparent")
        header.pack(fill="x", padx=PAD, pady=(PAD, PAD_SMALL))

        self._dot = ctk.CTkLabel(
            header, text="●", text_color=DOT_NONE,
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._dot.pack(side="left", padx=(0, PAD_SMALL))

        ctk.CTkLabel(
            header, text="Nexon Open API 키",
            text_color=THEME["TEXT"], anchor="w",
            font=ctk.CTkFont(size=TITLE_SIZE, weight="bold"),
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            header, text="", text_color=THEME["TEXT_MUTED"], anchor="e",
            font=ctk.CTkFont(size=STATUS_SIZE),
        )
        self._status_label.pack(side="right")

        # 가변 컨텐츠 영역 — 모드 전환마다 children 비우고 다시 채움
        self._content_frame = ctk.CTkFrame(host, fg_color="transparent")
        self._content_frame.pack(fill="x", padx=PAD, pady=PAD_SMALL)

        # 주의 안내
        ctk.CTkLabel(
            host,
            text="⚠ 키는 본인의 quota를 사용하는 개인 정보입니다. "
                 "절대 외부에 공유하지 마세요.",
            text_color=THEME["TEXT_MUTED"],
            font=ctk.CTkFont(size=NOTE_SIZE),
            anchor="w", justify="left",
            wraplength=POPOVER_W - PAD * 2 - 4,
        ).pack(fill="x", padx=PAD, pady=(0, PAD_SMALL))

        # 가변 버튼 행 — 모드별 버튼 구성이 다름
        self._button_frame = ctk.CTkFrame(host, fg_color="transparent")
        self._button_frame.pack(fill="x", padx=PAD, pady=(0, PAD))

    def _clear_frame(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    # ─────────────────────────────────────────
    # 모드: 편집 (입력 필드)
    # ─────────────────────────────────────────

    def _show_edit_mode(self, focus: bool = False, fill_current: bool = False):
        """편집 모드 진입.

        fill_current=True면:
          - 입력 필드를 현재 저장된 키로 미리 채움
          - [취소] 버튼 표시 → 누르면 라벨 모드로 복귀 (app_state 변경 없음)
        라벨 모드에서 [변경] 누르면 fill_current=True로 진입.
        최초 등록(저장된 키 없음)일 땐 fill_current=False, [취소] 없음.
        """
        self._clear_frame(self._content_frame)
        self._clear_frame(self._button_frame)

        self._entry = ctk.CTkEntry(
            self._content_frame, show="•",
            placeholder_text="발급받은 API 키를 붙여넣기",
            height=34,
            font=ctk.CTkFont(size=BODY_SIZE),
        )
        self._entry.pack(fill="x")
        self._entry.bind("<KeyRelease>", self._on_key_change)
        self._entry.bind("<Return>", lambda _e: self._on_save())

        saved = app_state.get_api_key()
        if fill_current and saved:
            self._entry.insert(0, saved)

        # 버튼 행
        ctk.CTkButton(
            self._button_frame, text="도움말", width=80, height=30,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=BODY_SIZE),
            command=self._open_help,
        ).pack(side="left")

        ctk.CTkButton(
            self._button_frame, text="닫기", width=70, height=30,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=BODY_SIZE),
            command=self._close,
        ).pack(side="right", padx=(PAD_SMALL, 0))

        self._save_btn = ctk.CTkButton(
            self._button_frame, text="저장", width=80, height=30,
            font=ctk.CTkFont(size=BODY_SIZE),
            command=self._on_save,
        )
        self._save_btn.pack(side="right")

        # baseline(검증 통과한 키)이 있을 때만 [취소] 노출
        if saved:
            ctk.CTkButton(
                self._button_frame, text="취소", width=70, height=30,
                fg_color="transparent", border_width=1,
                font=ctk.CTkFont(size=BODY_SIZE),
                command=self._show_label_mode,
            ).pack(side="right", padx=(0, PAD_SMALL))

        # 인디케이터 초기 상태
        if saved:
            if fill_current:
                self._set_indicator(DOT_OK, "현재 키 — 수정 후 저장")
            else:
                self._set_indicator(DOT_OK, "저장됨 — 변경하려면 새 키를 입력하세요")
        else:
            self._set_indicator(DOT_NONE, "미설정")

        if focus:
            self.after(50, self._entry.focus_set)

    # ─────────────────────────────────────────
    # 모드: 라벨 (검증 통과 키 보유)
    # ─────────────────────────────────────────

    def _show_label_mode(self):
        self._clear_frame(self._content_frame)
        self._clear_frame(self._button_frame)
        self._entry = None

        saved = app_state.get_api_key()
        masked = _mask_key(saved)

        label_box = ctk.CTkFrame(
            self._content_frame, fg_color=THEME["LOG_BG"], corner_radius=6, height=34,
        )
        label_box.pack(fill="x")
        ctk.CTkLabel(
            label_box, text=masked,
            text_color=THEME["TEXT"], anchor="w",
            font=ctk.CTkFont(size=BODY_SIZE),
        ).pack(fill="x", padx=PAD, pady=PAD_SMALL)

        # 버튼 행
        ctk.CTkButton(
            self._button_frame, text="도움말", width=80, height=30,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=BODY_SIZE),
            command=self._open_help,
        ).pack(side="left")

        ctk.CTkButton(
            self._button_frame, text="닫기", width=70, height=30,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=BODY_SIZE),
            command=self._close,
        ).pack(side="right", padx=(PAD_SMALL, 0))

        ctk.CTkButton(
            self._button_frame, text="변경", width=80, height=30,
            font=ctk.CTkFont(size=BODY_SIZE),
            command=lambda: self._show_edit_mode(focus=True, fill_current=True),
        ).pack(side="right")

        self._set_indicator(DOT_OK, "등록됨")

    # ─────────────────────────────────────────
    # 상태 / 이벤트
    # ─────────────────────────────────────────

    def _on_key_change(self, _evt=None):
        if self._entry is None:
            return
        current = self._entry.get().strip()
        saved = app_state.get_api_key()
        if not current:
            if saved:
                self._set_indicator(DOT_CHECK, "비워서 저장하면 등록 해제됩니다")
            else:
                self._set_indicator(DOT_NONE, "미설정")
        elif current != saved:
            self._set_indicator(DOT_CHECK, "변경됨 — 저장 필요")
        else:
            self._set_indicator(DOT_OK, "저장됨")

    def _set_indicator(self, color: str, msg: str):
        self._dot.configure(text_color=color)
        self._status_label.configure(text=msg)

    def _on_save(self):
        if self._entry is None:
            return
        key = self._entry.get().strip()
        if not key:
            # 빈 키 저장 = 등록 해제 (Worker 폴백 모드로)
            app_state.set_api_key("")
            self._set_indicator(DOT_NONE, "등록 해제됨")
            self._notify_parent_changed()
            return

        # 이미 저장된 동일 키면 검증 skip
        if key == app_state.get_api_key():
            self._show_label_mode()
            return

        # 검증 중 상태
        self._set_indicator(DOT_CHECK, "검증 중…")
        try:
            self._save_btn.configure(state="disabled")
        except Exception:
            pass
        threading.Thread(
            target=self._validate_in_thread, args=(key,), daemon=True,
        ).start()

    def _validate_in_thread(self, key: str):
        ok, msg = fc_api.validate_api_key(key)
        self.after(0, lambda: self._on_validate_done(key, ok, msg))

    def _on_validate_done(self, key: str, ok: bool, msg: str):
        if self._closing or not self.winfo_exists():
            return
        if ok:
            app_state.set_api_key(key)
            self._show_label_mode()
            self._set_indicator(DOT_OK, "유효 — 저장됨")
            self._notify_parent_changed()
            return
        self._set_indicator(DOT_ERR, msg)
        try:
            self._save_btn.configure(state="normal")
        except Exception:
            pass

    def _notify_parent_changed(self):
        """키 상태 변경 시 부모 윈도우(메인)의 배지 갱신 훅 호출."""
        fn = getattr(self._parent, "_refresh_api_key_badge", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _open_help(self):
        ApiKeyHelpDialog(self._parent)

    # ─────────────────────────────────────────
    # 위치 / 닫기
    # ─────────────────────────────────────────

    def _position(self, anchor):
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        # 화면 오른쪽 넘어가지 않게
        screen_w = self.winfo_screenwidth()
        if x + POPOVER_W > screen_w:
            x = max(0, screen_w - POPOVER_W - 8)
        self.geometry(f"{POPOVER_W}x{POPOVER_H}+{x}+{y}")

    def _on_global_click(self, event):
        # 클릭이 self 내부거나 anchor 버튼이면 무시
        # (anchor 버튼은 toggle 로직이 처리하므로 외부 클릭 닫기와 충돌하면
        #  계속 열리는 버그가 생긴다)
        try:
            w = event.widget
        except Exception:
            return
        cur = w
        while cur is not None:
            if cur is self or cur is self._anchor:
                return
            cur = getattr(cur, "master", None)
        self._close()

    def _close(self):
        if self._closing:
            return
        self._closing = True
        try:
            self._parent.unbind("<Button-1>", self._global_click_id)
        except Exception:
            pass
        try:
            ApiKeyPopover._open_instance = None
        except Exception:
            pass
        self.destroy()


def _mask_key(key: str) -> str:
    """저장된 키를 라벨 모드에서 화면 노출할 마스킹 형태로 변환.

    앞 4글자만 보여주고 나머지는 점으로. 너무 길면 잘라낸다.
    예: "abcdEFGH...xyz" → "abcd••••••••••••"
    """
    if not key:
        return ""
    visible = key[:4]
    return f"{visible}••••••••••••••••"
