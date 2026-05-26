"""요일 패턴 탭 — 월~일 요일별 활동량과 승률."""

from __future__ import annotations

import customtkinter as ctk

from core import app_state, fc_stats
from ui.tabs._base import BaseTab
from ui.theme import THEME
from ui.widgets import BarChart

PAD = 12
PAD_SMALL = 6

_MIN_SAMPLES_FOR_WR = 20
_PREF_AVG = "weekday_avg"


class WeekdayTab(BaseTab):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._cached = None
        self._build_ui()

    def _build_ui(self):
        # 옵션 바
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=0, column=0, padx=PAD, pady=(PAD, 0), sticky="ew")
        self._avg_var = ctk.BooleanVar(
            value=bool(app_state.get_ui_pref(_PREF_AVG, True))
        )
        ctk.CTkSwitch(
            opts, text="평균선 표시",
            variable=self._avg_var, command=self._on_avg_change,
        ).pack(side="left")

        insights = ctk.CTkFrame(self, fg_color="transparent")
        insights.grid(row=1, column=0, padx=PAD, pady=(PAD_SMALL, PAD_SMALL), sticky="ew")
        insights.grid_columnconfigure((0, 1, 2), weight=1)

        self._insight_cards = []
        for i in range(3):
            card = ctk.CTkFrame(insights, fg_color=THEME["LOG_BG"], corner_radius=8)
            card.grid(row=0, column=i, padx=(0 if i == 0 else PAD_SMALL, 0),
                      pady=0, sticky="ew")
            t = ctk.CTkLabel(card, text="-", anchor="w",
                             text_color=THEME["TEXT_MUTED"],
                             font=ctk.CTkFont(size=14, weight="bold"))
            t.pack(fill="x", padx=PAD, pady=(PAD_SMALL, 0))
            v = ctk.CTkLabel(card, text="-", anchor="w",
                             text_color=THEME["TEXT"],
                             font=ctk.CTkFont(size=16, weight="bold"))
            v.pack(fill="x", padx=PAD, pady=(0, PAD_SMALL))
            self._insight_cards.append({"title": t, "value": v})

        self._count_chart = BarChart(self, height=180)
        self._count_chart.grid(row=2, column=0, padx=PAD, pady=PAD_SMALL, sticky="nsew")

        self._wr_chart = BarChart(self, height=180)
        self._wr_chart.grid(row=3, column=0, padx=PAD, pady=(PAD_SMALL, PAD), sticky="nsew")

    def _on_avg_change(self):
        app_state.set_ui_pref(_PREF_AVG, bool(self._avg_var.get()))
        self._reapply()

    def set_data(self, matches, start, end, unit, label):
        self._cached = (matches, start, end, unit, label)
        self._reapply()

    def _reapply(self):
        if self._cached is None:
            return
        matches, start, end, unit, label = self._cached
        buckets = fc_stats.weekday_breakdown(matches)
        total = sum(b["total"] for b in buckets)
        show_avg = self._avg_var.get()

        count_items = [{
            "label": b["label"],
            "value": b["total"],
            "tooltip_lines": _tooltip_lines(b),
        } for b in buckets]
        self._count_chart.set_data(count_items, {
            "y_format": "{:,.0f}",
            "title": f"{label} · 요일별 매치 수",
            "avg_line": show_avg,
            "avg_label_fmt": "요일 평균 {:.1f}판",
            "max_x_ticks": 7,
        })

        wr_items = []
        for b in buckets:
            if b["total"] > 0:
                wr_items.append({
                    "label": b["label"],
                    "value": b["win_rate"],
                    "tooltip_lines": _tooltip_lines(b),
                })
            else:
                wr_items.append({
                    "label": b["label"], "value": 0.0,
                    "color": THEME["BORDER"],
                    "tooltip_lines": [b["label"], "매치 없음"],
                })
        self._wr_chart.set_data(wr_items, {
            "y_format": "{:.0%}",
            "title": f"{label} · 요일별 승률",
            "avg_line": show_avg and total > 0,
            "avg_label_fmt": "평균 {:.0%}",
            "max_x_ticks": 7,
        })

        self._update_insights(buckets, total)

    def _update_insights(self, buckets, total):
        if total == 0:
            for c in self._insight_cards:
                c["title"].configure(text="-")
                c["value"].configure(text="-", text_color=THEME["TEXT_MUTED"])
            return

        most_active = max(buckets, key=lambda b: b["total"])
        self._insight_cards[0]["title"].configure(text="📅 가장 활발한 요일")
        self._insight_cards[0]["value"].configure(
            text=f"{most_active['label']}요일  ({most_active['total']}판)",
            text_color=THEME["TEXT"],
        )

        eligible = [b for b in buckets if b["total"] >= _MIN_SAMPLES_FOR_WR]
        if eligible:
            best = max(eligible, key=lambda b: b["win_rate"])
            worst = min(eligible, key=lambda b: b["win_rate"])
            self._insight_cards[1]["title"].configure(
                text=f"🏆 최고 승률 요일 (≥{_MIN_SAMPLES_FOR_WR}판)")
            self._insight_cards[1]["value"].configure(
                text=f"{best['label']}요일  {best['win_rate']*100:.1f}%  ({best['total']}판)",
                text_color=THEME["OK"],
            )
            self._insight_cards[2]["title"].configure(
                text=f"💀 최저 승률 요일 (≥{_MIN_SAMPLES_FOR_WR}판)")
            self._insight_cards[2]["value"].configure(
                text=f"{worst['label']}요일  {worst['win_rate']*100:.1f}%  ({worst['total']}판)",
                text_color=THEME["ERR"],
            )
        else:
            for c in self._insight_cards[1:]:
                c["title"].configure(text="승률 인사이트")
                c["value"].configure(
                    text=f"표본 부족 (요일당 {_MIN_SAMPLES_FOR_WR}판 미만)",
                    text_color=THEME["TEXT_MUTED"],
                )


def _tooltip_lines(b):
    if b["total"] == 0:
        return [b["label"] + "요일", "매치 없음"]
    return [
        b["label"] + "요일",
        f"판수: {b['total']}",
        f"{b['wins']}승 {b['losses']}패  ({b['win_rate']*100:.1f}%)",
        f"FC: {b['fc']:,}",
    ]
