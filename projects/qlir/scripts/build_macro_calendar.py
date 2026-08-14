"""Build the frozen Q-LIR ``macro_events_v2.csv`` calendar.

This is a provenance/build utility, not part of the statistical run.  It reads
only public release schedules and issuer calendars; it never opens a market
data file.  The generated CSV remains the analysis input so a later source-page
change cannot silently alter an already committed run.

Research-only dependencies (in addition to the qlir environment)::

    python -m pip install requests pdfplumber lxml beautifulsoup4

Usage::

    python projects/qlir/scripts/build_macro_calendar.py
"""

from __future__ import annotations

import calendar as month_calendar
import csv
import datetime as dt
import io
import re
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

import pandas as pd
import pdfplumber
import requests

YEARS = tuple(range(2021, 2025))
SOURCE_ASOF_UTC = "2026-08-13T00:00:00Z"
OUTPUT = Path(__file__).resolve().parent.parent / "calendars" / "macro_events_v2.csv"
USER_AGENT = "qlir-calendar-audit/2.0 (public release-schedule research)"


@dataclass(frozen=True)
class Event:
    date: str
    time_ct: str
    event: str
    source: str
    source_url: str
    source_asof_utc: str


EVENTS: list[Event] = []
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def add(
    date: dt.date,
    time_ct: str,
    event: str,
    source: str,
    source_url: str,
    source_asof_utc: str = SOURCE_ASOF_UTC,
) -> None:
    EVENTS.append(
        Event(
            date=date.isoformat(),
            time_ct=time_ct,
            event=event,
            source=source,
            source_url=source_url,
            source_asof_utc=source_asof_utc,
        )
    )


def get(url: str, **kwargs: object) -> requests.Response:
    response = SESSION.get(url, timeout=90, **kwargs)
    response.raise_for_status()
    return response


def first_day(value: object) -> int | None:
    match = re.search(r"\d{1,2}", str(value or ""))
    return int(match.group()) if match else None


def compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def archive_asof(url: str) -> str:
    match = re.search(r"/web/(\d{14})id_/", url)
    if not match:
        return SOURCE_ASOF_UTC
    stamp = dt.datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=dt.UTC)
    return stamp.isoformat().replace("+00:00", "Z")


def add_usda_pfei(year: int, pdf: pdfplumber.PDF, source_url: str) -> None:
    definitions = {
        "World Agricultural Supply and Demand Estimates": (
            "USDA_WASDE",
            "11:00",
        ),
        "Agricultural Prices": ("USDA_Agricultural_Prices", "14:00"),
        "Crop Production": ("USDA_Crop_Production", "11:00"),
        "Grain Stocks": ("USDA_Grain_Stocks", "11:00"),
        "Cattle on Feed": ("USDA_Cattle_on_Feed", "14:00"),
        "Hogs and Pigs": ("USDA_Hogs_and_Pigs", "14:00"),
        "Plantings": ("USDA_Plantings", "11:00"),
        "World Agricultural Production": (
            "USDA_World_Agricultural_Production",
            "11:00",
        ),
    }
    table = pdf.pages[0].extract_tables()[0]
    found = 0
    for row in table:
        label = compact(row[1] if len(row) > 1 else "")
        definition = next(
            (value for prefix, value in definitions.items() if label.startswith(prefix)),
            None,
        )
        if definition is None:
            continue
        event, time_ct = definition
        for month, cell in enumerate(row[2:14], start=1):
            day = first_day(cell)
            if day is not None:
                add(
                    dt.date(year, month, day),
                    time_ct,
                    event,
                    "OMB_PFEI_USDA",
                    source_url,
                )
                found += 1
    if found not in {69, 70}:
        raise RuntimeError(f"Unexpected {year} USDA PFEI count: {found}")


