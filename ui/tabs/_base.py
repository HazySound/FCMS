"""모든 분석 탭의 공통 베이스."""

from __future__ import annotations

import datetime as _dt

import customtkinter as ctk

from ui.theme import THEME


class BaseTab(ctk.CTkFrame):
    """탭 공통 베이스 — 단순 패널 + set_data 인터페이스."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=THEME["PANEL_BG"], **kwargs)
        self.grid_columnconfigure(0, weight=1)

    def set_data(self, matches: list[dict], start: _dt.date, end: _dt.date,
                 unit: str, label: str) -> None:
        """기간/단위 변경 또는 sync 후 데이터 갱신.
        모든 탭이 override 한다."""
        raise NotImplementedError


# 단위 라벨 (사용자 친화)
UNIT_LABELS = {
    "hour":  "시간대",
    "day":   "일별",
    "week":  "주별",
    "month": "월별",
    "year":  "연별",
}


def unit_label(unit: str) -> str:
    return UNIT_LABELS.get(unit, unit)


def avg_label_fmt_for_unit(unit: str) -> str:
    """평균선 라벨 포맷 (BarChart 옵션용)."""
    mapping = {
        "hour":  "시간당 평균 {:.1f}",
        "day":   "일 평균 {:.1f}",
        "week":  "주 평균 {:.1f}",
        "month": "월 평균 {:.1f}",
        "year":  "연 평균 {:.1f}",
    }
    return mapping.get(unit, "평균 {:.1f}")


# 단위 선택 드롭다운 공통 옵션 (개요/추이 등 여러 탭이 사용)
UNIT_CHOICES = [
    ("자동", None),
    ("시간대", "hour"),
    ("일", "day"),
    ("주", "week"),
    ("월", "month"),
    ("연", "year"),
]
UNIT_LABEL_LIST = [name for name, _ in UNIT_CHOICES]


def resolve_unit(menu_label: str, auto_unit: str) -> str:
    """드롭다운 메뉴 라벨 → 실제 단위 문자열. '자동'이면 auto_unit으로 fallback."""
    for name, u in UNIT_CHOICES:
        if name == menu_label:
            return u if u is not None else auto_unit
    return auto_unit
