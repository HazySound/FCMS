"""개요 탭 — 기간의 핵심 통계 카드 + 자동 단위 막대 차트.

이전 StatsView를 대체. 시즌만 보던 차트가 PeriodPicker의 임의 구간으로 일반화되었고
단위(hour/day/week/month/year)는 determine_unit이 자동 선택한다.
"""

from __future__ import annotations

import datetime as _dt

import customtkinter as ctk

from core import fc_stats
from ui.tabs._base import BaseTab, avg_label_fmt_for_unit, unit_label
from ui.theme import THEME
from ui.widgets import BarChart

PAD = 12
PAD_SMALL = 6


_UNIT_CHOICES = [
    ("자동", None),
    ("시간대", "hour"),
    ("일", "day"),
    ("주", "week"),
    ("월", "month"),
    ("연", "year"),
]


class OverviewTab(BaseTab):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(3, weight=1)
        self._cached = None  # (matches, start, end, auto_unit, label)
        self._build_ui()

    # ─────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────

    def _build_ui(self):
        # row 0: 옵션 바 (단위 선택 + 평균선 토글)
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=0, column=0, padx=PAD, pady=(PAD, 0), sticky="ew")

        ctk.CTkLabel(
            opts, text="단위:", anchor="w", text_color=THEME["TEXT_MUTED"],
        ).pack(side="left", padx=(0, PAD_SMALL))
        unit_labels = [name for name, _ in _UNIT_CHOICES]
        self._unit_menu = ctk.CTkOptionMenu(
            opts, values=unit_labels, command=lambda _v: self._reapply(),
            width=110,
        )
        self._unit_menu.set("자동")
        self._unit_menu.pack(side="left", padx=(0, PAD))

        self._avg_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            opts, text="평균선 표시",
            variable=self._avg_var, command=self._reapply,
        ).pack(side="left")

        # row 1: 통계 카드 격자
        summary = ctk.CTkFrame(self, fg_color="transparent")
        summary.grid(row=1, column=0, padx=PAD, pady=(PAD_SMALL, PAD_SMALL), sticky="ew")
        summary.grid_columnconfigure((1, 3), weight=1)

        self.lbl_fc           = self._pair(summary, 0, 0, "FC 채굴량")
        self.lbl_total        = self._pair(summary, 0, 2, "매치 수")
        self.lbl_winrate      = self._pair(summary, 1, 0, "승률")
        self.lbl_record       = self._pair(summary, 1, 2, "전적")
        self.lbl_sc_wins      = self._pair(summary, 2, 0, "슈챔 승")
        self.lbl_ch_wins      = self._pair(summary, 2, 2, "챔스 승")
        self.lbl_fc_per_day   = self._pair(summary, 3, 0, "일 평균 FC")
        self.lbl_fc_per_match = self._pair(summary, 3, 2, "판수당 평균")

        # 안내 텍스트 + 자세히 버튼
        note_frame = ctk.CTkFrame(self, fg_color="transparent")
        note_frame.grid(row=2, column=0, padx=PAD * 2, pady=(0, PAD_SMALL), sticky="ew")
        note_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            note_frame, anchor="w", justify="left",
            text=(
                "* 챔피언스 / 슈퍼챔피언스 매치만 집계됩니다. FC는 챔피언스 승 +15 / 슈퍼챔피언스 승 +20.\n"
                "* 30일이 지난 매치는 조회되지 않아 표시 데이터에 한계가 있을 수 있습니다.\n"
                "* 30일 이내에 최소 1회 동기화해야 데이터에 공백이 생기지 않습니다."
            ),
            text_color=THEME["TEXT_MUTED"],
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            note_frame, text="ⓘ  자세히",
            width=120, height=34,
            fg_color="transparent", border_width=1,
            command=self._show_info_dialog,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=THEME["TEXT_MUTED"],
        ).grid(row=0, column=1, sticky="ne", padx=(PAD, 0))

        # 막대 차트
        self._chart = BarChart(self, height=240)
        self._chart.grid(row=3, column=0, padx=PAD, pady=(PAD_SMALL, PAD), sticky="nsew")

    def _pair(self, parent, row, col, label_text):
        ctk.CTkLabel(parent, text=label_text, anchor="w",
                     text_color=THEME["TEXT_MUTED"]).grid(
            row=row, column=col, padx=(PAD, PAD_SMALL), pady=4, sticky="w"
        )
        value = ctk.CTkLabel(
            parent, text="-", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=THEME["TEXT"],
        )
        value.grid(row=row, column=col + 1, padx=(0, PAD), pady=4, sticky="w")
        return value

    # ─────────────────────────────────────────
    # 데이터 갱신
    # ─────────────────────────────────────────

    def set_data(self, matches, start, end, unit, label):
        # 자동 단위(unit)와 함께 캐시 — 사용자가 토글/단위 변경 시 _reapply가 재사용
        self._cached = (matches, start, end, unit, label)
        self._reapply()

    def _reapply(self):
        if self._cached is None:
            return
        matches, start, end, auto_unit, label = self._cached

        s = fc_stats.summarize_matches(matches)
        self.lbl_fc.configure(text=f"{s['fc']:,}")
        self.lbl_total.configure(text=f"{s['total']:,}")
        self.lbl_winrate.configure(text=f"{s['win_rate'] * 100:.1f}%")
        self.lbl_record.configure(text=f"{s['wins']}승 {s['losses']}패")
        self.lbl_sc_wins.configure(text=f"{s['sc_wins']:,}")
        self.lbl_ch_wins.configure(text=f"{s['ch_wins']:,}")
        self.lbl_fc_per_day.configure(
            text=f"{s['fc_per_day']:.1f}  ({s['active_days']}일 활동)"
        )
        self.lbl_fc_per_match.configure(text=f"{s['fc_per_match']:.2f}")

        # 사용자 선택 단위 (자동이면 auto_unit)
        sel_label = self._unit_menu.get()
        override = next((u for name, u in _UNIT_CHOICES if name == sel_label), None)
        unit = override if override is not None else auto_unit

        breakdown = fc_stats.breakdown_for_unit(matches, unit)
        items = [_breakdown_to_item(b) for b in breakdown]
        title = f"{label} · {unit_label(unit)} FC 채굴량"
        avg_tooltip = [
            f"일 평균 FC: {s['fc_per_day']:.1f}",
            f"활동일: {s['active_days']}일 (총 FC {s['fc']:,})",
        ]
        self._chart.set_data(items, {
            "avg_line": self._avg_var.get(),
            "avg_label_fmt": avg_label_fmt_for_unit(unit) + " FC",
            "avg_tooltip_lines": avg_tooltip,
            "y_format": "{:,.0f}",
            "title": title,
            "max_x_ticks": 12,
        })

    def clear(self):
        for lbl in (self.lbl_fc, self.lbl_total, self.lbl_winrate, self.lbl_record,
                    self.lbl_sc_wins, self.lbl_ch_wins, self.lbl_fc_per_day,
                    self.lbl_fc_per_match):
            lbl.configure(text="-")
        self._chart.clear()

    # ─────────────────────────────────────────
    # 안내 팝업
    # ─────────────────────────────────────────

    def _show_info_dialog(self):
        parent = self.winfo_toplevel()
        dlg = ctk.CTkToplevel(parent)
        dlg.title("FCMS 안내")
        dlg.geometry("580x560")
        dlg.minsize(540, 480)
        dlg.transient(parent)
        dlg.configure(fg_color=THEME["APP_BG"])

        ctk.CTkLabel(
            dlg, text="FCMS가 어떻게 동작하나요?",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=THEME["TEXT"], anchor="w",
        ).pack(fill="x", padx=PAD, pady=(PAD, PAD_SMALL))

        textbox = ctk.CTkTextbox(
            dlg, font=ctk.CTkFont(size=14),
            wrap="word", fg_color=THEME["LOG_BG"], text_color=THEME["TEXT"],
        )
        textbox.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD_SMALL))
        textbox.insert("0.0", _INFO_TEXT)
        textbox.configure(state="disabled")

        ctk.CTkButton(
            dlg, text="닫기", width=100, command=dlg.destroy,
        ).pack(pady=(0, PAD))

        if hasattr(parent, "_center_child"):
            parent._center_child(dlg)
        dlg.grab_set()
        dlg.focus()


