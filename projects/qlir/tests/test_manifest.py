"""Hash-chained, ANCHORED, append-only acquisition ledger (round 5):
date-derived locked-period enforcement, supported-stype validation,
typed resolved_contracts, chain integrity, TAIL-truncation detection,
read-time revalidation, true O_APPEND writes, and writer locking."""

from __future__ import annotations

import json

import pytest
from qlir import QlirError
from qlir.manifest import (
    GENESIS,
    _anchor_path,
    _link_hash,
    append_acquisition,
    load_ledger,
    split_for_range,
    validate_record,
    verify_ledger,
)


def valid_record(**overrides):
    record = {
        "dataset": "GLBX.MDP3",
        "schema": "trades",
        "requested_symbols": ["ES.v.0", "NQ.v.0"],
        "stype_in": "continuous",
        "stype_out": "instrument_id",  # continuous resolves to id ONLY
        "resolved_contracts": {
            "ES.v.0": [
                {
                    "instrument_id": 4916,
                    "raw_symbol": "ESH2",
                    "d0": "2022-01-01",
                    "d1": "2022-03-14",
                }
            ]
        },
        "start_utc": "2022-01-01T00:00:00Z",
        "end_utc": "2023-01-01T00:00:00Z",
        "request_cost_usd": 123.45,
        "record_count": 1_000_000,
        "billable_size_bytes": 48_000_000,
        "client_version": "databento 0.83.0",
        "file_hashes": "manifests/files.sha256",
        "dataset_conditions": {"2022-01-03": "available"},
        "derivation_code_commit": "de30ea2",
        "split": "development",
    }
    record.update(overrides)
    return record


class TestSymbologyValidation:
    """Round-5 defect 3: the ledger must never attest to the invalid
    direct pairing or an untyped resolved_contracts."""

    def test_sols_reproduction_now_refused(self) -> None:
        """stype continuous->raw_symbol + resolved_contracts='garbage'
        was ACCEPTED in round 4; both must now raise."""
        record = valid_record(stype_out="raw_symbol", resolved_contracts="garbage")
        with pytest.raises(QlirError, match="unsupported symbology pair"):
            validate_record(record)

    def test_untyped_resolved_contracts_refused(self) -> None:
        with pytest.raises(QlirError, match="resolved_contracts"):
            validate_record(valid_record(resolved_contracts="garbage"))

    def test_serialized_surrogate_raw_symbol_refused(self) -> None:
        bad = {
            "ES.v.0": [
                {
                    "instrument_id": 4916,
                    "raw_symbol": "[{'d0': '2022-01-01', 's': 'ESH2'}]",
                    "d0": "2022-01-01",
                    "d1": "2022-03-14",
                }
            ]
        }
        with pytest.raises(QlirError, match="serialized structure"):
            validate_record(valid_record(resolved_contracts=bad))

    def test_supported_pairs_accepted(self) -> None:
        validate_record(valid_record(stype_in="instrument_id", stype_out="raw_symbol"))


class TestTailCompleteness:
    """Round-5 defect 3: an unanchored chain cannot detect tail
    truncation — the anchor makes it detectable."""

    def test_tail_line_removal_detected(self) -> None:
        """Sol's reproduction: append two, remove the last line —
        load_ledger returned one record cleanly. Now it must raise."""
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp())
        path = tmp / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        append_acquisition(path, valid_record(schema="tbbo"))
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(lines[0] + "\n", encoding="utf-8")
        with pytest.raises(QlirError, match="tail"):
            load_ledger(path)

    def test_whole_ledger_deletion_detected(self, tmp_path) -> None:
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        path.unlink()
        with pytest.raises(QlirError, match="tail truncation or ledger deletion"):
            load_ledger(path)

    def test_anchor_deletion_detected(self, tmp_path) -> None:
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        _anchor_path(path).unlink()
        with pytest.raises(QlirError, match="no anchor"):
            load_ledger(path)

    def test_read_time_revalidation_catches_now_invalid_records(self, tmp_path) -> None:
        """A chained record that no longer passes validate_record fails
        the READ — the chain alone is not sufficient attestation."""
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        raw = path.read_text(encoding="utf-8")
        tampered = raw.replace('"instrument_id"', '"unknown_field"')
        path.write_text(tampered, encoding="utf-8")
        with pytest.raises(QlirError):
            load_ledger(path)


