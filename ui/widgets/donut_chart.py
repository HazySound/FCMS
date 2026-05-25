"""범용 도넛 / 원형 차트.

데이터 형식:
    items = [
        {"label": "챔피언스", "value": 2246, "color": "#xxxxxx"},
        ...
    ]

options:
    hole_ratio: 0.0 (pie) ~ 0.7 (얇은 도넛) — default 0.55
    title: 차트 상단 타이틀
    center_text: 도넛 중앙 큰 텍스트 (선택)
    center_subtext: 그 아래 작은 텍스트 (선택)
    legend: True/False — 우측 범례 (default True)
    value_format: 범례 값 포맷 "{:,}" 등
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from ui.theme import THEME
from ui.widgets._tooltip import HoverTooltip

PAD = 12
PAD_SMALL = 6

# 도넛 기본 색 팔레트 (양호한 대비 + 색맹 친화)
_DEFAULT_PALETTE = [
    "#4A9EFF",  # ACCENT (파랑)
    "#F59E0B",  # WARN (호박)
    "#10B981",  # OK (초록)
    "#EF4444",  # ERR (빨강)
    "#8B5CF6",  # 보라
    "#EC4899",  # 분홍
    "#06B6D4",  # 청록
    "#A3A3A3",  # 회색 (기타)
]


class DonutChart(ctk.CTkFrame):
    def __init__(self, master, height: int = 220, **kwargs):
        super().__init__(master, fg_color=THEME["LOG_BG"], **kwargs)
        self._items: list[dict] = []
        self._opts: dict = {}
        self._segments: list[dict] = []  # 호버용
        self._cx = 0
        self._cy = 0
        self._r_outer = 0
        self._r_inner = 0
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
        self._items = [it for it in (items or []) if float(it.get("value", 0)) > 0]
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
        self._segments.clear()
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
        legend_enabled = opts.get("legend", True)
        hole_ratio = float(opts.get("hole_ratio", 0.55))

        # 차트 영역(좌)/범례 영역(우) 분할. legend 영역을 좀 더 넓게.
        if legend_enabled:
            chart_area_w = w * 0.50
        else:
            chart_area_w = w

        # 최대 segment 확장 분(EXTRA_MAX)까지 들어갈 여유. 영역 size 계산 시 차감.
        edge_pad = 24
        size = min(chart_area_w - edge_pad, h - edge_pad)
        if size < 40:
            size = 40
        self._cx = int(chart_area_w / 2)
        self._cy = int(h / 2)
        self._r_outer = int(size / 2)
        self._r_inner = int(self._r_outer * hole_ratio)

        total = sum(float(it["value"]) for it in items)
        if total <= 0:
            return

        # 최대/최소 강조 옵션 — segment 반지름을 확실히 차등
        highlight_extreme = opts.get("highlight_extreme", False) and len(items) >= 3
        max_v = max(float(it["value"]) for it in items)
        min_v = min(float(it["value"]) for it in items)
        EXTRA_MAX = 14   # 최대 segment 반지름 추가 (눈에 띄게)
        SHRINK_MIN = 14  # 최소 segment 반지름 차감

        # 각 segment 그리기
        start_angle = 90.0
        for i, it in enumerate(items):
            v = float(it["value"])
            sweep = v / total * 360.0
            color = it.get("color") or _DEFAULT_PALETTE[i % len(_DEFAULT_PALETTE)]

            r = self._r_outer
            extreme_kind = None
            if highlight_extreme and max_v != min_v:
                if v == max_v:
                    r = self._r_outer + EXTRA_MAX
                    extreme_kind = "max"
                elif v == min_v:
                    r = self._r_outer - SHRINK_MIN
                    extreme_kind = "min"

            canvas.create_arc(
                self._cx - r, self._cy - r,
                self._cx + r, self._cy + r,
                start=start_angle, extent=-sweep,
                fill=color, outline=THEME["LOG_BG"], width=2,
                style="pieslice",
            )

            # segment 안에 라벨 — sweep 충분히 크고 inner 폭에 들어가야
            if sweep >= 14 and (r - self._r_inner) >= 22:
                mid_angle = start_angle - sweep / 2
                mid_r = (r + self._r_inner) / 2
                rad = math.radians(mid_angle)
                tx = self._cx + mid_r * math.cos(rad)
                ty = self._cy - mid_r * math.sin(rad)
                # item에 segment_label이 명시되면 그것, 아니면 value를 포맷.
                seg_text = it.get("segment_label")
                if seg_text is None:
                    value_fmt = opts.get("value_format", "{:,}")
                    seg_text = value_fmt.format(int(v))
                canvas.create_text(
                    tx, ty, text=seg_text,
                    fill="#FFFFFF", font=("Arial", 10, "bold"),
                )

            self._segments.append({
                "start": start_angle,
                "end": start_angle - sweep,
                "label": it.get("label", ""),
                "value": v,
                "color": color,
                "ratio": v / total,
                "r_outer": r,
                "extreme": extreme_kind,
                "tooltip_lines": it.get("tooltip_lines"),
            })
            start_angle -= sweep

        # 도넛 중앙 hole
        if hole_ratio > 0:
            canvas.create_oval(
                self._cx - self._r_inner, self._cy - self._r_inner,
                self._cx + self._r_inner, self._cy + self._r_inner,
                fill=THEME["LOG_BG"], outline="",
            )

        # 중앙 텍스트
        center_text = opts.get("center_text")
        if center_text:
            canvas.create_text(
                self._cx, self._cy - 8, text=center_text,
                fill=THEME["TEXT"], font=("Arial", 18, "bold"),
            )
        center_sub = opts.get("center_subtext")
        if center_sub:
            canvas.create_text(
                self._cx, self._cy + 14, text=center_sub,
                fill=THEME["TEXT_MUTED"], font=("Arial", 10),
            )

        # 범례 (오른쪽). 값은 segment 안에 표시되므로 라벨엔 비율만.
        if legend_enabled:
            legend_x = chart_area_w + 10
            legend_text_x = legend_x + 18
            legend_text_max_w = max(60, w - legend_text_x - 8)
            legend_y = 24
            row_h = 22
            for seg in self._segments:
                canvas.create_rectangle(
                    legend_x, legend_y, legend_x + 12, legend_y + 12,
                    fill=seg["color"], outline="",
                )
                text = f"{seg['label']}  {seg['ratio']*100:.1f}%"
                canvas.create_text(
                    legend_text_x, legend_y + 6, text=text,
                    fill=THEME["TEXT"], anchor="w", font=("Arial", 10),
                    width=legend_text_max_w,
                )
                legend_y += row_h

    # ─────────────────────────────────────────
    # 호버: 마우스 → 어느 segment 안인지
    # ─────────────────────────────────────────

    def _on_motion(self, event):
        if not self._segments or self._r_outer <= 0:
            return
        dx = event.x - self._cx
        dy = event.y - self._cy
        dist = math.hypot(dx, dy)
        # 확장된 max segment까지 cover하기 위해 가장 큰 r_outer를 기준으로 검사
        max_r = max((s.get("r_outer", self._r_outer) for s in self._segments),
                    default=self._r_outer)
        if dist > max_r or dist < self._r_inner:
            self._clear_highlight()
            self._tooltip.hide()
            return
        ang = math.degrees(math.atan2(-dy, dx))
        if ang < 0:
            ang += 360

        for seg in self._segments:
            start = seg["start"] % 360
            end = seg["end"] % 360
            if start >= end:
                in_seg = end <= ang <= start
            else:
                in_seg = ang <= start or ang >= end
            if in_seg and dist <= seg.get("r_outer", self._r_outer):
                self._highlight_segment(seg)
                lines = seg.get("tooltip_lines") or [
                    seg["label"],
                    f"{int(seg['value']):,}건  ({seg['ratio']*100:.1f}%)",
                ]
                self._tooltip.show(event.x_root, event.y_root, "\n".join(lines))
                return
        self._clear_highlight()
        self._tooltip.hide()

    def _highlight_segment(self, seg: dict):
        """호버 segment를 약간 큰 반지름으로 다시 그려 강조 + 흰색 outline."""
        canvas = self._canvas
        canvas.delete("hl")
        sweep = seg["start"] - seg["end"]
        base_r = seg.get("r_outer", self._r_outer)
        extra = 4
        canvas.create_arc(
            self._cx - base_r - extra, self._cy - base_r - extra,
            self._cx + base_r + extra, self._cy + base_r + extra,
            start=seg["start"], extent=-sweep,
            outline=THEME["TEXT"], width=2, style="arc",
            tags="hl",
        )

    def _clear_highlight(self):
        try:
            self._canvas.delete("hl")
        except Exception:
            pass