def add_census_pfei(year: int) -> None:
    source_url = f"https://www.census.gov/economic-indicators/calendar-listview-{year}.html"
    tables = pd.read_html(io.StringIO(get(source_url).text))
    frame = tables[0].copy()
    frame.columns = [compact(value) for value in frame.iloc[0]]
    frame = frame.iloc[1:].copy()
    frame["Indicator"] = frame["Indicator"].map(compact)
    frame["Time"] = frame["Time"].map(compact)

    def canonical(indicator: str) -> str | None:
        choices = (
            ("Construction Spending", "Census_Construction_Spending"),
            ("New Residential Sales", "Census_New_Residential_Sales"),
            ("Monthly Wholesale Trade", "Census_Monthly_Wholesale_Trade"),
            (
                "Preliminary U.S. Imports",
                "Census_Preliminary_Steel_Imports",
            ),
            (
                "Manufacturing and Trade",
                "Census_Manufacturing_and_Trade_Inventories_and_Sales",
            ),
            (
                "Full Report - Manufacturers",
                "Census_Manufacturers_Shipments_Inventories_and_Orders",
            ),
            ("Housing Vacancies", "Census_Housing_Vacancies_and_Homeownership"),
            ("Quarterly Services Survey", "Census_Quarterly_Services_Survey"),
        )
        for prefix, event in choices:
            if indicator.startswith(prefix):
                return event
        if indicator.startswith("Quarterly Financial Report"):
            return (
                "Census_Quarterly_Financial_Report_Retail"
                if "Retail" in indicator
                else "Census_Quarterly_Financial_Report_Manufacturing"
            )
        return None

    found = 0
    for _, row in frame.iterrows():
        event = canonical(str(row["Indicator"]))
        if event is None or row["Time"] != "10:00 AM":
            continue
        date = dt.datetime.strptime(str(row["Release Date"]), "%B %d, %Y").date()
        add(date, "09:00", event, "Census_PFEI", source_url)
        found += 1
    if found != 88:
        raise RuntimeError(f"Unexpected {year} Census PFEI count: {found}")


def eia_dates(page: pdfplumber.page.Page, year: int) -> list[dt.date]:
    month_numbers = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "JULY": 7,
        "AUG": 8,
        "SEP": 9,
        "SEPT": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }
    target = None
    for table in page.find_tables():
        cells = table.extract()
        if any("Weekly Natural Gas" in compact(cell) for row in cells for cell in row):
            target = table
            break
    if target is None:
        raise RuntimeError(f"EIA PFEI table not found for {year}")

    x0, top, x1, bottom = target.bbox
    words = [
        word
        for word in page.extract_words()
        if x0 <= float(word["x0"]) <= x1 and top <= float(word["top"]) <= bottom
    ]
    headers = [
        (
            month_numbers[str(word["text"]).upper()],
            (float(word["x0"]) + float(word["x1"])) / 2,
            float(word["bottom"]),
        )
        for word in words
        if str(word["text"]).upper() in month_numbers
    ]
    by_month: dict[int, tuple[float, float]] = {}
    for month, center, header_bottom in headers:
        by_month[month] = (center, header_bottom)
    if set(by_month) != set(range(1, 13)):
        raise RuntimeError(f"EIA month headers not found for {year}: {sorted(by_month)}")

    centers = [by_month[month][0] for month in range(1, 13)]
    max_header_bottom = max(value[1] for value in by_month.values())
    step = median(b - a for a, b in pairwise(centers))
    footnote_tops = [
        float(word["top"])
        for word in words
        if str(word["text"]).lower() in {"when", "week"} and float(word["top"]) > max_header_bottom
    ]
    data_bottom = min(footnote_tops) if footnote_tops else bottom

    dates: list[dt.date] = []
    for word in words:
        text = str(word["text"])
        if not text.isdigit() or not (1 <= int(text) <= 31):
            continue
        word_top = float(word["top"])
        if not (max_header_bottom < word_top < data_bottom):
            continue
        center = (float(word["x0"]) + float(word["x1"])) / 2
        month = min(range(1, 13), key=lambda value: abs(center - by_month[value][0]))
        if abs(center - by_month[month][0]) > step * 0.48:
            continue
        dates.append(dt.date(year, month, int(text)))
    dates = sorted(set(dates))
    if len(dates) not in {52, 53}:
        raise RuntimeError(f"Unexpected {year} EIA date count: {len(dates)}")
    if any(date.weekday() not in {2, 3, 4} for date in dates):
        raise RuntimeError(f"Unexpected EIA release weekday in {year}")
    return dates


