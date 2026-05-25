"""다크 테마 색상 상수 + 폰트 패밀리.

폰트는 assets/ 안에 번들된 Pretendard를 core.font_loader가 process-private
등록한 뒤 family 이름으로 참조한다. 등록 실패 시 customtkinter가 시스템
기본 폰트로 fallback.
"""

APP_FONT_FAMILY = "Pretendard"

THEME = {
    "APP_BG":    "#2f3238",  # 메인 윈도우 배경
    "PANEL_BG":  "#363a40",  # 프레임/카드 배경
    "LOG_BG":    "#3d424a",  # 차트 등 짙은 배경
    "TEXT":      "#e7e9ec",  # 기본 텍스트
    "TEXT_MUTED": "#9ca3af", # 보조 텍스트
    "ACCENT":    "#4A9EFF",  # 강조
    "OK":        "#10b981",  # green (sync 신선)
    "WARN":      "#f59e0b",  # amber
    "ERR":       "#ef4444",  # red (sync 오래됨)
    "BORDER":    "#4a4e55",
    "BAR":       "#1f77b4",  # 차트 막대
    "TOOLTIP_BG":"#1f1f1f",
    "TOOLTIP_FG":"#ffffff",
}
