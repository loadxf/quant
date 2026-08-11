"""Small deterministic NYSE session calendar used by calendar signals."""

from __future__ import annotations

from typing import ClassVar

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
)


def _observe_nyse_new_year(date: pd.Timestamp) -> pd.Timestamp:
    # Unlike US federal offices, NYSE does not close the preceding Friday
    # when January 1 falls on Saturday. A Sunday holiday moves to Monday.
    return date + pd.Timedelta(days=1) if date.weekday() == 6 else date


class _NyseRegularHolidays(AbstractHolidayCalendar):
    rules: ClassVar = [
        Holiday("New Year", month=1, day=1, observance=_observe_nyse_new_year),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday(
            "Juneteenth",
            month=6,
            day=19,
            start_date=pd.Timestamp("2022-01-01"),
            observance=nearest_workday,
        ),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


_ONE_OFF_CLOSURES = pd.DatetimeIndex(
    [
        "2001-09-11",
        "2001-09-12",
        "2001-09-13",
        "2001-09-14",
        "2004-06-11",
        "2007-01-02",
        "2012-10-29",
        "2012-10-30",
        "2018-12-05",
        "2025-01-09",
    ]
)


def nyse_sessions(start, end) -> pd.DatetimeIndex:
    """Regular NYSE trading dates, including known exceptional closures."""
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    weekdays = pd.date_range(start_ts, end_ts, freq="B")
    holidays = _NyseRegularHolidays().holidays(start=start_ts, end=end_ts)
    closures = holidays.union(_ONE_OFF_CLOSURES)
    return weekdays[~weekdays.isin(closures)]
