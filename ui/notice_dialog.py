"""공지사항 표시 다이얼로그.

본문은 단순 평문(줄바꿈 보존)으로 렌더링. 상단에 색상 바, urgent면 ⚠️ 아이콘.
링크는 옵션 — link_url이 있으면 [link_label or "<링크>"] 버튼 표시.

모든 공지는 modal + topmost — 사용자가 확인 / X로 닫기 전까지 메인 창 사용 불가.
사용자가 못 보고 지나치지 않게 강제 표시.

닫기(X) 또는 [확인] 시 mark_seen 호출. 한 번 본 공지는 다시 안 뜸.
"""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from core import notices
from ui.theme import THEME

PAD = 12
PAD_SMALL = 6

DEFAULT_INFO_COLOR = THEME["ACCENT"]    # #4A9EFF
DEFAULT_URGENT_COLOR = THEME["ERR"]     # #ef4444
DEFAULT_LINK_LABEL = "<링크>"

DIALOG_W = 620
DIALOG_H = 500

TITLE_SIZE = 20
BODY_SIZE = 16
DATE_SIZE = 14
BUTTON_SIZE = 14


class NoticeDialog(ctk.CTkToplevel):
    """공지 1건 표시. 사용자가 dismiss할 때까지 modal로 잡진 않음 (메인 사용 가능)."""

    def __init__(self, parent, notice: dict):
        super().__init__(parent)
        self._notice = notice
        self._notice_id = notice.get("id", "")

        title = notice.get("title") or "공지"
        urgent = bool(notice.get("urgent"))
        color = notice.get("color") or (
            DEFAULT_URGENT_COLOR if urgent else DEFAULT_INFO_COLOR
        )

        self.title(f"{'⚠️ ' if urgent else ''}{title}")
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.minsize(440, 340)
        self.configure(fg_color=THEME["APP_BG"])
        self.transient(parent)

        # 상단 색상 바
        bar = ctk.CTkFrame(self, fg_color=color, height=6, corner_radius=0)
        bar.pack(fill="x")

        # 제목 + 날짜
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PAD, pady=(PAD, PAD_SMALL))

        title_text = f"⚠️ {title}" if urgent else title
        ctk.CTkLabel(
            header, text=title_text, anchor="w",
            text_color=THEME["TEXT"],
            font=ctk.CTkFont(size=TITLE_SIZE, weight="bold"),
            wraplength=DIALOG_W - PAD * 4,
            justify="left",
        ).pack(side="left", fill="x", expand=True)

        date_str = notice.get("date")
        if date_str:
            ctk.CTkLabel(
                header, text=str(date_str), anchor="e",
                text_color=THEME["TEXT_MUTED"],
                font=ctk.CTkFont(size=DATE_SIZE),
            ).pack(side="right", padx=(PAD_SMALL, 0))

        # 본문 — CTkTextbox(disabled)로 두면 드래그 선택 + Ctrl+C 복사가 가능하다.
        # CTkLabel은 selectable이 안 돼서 메일/URL 같은 텍스트 복사 불가능.
        body = notice.get("body") or ""
        body_box = ctk.CTkTextbox(
            self, fg_color=THEME["LOG_BG"],
            text_color=THEME["TEXT"],
            font=ctk.CTkFont(size=BODY_SIZE),
            wrap="word",
        )
        body_box.pack(fill="both", expand=True, padx=PAD, pady=PAD_SMALL)
        body_box.insert("1.0", body)
        # state="disabled"여도 tk.Text는 마우스 드래그 선택과 Ctrl+C 복사가 가능.
        # 사용자 입력만 막아 본문 변조 방지.
        body_box.configure(state="disabled")

        # 버튼 행
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=PAD, pady=(0, PAD))

        link_url = notice.get("link_url")
        if link_url:
            link_label = notice.get("link_label") or DEFAULT_LINK_LABEL
            ctk.CTkButton(
                btns, text=link_label, height=34,
                fg_color="transparent", border_width=1,
                text_color=THEME["ACCENT"],
                font=ctk.CTkFont(size=BUTTON_SIZE),
                command=lambda u=link_url: webbrowser.open(u),
            ).pack(side="left")

        ctk.CTkButton(
            btns, text="확인", width=100, height=34,
            font=ctk.CTkFont(size=BUTTON_SIZE),
            command=self._dismiss,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._dismiss)

        if hasattr(parent, "_center_child"):
            parent._center_child(self)

        # 모든 공지는 항상 위 + modal — 메인 창 클릭 막아 확인 강제.
        # grab_set은 윈도우가 매핑된 후 호출해야 안전.
        self.after(50, self._activate_modal)

    def _activate_modal(self):
        try:
            self.attributes("-topmost", True)
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _dismiss(self):
        if self._notice_id:
            notices.mark_seen(self._notice_id)
        self.destroy()