def _breakdown_to_item(b: dict) -> dict:
    label = b.get("label", "")
    fc = int(b.get("fc", 0))
    total = int(b.get("total", 0))
    wins = int(b.get("wins", 0))
    losses = int(b.get("losses", 0))
    win_rate = (wins / total * 100) if total > 0 else 0.0
    tooltip = [
        label,
        f"FC: {fc:,}",
        "",
        f"판수: {total}",
        f"{wins}승 {losses}패  ({win_rate:.1f}%)",
        f"  ㄴ 챔스 승: {b.get('ch_wins', 0)}  /  슈챔 승: {b.get('sc_wins', 0)}",
    ]
    return {"label": label, "value": fc, "tooltip_lines": tooltip}


_INFO_TEXT = """[ 표시되는 데이터에 한계가 있을 수 있습니다 ]

FC 온라인 시스템 상 30일이 지난 매치는 조회되지 않습니다.
따라서 처음 동기화할 때 표시되는 매치는 최근 30일치까지만 받을 수 있고,
그 이전 매치는 받아올 수 없습니다.

매치를 자주 진행한 사용자일수록 30일 안에 더 많은 판수를 받게 되고,
가볍게 즐기는 사용자라면 같은 30일 동안 더 적은 판수가 받아집니다.


[ 데이터 공백을 막으려면 ]

처음 동기화한 뒤에는 30일이 지나기 전에 최소 1회 다시 동기화해 주세요.
30일 이내에 한 번이라도 동기화하면 그 사이 진행한 매치가 빠짐없이
저장되어 데이터에 공백이 생기지 않습니다.

매치를 많이 하는 분이라면 더 자주 동기화하는 것을 권장합니다:

  · 하루 100판 이상  →  매일 동기화 권장
  · 하루 30~50판     →  주 1~2회 동기화
  · 하루 10판 이하   →  월 1~2회로도 충분


[ 데이터는 어떻게 보관되나요? ]

한 번 동기화한 매치는 PC에 영구적으로 저장됩니다.
시즌이 끝나도, 1년이 지나도 그대로 남아 시즌 전체 통계가
점점 완성됩니다.

→ 30일이 지난 옛 매치는 받아올 수 없지만, 지금부터의 매치는
   동기화만 꾸준히 하면 모두 보존됩니다.


[ 어떤 매치가 통계에 포함되나요? ]

  · 챔피언스 / 슈퍼챔피언스 매치만 포함됩니다.
    (다른 디비전은 FC 보상이 없어 채굴 통계에서 제외)
  · 1매치당 FC: 챔피언스 승 +15 / 슈퍼챔피언스 승 +20
    (몰수승도 동일하게 적립됩니다)
  · 무승부 매치는 통계에서 제외되어 전적 = 승 + 패가 보장됩니다.


[ 저장 위치 ]

매치 데이터는 FCMS.exe 옆의 data 폴더에 저장됩니다.
  · fc_stats_meta.json   — 등록된 계정 목록
  · fc_stats_(ouid).db   — 계정별 매치 데이터
  · window_state.json    — 창 위치/크기

이 폴더와 exe를 함께 다른 PC로 옮기면 거기서도 그대로 사용 가능합니다.
"""
