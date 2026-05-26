"""기간 선택 위젯.

단일 드롭다운에 빠른 프리셋 + 등록된 시즌 + "사용자 정의…" 항목.
"사용자 정의" 선택 시 시작/종료 날짜 입력 다이얼로그.

콜백:
    on_change(start_date: date, end_date: date, label: str)
    기간이 확정되면 호출. 단일 일자는 start == end.
"""

from __future__ import annotations

import datetime as _dt
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk

from core import app_state, fc_stats, fc_stats_db as db
from ui.theme import THEME

_PREF_LABEL = "period_label"
_PREF_CUSTOM_START = "period_custom_start"
_PREF_CUSTOM_END = "period_custom_end"

PAD = 12
PAD_SMALL = 6

# 빠른 프리셋 — 라벨 → 일 수 (None이면 단일 일자 처리)
_QUICK_PRESETS = [
    ("오늘", 0),
    ("어제", -1),
    ("최근 7일", 6),
    ("최근 30일", 29),
    ("최근 90일", 89),
]
_CUSTOM_LABEL = "사용자 정의…"


class PeriodPicker(ctk.CTkFrame):
    def __init__(self, master, on_change: Optional[Callable] = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change
        self._seasons: list[int] = []
        # 기본: 최근 30일
        self._current = self._compute("최근 30일")

        ctk.CTkLabel(
            self, text="기간:", width=50, anchor="w",
            text_color=THEME["TEXT"],
        ).pack(side="left", padx=(0, PAD_SMALL))

        self._menu = ctk.CTkOptionMenu(
            self, values=self._option_list(),
            command=self._on_menu_select, width=180,
        )
        self._menu.set("최근 30일")
        self._menu.pack(side="left")

    # ─────────────────────────────────────────
    # 외부 API
    # ─────────────────────────────────────────

    def set_seasons(self, season_ids: list[int]):
        """시즌 옵션 갱신 (최신 → 옛날 순으로 받음)."""
        self._seasons = list(season_ids)
        cur_label = self._current[2]
        self._menu.configure(values=self._option_list())
        self._menu.set(cur_label)

    def restore_saved_label(self) -> bool:
        """app_state에 저장된 라벨/기간을 복원. True/False = 복원 여부.

        1) 프리셋/시즌 라벨이면 그대로 compute해서 적용.
        2) 사용자 정의 라벨이면 저장된 start/end 날짜를 직접 복원.
        """
        saved = app_state.get_ui_pref(_PREF_LABEL)
        if not saved:
            return False

        # 1) 프리셋/시즌 옵션에 있으면 직접 복원
        if saved in self._option_list():
            period = self._compute(saved)
            if period is None:
                return False
            self._current = period
            self._menu.set(saved)
            self._notify()
            return True

        # 2) 사용자 정의 — start/end 날짜 가져와 복원
        s_str = app_state.get_ui_pref(_PREF_CUSTOM_START)
        e_str = app_state.get_ui_pref(_PREF_CUSTOM_END)
        if not s_str or not e_str:
            return False
        try:
            start = _dt.datetime.strptime(s_str, "%Y-%m-%d").date()
            end = _dt.datetime.strptime(e_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return False
        if start > end:
            return False
        self._current = (start, end, saved)
        self._menu.set(saved)
        self._notify()
        return True

    def get_period(self) -> tuple[_dt.date, _dt.date, str]:
        return self._current

    def reset_to_default(self):
        """가장 좋은 기본 라벨로 리셋 (등록 시즌이 있으면 '이번 시즌', 없으면 최근 30일)."""
        if self._seasons:
            label = fc_stats.format_season_id(self._seasons[0])
        else:
            label = "최근 30일"
        period = self._compute(label)
        if period is None:
            return
        self._current = period
        self._menu.set(label)
        self._notify()

    # ─────────────────────────────────────────
    # 옵션 리스트
    # ─────────────────────────────────────────

    def _option_list(self) -> list[str]:
        opts = [name for name, _ in _QUICK_PRESETS]
        for sid in self._seasons:
            opts.append(fc_stats.format_season_id(sid))
        opts.append(_CUSTOM_LABEL)
        return opts

    # ─────────────────────────────────────────
    # 메뉴 선택 핸들러
    # ─────────────────────────────────────────

    def _on_menu_select(self, value: str):
        if value == _CUSTOM_LABEL:
            self._open_custom_dialog()
            return
        period = self._compute(value)
        if period is None:
            return
        self._current = period
        app_state.set_ui_pref(_PREF_LABEL, value)
        self._notify()

    def _compute(self, label: str) -> Optional[tuple[_dt.date, _dt.date, str]]:
        today = _dt.date.today()
        for name, offset in _QUICK_PRESETS:
            if name == label:
                if name == "오늘":
                    return today, today, name
                if name == "어제":
                    y = today - _dt.timedelta(days=1)
                    return y, y, name
                return today - _dt.timedelta(days=offset), today, name
        # 시즌 라벨 매칭
        for sid in self._seasons:
            if fc_stats.format_season_id(sid) == label:
                return self._season_period(sid)
        return None

    def _season_period(self, season_id: int) -> tuple[_dt.date, _dt.date, str]:
        """시즌 기간 = 그 시즌 매치들의 KST 최소/최대 날짜."""
        label = fc_stats.format_season_id(season_id)
        try:
            matches = db.get_matches_by_season(season_id)
        except Exception:
            matches = []
        if not matches:
            t = _dt.date.today()
            return t, t, label
        dates = [fc_stats._utc_iso_to_kst(m["match_date"]).date() for m in matches]
        return min(dates), max(dates), label

    # ─────────────────────────────────────────
    # 사용자 정의 다이얼로그
    # ─────────────────────────────────────────

    def _open_custom_dialog(self):
        dlg = _CustomRangeDialog(self.winfo_toplevel(), self._current)
        result = dlg.get_result()
        if result is None:
            # 취소 — 메뉴 표시는 이전 라벨로 복원
            self._menu.set(self._current[2])
            return
        start, end = result
        if start == end:
            label = start.strftime("%Y-%m-%d")
        else:
            label = f"{start.strftime('%m-%d')} ~ {end.strftime('%m-%d')}"
        self._current = (start, end, label)
        self._menu.set(label)
        # 사용자 정의도 영속화 — 라벨 + 시작/종료 날짜를 별도 키로 저장.
        # 다음 실행 시 restore_saved_label이 이 키들을 보고 정확한 기간 복원.
        app_state.set_ui_pref(_PREF_LABEL, label)
        app_state.set_ui_pref(_PREF_CUSTOM_START, start.strftime("%Y-%m-%d"))
        app_state.set_ui_pref(_PREF_CUSTOM_END, end.strftime("%Y-%m-%d"))
        self._notify()

    def _notify(self):
        if self._on_change:
            try:
                self._on_change(*self._current)
            except Exception:
                pass


# ─────────────────────────────────────────────
# 사용자 정의 입력 다이얼로그
# ─────────────────────────────────────────────

class _CustomRangeDialog(ctk.CTkToplevel):
    def __init__(self, parent, initial: tuple[_dt.date, _dt.date, str]):
        super().__init__(parent)
        self.title("기간 선택")
        self.geometry("400x230")
        self.minsize(400, 220)
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=THEME["APP_BG"])
        self._result: Optional[tuple[_dt.date, _dt.date]] = None

        start, end, _ = initial

        ctk.CTkLabel(
            self, text="기간을 입력하세요 (YYYY-MM-DD)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["TEXT"], anchor="w",
        ).pack(fill="x", padx=PAD * 2, pady=(PAD * 2, PAD_SMALL))

        # 시작일
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=PAD * 2, pady=PAD_SMALL)
        ctk.CTkLabel(row1, text="시작일", width=60, anchor="w",
                     text_color=THEME["TEXT_MUTED"]).pack(side="left")
        self._start_entry = ctk.CTkEntry(row1, width=220)
        self._start_entry.insert(0, start.strftime("%Y-%m-%d"))
        self._start_entry.pack(side="left", padx=(PAD_SMALL, 0))

        # 종료일
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=PAD * 2, pady=PAD_SMALL)
        ctk.CTkLabel(row2, text="종료일", width=60, anchor="w",
                     text_color=THEME["TEXT_MUTED"]).pack(side="left")
        self._end_entry = ctk.CTkEntry(row2, width=220)
        self._end_entry.insert(0, end.strftime("%Y-%m-%d"))
        self._end_entry.pack(side="left", padx=(PAD_SMALL, 0))

        ctk.CTkLabel(
            self, text="* 단일 일자를 보려면 시작일 = 종료일로 입력하세요.",
            text_color=THEME["TEXT_MUTED"], font=ctk.CTkFont(size=10), anchor="w",
        ).pack(fill="x", padx=PAD * 2, pady=(PAD_SMALL, 0))

        # 버튼
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=PAD * 2, pady=(PAD, PAD))
        ctk.CTkButton(btns, text="확인", width=80, command=self._ok).pack(side="right")
        ctk.CTkButton(
            btns, text="취소", width=80,
            fg_color="transparent", border_width=1, command=self._cancel,
        ).pack(side="right", padx=(0, PAD_SMALL))

        self.protocol("WM_DELETE_WINDOW", self._cancel)

        if hasattr(parent, "_center_child"):
            parent._center_child(self)
        self.grab_set()
        self.after(50, lambda: self._start_entry.focus_force())

    def _ok(self):
        try:
            s = _dt.datetime.strptime(self._start_entry.get().strip(), "%Y-%m-%d").date()
            e = _dt.datetime.strptime(self._end_entry.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror(
                "기간 오류",
                "날짜 형식이 잘못됐습니다. YYYY-MM-DD 형식으로 입력해 주세요.",
                parent=self,
            )
            return
        if s > e:
            messagebox.showerror(
                "기간 오류",
                "시작일이 종료일보다 늦습니다.",
                parent=self,
            )
            return
        self._result = (s, e)
        self.destroy()

    def _cancel(self):
        self._result = None
        self.destroy()

    def get_result(self) -> Optional[tuple[_dt.date, _dt.date]]:
        self.wait_window()
        return self._result