def add_other_pfei(year: int, pdf: pdfplumber.PDF, source_url: str) -> None:
    # BEA's normally 08:30-ET Personal Income and Outlays release moved to
    # 10:00 ET on the two dates explicitly marked in the PFEI schedules.
    for table in pdf.pages[2].extract_tables():
        for row in table:
            if len(row) < 14 or "Personal Income and Outlays" not in compact(row[1]):
                continue
            for month, cell in enumerate(row[2:14], start=1):
                if "10 a.m." in str(cell or "").lower():
                    day = first_day(cell)
                    if day is None:
                        raise RuntimeError("10 a.m. BEA cell lacks a date")
                    add(
                        dt.date(year, month, day),
                        "09:00",
                        "BEA_Personal_Income_and_Outlays",
                        "OMB_PFEI_BEA",
                        source_url,
                    )

    for date in eia_dates(pdf.pages[2], year):
        # The PFEI footnote sets 10:30 ET for Thursday/Friday releases and
        # noon ET for Wednesday holiday shifts.
        time_ct = "11:00" if date.weekday() == 2 else "09:30"
        add(
            date,
            time_ct,
            "EIA_Weekly_Natural_Gas_Storage_Report",
            "OMB_PFEI_EIA",
            source_url,
        )

    found_credit = 0
    for table in pdf.pages[3].extract_tables():
        for row in table:
            if len(row) < 14 or not compact(row[1]).startswith("Consumer Credit"):
                continue
            for month, cell in enumerate(row[2:14], start=1):
                day = first_day(cell)
                if day is not None:
                    add(
                        dt.date(year, month, day),
                        "14:00",
                        "Federal_Reserve_Consumer_Credit_G19",
                        "OMB_PFEI_Federal_Reserve",
                        source_url,
                    )
                    found_credit += 1
    if found_credit != 12:
        raise RuntimeError(f"Unexpected {year} Consumer Credit count: {found_credit}")


def add_pfei() -> None:
    for year in YEARS:
        source_url = (
            "https://www.statspolicy.gov/assets/fcsm/files/docs/"
            f"OMB_pfei_schedule_of_release_dates_{year}.pdf"
        )
        with pdfplumber.open(io.BytesIO(get(source_url).content)) as pdf:
            add_usda_pfei(year, pdf, source_url)
            add_other_pfei(year, pdf, source_url)
        add_census_pfei(year)


FOMC_DATES = {
    2021: ("01-27", "03-17", "04-28", "06-16", "07-28", "09-22", "11-03", "12-15"),
    2022: ("01-26", "03-16", "05-04", "06-15", "07-27", "09-21", "11-02", "12-14"),
    2023: ("02-01", "03-22", "05-03", "06-14", "07-26", "09-20", "11-01", "12-13"),
    2024: ("01-31", "03-20", "05-01", "06-12", "07-31", "09-18", "11-07", "12-18"),
}


def add_fomc() -> None:
    source_url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    for year, values in FOMC_DATES.items():
        for value in values:
            date = dt.date.fromisoformat(f"{year}-{value}")
            add(date, "13:00", "FOMC_statement", "Federal_Reserve", source_url)
            add(date, "13:30", "FOMC_press_conference", "Federal_Reserve", source_url)


JOLTS_RELEASES = {
    2021: (
        "01-12",
        "02-09",
        "03-11",
        "04-06",
        "05-11",
        "06-08",
        "07-07",
        "08-09",
        "09-08",
        "10-12",
        "11-12",
        "12-08",
    ),
    2022: (
        "01-04",
        "02-01",
        "03-09",
        "03-29",
        "05-03",
        "06-01",
        "07-06",
        "08-02",
        "08-30",
        "10-04",
        "11-01",
        "11-30",
    ),
    2023: (
        "01-04",
        "02-01",
        "03-08",
        "04-04",
        "05-02",
        "05-31",
        "07-06",
        "08-01",
        "08-29",
        "10-03",
        "11-01",
        "12-05",
    ),
    2024: (
        "01-03",
        "01-30",
        "03-06",
        "04-02",
        "05-01",
        "06-04",
        "07-02",
        "07-30",
        "09-04",
        "10-01",
        "10-29",
        "12-03",
    ),
}


