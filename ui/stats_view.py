"""통계 카드 + 일별 FC 채굴량 차트.

CTkFrame 서브클래스. 활성 계정의 선택된 시즌 통계를 표시.
시즌 변경/sync 후 부모가 refresh()를 호출하면 다시 그린다.

호버 툴팁:
    차트 막대 위에 마우스 올리면 그 날짜의 FC/판수/승패 상세를 띄운다.
    tk.Toplevel + overrideredirect로 보더리스 라벨을 띄우는 방식.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk

from core import fc_stats
from ui.theme import THEME

PAD = 12
PAD_SMALL = 6
CHART_HEIGHT = 220


class StatsView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=THEME["PANEL_BG"], **kwargs)
        self._selected_season: Optional[int] = None
        self._chart_bars: list[dict] = []
        self._chart_avg: Optional[dict] = None
        self._tooltip: Optional[tk.Toplevel] = None
        self._tooltip_label: Optional[tk.Label] = None

        self._build_ui()

    # ─────────────────────────────────────────
    # UI 구축
    # ─────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # 통계 카드
        summary = ctk.CTkFrame(self, fg_color="transparent")
        summary.grid(row=0, column=0, padx=PAD, pady=(PAD, PAD_SMALL), sticky="ew")
        summary.grid_columnconfigure((1, 3), weight=1)

        self.lbl_fc           = self._summary_pair(summary, 0, 0, "FC 채굴량")
        self.lbl_total        = self._summary_pair(summary, 0, 2, "매치 수")
        self.lbl_winrate      = self._summary_pair(summary, 1, 0, "승률")
        self.lbl_record       = self._summary_pair(summary, 1, 2, "전적")
        self.lbl_sc_wins      = self._summary_pair(summary, 2, 0, "슈챔 승")
        self.lbl_ch_wins      = self._summary_pair(summary, 2, 2, "챔스 승")
        self.lbl_fc_per_day   = self._summary_pair(summary, 3, 0, "일 평균 FC")
        self.lbl_fc_per_match = self._summary_pair(summary, 3, 2, "판수당 평균")

        # 안내 텍스트 + ℹ 자세히 버튼
        note_frame = ctk.CTkFrame(self, fg_color="transparent")
        note_frame.grid(row=1, column=0, padx=PAD * 2, pady=(0, PAD_SMALL), sticky="ew")
        note_frame.grid_columnconfigure(0, weight=1)

        note = ctk.CTkLabel(
            note_frame, anchor="w", justify="left",
            text=(
                "* 챔피언스 / 슈퍼챔피언스 매치만 집계됩니다. FC는 챔피언스 승 +15 / 슈퍼챔피언스 승 +20.\n"
                "* 30일이 지난 매치는 조회되지 않아 표시 데이터에 한계가 있을 수 있습니다.\n"
                "* 30일 이내에 최소 1회 동기화해야 데이터에 공백이 생기지 않습니다."
            ),
            text_color=THEME["TEXT_MUTED"],
            font=ctk.CTkFont(size=11),
        )
        note.grid(row=0, column=0, sticky="w")

        info_btn = ctk.CTkButton(
            note_frame, text="ⓘ  자세히",
            width=120, height=34,
            fg_color="transparent", border_width=1,
            command=self._show_info_dialog,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=THEME["TEXT_MUTED"],
        )
        info_btn.grid(row=0, column=1, sticky="ne", padx=(PAD, 0))

        # 일별 차트
        chart_box = ctk.CTkFrame(self, fg_color=THEME["LOG_BG"])
        chart_box.grid(row=2, column=0, padx=PAD, pady=(PAD_SMALL, PAD), sticky="nsew")
        chart_box.grid_rowconfigure(1, weight=1)
        chart_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            chart_box, text="일별 FC 채굴량", anchor="w",
            text_color=THEME["TEXT"],
        ).grid(row=0, column=0, padx=PAD, pady=(PAD_SMALL, 0), sticky="w")

        self.chart_canvas = tk.Canvas(
            chart_box, height=CHART_HEIGHT, highlightthickness=0,
            bg=THEME["LOG_BG"],
        )
        self.chart_canvas.grid(row=1, column=0, padx=PAD, pady=(PAD_SMALL, PAD), sticky="nsew")
        self.chart_canvas.bind("<Configure>", lambda e: self._draw_chart())
        self.chart_canvas.bind("<Motion>", self._on_chart_motion)
        self.chart_canvas.bind("<Leave>", lambda e: self._hide_tooltip())

    def _summary_pair(self, parent, row, col, label_text):
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
    # 안내 팝업
    # ─────────────────────────────────────────

    def _show_info_dialog(self):
        parent = self.winfo_toplevel()
        dlg = ctk.CTkToplevel(parent)
        dlg.title("FCStats 안내")
        dlg.geometry("580x560")
        dlg.minsize(540, 480)
        dlg.transient(parent)
        dlg.configure(fg_color=THEME["APP_BG"])

        ctk.CTkLabel(
            dlg, text="FCStats가 어떻게 동작하나요?",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=THEME["TEXT"], anchor="w",
        ).pack(fill="x", padx=PAD, pady=(PAD, PAD_SMALL))

        textbox = ctk.CTkTextbox(
            dlg, font=ctk.CTkFont(size=15),
            wrap="word", fg_color=THEME["LOG_BG"], text_color=THEME["TEXT"],
        )
        textbox.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD_SMALL))
        textbox.insert("0.0", _INFO_TEXT)
        textbox.configure(state="disabled")

        ctk.CTkButton(
            dlg, text="닫기", width=100, command=dlg.destroy,
        ).pack(pady=(0, PAD))

        # 부모(메인 윈도우)에 _center_child가 있으면 활용해 정중앙 배치
        if hasattr(parent, "_center_child"):
            parent._center_child(dlg)
        dlg.grab_set()
        dlg.focus()

    # ─────────────────────────────────────────
    # 외부 API
    # ─────────────────────────────────────────

    def set_season(self, season_id: Optional[int]):
        self._selected_season = season_id
        self.refresh()

    def refresh(self):
        self._refresh_summary()
        self._draw_chart()

    def clear(self):
        """계정 없음/데이터 없음 상태로 초기화."""
        self._selected_season = None
        for lbl in (self.lbl_fc, self.lbl_total, self.lbl_winrate, self.lbl_record,
                    self.lbl_sc_wins, self.lbl_ch_wins, self.lbl_fc_per_day,
                    self.lbl_fc_per_match):
            lbl.configure(text="-")
        self._chart_bars.clear()
        self._chart_avg = None
        self.chart_canvas.delete("all")
        self._hide_tooltip()

    # ─────────────────────────────────────────
    # 통계 갱신
    # ─────────────────────────────────────────

    def _refresh_summary(self):
        if self._selected_season is None:
            for lbl in (self.lbl_fc, self.lbl_total, self.lbl_winrate, self.lbl_record,
                        self.lbl_sc_wins, self.lbl_ch_wins, self.lbl_fc_per_day,
                        self.lbl_fc_per_match):
                lbl.configure(text="-")
            return

        s = fc_stats.get_season_summary_extended(self._selected_season)
        self.lbl_fc.configure(text=f"{s['fc']:,}")
        self.lbl_total.configure(text=f"{s['total']:,}")
        self.lbl_winrate.configure(text=f"{s['win_rate'] * 100:.1f}%")
        # 챔/슈챔만 집계 → 무승부 없음
        self.lbl_record.configure(text=f"{s['wins']}승 {s['losses']}패")
        self.lbl_sc_wins.configure(text=f"{s['sc_wins']:,}")
        self.lbl_ch_wins.configure(text=f"{s['ch_wins']:,}")
        self.lbl_fc_per_day.configure(
            text=f"{s['fc_per_day']:.1f}  ({s['active_days']}일 활동)"
        )
        self.lbl_fc_per_match.configure(text=f"{s['fc_per_match']:.2f}")

    # ─────────────────────────────────────────
    # 차트 그리기
    # ─────────────────────────────────────────

    def _draw_chart(self):
        canvas = self.chart_canvas
        canvas.delete("all")
        self._chart_bars.clear()
        self._chart_avg = None
        self._hide_tooltip()

        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1 or h <= 1:
            return

        if self._selected_season is None:
            canvas.create_text(
                w // 2, h // 2, text="데이터 없음",
                fill=THEME["TEXT_MUTED"], font=("Arial", 12),
            )
            return

        daily_data = fc_stats.get_daily_summary(self._selected_season)
        if not daily_data:
            canvas.create_text(
                w // 2, h // 2, text="데이터 없음",
                fill=THEME["TEXT_MUTED"], font=("Arial", 12),
            )
            return

        margin_left = 40
        margin_right = 10
        margin_top = 10
        margin_bottom = 24

        plot_w = w - margin_left - margin_right
        plot_h = h - margin_top - margin_bottom

        max_fc = max((d["fc"] for d in daily_data), default=0) or 1
        n = len(daily_data)
        bar_gap = 2
        bar_w = max(1, (plot_w - bar_gap * (n - 1)) / n) if n > 0 else 0

        # y축 보조선 + 라벨
        for i in range(5):
            ratio = i / 4
            y = margin_top + plot_h * (1 - ratio)
            value = int(max_fc * ratio)
            canvas.create_line(
                margin_left, y, w - margin_right, y,
                fill=THEME["BORDER"], dash=(2, 4),
            )
            canvas.create_text(
                margin_left - 4, y, text=str(value), anchor="e",
                fill=THEME["TEXT_MUTED"], font=("Arial", 9),
            )

        # 일 평균 FC (활동일 기준)
        avg_fc = sum(d["fc"] for d in daily_data) / n if n > 0 else 0.0

        # 막대 — 평균 위/아래에 따라 색 다르게 (시각적 구분)
        bar_color_above = THEME["BAR"]
        bar_color_below = "#5a6a7a"  # 평균 이하: muted blue-gray
        for i, d in enumerate(daily_data):
            x0 = margin_left + i * (bar_w + bar_gap)
            x1 = x0 + bar_w
            fc = d["fc"]
            bar_h = (fc / max_fc) * plot_h if max_fc > 0 else 0
            y0 = margin_top + plot_h - bar_h
            y1 = margin_top + plot_h
            color = bar_color_above if fc >= avg_fc else bar_color_below
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

            self._chart_bars.append({
                "x0": x0, "x1": x1,
                "y0": y0, "y1": y1,
                "date": d["date"], "fc": fc,
                "total": d["total"],
                "wins": d["wins"], "losses": d["losses"],
                "sc_wins": d.get("sc_wins", 0),
                "ch_wins": d.get("ch_wins", 0),
            })

        # 일 평균 FC 가로선 (막대 위에 그려야 보임)
        if avg_fc > 0:
            avg_y = margin_top + plot_h - (avg_fc / max_fc) * plot_h
            canvas.create_line(
                margin_left, avg_y, w - margin_right, avg_y,
                fill=THEME["WARN"], width=2, dash=(6, 4),
            )
            # 라벨이 차트 위쪽이면 선 아래에, 아래쪽이면 선 위에 배치해 가독성 확보
            label_above = avg_y > margin_top + 20
            label_y = avg_y - 4 if label_above else avg_y + 4
            label_anchor = "se" if label_above else "ne"
            canvas.create_text(
                w - margin_right - 4, label_y,
                text=f"일 평균 {avg_fc:.1f} FC",
                anchor=label_anchor,
                fill=THEME["WARN"], font=("Arial", 9, "bold"),
            )

            # 평균선 hover 영역 저장 (±4px 여유로 dash 사이 공백에도 동작)
            self._chart_avg = {
                "x0": margin_left, "x1": w - margin_right,
                "y": avg_y,
                "avg_fc": avg_fc,
                "active_days": n,
                "total_fc": sum(d["fc"] for d in daily_data),
                "above_count": sum(1 for d in daily_data if d["fc"] >= avg_fc),
                "below_count": sum(1 for d in daily_data if d["fc"] < avg_fc),
            }

        # x축 라벨 (혼잡 방지: 처음/중간/끝만)
        if n > 0:
            tick_idxs = sorted({0, n // 2, n - 1})
            for i in tick_idxs:
                d = daily_data[i]
                x0 = margin_left + i * (bar_w + bar_gap) + bar_w / 2
                short = d["date"][5:]
                canvas.create_text(
                    x0, h - 8, text=short, anchor="s",
                    fill=THEME["TEXT_MUTED"], font=("Arial", 9),
                )

    # ─────────────────────────────────────────
    # 호버 툴팁
    # ─────────────────────────────────────────

    def _on_chart_motion(self, event):
        if not self._chart_bars and self._chart_avg is None:
            return
        x, y = event.x, event.y

        # 평균선 hover (±5px 여유로 dash 사이 공백에서도 동작) 우선 처리
        avg = self._chart_avg
        if avg is not None and avg["x0"] <= x <= avg["x1"] and abs(y - avg["y"]) <= 5:
            self._show_avg_tooltip(event.x_root, event.y_root, avg)
            return

        # 막대 hover — 실제 막대 영역 (x AND y 둘 다 안에 있어야)
        for bar in self._chart_bars:
            if bar["x0"] <= x <= bar["x1"] and bar["y0"] <= y <= bar["y1"]:
                self._show_tooltip(event.x_root, event.y_root, bar)
                return

        self._hide_tooltip()

    def _ensure_tooltip(self):
        if self._tooltip is None:
            self._tooltip = tk.Toplevel(self)
            self._tooltip.overrideredirect(True)
            self._tooltip.attributes("-topmost", True)
            self._tooltip_label = tk.Label(
                self._tooltip, justify="left",
                bg=THEME["TOOLTIP_BG"], fg=THEME["TOOLTIP_FG"],
                padx=10, pady=6, font=("Arial", 10),
            )
            self._tooltip_label.pack()

    def _place_tooltip(self, x_root: int, y_root: int, text: str):
        self._ensure_tooltip()
        self._tooltip_label.configure(text=text)
        self._tooltip.geometry(f"+{x_root + 15}+{y_root + 12}")
        self._tooltip.deiconify()

    def _show_tooltip(self, x_root: int, y_root: int, bar: dict):
        date_with_w = fc_stats.format_date_with_weekday(bar["date"])
        win_rate = (bar["wins"] / bar["total"] * 100) if bar["total"] > 0 else 0.0
        text = (
            f"{date_with_w}\n"
            f"FC: {bar['fc']}\n"
            f"\n"
            f"판수: {bar['total']}\n"
            f"{bar['wins']}승 {bar['losses']}패 ({win_rate:.1f}%)\n"
            f"  ㄴ 챔스 승: {bar['ch_wins']}  /  슈챔 승: {bar['sc_wins']}"
        )
        self._place_tooltip(x_root, y_root, text)

    def _show_avg_tooltip(self, x_root: int, y_root: int, avg: dict):
        active = avg["active_days"]
        above = avg["above_count"]
        below = avg["below_count"]
        total_fc = avg["total_fc"]
        above_pct = (above / active * 100) if active else 0.0
        text = (
            f"일 평균 FC: {avg['avg_fc']:.1f}\n"
            f"활동일: {active}일 (총 FC {total_fc:,})\n"
            f"\n"
            f"평균 이상: {above}일 ({above_pct:.1f}%)\n"
            f"평균 미만: {below}일"
        )
        self._place_tooltip(x_root, y_root, text)

    def _hide_tooltip(self):
        if self._tooltip is not None:
            try:
                self._tooltip.withdraw()
            except Exception:
                pass


# ─────────────────────────────────────────────
# 안내 팝업 본문
# ─────────────────────────────────────────────

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
시즌이 끝나도, 1년이 지나도 그대로 남아 있어 시즌 전체 통계가
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
