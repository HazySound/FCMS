"""차트 위젯 공용 툴팁 헬퍼.

각 차트 위젯이 자체적으로 tk.Toplevel 툴팁을 관리. helper 함수는 그 관리를 단순화.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from ui.theme import THEME


class HoverTooltip:
    """차트 위젯에 부착하는 호버 툴팁. lazy create."""

    def __init__(self, master: tk.Misc):
        self._master = master
        self._top: Optional[tk.Toplevel] = None
        self._label: Optional[tk.Label] = None

    def _ensure(self):
        if self._top is None:
            self._top = tk.Toplevel(self._master)
            self._top.overrideredirect(True)
            self._top.attributes("-topmost", True)
            self._label = tk.Label(
                self._top, justify="left",
                bg=THEME["TOOLTIP_BG"], fg=THEME["TOOLTIP_FG"],
                padx=10, pady=6, font=("Arial", 10),
            )
            self._label.pack()

    def show(self, x_root: int, y_root: int, text: str):
        self._ensure()
        self._label.configure(text=text)
        self._top.geometry(f"+{x_root + 15}+{y_root + 12}")
        self._top.deiconify()

    def hide(self):
        if self._top is not None:
            try:
                self._top.withdraw()
            except Exception:
                pass
