from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STATS_PATH = ROOT / "scripts" / "timing_smoke_stats.py"
CALENDAR_PATH = ROOT / "calendars" / "macro_events_v2.csv"
EMBEDDED_PATH = ROOT / "qc" / "macro_events_v2_embedded.py"

SPEC = importlib.util.spec_from_file_location("qlir_timing_smoke_stats", STATS_PATH)
assert SPEC is not None and SPEC.loader is not None
STATS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATS)

EMBEDDED_SPEC = importlib.util.spec_from_file_location(
    "macro_events_v2_embedded", EMBEDDED_PATH
)
assert EMBEDDED_SPEC is not None and EMBEDDED_SPEC.loader is not None
EMBEDDED = importlib.util.module_from_spec(EMBEDDED_SPEC)
EMBEDDED_SPEC.loader.exec_module(EMBEDDED)


def test_embedded_calendar_matches_canonical_csv() -> None:
    canonical = CALENDAR_PATH.read_bytes().replace(b"\r\n", b"\n")

    assert EMBEDDED.macro_calendar_csv_text().encode("utf-8") == canonical


def test_v2_calendar_has_frozen_complete_provenance() -> None:
    calendar, header = STATS.load_calendar(CALENDAR_PATH)

    assert "coverage: complete" in " ".join(header).lower()
    assert len(calendar) == 1_482
    assert len(calendar[["date", "time_ct"]].drop_duplicates()) == 1_156
    assert calendar.duplicated().sum() == 0
    assert set(pd.to_datetime(calendar["date"]).dt.year) == {2021, 2022, 2023, 2024}
    assert calendar["source_url"].str.startswith("https://").all()
    assert calendar["source_asof_utc"].str.endswith("Z").all()


def test_v2_calendar_reconciles_source_and_time_counts() -> None:
    calendar, _ = STATS.load_calendar(CALENDAR_PATH)
    calendar["year"] = calendar["date"].str[:4].astype(int)

    expected_each_year = {
        "BLS": 12,
        "Census_PFEI": 88,
        "Conference_Board": 24,
        "Federal_Reserve": 16,
        "ISM": 24,
        "NAR": 12,
        "OMB_PFEI_EIA": 52,
        "OMB_PFEI_Federal_Reserve": 12,
        "OMB_PFEI_USDA": 70,
        "SP_Global": 36,
        "University_of_Michigan": 24,
    }
    for year in (2021, 2022, 2023, 2024):
        counts = calendar[calendar["year"] == year].groupby("source").size()
        for source, expected in expected_each_year.items():
            assert counts[source] == expected
    assert calendar.groupby("time_ct").size().to_dict() == {
        "08:45": 144,
        "09:00": 738,
        "09:30": 201,
        "11:00": 175,
        "13:00": 32,
        "13:30": 32,
        "14:00": 160,
    }
    assert calendar.groupby("source").size()["OMB_PFEI_BEA"] == 2


def test_release_mask_deduplicates_timestamps_and_is_symmetric() -> None:
    frame = pd.DataFrame(
        {
            "date": [
                "2024-01-03",
                "2024-01-03",
                "2024-01-03",
                "2024-01-03",
                "2024-01-03",
                "2024-01-04",
            ],
            "boundary_ct": ["08:49", "08:50", "09:00", "09:10", "09:11", "09:00"],
            "instrument": ["ES", "ES", "NQ", "ES", "NQ", "ES"],
            "boundary_class": [
                "placebo",
                "A_00_30",
                "B_15_45",
                "placebo",
                "A_00_30",
                "B_15_45",
            ],
        }
    )
    # Two source rows at one timestamp must be equivalent to one mask event.
    calendar = pd.DataFrame(
        {
            "date": ["2024-01-03", "2024-01-03"],
            "time_ct": ["09:00", "09:00"],
            "event": ["one", "two"],
        }
    )

    mask = STATS.release_excluded(frame, calendar)

    assert mask.tolist() == [False, True, True, True, False, False]
    assert set(frame.loc[mask, "instrument"]) == {"ES", "NQ"}
    assert set(frame.loc[mask, "boundary_class"]) == {
        "A_00_30",
        "B_15_45",
        "placebo",
    }


def test_incomplete_v1_calendar_is_blocked() -> None:
    with pytest.raises(SystemExit, match=r"calendar lacks columns|complete frozen-taxonomy"):
        STATS.load_calendar(ROOT / "calendars" / "macro_events_v1.csv")
