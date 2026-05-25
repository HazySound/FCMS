"""분석 탭 모음.

각 탭은 BaseTab을 상속하고 set_data(matches, start, end, unit, label)를 구현.
main_window가 PeriodPicker 변경 시 모든 탭에 set_data를 호출한다.
"""

from ui.tabs.overview_tab import OverviewTab
from ui.tabs.time_pattern_tab import TimePatternTab
from ui.tabs.weekday_tab import WeekdayTab
from ui.tabs.trend_tab import TrendTab
from ui.tabs.distribution_tab import DistributionTab

__all__ = [
    "OverviewTab", "TimePatternTab", "WeekdayTab", "TrendTab", "DistributionTab",
]
