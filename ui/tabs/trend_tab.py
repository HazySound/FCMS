"""추이 탭 — 시간 흐름에 따른 승률과 FC 채굴량 변화.

자체 단위 드롭다운 + 평균선 토글 (개요 탭과 독립). 설정은 영속화.
"""

from __future__ import annotations

import customtkinter as ctk

from core import app_state, fc_stats
from ui.tabs._base import (
    BaseTab, unit_label, UNIT_LABEL_LIST, resolve_unit,
)
from ui.theme import THEME
from ui.widgets import LineChart

PAD = 12
PAD_SMALL = 6

_PREF_UNIT = "trend_unit"
_PREF_AVG = "trend_avg"


class TrendTab(BaseTab):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._cached = None
        self._build_ui()

    def _build_ui(self):
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=0, column=0, padx=PAD, pady=(PAD, 0), sticky="ew")

        ctk.CTkLabel(
            opts, text="단위:", anchor="w", text_color=THEME["TEXT_MUTED"],
        ).pack(side="left", padx=(0, PAD_SMALL))
        self._unit_menu = ctk.CTkOptionMenu(
            opts, values=UNIT_LABEL_LIST,
            command=lambda _v: self._on_pref_change(),
            width=110,
        )
        saved_unit = app_state.get_ui_pref(_PREF_UNIT, "자동")
        if saved_unit not in UNIT_LABEL_LIST:
            saved_unit = "자동"
        self._unit_menu.set(saved_unit)
        self._unit_menu.pack(side="left", padx=(0, PAD))

        self._avg_var = ctk.BooleanVar(
            value=bool(app_state.get_ui_pref(_PREF_AVG, True))
        )
        ctk.CTkSwitch(
            opts, text="평균선 표시",
            variable=self._avg_var, command=self._on_pref_change,
        ).pack(side="left")

        self._wr_chart = LineChart(self, height=220)
        self._wr_chart.grid(row=1, column=0, padx=PAD, pady=(PAD_SMALL, PAD_SMALL), sticky="nsew")

        self._fc_chart = LineChart(self, height=220)
        self._fc_chart.grid(row=2, column=0, padx=PAD, pady=(PAD_SMALL, PAD), sticky="nsew")

    def _on_pref_change(self):
        app_state.set_ui_pref(_PREF_UNIT, self._unit_menu.get())
        app_state.set_ui_pref(_PREF_AVG, bool(self._avg_var.get()))
        self._reapply()

    def set_data(self, matches, start, end, unit, label):
        self._cached = (matches, start, end, unit, label)
        self._reapply()

    def _reapply(self):
        if self._cached is None:
            return
        matches, start, end, auto_unit, label = self._cached
        unit = resolve_unit(self._unit_menu.get(), auto_unit)

        buckets = fc_stats.breakdown_for_unit(matches, unit)
        valid = [b for b in buckets if b["total"] > 0]

        if not valid:
            self._wr_chart.clear()
            self._fc_chart.clear()
            return

        u_label = unit_label(unit)
        show_avg = self._avg_var.get()

        total_w = sum(b["wins"] for b in valid)
        total_m = sum(b["total"] for b in valid)
        overall_wr = (total_w / total_m) if total_m else 0
        total_fc = sum(b["fc"] for b in valid)

        wr_items = [{
            "label": b["label"],
            "value": b["win_rate"],
            "tooltip_lines": _tooltip(b),
        } for b in valid]
        self._wr_chart.set_data(wr_items, {
            "y_min": 0.0, "y_max": 1.0,
            "y_format": "{:.0%}",
            "title": f"{label} · {u_label} 승률 추이",
            "max_x_ticks": 10,
            "line_color": THEME["OK"],
            "avg_line": show_avg,
            "avg_label_fmt": "단순 평균 {:.0%}",
            "avg_tooltip_lines": [
                f"단위별 단순 평균: {sum(it['value'] for it in wr_items)/len(wr_items)*100:.1f}%",
                f"전체 가중 평균: {overall_wr*100:.1f}%",
                f"({total_w}승 / {total_m}판)",
            ],
        })

        fc_items = [{
            "label": b["label"],
            "value": b["fc"],
            "tooltip_lines": _tooltip(b),
        } for b in valid]
        self._fc_chart.set_data(fc_items, {
            "y_min": 0,
            "y_format": "{:,.0f}",
            "title": f"{label} · {u_label} FC 채굴량 추이",
            "max_x_ticks": 10,
            "line_color": THEME["WARN"],
            "fill_under": True,
            "avg_line": show_avg,
            "avg_line_color": THEME["TEXT"],
            "avg_label_fmt": "평균 {:,.0f} FC",
            "avg_tooltip_lines": [
                f"단위 평균 FC: {sum(it['value'] for it in fc_items)/len(fc_items):,.1f}",
                f"총 FC: {total_fc:,}",
                f"({len(fc_items)}개 단위)",
            ],
        })


def _tooltip(b):
    return [
        b["label"],
        f"승률: {b['win_rate']*100:.1f}%  ({b['wins']}승 {b['losses']}패)",
        f"판수: {b['total']}",
        f"FC: {b['fc']:,}",
    ]