def add_jolts() -> None:
    for year, values in JOLTS_RELEASES.items():
        for value in values:
            date = dt.date.fromisoformat(f"{year}-{value}")
            source_url = f"https://www.bls.gov/news.release/archives/jolts_{date:%m%d%Y}.htm"
            add(date, "09:00", "BLS_JOLTS", "BLS", source_url)


ISM_SOURCES = {
    2021: (
        "https://web.archive.org/web/20210919231647id_/https://www.ismworld.org/"
        "supply-management-news-and-reports/reports/rob-report-calendar/",
        1,
    ),
    2022: (
        "https://web.archive.org/web/20221128214714id_/https://www.ismworld.org/"
        "supply-management-news-and-reports/reports/rob-report-calendar/",
        0,
    ),
    2023: (
        "https://web.archive.org/web/20230924002356id_/https://www.ismworld.org/"
        "supply-management-news-and-reports/reports/rob-report-calendar/",
        0,
    ),
    2024: (
        "https://web.archive.org/web/20240128015019id_/https://www.ismworld.org/"
        "supply-management-news-and-reports/reports/rob-report-calendar/",
        1,
    ),
}


def add_ism() -> None:
    month_by_name = {name: number for number, name in enumerate(month_calendar.month_name) if name}
    for year, (source_url, table_index) in ISM_SOURCES.items():
        tables = pd.read_html(io.StringIO(get(source_url).text))
        frame = tables[table_index]
        found = 0
        for _, row in frame.iterrows():
            month = month_by_name.get(compact(row["Month"]))
            if month is None:
                continue
            for column, event in (
                ("Manufacturing", "ISM_Manufacturing_PMI"),
                ("Services", "ISM_Services_PMI"),
            ):
                day = first_day(row[column])
                if day is None:
                    raise RuntimeError(f"Missing {year} ISM {column} date for month {month}")
                add(
                    dt.date(year, month, day),
                    "09:00",
                    event,
                    "ISM",
                    source_url,
                    archive_asof(source_url),
                )
                found += 1
        if found != 24:
            raise RuntimeError(f"Unexpected {year} ISM count: {found}")


SP_SOURCES = {
    2021: "https://web.archive.org/web/20210607095255id_/https://www.markiteconomics.com/Public/Home/PDF/UK_Rel_Dates",
    2022: "https://web.archive.org/web/20220722035105id_/https://www.pmi.spglobal.com/Public/Home/PDF/UK_Rel_Dates",
    2023: "https://web.archive.org/web/20230710052720id_/https://www.pmi.spglobal.com/Public/Home/PDF/UK_Rel_Dates",
    2024: "https://web.archive.org/web/20240615124118id_/https://www.pmi.spglobal.com/Public/Home/PDF/UK_Rel_Dates",
    2025: "https://web.archive.org/web/20250602162444id_/https://www.pmi.spglobal.com/Public/Home/PDF/UK_Rel_Dates",
}