class TestDateDerivedLock:
    """Round-4 blocker 2b: the lock comes from parsed UTC dates — a
    label can never bypass it."""

    def test_locked_period_refused_regardless_of_label(self) -> None:
        record = valid_record(
            start_utc="2025-01-01T00:00:00Z",
            end_utc="2027-01-01T00:00:00Z",
            split="development",  # the exact bypass Sol demonstrated
        )
        with pytest.raises(QlirError, match="LOCKED PERIOD"):
            validate_record(record)

    def test_range_touching_2025_refused(self) -> None:
        record = valid_record(
            start_utc="2024-06-01T00:00:00Z",
            end_utc="2025-01-01T00:00:01Z",
            split="validation",
        )
        with pytest.raises(QlirError, match="LOCKED PERIOD"):
            validate_record(record)

    def test_label_must_match_dates(self) -> None:
        record = valid_record(split="validation")  # dates are 2022: development
        with pytest.raises(QlirError, match="contradicts"):
            validate_record(record)

    def test_dev_val_spanning_range_refused(self) -> None:
        record = valid_record(
            start_utc="2023-06-01T00:00:00Z",
            end_utc="2024-06-01T00:00:00Z",
            split="development",
        )
        with pytest.raises(QlirError, match="crosses 2024-01-01"):
            validate_record(record)

    def test_validation_range_accepted(self) -> None:
        validate_record(
            valid_record(
                start_utc="2024-01-01T00:00:00Z",
                end_utc="2025-01-01T00:00:00Z",
                split="validation",
            )
        )

    def test_naive_datetime_refused(self) -> None:
        with pytest.raises(QlirError, match="timezone-aware"):
            validate_record(valid_record(start_utc="2022-01-01T00:00:00"))

    def test_split_for_range_classifies(self) -> None:
        import datetime as dt

        utc = dt.UTC
        assert (
            split_for_range(
                dt.datetime(2022, 1, 1, tzinfo=utc), dt.datetime(2023, 1, 1, tzinfo=utc)
            )
            == "development"
        )
        assert (
            split_for_range(
                dt.datetime(2024, 2, 1, tzinfo=utc), dt.datetime(2024, 9, 1, tzinfo=utc)
            )
            == "validation"
        )


class TestValidation:
    def test_valid_record_passes(self) -> None:
        validate_record(valid_record())

    @pytest.mark.parametrize("missing", ["dataset", "request_cost_usd", "split", "file_hashes"])
    def test_missing_field_rejected(self, missing: str) -> None:
        record = valid_record()
        del record[missing]
        with pytest.raises(QlirError, match="missing required"):
            validate_record(record)

    def test_empty_symbols_rejected(self) -> None:
        with pytest.raises(QlirError, match="requested_symbols"):
            validate_record(valid_record(requested_symbols=[]))


class TestHashChain:
    def test_chain_links_and_loads(self, tmp_path) -> None:
        path = tmp_path / "acquisition.jsonl"
        first = valid_record()
        second = valid_record(schema="tbbo")
        append_acquisition(path, first)
        append_acquisition(path, second)
        records = load_ledger(path)
        assert records == [first, second]
        links = verify_ledger(path)
        assert links[0]["prev_hash"] == GENESIS
        assert links[1]["prev_hash"] == links[0]["record_hash"]
        assert links[1]["record_hash"] == _link_hash(links[0]["record_hash"], second)

    def test_append_is_pure_append(self, tmp_path) -> None:
        """Prior BYTES are untouched by later appends — the file only grows."""
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        before = path.read_bytes()
        append_acquisition(path, valid_record(schema="tbbo"))
        after = path.read_bytes()
        assert after[: len(before)] == before
        assert len(after) > len(before)

    def test_tampered_record_detected(self, tmp_path) -> None:
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        append_acquisition(path, valid_record(schema="tbbo"))
        lines = path.read_text(encoding="utf-8").splitlines()
        link = json.loads(lines[0])
        link["record"]["request_cost_usd"] = 0.01  # the tamper
        lines[0] = json.dumps(link, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(QlirError, match="hash mismatch"):
            load_ledger(path)

    def test_deleted_first_line_detected(self, tmp_path) -> None:
        """Dropping the first of two lines trips the anchor count before
        the chain walk; a re-headed equal-count forgery trips the chain."""
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        append_acquisition(path, valid_record(schema="tbbo"))
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(lines[1] + "\n", encoding="utf-8")  # drop the first
        with pytest.raises(QlirError, match=r"tail mismatch|chain broken"):
            load_ledger(path)

    def test_append_refuses_corrupt_chain(self, tmp_path) -> None:
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        raw = path.read_text(encoding="utf-8").replace("123.45", "999.99")
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(QlirError, match="hash mismatch"):
            append_acquisition(path, valid_record(schema="tbbo"))

    def test_invalid_append_leaves_ledger_untouched(self, tmp_path) -> None:
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        before = path.read_bytes()
        with pytest.raises(QlirError):
            append_acquisition(path, valid_record(split="locked_test"))
        assert path.read_bytes() == before


class TestWriterLock:
    def test_concurrent_writer_lock_times_out(self, tmp_path) -> None:
        from qlir.locks import ExclusiveLock

        path = tmp_path / "acquisition.jsonl"
        with (
            ExclusiveLock(path),
            pytest.raises(QlirError, match="locked by another writer"),
            ExclusiveLock(path, timeout_s=0.2),
        ):
            pass  # pragma: no cover

    def test_lock_released_after_append(self, tmp_path) -> None:
        path = tmp_path / "acquisition.jsonl"
        append_acquisition(path, valid_record())
        assert not path.with_suffix(path.suffix + ".lock").exists()
        append_acquisition(path, valid_record(schema="tbbo"))  # no deadlock
