# Q-LIR macro exclusion audit - paste as ONE QuantConnect Research cell.
#
# 1. Paste and run macro_events_v2_embedded.py as its own notebook cell.
#    This works on free accounts; no Object Store or Research restart is needed.
# 2. Keep the locked 2021-2024 event frame in memory as `locked_events`
#    (the code also accepts `all_events`).
# 3. Run this cell BEFORE any return/effect calculation.
#
# This cell deliberately selects only date/time/class/identity columns. It
# does not read price, return, volume, or volatility values.

from hashlib import sha256
from io import StringIO
from pathlib import Path

import pandas as pd

CALENDAR_FILE = "macro_events_v2.csv"
EXPECTED_CALENDAR_SHA256 = "db16c107e06903e4731323a3ed71256d1314fa96275a8197349aac5d5a1c3c37"
EXCLUDE_MINUTES = 10
ALLOWED_YEARS = {2021, 2022, 2023, 2024}


def load_calendar():
    """Read locally or from the free-tier-compatible embedded QC module."""
    local_file = Path(CALENDAR_FILE)
    if local_file.exists():
        calendar_text = local_file.read_text(encoding="utf-8")
    elif "macro_calendar_csv_text" in globals():
        calendar_text = globals()["macro_calendar_csv_text"]()
    else:
        try:
            from macro_events_v2_embedded import macro_calendar_csv_text
        except ImportError as exc:
            raise RuntimeError(
                "Paste and run macro_events_v2_embedded.py as a notebook cell, "
                "then rerun this audit cell. No Object Store is required."
            ) from exc
        calendar_text = macro_calendar_csv_text()

    calendar_text = calendar_text.replace("\r\n", "\n")
    actual_digest = sha256(calendar_text.encode("utf-8")).hexdigest()
    if actual_digest != EXPECTED_CALENDAR_SHA256:
        raise RuntimeError(
            "Macro calendar checksum mismatch: "
            f"expected {EXPECTED_CALENDAR_SHA256}, found {actual_digest}"
        )
    return pd.read_csv(StringIO(calendar_text), comment="#", dtype=str)


if "locked_events" in globals():
    _source_events = globals()["locked_events"]
elif "all_events" in globals():
    _source_events = globals()["all_events"]
else:
    raise RuntimeError("Expected the locked frame in `locked_events` or `all_events`.")

identity_columns = ["date", "instrument", "boundary_ct", "boundary_class"]
missing_event_columns = set(identity_columns) - set(_source_events.columns)
if missing_event_columns:
    raise RuntimeError(f"Locked frame lacks columns: {sorted(missing_event_columns)}")

calendar = load_calendar()
required_calendar = {
    "date",
    "time_ct",
    "event",
    "source",
    "source_url",
    "source_asof_utc",
}
missing_calendar = required_calendar - set(calendar.columns)
if missing_calendar:
    raise RuntimeError(f"Calendar lacks columns: {sorted(missing_calendar)}")
if len(calendar) != 1_482:
    raise RuntimeError(f"Expected 1,482 v2 source rows, found {len(calendar):,}")
if calendar.duplicated(list(required_calendar)).any():
    raise RuntimeError("Calendar contains an exact duplicate provenance row")
calendar_years = set(pd.to_datetime(calendar["date"], format="%Y-%m-%d").dt.year)
if calendar_years != ALLOWED_YEARS:
    raise RuntimeError(f"Calendar years are not locked 2021-2024: {calendar_years}")

# Work on an identity-only copy. This makes accidental outcome inspection
# impossible in the exclusion-audit cell even if those columns exist upstream.
audit = _source_events.loc[:, identity_columns].copy()
audit["date"] = audit["date"].astype(str)
audit["year"] = pd.to_datetime(audit["date"], format="%Y-%m-%d").dt.year
if set(audit["year"]) - ALLOWED_YEARS:
    raise RuntimeError("Locked frame contains a 2025+ or pre-2021 observation")
if audit.duplicated(identity_columns).any():
    raise RuntimeError("Locked frame contains a duplicate instrument-boundary row")

unique_releases = calendar[["date", "time_ct"]].drop_duplicates().copy()
if len(unique_releases) != 1_156:
    raise RuntimeError(
        f"Expected 1,156 unique v2 release timestamps, found {len(unique_releases):,}"
    )
unique_releases["event_minute"] = unique_releases["time_ct"].str[:2].astype(
    int
) * 60 + unique_releases["time_ct"].str[3:5].astype(int)
release_minutes_by_date = unique_releases.groupby("date")["event_minute"].apply(
    lambda values: tuple(values)
)

boundary_minutes = audit["boundary_ct"].str[:2].astype(int) * 60 + audit["boundary_ct"].str[
    3:5
].astype(int)
audit["release_excluded"] = [
    any(
        abs(int(boundary) - int(event)) <= EXCLUDE_MINUTES
        for event in release_minutes_by_date.get(date, ())
    )
    for date, boundary in zip(audit["date"], boundary_minutes, strict=True)
]

# The same date/boundary must always receive the same decision, independent of
# instrument and treatment class.
decisions_per_timestamp = audit.groupby(["date", "boundary_ct"])["release_excluded"].nunique()
if not decisions_per_timestamp.eq(1).all():
    raise RuntimeError("Exclusion decision varies by instrument or boundary class")

group_columns = ["year", "instrument", "boundary_class"]
before = audit.groupby(group_columns).size().rename("before")
excluded = audit[audit["release_excluded"]].groupby(group_columns).size().rename("excluded")
retained = audit[~audit["release_excluded"]].groupby(group_columns).size().rename("retained")
exclusion_audit = pd.concat([before, excluded, retained], axis=1).fillna(0).astype(int)
reconciled = exclusion_audit["before"] == exclusion_audit["excluded"] + exclusion_audit["retained"]
if not reconciled.all():
    raise RuntimeError("Before != excluded + retained")

release_exclusion_mask = audit["release_excluded"].copy()
release_exclusion_mask.index = _source_events.index
locked_events_excluded = _source_events.loc[~release_exclusion_mask].copy()

print("--- MACRO CALENDAR V2 AUDIT ---")
print("source rows:", len(calendar))
print("unique release timestamps:", len(unique_releases))
print("locked input rows:", len(audit))
print("excluded rows:", int(audit["release_excluded"].sum()))
print("retained rows:", int((~audit["release_excluded"]).sum()))
print("\n--- BEFORE / EXCLUDED / RETAINED ---")
print(exclusion_audit.to_string())
print("\nPASS: date-specific +/-10-minute mask is symmetric and outcome-blind")
print("Filtered frame is available as `locked_events_excluded`; do not analyze it yet.")