def sp_rows(source_url: str) -> dict[str, list[tuple[int, int]]]:
    with pdfplumber.open(io.BytesIO(get(source_url).content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    prefixes = {
        r"US PMI\US\COM\OB\F": "flash",
        r"US PMI\US\MAN\ME\HE": "manufacturing",
        r"US PMI\US\SER\HE": "services",
    }
    output: dict[str, list[tuple[int, int]]] = {}
    month_numbers = {name: number for number, name in enumerate(month_calendar.month_abbr) if name}
    for line in text.splitlines():
        for prefix, key in prefixes.items():
            if not line.startswith(prefix):
                continue
            pairs = re.findall(r"(\d{1,2}) ([A-Z][a-z]{2}) \d{2}:\d{2}", line)
            output[key] = [(month_numbers[month], int(day)) for day, month in pairs]
    if set(output) != {"flash", "manufacturing", "services"}:
        raise RuntimeError(f"S&P US PMI rows not found in {source_url}")
    if any(len(values) != 12 for values in output.values()):
        raise RuntimeError(f"Unexpected S&P US PMI row length in {source_url}")
    return output


def add_sp_global() -> None:
    rows = {year: sp_rows(source_url) for year, source_url in SP_SOURCES.items()}
    for year in YEARS:
        source_url = SP_SOURCES[year]
        source_asof = archive_asof(source_url)
        for key, event in (
            ("manufacturing", "SP_Global_US_Manufacturing_PMI"),
            ("services", "SP_Global_US_Services_PMI"),
        ):
            for month, day in rows[year][key]:
                add(
                    dt.date(year, month, day),
                    "08:45",
                    event,
                    "SP_Global",
                    source_url,
                    source_asof,
                )

        # Each annual calendar starts with the prior December flash and then
        # lists January-November.  The following year's first cell supplies the
        # target year's December flash.
        for month, day in rows[year]["flash"][1:]:
            add(
                dt.date(year, month, day),
                "08:45",
                "SP_Global_US_Flash_PMI",
                "SP_Global",
                source_url,
                source_asof,
            )
        next_url = SP_SOURCES[year + 1]
        december_month, december_day = rows[year + 1]["flash"][0]
        if december_month != 12:
            raise RuntimeError(f"S&P following-year row lacks December for {year}")
        add(
            dt.date(year, 12, december_day),
            "08:45",
            "SP_Global_US_Flash_PMI",
            "SP_Global",
            next_url,
            archive_asof(next_url),
        )


def add_conference_board() -> None:
    endpoint = "https://www.conference-board.org/data/calendar/events.json.cfm"
    eastern = ZoneInfo("America/New_York")
    for year in YEARS:
        start = int(dt.datetime(year, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
        end = int(dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
        response = get(
            endpoint,
            params={
                "from": start,
                "to": end,
                "browser_timezone": "America/New_York",
            },
        )
        found = 0
        for record in response.json()["result"]:
            title = str(record["title"])
            if title.startswith("US: Consumer Confidence Index"):
                event = "Conference_Board_Consumer_Confidence"
            elif title.startswith("US: Leading Index"):
                event = "Conference_Board_LEI"
            else:
                continue
            instant = dt.datetime.fromtimestamp(int(record["start"]) / 1000, tz=dt.UTC).astimezone(
                eastern
            )
            if instant.hour != 10 or instant.minute != 0:
                raise RuntimeError(f"Unexpected Conference Board time: {instant}")
            add(
                instant.date(),
                "09:00",
                event,
                "Conference_Board",
                response.url,
            )
            found += 1
        if found != 24:
            raise RuntimeError(f"Unexpected {year} Conference Board count: {found}")


def add_michigan() -> None:
    source_url = "https://data.sca.isr.umich.edu/fetchdoc.php?docid=75443"
    with pdfplumber.open(io.BytesIO(get(source_url).content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    pattern = re.compile(
        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
        r"(2021|2022|2023|2024) (\d{1,2}/\d{1,2}/\d{4}) "
        r"(\d{1,2}/\d{1,2}/\d{4})$"
    )
    found = 0
    for line in text.splitlines():
        match = pattern.match(compact(line))
        if not match:
            continue
        for event, value in (
            ("University_of_Michigan_Consumer_Sentiment_preliminary", match.group(3)),
            ("University_of_Michigan_Consumer_Sentiment_final", match.group(4)),
        ):
            date = dt.datetime.strptime(value, "%m/%d/%Y").date()
            add(date, "09:00", event, "University_of_Michigan", source_url)
            found += 1
    if found != 96:
        raise RuntimeError(f"Unexpected Michigan release count: {found}")


NAR_RELEASES = {
    2021: (
        "01-22",
        "02-19",
        "03-22",
        "04-22",
        "05-21",
        "06-22",
        "07-22",
        "08-23",
        "09-22",
        "10-21",
        "11-22",
        "12-22",
    ),
    2022: (
        "01-20",
        "02-18",
        "03-18",
        "04-20",
        "05-19",
        "06-21",
        "07-20",
        "08-18",
        "09-21",
        "10-20",
        "11-18",
        "12-21",
    ),
    2023: (
        "01-20",
        "02-21",
        "03-21",
        "04-20",
        "05-18",
        "06-22",
        "07-20",
        "08-22",
        "09-21",
        "10-19",
        "11-21",
        "12-20",
    ),
    2024: (
        "01-19",
        "02-22",
        "03-21",
        "04-18",
        "05-22",
        "06-21",
        "07-23",
        "08-22",
        "09-19",
        "10-23",
        "11-21",
        "12-19",
    ),
}
NAR_SOURCES = {
    2021: "https://www.nar.realtor/research-and-statistics/housing-statistics/existing-home-sales",
    2022: "https://www.globenewswire.com/news-release/2021/10/14/2314446/0/en/NAR-Releases-Its-2022-Statistical-Forecast-News-Release-Schedule.html",
    2023: "https://www.globenewswire.com/news-release/2022/10/26/2542020/0/en/NAR-Releases-2023-Statistical-and-Forecast-News-Release-Schedule.html",
    2024: "https://www.globenewswire.com/en/news-release/2023/11/02/2772362/0/en/NAR-Releases-2024-Statistical-and-Quarterly-Economic-Forecast-News-Release-Schedule.html",
}


def add_nar() -> None:
    for year, values in NAR_RELEASES.items():
        for value in values:
            add(
                dt.date.fromisoformat(f"{year}-{value}"),
                "09:00",
                "NAR_Existing_Home_Sales",
                "NAR",
                NAR_SOURCES[year],
            )


def validate() -> None:
    if not EVENTS:
        raise RuntimeError("No calendar events were built")
    if len(EVENTS) != len(set(EVENTS)):
        raise RuntimeError("Exact duplicate source rows found")
    for event in EVENTS:
        date = dt.date.fromisoformat(event.date)
        time = dt.time.fromisoformat(event.time_ct)
        if date.year not in YEARS:
            raise RuntimeError(f"Out-of-sample date in calendar: {event}")
        if not (dt.time(8, 45) <= time <= dt.time(14, 45)):
            raise RuntimeError(f"Out-of-window time in calendar: {event}")
        if not event.source_url.startswith("https://"):
            raise RuntimeError(f"Non-HTTPS source in calendar: {event}")
    by_year = pd.Series([event.date[:4] for event in EVENTS]).value_counts()
    if set(map(int, by_year.index)) != set(YEARS):
        raise RuntimeError(f"Unexpected calendar years: {by_year.to_dict()}")


def write() -> None:
    header = (
        "# macro_events calendar v2 - Q-LIR Gate II release-window exclusions\n"
        "# version: 2\n"
        "# compiled: 2026-08-13\n"
        "# coverage: complete for the frozen 2021-01-01 .. 2024-12-31 source taxonomy\n"
        "# event-time timezone: America/Chicago (CT, DST-aware source conversion)\n"
        "# inclusion: all PFEI releases announced inside 08:45..14:45 CT plus the\n"
        "#   frozen JOLTS, FOMC, ISM, S&P Global, Conference Board, University of\n"
        "#   Michigan, and NAR benchmark families\n"
        "# exclusion: symmetric inclusive +/-10 minutes on the dated event only\n"
        "# row policy: preserve coincident source rows; deduplicate only the mask timestamp\n"
        "# format: date,time_ct,event,source,source_url,source_asof_utc\n"
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        handle.write(header)
        writer = csv.DictWriter(handle, fieldnames=list(asdict(EVENTS[0])))
        writer.writeheader()
        for event in sorted(EVENTS, key=lambda value: tuple(asdict(value).values())):
            writer.writerow(asdict(event))


def main() -> int:
    add_pfei()
    add_jolts()
    add_fomc()
    add_ism()
    add_sp_global()
    add_conference_board()
    add_michigan()
    add_nar()
    validate()
    write()
    unique_timestamps = len({(event.date, event.time_ct) for event in EVENTS})
    print(f"wrote {len(EVENTS):,} source rows to {OUTPUT}")
    print(f"unique exclusion timestamps: {unique_timestamps:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
