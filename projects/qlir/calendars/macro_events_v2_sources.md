# Q-LIR macro calendar v2 source contract

Frozen on 2026-08-13 for the 2021-01-01 through 2024-12-31 Gate II
sample. The generated artifact is `macro_events_v2.csv`; the reproducible
compiler is `../scripts/build_macro_calendar.py`.

## Inclusion rule

1. Include every release in the annual U.S. Principal Federal Economic
   Indicators schedules whose announced release time is within 08:45
   through 14:45 America/Chicago, inclusive.
2. Add the fixed benchmark families: BLS JOLTS; FOMC statements and
   press conferences; ISM Manufacturing and Services PMI; S&P Global US
   flash, manufacturing, and services PMI; Conference Board Consumer
   Confidence and Leading Economic Index; University of Michigan
   preliminary and final Consumer Sentiment; and NAR Existing-Home Sales.
3. Preserve every source row, including releases that share a timestamp.
   The exclusion mask alone deduplicates `(date, time_ct)` and applies an
   inclusive ±10-minute window on that date to every instrument and class.

Eastern release times convert to Central by subtracting one hour. Both
zones change daylight-saving time together, so the offset is one hour
throughout this sample. The v2 artifact has 1,482 source rows and 1,156
unique exclusion timestamps. It contains no 2025 or 2026 observation.

## Sources and transformations

| Family | Official or issuer source | Time handling |
| --- | --- | --- |
| PFEI annual schedules | `https://www.statspolicy.gov/assets/fcsm/files/docs/OMB_pfei_schedule_of_release_dates_{year}.pdf` | USDA noon/3 p.m. ET, EIA 10:30 a.m. ET or noon holiday shift, exceptional BEA 10 a.m. ET cells, and Federal Reserve Consumer Credit 3 p.m. ET are inside the window. Other PFEI releases outside the window are not added. |
| Census PFEI dates and announced times | `https://www.census.gov/economic-indicators/calendar-listview-{year}.html` | Only indicators present in the PFEI schedule and marked 10:00 a.m. ET are added. |
| BLS JOLTS | `https://www.bls.gov/bls/news-release/jolts.htm` and the row-level archived release URL | The archive filename supplies the release date; each release page states 10:00 a.m. ET. |
| FOMC | `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` | Statements are 13:00 CT and press conferences 13:30 CT on scheduled decision dates. |
| ISM PMI | Issuer calendar snapshots of `https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/` pinned through the Internet Archive | Manufacturing and Services releases are 10:00 a.m. ET. The exact archive timestamp is stored in each row. |
| S&P Global US PMI | Issuer PDF calendar snapshots of `https://www.pmi.spglobal.com/Public/Home/PDF/UK_Rel_Dates` pinned through the Internet Archive | The PDFs state UTC times that resolve to 09:45 a.m. ET, or 08:45 CT. A following-year PDF supplies each target year's December flash date. |
| Conference Board | `https://www.conference-board.org/data/calendar/events.json.cfm` | The issuer API's epoch timestamps are converted to America/New_York, verified as 10:00 a.m., then recorded as 09:00 CT. |
| University of Michigan | `https://data.sca.isr.umich.edu/fetchdoc.php?docid=75443` | The issuer's historical preliminary/final date table is used; release time is 10:00 a.m. ET. |
| NAR Existing-Home Sales | NAR annual release schedules syndicated under NAR as source for 2022-2024, plus NAR historical release dates for 2021 | All are announced for 10:00 a.m. ET. Row-level source URLs are retained. |

`source_asof_utc` is the exact Internet Archive capture timestamp for a
pinned snapshot. For direct official/issuer sources it is the v2 research
freeze timestamp, `2026-08-13T00:00:00Z`. The calendar is immutable input
for this protocol; a later source correction requires a new version and a
fresh approval, not an in-place edit.

## Reconciliation invariants

- Exactly 88 Census PFEI rows, 70 USDA PFEI rows, 52 EIA rows, and 12
  Federal Reserve Consumer Credit rows occur in each year.
- The two exceptional in-window BEA releases are 2021-11-24 and
  2024-11-27.
- Each year has 12 JOLTS, 16 FOMC, 24 ISM, 36 S&P Global, 24 Conference
  Board, 24 Michigan, and 12 NAR rows.
- Valid CT release times are limited to 08:45, 09:00, 09:30, 11:00,
  13:00, 13:30, and 14:00.
- Exact duplicate provenance rows are forbidden; coincident but distinct
  releases are required to remain separate.
