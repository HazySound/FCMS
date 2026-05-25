"""추이 탭 — 시간 흐름에 따른 승률과 FC 채굴량 변화.

자동 단위(determine_unit)에 따라 시간대/일/주/월/연 단위로 점들을 잇는다.
상단에 평균선 토글 스위치.
"""

from __future__ import annotations

import customtkinter as ctk

from core import fc_stats
from ui.tabs._base import BaseTab, unit_label
from ui.theme import THEME
from ui.widgets import LineChart

PAD = 12
PAD_SMALL = 6


class TrendTab(BaseTab):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        # 마지막 데이터 캐시 (토글 시 재사용)
        self._cached = None
        self._build_ui()

    def _build_ui(self):
        # 옵션 바 (평균선 토글)
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=0, column=0, padx=PAD, pady=(PAD, 0), sticky="ew")

        self._avg_var = ctk.BooleanVar(value=True)
        self._avg_switch = ctk.CTkSwitch(
            opts, text="평균선 표시",
            variable=self._avg_var, command=self._reapply,
        )
        self._avg_switch.pack(side="left")

        self._wr_chart = LineChart(self, height=220)
        self._wr_chart.grid(row=1, column=0, padx=PAD, pady=(PAD_SMALL, PAD_SMALL), sticky="nsew")

        self._fc_chart = LineChart(self, height=220)
        self._fc_chart.grid(row=2, column=0, padx=PAD, pady=(PAD_SMALL, PAD), sticky="nsew")

    def set_data(self, matches, start, end, unit, label):
        self._cached = (matches, start, end, unit, label)
        self._reapply()

    def _reapply(self):
        if self._cached is None:
            return
        matches, start, end, unit, label = self._cached

        buckets = fc_stats.breakdown_for_unit(matches, unit)
        valid = [b for b in buckets if b["total"] > 0]

        if not valid:
            self._wr_chart.clear()
            self._fc_chart.clear()
            return

        u_label = unit_label(unit)
        show_avg = self._avg_var.get()

        # 가중 평균 승률 (참고용, tooltip)
        total_w = sum(b["wins"] for b in valid)
        total_m = sum(b["total"] for b in valid)
        overall_wr = (total_w / total_m) if total_m else 0
        total_fc = sum(b["fc"] for b in valid)

        wr_items = [{
            "label": b["label"],
            "value": b["win_rate"],
            "tooltip_lines": _tooltip(b),
        } for b in valid]
        wr_opts = {
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
        }
        self._wr_chart.set_data(wr_items, wr_opts)

        fc_items = [{
            "label": b["label"],
            "value": b["fc"],
            "tooltip_lines": _tooltip(b),
        } for b in valid]
        fc_opts = {
            "y_min": 0,
            "y_format": "{:,.0f}",
            "title": f"{label} · {u_label} FC 채굴량 추이",
            "max_x_ticks": 10,
            "line_color": THEME["WARN"],
            "fill_under": True,
            "avg_line": show_avg,
            "avg_line_color": THEME["TEXT"],  # 라인(주황)과 분리되도록 밝은 회색
            "avg_label_fmt": "평균 {:,.0f} FC",
            "avg_tooltip_lines": [
                f"단위 평균 FC: {sum(it['value'] for it in fc_items)/len(fc_items):,.1f}",
                f"총 FC: {total_fc:,}",
                f"({len(fc_items)}개 단위)",
            ],
        }
        self._fc_chart.set_data(fc_items, fc_opts)


def _tooltip(b):
    return [
        b["label"],
        f"승률: {b['win_rate']*100:.1f}%  ({b['wins']}승 {b['losses']}패)",
        f"판수: {b['total']}",
        f"FC: {b['fc']:,}",
    ]
