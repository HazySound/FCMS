"""API 키 발급 안내 도움말 다이얼로그.

assets/help/api_key_guide.md 를 읽어 미니 마크업으로 렌더링.

지원 마크업:
    # / ## / ### 제목
    ---             구분선
    > 인용          블록 인용 (배경 박스)
    - 항목          불릿 리스트
    ![](image.png)  이미지 (assets/help/ 기준)
    [COPY:text]     복사 가능한 인라인 텍스트 + 복사 버튼
    [LINK:url|label] 외부 브라우저로 여는 링크 버튼
    **굵게**         인라인 굵은 글씨 (특수 토큰이 같은 줄에 있을 때만 굵게,
                     그 외에는 * 만 제거)
"""

from __future__ import annotations

import re
import webbrowser
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from path_manager import get_resource_path
from ui.theme import THEME

PAD = 12
PAD_SMALL = 6
MAX_IMG_WIDTH = 660
WRAP_LENGTH = 680

# 본문 글씨 크기 — 가독성 위해 ctk 기본보다 한 단계 큼
BODY_SIZE = 15
QUOTE_SIZE = 13
HEADING_SIZES = {"h1": 26, "h2": 21, "h3": 17}

GUIDE_PATH = "assets/help/api_key_guide.md"
HELP_IMAGE_DIR = "assets/help"


class ApiKeyHelpDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("API 키 발급 도움말")
        self.geometry("780x720")
        self.minsize(700, 600)
        self.configure(fg_color=THEME["APP_BG"])
        # transient는 두지 않는다 — transient면 부모 활성화 시 함께 minimize/restore.
        # topmost로 브라우저 위에 항상 보이게 + grab_set 없이 메인 창 상호작용 허용.
        self._images = []  # CTkImage 참조 유지 (GC 방지)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=THEME["APP_BG"])
        self._scroll.pack(fill="both", expand=True, padx=PAD, pady=(PAD, 0))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkButton(
            btn_frame, text="닫기", width=80, command=self.destroy,
        ).pack(side="right")

        self._render_markdown()

        if hasattr(parent, "_center_child"):
            parent._center_child(self)
        # 항상 위 — 브라우저 + 메인 창 모두 위에 띄움.
        # after로 약간 지연시켜 윈도우 매니저가 위치 잡은 뒤 적용 (안정성)
        self.after(100, lambda: self.attributes("-topmost", True))

    def _render_markdown(self):
        try:
            md_path = get_resource_path(GUIDE_PATH)
            text = Path(md_path).read_text(encoding="utf-8")
        except (OSError, FileNotFoundError) as e:
            ctk.CTkLabel(
                self._scroll, text=f"도움말 파일을 읽을 수 없습니다: {e}",
                text_color=THEME["ERR"],
            ).pack(anchor="w", padx=4, pady=PAD)
            return

        for line in text.splitlines():
            self._render_line(line.rstrip())

    def _render_line(self, line: str):
        if not line:
            _spacer(self._scroll, PAD_SMALL)
            return
        if line == "---":
            _separator(self._scroll)
            return
        if line.startswith("# "):
            self._render_heading(line[2:].strip(), size=HEADING_SIZES["h1"], top_pad=PAD)
            return
        if line.startswith("## "):
            self._render_heading(line[3:].strip(), size=HEADING_SIZES["h2"], top_pad=PAD)
            return
        if line.startswith("### "):
            self._render_heading(line[4:].strip(), size=HEADING_SIZES["h3"], top_pad=PAD_SMALL)
            return
        if line.startswith("> "):
            self._render_blockquote(line[2:].strip())
            return
        img_match = re.match(r'^!\[\]\(([^)]+)\)$', line)
        if img_match:
            self._render_image(img_match.group(1))
            return
        if line.startswith("- "):
            self._render_bullet(line[2:].strip())
            return
        self._render_paragraph(line)

    def _render_heading(self, text, size, top_pad):
        ctk.CTkLabel(
            self._scroll, text=_strip_inline_markup(text),
            font=ctk.CTkFont(size=size, weight="bold"),
            text_color=THEME["TEXT"], anchor="w", justify="left",
            wraplength=WRAP_LENGTH,
        ).pack(fill="x", padx=4, pady=(top_pad, 2))

    def _render_blockquote(self, text):
        frame = ctk.CTkFrame(self._scroll, fg_color=THEME["LOG_BG"], corner_radius=6)
        frame.pack(fill="x", padx=4, pady=(2, 4))
        ctk.CTkLabel(
            frame, text=_strip_inline_markup(text),
            text_color=THEME["TEXT_MUTED"], anchor="w", justify="left",
            wraplength=WRAP_LENGTH - 20,
            font=ctk.CTkFont(size=QUOTE_SIZE),
        ).pack(fill="x", padx=PAD, pady=PAD_SMALL)

    def _render_bullet(self, text):
        tokens = _tokenize(text)
        if _is_simple_text(tokens):
            ctk.CTkLabel(
                self._scroll, text=f"  •  {_strip_inline_markup(text)}",
                text_color=THEME["TEXT"], anchor="w", justify="left",
                wraplength=WRAP_LENGTH,
                font=ctk.CTkFont(size=BODY_SIZE),
            ).pack(fill="x", padx=4, pady=2)
            return
        frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        frame.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(
            frame, text="  •  ", text_color=THEME["TEXT"],
            font=ctk.CTkFont(size=BODY_SIZE),
        ).pack(side="left")
        self._render_tokens_into(frame, tokens)

    def _render_paragraph(self, text):
        tokens = _tokenize(text)
        if _is_simple_text(tokens):
            ctk.CTkLabel(
                self._scroll, text=_strip_inline_markup(text),
                text_color=THEME["TEXT"], anchor="w", justify="left",
                wraplength=WRAP_LENGTH,
                font=ctk.CTkFont(size=BODY_SIZE),
            ).pack(fill="x", padx=4, pady=2)
            return
        frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        frame.pack(fill="x", padx=4, pady=2)
        self._render_tokens_into(frame, tokens)

    def _render_tokens_into(self, frame, tokens):
        for tok in tokens:
            kind = tok[0]
            if kind == "text":
                txt = tok[1]
                if not txt:
                    continue
                ctk.CTkLabel(
                    frame, text=txt, text_color=THEME["TEXT"],
                    font=ctk.CTkFont(size=BODY_SIZE),
                ).pack(side="left")
            elif kind == "bold":
                ctk.CTkLabel(
                    frame, text=tok[1], text_color=THEME["TEXT"],
                    font=ctk.CTkFont(size=BODY_SIZE, weight="bold"),
                ).pack(side="left")
            elif kind == "copy":
                self._render_copy_token(frame, tok[1])
            elif kind == "link":
                self._render_link_token(frame, tok[1], tok[2])

    def _render_copy_token(self, frame, content):
        sub = ctk.CTkFrame(frame, fg_color=THEME["LOG_BG"], corner_radius=4)
        sub.pack(side="left", padx=2)
        ctk.CTkLabel(
            sub, text=f" {content} ",
            text_color=THEME["TEXT"],
            font=ctk.CTkFont(size=BODY_SIZE),
        ).pack(side="left", padx=2)
        btn = ctk.CTkButton(
            sub, text="복사", width=56, height=26,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=BODY_SIZE - 2),
        )
        btn.configure(command=lambda c=content, b=btn: self._do_copy(c, b))
        btn.pack(side="left", padx=(2, 4), pady=2)

    def _do_copy(self, content, btn):
        try:
            self.clipboard_clear()
            self.clipboard_append(content)
            self.update()
        except Exception:
            return
        btn.configure(text="✓")
        btn.after(1200, lambda: btn.configure(text="복사"))

    def _render_link_token(self, frame, url, label):
        btn = ctk.CTkButton(
            frame, text=label, height=30,
            fg_color="transparent", border_width=1,
            text_color=THEME["ACCENT"],
            hover_color=THEME["LOG_BG"],
            font=ctk.CTkFont(size=BODY_SIZE),
            command=lambda u=url: webbrowser.open(u),
        )
        btn.pack(side="left", padx=2, pady=2)

    def _render_image(self, fname):
        try:
            img_path = get_resource_path(f"{HELP_IMAGE_DIR}/{fname}")
            pil_img = Image.open(img_path)
        except Exception as e:
            ctk.CTkLabel(
                self._scroll, text=f"[이미지 로드 실패: {fname} - {e}]",
                text_color=THEME["ERR"],
            ).pack(anchor="w", padx=4, pady=PAD_SMALL)
            return
        w, h = pil_img.size
        if w > MAX_IMG_WIDTH:
            ratio = MAX_IMG_WIDTH / w
            w = MAX_IMG_WIDTH
            h = int(h * ratio)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(w, h))
        self._images.append(ctk_img)
        ctk.CTkLabel(
            self._scroll, text="", image=ctk_img,
        ).pack(anchor="w", padx=4, pady=PAD_SMALL)


def _spacer(parent, height):
    f = ctk.CTkFrame(parent, fg_color="transparent", height=height)
    f.pack(fill="x")


def _separator(parent):
    f = ctk.CTkFrame(parent, fg_color=THEME["BORDER"], height=1)
    f.pack(fill="x", padx=4, pady=PAD)


_TOKEN_PATTERN = re.compile(
    r'\[COPY:([^\]]+)\]|\[LINK:([^|\]]+)\|([^\]]+)\]|\*\*([^*]+)\*\*'
)


def _tokenize(text):
    tokens = []
    pos = 0
    for m in _TOKEN_PATTERN.finditer(text):
        if m.start() > pos:
            tokens.append(("text", text[pos:m.start()]))
        if m.group(1) is not None:
            tokens.append(("copy", m.group(1)))
        elif m.group(2) is not None:
            tokens.append(("link", m.group(2), m.group(3)))
        elif m.group(4) is not None:
            tokens.append(("bold", m.group(4)))
        pos = m.end()
    if pos < len(text):
        tokens.append(("text", text[pos:]))
    return tokens


def _is_simple_text(tokens):
    return len(tokens) == 1 and tokens[0][0] == "text"


def _strip_inline_markup(text):
    return re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
