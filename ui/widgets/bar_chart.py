"""범용 막대 차트.

데이터 형식:
    items = [
        {
            "label": "21시",            # x축 라벨
            "value": 115,               # 막대 높이
            "tooltip_lines": [...],     # 호버 텍스트 (줄 단위)
            "color": "#xxxxxx",         # 선택 — 막대 색 override
        },
        ...
    ]

options:
    avg_line: True          → 평균선 + 라벨 자동 표시
    avg_label_fmt: "평균 {:.1f}"
    bar_color: 평균 이상 색 (default THEME["BAR"])
    below_color: 평균 미만 색 (default 약간 흐린 톤)
    y_format: y축 라벨 포맷 (default "{:.0f}")
    title: 차트 상단 타이틀 (없으면 미표시)
    max_x_ticks: x축 라벨 개수 상한 (default 8 — 자동 thinning)
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk

from ui.theme import THEME
from ui.widgets._tooltip import HoverTooltip

PAD = 12
PAD_SMALL = 6


class BarChart(ctk.CTkFrame):
    def __init__(self, master, height: int = 220, **kwargs):
        super().__init__(master, fg_color=THEME["LOG_BG"], **kwargs)
        self._items: list[dict] = []
        self._opts: dict = {}
        self._bars: list[dict] = []
        self._avg_hover: Optional[dict] = None
        self._tooltip = HoverTooltip(self)

        # title 라벨 (선택)
        self._title_label = ctk.CTkLabel(
            self, text="", anchor="w", text_color=THEME["TEXT"],
        )
        self._title_label.pack(fill="x", padx=PAD, pady=(PAD_SMALL, 0))
        self._title_label.pack_forget()  # 기본 숨김

        self._canvas = tk.Canvas(
            self, height=height, highlightthickness=0, bg=THEME["LOG_BG"],
        )
        self._canvas.pack(fill="both", expand=True, padx=PAD, pady=(PAD_SMALL, PAD))
        self._canvas.bind("<Configure>", lambda e: self._render())
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", lambda e: (self._clear_highlight(), self._tooltip.hide()))

    def set_data(self, items: list[dict], options: Optional[dict] = None):
        self._items = list(items or [])
        self._opts = dict(options or {})
        title = self._opts.get("title")
        if title:
            self._title_label.configure(text=title)
            # before=canvas로 항상 차트 위에 위치 (pack 순서 문제 fix)
            self._title_label.pack(fill="x", padx=PAD, pady=(PAD_SMALL, 0),
                                   before=self._canvas)
        else:
            self._title_label.pack_forget()
        self._render()

    def clear(self):
        self.set_data([], {})

    # ─────────────────────────────────────────
    # 그리기
    # ─────────────────────────────────────────

    def _render(self):
        canvas = self._canvas
        canvas.delete("all")
        self._bars.clear()
        self._avg_hover = None
        self._tooltip.hide()

        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1 or h <= 1:
            return

        items = self._items
        if not items:
            canvas.create_text(
                w // 2, h // 2, text="데이터 없음",
                fill=THEME["TEXT_MUTED"], font=("Arial", 12),
            )
            return

        opts = self._opts
        margin_left = 44
        margin_right = 14
        margin_top = 10
        margin_bottom = 24
        plot_w = w - margin_left - margin_right
        plot_h = h - margin_top - margin_bottom

        values = [float(it.get("value", 0)) for it in items]
        max_v = max(values, default=0) or 1.0
        n = len(items)
        bar_gap = 2
        bar_w = max(1, (plot_w - bar_gap * (n - 1)) / n) if n > 0 else 0

        y_format = opts.get("y_format", "{:.0f}")

        # y축 보조선 + 라벨
        for i in range(5):
            ratio = i / 4
            y = margin_top + plot_h * (1 - ratio)
            value = max_v * ratio
            canvas.create_line(
                margin_left, y, w - margin_right, y,
                fill=THEME["BORDER"], dash=(2, 4),
            )
            canvas.create_text(
                margin_left - 4, y, text=y_format.format(value), anchor="e",
                fill=THEME["TEXT_MUTED"], font=("Arial", 9),
            )

        # 평균선 계산
        avg_v = 0.0
        avg_line_enabled = opts.get("avg_line", False)
        if avg_line_enabled and n > 0:
            avg_v = sum(values) / n

        bar_color = opts.get("bar_color", THEME["BAR"])
        below_color = opts.get("below_color", "#5a6a7a")

        # 막대
        for i, it in enumerate(items):
            x0 = margin_left + i * (bar_w + bar_gap)
            x1 = x0 + bar_w
            v = float(it.get("value", 0))
            bar_h = (v / max_v) * plot_h if max_v > 0 else 0
            y0 = margin_top + plot_h - bar_h
            y1 = margin_top + plot_h
            color = it.get("color")
            if color is None:
                color = bar_color if (not avg_line_enabled or v >= avg_v) else below_color
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

            self._bars.append({
                "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                "lines": it.get("tooltip_lines", [it.get("label", ""), str(v)]),
            })

        # 평균선
        if avg_line_enabled and avg_v > 0:
            avg_y = margin_top + plot_h - (avg_v / max_v) * plot_h
            canvas.create_line(
                margin_left, avg_y, w - margin_right, avg_y,
                fill=THEME["WARN"], width=2, dash=(6, 4),
            )
            label_above = avg_y > margin_top + 20
            label_y = avg_y - 4 if label_above else avg_y + 4
            anchor = "se" if label_above else "ne"
            label_fmt = opts.get("avg_label_fmt", "평균 {:.1f}")
            canvas.create_text(
                w - margin_right - 4, label_y,
                text=label_fmt.format(avg_v), anchor=anchor,
                fill=THEME["WARN"], font=("Arial", 9, "bold"),
            )
            self._avg_hover = {
                "x0": margin_left, "x1": w - margin_right,
                "y": avg_y, "value": avg_v,
                "lines": opts.get("avg_tooltip_lines"),
            }

        # x축 라벨 (자동 thinning)
        max_ticks = int(opts.get("max_x_ticks", 8))
        if n > 0:
            if n <= max_ticks:
                tick_idxs = list(range(n))
            else:
                step = max(1, n // max_ticks)
                tick_idxs = list(range(0, n, step))
                if tick_idxs[-1] != n - 1:
                    tick_idxs.append(n - 1)
            for i in tick_idxs:
                x0 = margin_left + i * (bar_w + bar_gap) + bar_w / 2
                canvas.create_text(
                    x0, h - 8, text=items[i].get("label", ""), anchor="s",
                    fill=THEME["TEXT_MUTED"], font=("Arial", 9),
                )

    # ─────────────────────────────────────────
    # 호버
    # ─────────────────────────────────────────

    def _on_motion(self, event):
        if not self._bars and self._avg_hover is None:
            return
        x, y = event.x, event.y

        # 평균선 우선 (좁은 y 범위)
        avg = self._avg_hover
        if avg is not None and avg.get("lines") and \
           avg["x0"] <= x <= avg["x1"] and abs(y - avg["y"]) <= 5:
            self._clear_highlight()
            self._tooltip.show(event.x_root, event.y_root, "\n".join(avg["lines"]))
            return

        # 막대 영역
        for bar in self._bars:
            if bar["x0"] <= x <= bar["x1"] and bar["y0"] <= y <= bar["y1"]:
                self._highlight_bar(bar)
                self._tooltip.show(event.x_root, event.y_root, "\n".join(bar["lines"]))
                return

        self._clear_highlight()
        self._tooltip.hide()

    def _highlight_bar(self, bar: dict):
        """호버 막대에 흰색 outline + 반투명 톱 라이트."""
        canvas = self._canvas
        canvas.delete("hl")
        # outline
        canvas.create_rectangle(
            bar["x0"] - 1, bar["y0"] - 1, bar["x1"] + 1, bar["y1"],
            outline=THEME["TEXT"], width=2, fill="",
            tags="hl",
        )

    def _clear_highlight(self):
        try:
            self._canvas.delete("hl")
        except Exception:
            pass
