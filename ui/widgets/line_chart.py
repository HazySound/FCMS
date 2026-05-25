"""범용 꺾은선 차트.

데이터 형식:
    items = [
        {"label": "5-12", "value": 0.523, "tooltip_lines": [...]},
        ...
    ]

options:
    y_min: 0.0 (default 데이터 min)
    y_max: 1.0 (default 데이터 max)
    y_format: "{:.0%}" 등 (default "{:.0f}")
    line_color: 선 색 (default THEME["ACCENT"])
    fill_under: True/False — 선 아래 반투명 채우기 (default False)
    title: 차트 상단 타이틀
    max_x_ticks: x축 라벨 상한 (default 8)
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk

from ui.theme import THEME
from ui.widgets._tooltip import HoverTooltip

PAD = 12
PAD_SMALL = 6


class LineChart(ctk.CTkFrame):
    def __init__(self, master, height: int = 220, **kwargs):
        super().__init__(master, fg_color=THEME["LOG_BG"], **kwargs)
        self._items: list[dict] = []
        self._opts: dict = {}
        self._points: list[dict] = []
        self._avg_hover: Optional[dict] = None
        self._tooltip = HoverTooltip(self)

        self._title_label = ctk.CTkLabel(
            self, text="", anchor="w", text_color=THEME["TEXT"],
        )
        self._title_label.pack(fill="x", padx=PAD, pady=(PAD_SMALL, 0))
        self._title_label.pack_forget()

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
            self._title_label.pack(fill="x", padx=PAD, pady=(PAD_SMALL, 0),
                                   before=self._canvas)
        else:
            self._title_label.pack_forget()
        self._render()

    def clear(self):
        self.set_data([], {})

    def _render(self):
        canvas = self._canvas
        canvas.delete("all")
        self._points.clear()
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
        y_min = opts.get("y_min")
        y_max = opts.get("y_max")
        if y_min is None:
            y_min = min(values) if values else 0
        if y_max is None:
            y_max = max(values) if values else 1
        if y_max <= y_min:
            y_max = y_min + 1
        y_format = opts.get("y_format", "{:.0f}")

        # y축 보조선 + 라벨
        for i in range(5):
            ratio = i / 4
            y = margin_top + plot_h * (1 - ratio)
            value = y_min + (y_max - y_min) * ratio
            canvas.create_line(
                margin_left, y, w - margin_right, y,
                fill=THEME["BORDER"], dash=(2, 4),
            )
            canvas.create_text(
                margin_left - 4, y, text=y_format.format(value), anchor="e",
                fill=THEME["TEXT_MUTED"], font=("Arial", 9),
            )

        n = len(items)
        if n == 0:
            return

        line_color = opts.get("line_color", THEME["ACCENT"])

        # 점 좌표
        coords = []
        for i, it in enumerate(items):
            v = float(it.get("value", 0))
            ratio_y = (v - y_min) / (y_max - y_min)
            x = margin_left + (i / max(1, n - 1)) * plot_w if n > 1 else margin_left + plot_w / 2
            y = margin_top + plot_h * (1 - ratio_y)
            coords.append((x, y))
            self._points.append({
                "x": x, "y": y, "value": v,
                "lines": it.get("tooltip_lines", [it.get("label", ""), y_format.format(v)]),
            })

        # 채우기 (선택)
        if opts.get("fill_under") and len(coords) >= 2:
            poly = list(coords) + [(coords[-1][0], margin_top + plot_h), (coords[0][0], margin_top + plot_h)]
            flat = [c for pt in poly for c in pt]
            canvas.create_polygon(flat, fill=line_color, stipple="gray25", outline="")

        # 선
        if len(coords) >= 2:
            flat = [c for pt in coords for c in pt]
            canvas.create_line(*flat, fill=line_color, width=2, smooth=False)

        # 마커
        for x, y in coords:
            r = 3
            canvas.create_oval(x - r, y - r, x + r, y + r,
                               fill=line_color, outline=THEME["LOG_BG"], width=1)

        # 평균선 (선택)
        self._avg_hover = None
        if opts.get("avg_line") and values:
            avg_v = sum(values) / len(values)
            ratio = (avg_v - y_min) / (y_max - y_min)
            avg_y = margin_top + plot_h * (1 - ratio)
            # 라인 색과 다른 색을 자동 fallback. 명시 옵션이 우선.
            default_avg_color = THEME["WARN"] if line_color != THEME["WARN"] else THEME["TEXT"]
            avg_color = opts.get("avg_line_color", default_avg_color)
            canvas.create_line(
                margin_left, avg_y, w - margin_right, avg_y,
                fill=avg_color, width=2, dash=(6, 4),
            )
            label_above = avg_y > margin_top + 20
            label_y = avg_y - 4 if label_above else avg_y + 4
            anchor = "se" if label_above else "ne"
            label_fmt = opts.get("avg_label_fmt", "평균 " + y_format)
            canvas.create_text(
                w - margin_right - 4, label_y,
                text=label_fmt.format(avg_v), anchor=anchor,
                fill=avg_color, font=("Arial", 9, "bold"),
            )
            self._avg_hover = {
                "x0": margin_left, "x1": w - margin_right,
                "y": avg_y, "value": avg_v,
                "lines": opts.get("avg_tooltip_lines"),
            }

        # x축 라벨 (자동 thinning)
        max_ticks = int(opts.get("max_x_ticks", 8))
        if n <= max_ticks:
            tick_idxs = list(range(n))
        else:
            step = max(1, n // max_ticks)
            tick_idxs = list(range(0, n, step))
            if tick_idxs[-1] != n - 1:
                tick_idxs.append(n - 1)
        for i in tick_idxs:
            x = coords[i][0]
            canvas.create_text(
                x, h - 8, text=items[i].get("label", ""), anchor="s",
                fill=THEME["TEXT_MUTED"], font=("Arial", 9),
            )

    # ─────────────────────────────────────────
    # 호버: 마우스에 가장 가까운 점
    # ─────────────────────────────────────────

    def _on_motion(self, event):
        if not self._points and self._avg_hover is None:
            return
        x, y = event.x, event.y

        # 평균선 hover 우선
        avg = self._avg_hover
        if avg is not None and avg.get("lines") and \
           avg["x0"] <= x <= avg["x1"] and abs(y - avg["y"]) <= 5:
            self._clear_highlight()
            self._tooltip.show(event.x_root, event.y_root, "\n".join(avg["lines"]))
            return

        # 가까운 점 1개 (x 거리 < 24px)
        nearest = None
        nearest_dx = 24
        for p in self._points:
            dx = abs(p["x"] - x)
            if dx < nearest_dx:
                nearest = p
                nearest_dx = dx
        if nearest is None:
            self._clear_highlight()
            self._tooltip.hide()
            return
        self._highlight_point(nearest)
        self._tooltip.show(event.x_root, event.y_root, "\n".join(nearest["lines"]))

    def _highlight_point(self, p: dict):
        canvas = self._canvas
        canvas.delete("hl")
        line_color = self._opts.get("line_color", THEME["ACCENT"])
        # 큰 원 (확대된 점) + 흰색 outline
        r = 7
        canvas.create_oval(
            p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r,
            fill=line_color, outline=THEME["TEXT"], width=2,
            tags="hl",
        )

    def _clear_highlight(self):
        try:
            self._canvas.delete("hl")
        except Exception:
            pass
