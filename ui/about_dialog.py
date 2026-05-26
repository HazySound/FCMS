"""정보 다이얼로그.

footer의 [정보] 버튼으로 열림. 제작자 연락처 + GitHub + 인게임 닉네임을
한 곳에 모아 보여준다. 드래그 선택 + Ctrl+C 복사 가능.

모달은 아님 — 사용자가 정보 확인 중에도 메인 창 사용 가능.
"""

from __future__ import annotations

import customtkinter as ctk

from ui.theme import THEME
from version import APP_VERSION, GITHUB_REPO

PAD = 12
PAD_SMALL = 6

DIALOG_W = 500
DIALOG_H = 340

TITLE_SIZE = 18
SUBTITLE_SIZE = 13
BODY_SIZE = 14

FC_NICKNAME = "백준"
CONTACT_EMAIL = "cemigs1@gmail.com"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"


class AboutDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("정보")
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.minsize(420, 280)
        self.resizable(False, False)
        self.configure(fg_color=THEME["APP_BG"])
        self.transient(parent)

        # 제목
        ctk.CTkLabel(
            self, text="FCMS — FC 채굴 통계",
            text_color=THEME["TEXT"], anchor="w",
            font=ctk.CTkFont(size=TITLE_SIZE, weight="bold"),
        ).pack(fill="x", padx=PAD * 2, pady=(PAD * 2, 0))

        ctk.CTkLabel(
            self, text=f"버전 {APP_VERSION}",
            text_color=THEME["TEXT_MUTED"], anchor="w",
            font=ctk.CTkFont(size=SUBTITLE_SIZE),
        ).pack(fill="x", padx=PAD * 2, pady=(0, PAD_SMALL))

        # 구분선
        ctk.CTkFrame(self, fg_color=THEME["BORDER"], height=1).pack(
            fill="x", padx=PAD * 2, pady=PAD_SMALL,
        )

        # 섹션 헤더
        ctk.CTkLabel(
            self, text="제작자 정보",
            text_color=THEME["TEXT"], anchor="w",
            font=ctk.CTkFont(size=SUBTITLE_SIZE, weight="bold"),
        ).pack(fill="x", padx=PAD * 2, pady=(PAD_SMALL, 2))

        # 정보 영역 — CTkTextbox(disabled)로 드래그+복사 가능.
        # 라벨/값을 tk.Text의 tag로 시각적으로 분리:
        #   라벨 = TEXT_MUTED 회색 / 값 = TEXT 흰색 + bold
        info_box = ctk.CTkTextbox(
            self, fg_color=THEME["LOG_BG"],
            text_color=THEME["TEXT"],
            font=ctk.CTkFont(size=BODY_SIZE),
            wrap="word",
            height=110,
        )
        info_box.pack(fill="both", expand=True, padx=PAD * 2, pady=PAD_SMALL)

        # CTkTextbox 내부 tk.Text에 직접 tag 설정 (tag_configure는 wrapper에 없음)
        inner = info_box._textbox
        inner.tag_configure("label", foreground=THEME["TEXT_MUTED"])
        inner.tag_configure(
            "value",
            foreground=THEME["TEXT"],
            font=ctk.CTkFont(size=BODY_SIZE, weight="bold"),
            spacing1=2, spacing3=2,  # 값 라인 위아래 살짝 여백
        )

        items = [
            ("FC info 닉네임", FC_NICKNAME),
            ("GitHub", GITHUB_URL),
            ("문의", CONTACT_EMAIL),
        ]
        for i, (label, value) in enumerate(items):
            if i > 0:
                inner.insert("end", "\n")
            lbl_start = inner.index("end-1c")
            inner.insert("end", f"{label}: ")
            lbl_end = inner.index("end-1c")
            inner.tag_add("label", lbl_start, lbl_end)

            val_start = inner.index("end-1c")
            inner.insert("end", value)
            val_end = inner.index("end-1c")
            inner.tag_add("value", val_start, val_end)

        # disabled 상태에서도 드래그 선택과 Ctrl+C 복사는 가능 — 입력만 차단.
        info_box.configure(state="disabled")

        # 닫기 버튼
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=PAD * 2, pady=(PAD_SMALL, PAD * 2))
        ctk.CTkButton(
            btn_row, text="닫기", width=90, height=32,
            font=ctk.CTkFont(size=BODY_SIZE),
            command=self.destroy,
        ).pack(side="right")

        if hasattr(parent, "_center_child"):
            parent._center_child(self)
