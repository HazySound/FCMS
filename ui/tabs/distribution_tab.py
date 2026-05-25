"""분포 탭 — 시간대 그룹 / 요일 / 승·패 도넛.

레이아웃 (2-column):
    좌상: 시간대 4그룹(새벽/오전/오후/저녁) 도넛 — 크게
    우상: 요일 도넛 — 크게
    하단(컬럼 합쳐서 작게): 승/패 도넛

각 도넛에서 최대/최소 segment를 반지름 차등으로 시각 강조 (highlight_extreme).
"""

from __future__ import annotations

import customtkinter as ctk

from core import fc_stats
from ui.tabs._base import BaseTab
from ui.theme import THEME
from ui.widgets import DonutChart

PAD = 12
PAD_SMALL = 6


class DistributionTab(BaseTab):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        # 상단(시간/요일)이 비중 크고 하단(승/패)은 작게.
        # row 가중치 — 0:크게(가변) / 1:작게(고정)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=2)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._build_ui()

    def _build_ui(self):
        # 좌상: 시간대 그룹
        self._hourly_chart = DonutChart(self, height=280)
        self._hourly_chart.grid(row=0, column=0, padx=(PAD, PAD_SMALL),
                                pady=(PAD, PAD_SMALL), sticky="nsew")

        # 우상: 요일
        self._weekday_chart = DonutChart(self, height=280)
        self._weekday_chart.grid(row=0, column=1, padx=(PAD_SMALL, PAD),
                                 pady=(PAD, PAD_SMALL), sticky="nsew")

        # 하단(작게): 승/패 — 컬럼 풀폭이지만 height 작게
        self._result_chart = DonutChart(self, height=180)
        self._result_chart.grid(row=1, column=0, columnspan=2,
                                padx=PAD, pady=(PAD_SMALL, PAD), sticky="nsew")

    def set_data(self, matches, start, end, unit, label):
        # 전체 가중 평균 (중앙 표시)
        result = fc_stats.result_distribution(matches)
        wins = result.get("승", 0)
        losses = result.get("패", 0)
        total = wins + losses
        overall_wr = (wins / total * 100) if total else 0.0
        overall_label = f"{overall_wr:.1f}%" if total else "-"

        # 시간대 4그룹 — segment 크기 = 승률 (승률 높을수록 큰 파이)
        time_groups = fc_stats.time_group_breakdown(matches)
        time_items = []
        for b in time_groups:
            if b["total"] == 0:
                continue
            wr_pct = b["win_rate"] * 100
            time_items.append({
                "label": f"{b['label']} ({b['sub_label']})",
                "value": b["win_rate"],
                "segment_label": f"{wr_pct:.0f}%",
                "tooltip_lines": [
                    f"{b['label']} ({b['sub_label']})",
                    f"판수: {b['total']}",
                    f"{b['wins']}승 {b['losses']}패",
                    f"승률: {wr_pct:.1f}%",
                ],
            })
        self._hourly_chart.set_data(time_items, {
            "title": f"{label} · 시간대 그룹 (새벽/오전/오후/저녁)",
            "center_text": overall_label,
            "center_subtext": "전체 승률",
            "value_format": "{:,}",
            "hole_ratio": 0.55,
        })

        # 요일 — 동일 패턴, segment 크기 = 승률
        weekday = [b for b in fc_stats.weekday_breakdown(matches) if b["total"] > 0]
        wd_items = []
        for b in weekday:
            wr_pct = b["win_rate"] * 100
            wd_items.append({
                "label": f"{b['label']}요일",
                "value": b["win_rate"],
                "segment_label": f"{wr_pct:.0f}%",
                "tooltip_lines": [
                    f"{b['label']}요일",
                    f"판수: {b['total']}",
                    f"{b['wins']}승 {b['losses']}패",
                    f"승률: {wr_pct:.1f}%",
                ],
            })
        self._weekday_chart.set_data(wd_items, {
            "title": f"{label} · 요일별 승률 분포",
            "center_text": overall_label,
            "center_subtext": "전체 승률",
            "value_format": "{:,}",
            "hole_ratio": 0.55,
        })

        # 승/패 (작게, 강조 없음)
        res_items = [
            {"label": "승", "value": wins, "color": THEME["OK"]},
            {"label": "패", "value": losses, "color": THEME["ERR"]},
        ]
        self._result_chart.set_data(res_items, {
            "title": f"{label} · 전체 승/패",
            "center_text": overall_label,
            "center_subtext": "승률",
            "value_format": "{:,}",
            "hole_ratio": 0.55,
        })
