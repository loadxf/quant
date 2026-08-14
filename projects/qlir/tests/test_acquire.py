"""Round-6 acquisition binding: ONE spec across symbology envelopes, DBN
metadata, per-record identity, file attestations, and the ledger receipt
— Sol's XNAS-through-GLBX and unrelated-receipt reproductions refused."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest
from qlir import QlirError
from qlir.acquire import (
    build_verified_receipt,
    compose_contract_map,
    load_acquired_file,
)
from qlir.manifest import append_acquisition, load_ledger
from qlir.spec import AcquisitionSpec
from qlir.store import RawStore

NS = 10**9
UTC = dt.UTC

SPEC = AcquisitionSpec(
    dataset="GLBX.MDP3",
    schema="trades",
    symbols=("ES.v.0",),
    start_utc=dt.datetime(2022, 1, 1, tzinfo=UTC),
    end_utc=dt.datetime(2022, 6, 13, tzinfo=UTC),
)

STEP_ONE_RESPONSE = {
    "result": {
        "ES.v.0": [
            {"d0": "2022-01-01", "d1": "2022-03-14", "s": "4916"},
            {"d0": "2022-03-14", "d1": "2022-06-13", "s": "5203"},
        ]
    },
    "symbols": ["ES.v.0"],
    "stype_in": "continuous",
    "stype_out": "instrument_id",
    "start_date": "2022-01-01",
    "end_date": "2022-06-13",
    "dataset": "GLBX.MDP3",
    "partial": [],
    "not_found": [],
}
STEP_TWO_RESPONSE = {
    "result": {
        "4916": [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"}],
        "5203": [{"d0": "2022-03-14", "d1": "2022-06-13", "s": "ESM2"}],
    },
    "symbols": ["4916", "5203"],
    "stype_in": "instrument_id",
    "stype_out": "raw_symbol",
    "start_date": "2022-01-01",
    "end_date": "2022-06-13",
    "partial": [],
    "not_found": [],
}


def write_dbn(
    path,
    *,
    dataset: str = "GLBX.MDP3",
    symbols: list[str] | None = None,
    instrument_id: int = 4916,
    ts_base: int | None = None,
    n_records: int = 3,
    start: int | None = None,
    end: int | None = None,
) -> None:
    import databento_dbn as dbn

    fixed = dbn.FIXED_PRICE_SCALE
    if ts_base is None:
        ts_base = int(pd.Timestamp("2022-03-01 14:30:00", tz="UTC").value)
    meta = dbn.Metadata(
        dataset=dataset,
        start=start if start is not None else ts_base,
        end=end if end is not None else ts_base + 3600 * NS,
        stype_in=dbn.SType.CONTINUOUS,
        stype_out=dbn.SType.INSTRUMENT_ID,
        schema=dbn.Schema.TRADES,
        symbols=symbols or ["ES.v.0"],
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
        for i in range(n_records)
    ]
    path.write_bytes(bytes(meta.encode()) + b"".join(bytes(record) for record in records))


def contract_map():
    return compose_contract_map(SPEC, STEP_ONE_RESPONSE, STEP_TWO_RESPONSE)


class TestEnvelopeBinding:
    def test_exact_envelopes_compose(self) -> None:
        cmap = contract_map()
        assert cmap.raw_for(4916, dt.date(2022, 3, 1)) == "ESH2"
        assert cmap.raw_for(5203, dt.date(2022, 4, 1)) == "ESM2"

    def test_bare_payload_refused_without_flag(self) -> None:
        with pytest.raises(QlirError, match="missing required fields"):
            compose_contract_map(SPEC, STEP_ONE_RESPONSE["result"], STEP_TWO_RESPONSE["result"])

    def test_bare_payload_allowed_only_explicitly(self) -> None:
        cmap = compose_contract_map(
            SPEC,
            STEP_ONE_RESPONSE["result"],
            STEP_TWO_RESPONSE["result"],
            allow_unverified=True,
        )
        assert cmap.raw_for(4916, dt.date(2022, 2, 1)) == "ESH2"

    def test_result_only_wrapper_refused(self) -> None:
        """Round-7 finding 4: {'result': ...} alone bypassed the
        unverified gate. Every documented envelope field is required."""
        with pytest.raises(QlirError, match="missing required fields"):
            compose_contract_map(
                SPEC,
                {"result": STEP_ONE_RESPONSE["result"]},
                {"result": STEP_TWO_RESPONSE["result"]},
            )

    def test_step_two_symbols_must_equal_step_one_ids(self) -> None:
        response = dict(STEP_TWO_RESPONSE, symbols=["4916"])  # missing 5203
        with pytest.raises(QlirError, match="expected set"):
            compose_contract_map(SPEC, STEP_ONE_RESPONSE, response)

    def test_envelope_symbol_mismatch_refused(self) -> None:
        response = dict(STEP_ONE_RESPONSE, symbols=["NQ.v.0"])
        with pytest.raises(QlirError, match="symbols"):
            compose_contract_map(SPEC, response, STEP_TWO_RESPONSE)

    def test_envelope_date_mismatch_refused(self) -> None:
        response = dict(STEP_ONE_RESPONSE, end_date="2024-12-31")
        with pytest.raises(QlirError, match="end_date"):
            compose_contract_map(SPEC, response, STEP_TWO_RESPONSE)

    def test_not_found_leftovers_refused(self) -> None:
        response = dict(STEP_ONE_RESPONSE, not_found=["RTY.v.0"])
        with pytest.raises(QlirError, match="not_found"):
            compose_contract_map(SPEC, response, STEP_TWO_RESPONSE)

    def test_resolved_symbols_must_equal_spec(self) -> None:
        spec = AcquisitionSpec(
            dataset="GLBX.MDP3",
            schema="trades",
            symbols=("ES.v.0", "NQ.v.0"),
            start_utc=SPEC.start_utc,
            end_utc=SPEC.end_utc,
        )
        response = dict(STEP_ONE_RESPONSE, symbols=["ES.v.0", "NQ.v.0"])
        with pytest.raises(QlirError, match="missing spec symbols"):
            compose_contract_map(spec, response, STEP_TWO_RESPONSE)

    def test_coverage_must_span_spec_range(self) -> None:
        spec = AcquisitionSpec(
            dataset="GLBX.MDP3",
            schema="trades",
            symbols=("ES.v.0",),
            start_utc=SPEC.start_utc,
            end_utc=dt.datetime(2023, 1, 1, tzinfo=UTC),  # beyond mapping
        )
        step_one = dict(STEP_ONE_RESPONSE, end_date="2023-01-01")
        step_two = dict(STEP_TWO_RESPONSE, end_date="2023-01-01")
        with pytest.raises(QlirError, match=r"short of the attested|coverage gap"):
            compose_contract_map(spec, step_one, step_two)


class TestDbnSpecBinding:
    def test_sols_xnas_reproduction_refused(self, tmp_path) -> None:
        """Round-6 finding 2: an XNAS.ITCH / NQ.v.0 file decoded cleanly
        through the GLBX/ES contract map. The spec binding refuses it."""
        pytest.importorskip("databento")
        path = tmp_path / "2022-03-01.dbn"
        write_dbn(path, dataset="XNAS.ITCH", symbols=["NQ.v.0"], instrument_id=4916)
        with pytest.raises(QlirError, match=r"dataset 'XNAS\.ITCH'"):
            load_acquired_file(path, SPEC, contract_map())

    def test_symbols_outside_spec_refused(self, tmp_path) -> None:
        pytest.importorskip("databento")
        path = tmp_path / "2022-03-01.dbn"
        write_dbn(path, symbols=["NQ.v.0"])
        with pytest.raises(QlirError, match="not in the acquisition"):
            load_acquired_file(path, SPEC, contract_map())

    def test_metadata_interval_outside_spec_refused(self, tmp_path) -> None:
        pytest.importorskip("databento")
        path = tmp_path / "2021-06-01.dbn"
        ts_2021 = int(pd.Timestamp("2021-06-01 14:30:00", tz="UTC").value)
        write_dbn(path, ts_base=ts_2021)
        with pytest.raises(QlirError, match="precedes the spec range"):
            load_acquired_file(path, SPEC, contract_map())

    def test_publisher_id_preserved(self, tmp_path) -> None:
        pytest.importorskip("databento")
        path = tmp_path / "2022-03-01.dbn"
        write_dbn(path)
        frame = load_acquired_file(path, SPEC, contract_map())
        assert "publisher_id" in frame.columns
        assert list(frame["publisher_id"].unique()) == [1]

    def test_bound_identity_both_sides_of_roll(self, tmp_path) -> None:
        pytest.importorskip("databento")
        cmap = contract_map()
        march = tmp_path / "2022-03-01.dbn"
        write_dbn(march, instrument_id=4916)
        assert list(load_acquired_file(march, SPEC, cmap)["raw_symbol"].unique()) == ["ESH2"]
        april = tmp_path / "2022-04-01.dbn"
        ts_april = int(pd.Timestamp("2022-04-01 14:30:00", tz="UTC").value)
        write_dbn(april, instrument_id=5203, ts_base=ts_april)
        assert list(load_acquired_file(april, SPEC, cmap)["raw_symbol"].unique()) == ["ESM2"]

    def test_multi_symbol_file_gets_per_record_symbols(self, tmp_path) -> None:
        """'<multi>' eliminated: each record's requested symbol comes from
        the contract map by (instrument_id, event_date)."""
        pytest.importorskip("databento")
        import databento_dbn as dbn

        spec = AcquisitionSpec(
            dataset="GLBX.MDP3",
            schema="trades",
            symbols=("ES.v.0", "NQ.v.0"),
            start_utc=SPEC.start_utc,
            end_utc=SPEC.end_utc,
        )
        step_one = dict(
            STEP_ONE_RESPONSE,
            symbols=["ES.v.0", "NQ.v.0"],
            result={
                "ES.v.0": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "4916"}],
                "NQ.v.0": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "7777"}],
            },
        )
        step_two = dict(
            STEP_TWO_RESPONSE,
            result={
                "4916": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "ESH2"}],
                "7777": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "NQH2"}],
            },
            symbols=["4916", "7777"],
        )
        cmap = compose_contract_map(spec, step_one, step_two)
        fixed = dbn.FIXED_PRICE_SCALE
        ts0 = int(pd.Timestamp("2022-03-01 14:30:00", tz="UTC").value)
        meta = dbn.Metadata(
            dataset="GLBX.MDP3",
            start=ts0,
            end=ts0 + 3600 * NS,
            stype_in=dbn.SType.CONTINUOUS,
            stype_out=dbn.SType.INSTRUMENT_ID,
            schema=dbn.Schema.TRADES,
            symbols=["ES.v.0", "NQ.v.0"],
        )
        records = []
        for i, instrument_id in enumerate((4916, 7777)):
            records.append(
                dbn.TradeMsg(
                    publisher_id=1,
                    instrument_id=instrument_id,
                    ts_event=ts0 + (i + 1) * NS,
                    price=int(4500.25 * fixed),
                    size=4,
                    action=dbn.Action.TRADE,
                    side=dbn.Side.BID,
                    depth=0,
                    ts_recv=ts0 + (i + 1) * NS + 500,
                    sequence=i + 1,
                )
            )
        path = tmp_path / "2022-03-01.dbn"
        path.write_bytes(bytes(meta.encode()) + b"".join(bytes(r) for r in records))
        frame = load_acquired_file(path, spec, cmap)
        by_id = frame.set_index("instrument_id")
        assert by_id.loc[4916, "symbol"] == "ES.v.0"
        assert by_id.loc[7777, "symbol"] == "NQ.v.0"
        assert "<multi>" not in set(frame["symbol"])


class TestVerifiedReceipt:
    """Round-7 findings 1-2: receipts are DERIVED from decoded bytes and
    the server batch manifest — never asserted."""

    def _stored(self, tmp_path, payload_writer, date="2022-03-01"):
        root = tmp_path / "q_lir"
        store = RawStore(root)
        scratch = tmp_path / f"{date}.dbn"
        payload_writer(scratch)
        stored = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", date, scratch.read_bytes())
        return root, stored.relative_to(root).as_posix(), stored

    def _receipt(self, root, relpath, server_name, server_size, cmap, spec=SPEC):
        return build_verified_receipt(
            spec=spec,
            contract_map=cmap,
            data_root=root,
            stored_files=[(relpath, server_name)],
            server_manifest=[{"filename": server_name, "size_bytes": server_size}],
            request_cost_usd=12.34,
            billable_size_bytes=1024,
            client_version="databento 0.83.0",
            dataset_conditions={"2022-03-01": "available"},
            derivation_code_commit="57ba2c6",
            split="development",
        )

    def test_full_pipeline_derives_counts_and_reloads(self, tmp_path) -> None:
        pytest.importorskip("databento")
        root, relpath, stored = self._stored(tmp_path, lambda p: write_dbn(p, n_records=3))
        cmap = contract_map()
        record = self._receipt(
            root, relpath, "glbx-mdp3-20220301.trades.dbn.zst", stored.stat().st_size, cmap
        )
        assert record["record_count"] == 3  # DERIVED by decoding
        ledger = root / "manifests" / "acquisition.jsonl"
        append_acquisition(ledger, record, data_root=root)
        loaded = load_ledger(ledger)[0]
        assert loaded["files"][0]["record_count"] == 3
        assert loaded["server_manifest"][0]["filename"] == "glbx-mdp3-20220301.trades.dbn.zst"

    def test_sols_arbitrary_bytes_refused(self, tmp_path) -> None:
        """Round-7 finding 1: b'not dbn market data' with a claimed 777
        records was receipted. Counts now come from decoding — bytes
        that cannot decode cannot be attested."""
        pytest.importorskip("databento")
        root, relpath, stored = self._stored(
            tmp_path, lambda p: p.write_bytes(b"not dbn market data")
        )
        with pytest.raises(QlirError, match="not decodable as DBN"):
            self._receipt(root, relpath, "bogus.dbn.zst", stored.stat().st_size, contract_map())

    def test_sols_incomplete_acquisition_refused(self, tmp_path) -> None:
        """Round-7 finding 2: one ES file receipted as an ES+NQ
        acquisition. Derived symbol coverage refuses it."""
        pytest.importorskip("databento")
        spec = AcquisitionSpec(
            dataset="GLBX.MDP3",
            schema="trades",
            symbols=("ES.v.0", "NQ.v.0"),
            start_utc=SPEC.start_utc,
            end_utc=SPEC.end_utc,
        )
        step_one = dict(
            STEP_ONE_RESPONSE,
            symbols=["ES.v.0", "NQ.v.0"],
            result={
                "ES.v.0": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "4916"}],
                "NQ.v.0": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "7777"}],
            },
        )
        step_two = dict(
            STEP_TWO_RESPONSE,
            result={
                "4916": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "ESH2"}],
                "7777": [{"d0": "2022-01-01", "d1": "2022-06-13", "s": "NQH2"}],
            },
            symbols=["4916", "7777"],
        )
        cmap = compose_contract_map(spec, step_one, step_two)
        root = tmp_path / "q_lir"
        store = RawStore(root)
        scratch = tmp_path / "es-only.dbn"
        write_dbn(scratch, symbols=["ES.v.0", "NQ.v.0"], instrument_id=4916, n_records=1)
        stored = store.write_raw(
            "GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", scratch.read_bytes()
        )
        with pytest.raises(QlirError, match="no records for spec symbol"):
            build_verified_receipt(
                spec=spec,
                contract_map=cmap,
                data_root=root,
                stored_files=[(stored.relative_to(root).as_posix(), "batch-file-1.dbn.zst")],
                server_manifest=[
                    {"filename": "batch-file-1.dbn.zst", "size_bytes": stored.stat().st_size}
                ],
                request_cost_usd=1.0,
                billable_size_bytes=1,
                client_version="x",
                dataset_conditions={},
                derivation_code_commit="x",
                split="development",
            )

    def test_server_manifest_mismatch_refused(self, tmp_path) -> None:
        pytest.importorskip("databento")
        root, relpath, stored = self._stored(tmp_path, lambda p: write_dbn(p, n_records=3))
        with pytest.raises(QlirError, match="complete batch"):
            build_verified_receipt(
                spec=SPEC,
                contract_map=contract_map(),
                data_root=root,
                stored_files=[(relpath, "file-a.dbn.zst")],
                server_manifest=[
                    {"filename": "file-a.dbn.zst", "size_bytes": stored.stat().st_size},
                    {"filename": "file-b.dbn.zst", "size_bytes": 10},
                ],
                request_cost_usd=1.0,
                billable_size_bytes=1,
                client_version="x",
                dataset_conditions={},
                derivation_code_commit="x",
                split="development",
            )

    def test_server_size_mismatch_refused(self, tmp_path) -> None:
        pytest.importorskip("databento")
        root, relpath, stored = self._stored(tmp_path, lambda p: write_dbn(p, n_records=3))
        with pytest.raises(QlirError, match="does not match the server"):
            self._receipt(root, relpath, "f.dbn.zst", stored.stat().st_size + 1, contract_map())

    def test_out_of_range_record_refused(self, tmp_path) -> None:
        """Round-7 finding 5: metadata declaring [15:00, 16:00) with a
        record at 14:30 was accepted. The loader now enforces the
        half-open bound on ts_recv."""
        pytest.importorskip("databento")
        ts_1500 = int(pd.Timestamp("2022-03-01 15:00:00", tz="UTC").value)
        ts_1430 = int(pd.Timestamp("2022-03-01 14:30:00", tz="UTC").value)
        path = tmp_path / "2022-03-01.dbn"
        write_dbn(
            path,
            ts_base=ts_1430 - NS,  # record lands at 14:30
            n_records=1,
            start=ts_1500,
            end=ts_1500 + 3600 * NS,
        )
        with pytest.raises(QlirError, match="outside the DBN metadata"):
            load_acquired_file(path, SPEC, contract_map())
