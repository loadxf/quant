"""Mark-to-market equity cross-check (M10.e)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from quantlab.errors import QuantLabError
from quantlab.prop.equity_check import check_equity_curve, load_equity_csv
from quantlab.prop.registry import load_firm
from quantlab.schema.equity import EquityCurve

UTC = dt.UTC


def _curve(marks: list[tuple[str, float]]) -> EquityCurve:
    stamps = pd.DatetimeIndex([pd.Timestamp(t, tz="UTC") for t, _ in marks])
    return EquityCurve.from_series(pd.Series([v for _, v in marks], index=stamps))


class TestTrailingFromMarks:
    def test_intraday_dip_breaches_where_closes_hide_it(self) -> None:
        # Topstep 50K: EOD-ratcheted trailing $2,000 below the HWM, tested
        # in real time. Closes stay healthy; one intra-session mark dips
        # through the floor — only mark-to-market sees it.
        firm = load_firm("topstep_50k")
        marks = [
            ("2026-03-02 15:00", 50_000.0),
            ("2026-03-02 20:00", 50_500.0),  # session close (pre-17:00 CT cutoff spans)
            ("2026-03-03 15:00", 50_400.0),
            ("2026-03-03 18:00", 48_400.0),  # dip: 50_500 hwm - 2_000 = 48_500 floor
            ("2026-03-03 20:00", 50_200.0),  # recovers by the close
        ]
        check = check_equity_curve(_curve(marks), firm)
        assert check.first_breach is not None
        assert check.first_breach.rule.startswith("trailing_drawdown")

    def test_healthy_curve_clean(self) -> None:
        firm = load_firm("topstep_50k")
        marks = [(f"2026-03-{2 + d:02d} 15:00", 50_000.0 + 100 * d) for d in range(10)]
        check = check_equity_curve(_curve(marks), firm)
        assert check.first_breach is None

    def test_eod_ratchet_ignores_intraday_peak(self) -> None:
        # Intraday spike to 51k must NOT raise an EOD-ratcheted floor: a
        # later dip to 48.6k (above the close-based floor 48.5k) survives.
        firm = load_firm("topstep_50k")
        marks = [
            ("2026-03-02 15:00", 50_000.0),
            ("2026-03-02 16:00", 51_000.0),  # intraday peak, not a close
            ("2026-03-02 20:00", 50_000.0),  # close: hwm stays 50_000
            ("2026-03-03 15:00", 48_600.0),  # 50_000 - 2_000 = 48_000 floor: safe
        ]
        check = check_equity_curve(_curve(marks), firm)
        assert check.first_breach is None

    def test_daily_loss_crossing_recorded(self) -> None:
        # Apex 4.0 carries a $1,000 lockout DLL: a -$1,100 intra-session
        # swing records a crossing without failing the phase.
        firm = load_firm("apex40_50k_eod")
        marks = [
            ("2026-03-02 15:00", 50_000.0),
            ("2026-03-02 20:00", 50_050.0),
            ("2026-03-03 15:00", 48_950.0),  # -1,100 vs day open 50_050
            ("2026-03-03 20:00", 49_900.0),
        ]
        check = check_equity_curve(_curve(marks), firm)
        assert len(check.daily_loss_hits) == 1
        assert check.first_breach is None  # lockout, not fail

    def test_daily_resolution_warns(self) -> None:
        firm = load_firm("topstep_50k")
        marks = [(f"2026-03-{2 + d:02d} 20:00", 50_000.0 + 10 * d) for d in range(8)]
        check = check_equity_curve(_curve(marks), firm)
        assert not check.intraday_marks
        assert any("daily-sampled" in w for w in check.warnings)

    def test_unknown_phase_raises(self) -> None:
        with pytest.raises(QuantLabError, match="unknown phase"):
            check_equity_curve(
                _curve([("2026-03-02 15:00", 50_000.0)]),
                load_firm("topstep_50k"),
                phase_name="nope",
            )

    def test_json_serializable(self) -> None:
        import json

        firm = load_firm("topstep_50k")
        marks = [(f"2026-03-{2 + d:02d} 15:00", 50_000.0 - 700 * d) for d in range(6)]
        check = check_equity_curve(_curve(marks), firm)
        assert check.first_breach is not None  # steady bleed through the floor
        json.dumps(check.to_json_dict())


class TestCsvRoundTrip:
    def test_load_written_csv(self, tmp_path) -> None:
        curve = _curve([("2026-03-02 15:00", 50_000.0), ("2026-03-03 15:00", 50_500.0)])
        path = tmp_path / "eq.equity.csv"
        curve.to_series().rename("equity").to_csv(path, index_label="datetime")
        loaded = load_equity_csv(path)
        assert [p.equity for p in loaded.points] == [50_000.0, 50_500.0]

    def test_bad_csv_raises(self, tmp_path) -> None:
        path = tmp_path / "bad.csv"
        path.write_text("a,b\n1,2\n")
        with pytest.raises(QuantLabError, match="datetime,equity"):
            load_equity_csv(path)
