"""End-to-end acquisition integration (round 5): the EXACT documented
symbology response shapes composed into a ContractMap, bound to a
locally encoded DBN file with date-aware raw identity, and attested in
the anchored ledger — one pipeline, no incompatible interfaces."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest
from qlir import QlirError
from qlir.acquire import (
    build_acquisition_record,
    compose_contract_map,
    load_acquired_file,
)
from qlir.manifest import append_acquisition, load_ledger

NS = 10**9
TS0 = int(pd.Timestamp("2022-03-01 14:30:00", tz="UTC").value)

# Exact API envelopes (with the "result" wrapper and empty leftovers).
STEP_ONE_RESPONSE = {
    "result": {
        "ES.v.0": [
            {"d0": "2022-01-01", "d1": "2022-03-14", "s": "4916"},
            {"d0": "2022-03-14", "d1": "2022-06-13", "s": "5203"},
        ]
    },
    "partial": [],
    "not_found": [],
}
STEP_TWO_RESPONSE = {
    "result": {
        "4916": [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"}],
        "5203": [{"d0": "2022-03-14", "d1": "2022-06-13", "s": "ESM2"}],
    },
    "partial": [],
    "not_found": [],
}


def write_trades_dbn(path, ts_base: int, instrument_id: int = 4916) -> None:
    import databento_dbn as dbn

    fixed = dbn.FIXED_PRICE_SCALE
    meta = dbn.Metadata(
        dataset="GLBX.MDP3",
        start=ts_base,
        end=ts_base + 60 * NS,
        stype_in=dbn.SType.CONTINUOUS,
        stype_out=dbn.SType.INSTRUMENT_ID,
        schema=dbn.Schema.TRADES,
        symbols=["ES.v.0"],
    )
    records = [
        dbn.TradeMsg(
            publisher_id=1,
            instrument_id=instrument_id,
            ts_event=ts_base + (i + 1) * NS,
            price=int((4500.25 + 0.25 * i) * fixed),
            size=4,
            action=dbn.Action.TRADE,
            side=dbn.Side.BID,
            depth=0,
            ts_recv=ts_base + (i + 1) * NS + 500,
            sequence=i + 1,
        )
        for i in range(3)
    ]
    path.write_bytes(bytes(meta.encode()) + b"".join(bytes(record) for record in records))


class TestComposition:
    def test_exact_envelopes_compose(self) -> None:
        contract_map = compose_contract_map(STEP_ONE_RESPONSE, STEP_TWO_RESPONSE)
        assert contract_map.raw_for(4916, dt.date(2022, 3, 1)) == "ESH2"
        assert contract_map.raw_for(5203, dt.date(2022, 4, 1)) == "ESM2"

    def test_bare_result_dicts_also_accepted(self) -> None:
        contract_map = compose_contract_map(
            STEP_ONE_RESPONSE["result"], STEP_TWO_RESPONSE["result"]
        )
        assert contract_map.raw_for(4916, dt.date(2022, 2, 1)) == "ESH2"

    def test_not_found_leftovers_refused(self) -> None:
        response = dict(STEP_ONE_RESPONSE, not_found=["RTY.v.0"])
        with pytest.raises(QlirError, match="not_found"):
            compose_contract_map(response, STEP_TWO_RESPONSE)

    def test_partial_leftovers_refused(self) -> None:
        response = dict(STEP_ONE_RESPONSE, partial=["ES.v.0"])
        with pytest.raises(QlirError, match="partial"):
            compose_contract_map(response, STEP_TWO_RESPONSE)


class TestEndToEnd:
    def test_dbn_bound_with_date_aware_identity(self, tmp_path) -> None:
        pytest.importorskip("databento")
        contract_map = compose_contract_map(STEP_ONE_RESPONSE, STEP_TWO_RESPONSE)
        path = tmp_path / "2022-03-01.dbn"
        write_trades_dbn(path, TS0, instrument_id=4916)
        frame = load_acquired_file(path, "trades", contract_map)
        assert list(frame["raw_symbol"].unique()) == ["ESH2"]
        assert list(frame["symbol"].unique()) == ["ES.v.0"]

    def test_same_id_other_side_of_roll_gets_other_raw(self, tmp_path) -> None:
        """Date-awareness end-to-end: a file dated after the roll binds
        the SAME pipeline to the next contract."""
        pytest.importorskip("databento")
        contract_map = compose_contract_map(STEP_ONE_RESPONSE, STEP_TWO_RESPONSE)
        ts_april = int(pd.Timestamp("2022-04-01 14:30:00", tz="UTC").value)
        path = tmp_path / "2022-04-01.dbn"
        write_trades_dbn(path, ts_april, instrument_id=5203)
        frame = load_acquired_file(path, "trades", contract_map)
        assert list(frame["raw_symbol"].unique()) == ["ESM2"]

    def test_file_outside_mapping_coverage_fails(self, tmp_path) -> None:
        pytest.importorskip("databento")
        contract_map = compose_contract_map(STEP_ONE_RESPONSE, STEP_TWO_RESPONSE)
        ts_2023 = int(pd.Timestamp("2023-03-01 14:30:00", tz="UTC").value)
        path = tmp_path / "2023-03-01.dbn"
        write_trades_dbn(path, ts_2023, instrument_id=4916)
        with pytest.raises(QlirError, match=r"no instruments active|outside"):
            load_acquired_file(path, "trades", contract_map)

    def test_ledger_attestation_round_trip(self, tmp_path) -> None:
        """ContractMap → typed ledger record → append → verified read."""
        contract_map = compose_contract_map(STEP_ONE_RESPONSE, STEP_TWO_RESPONSE)
        record = build_acquisition_record(
            dataset="GLBX.MDP3",
            schema="trades",
            requested_symbols=["ES.v.0"],
            contract_map=contract_map,
            start_utc="2022-01-01T00:00:00Z",
            end_utc="2022-06-13T00:00:00Z",
            request_cost_usd=12.34,
            record_count=3,
            billable_size_bytes=1024,
            client_version="databento 0.83.0",
            dataset_conditions={"2022-03-01": "available"},
            derivation_code_commit="8aa8ec5",
            split="development",
        )
        ledger = tmp_path / "acquisition.jsonl"
        append_acquisition(ledger, record)
        loaded = load_ledger(ledger)
        assert loaded[0]["resolved_contracts"]["ES.v.0"][0]["raw_symbol"] == "ESH2"
        assert loaded[0]["stype_out"] == "instrument_id"
