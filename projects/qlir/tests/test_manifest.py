"""Round-6 ledger: bound receipts (symbols/coverage/files), disk-verified
appends, date-derived lock, hash chain + anchor, and the RECOVERABLE
pending-journal transaction with failure injection."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import pytest
from qlir import QlirError
from qlir.manifest import (
    GENESIS,
    _anchor_path,
    _link_hash,
    _pending_path,
    append_acquisition,
    load_ledger,
    recover_ledger,
    split_for_range,
    validate_record,
    verify_ledger,
)
from qlir.store import RawStore

PAYLOAD = b"synthetic-dbn-bytes-round6"
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()
RELPATH = "raw/GLBX.MDP3/trades/ES.v.0/2022-03-01.dbn.zst"


def contracts_for(start: str, end: str, symbol: str = "ES.v.0"):
    return {symbol: [{"instrument_id": 4916, "raw_symbol": "ESH2", "d0": start, "d1": end}]}


def valid_record(**overrides):
    record = {
        "dataset": "GLBX.MDP3",
        "schema": "trades",
        "requested_symbols": ["ES.v.0"],
        "stype_in": "continuous",
        "stype_out": "instrument_id",
        "resolved_contracts": contracts_for("2022-01-01", "2022-03-14"),
        "start_utc": "2022-01-01T00:00:00Z",
        "end_utc": "2022-03-14T00:00:00Z",
        "request_cost_usd": 123.45,
        "record_count": 456,
        "billable_size_bytes": 48_000_000,
        "client_version": "databento 0.83.0",
        "files": [
            {
                "relative_path": RELPATH,
                "sha256": PAYLOAD_SHA,
                "size_bytes": len(PAYLOAD),
                "record_count": 456,
                "server_filename": "glbx-mdp3-20220301.trades.dbn.zst",
            }
        ],
        "server_manifest": [
            {"filename": "glbx-mdp3-20220301.trades.dbn.zst", "size_bytes": len(PAYLOAD)}
        ],
        "dataset_conditions": {"2022-01-03": "available"},
        "derivation_code_commit": "60f574e",
        "split": "development",
    }
    record.update(overrides)
    return record


@pytest.fixture
def env(tmp_path):
    """A data root with the attested raw file actually on disk."""
    root = tmp_path / "q_lir"
    store = RawStore(root)
    store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
    return root, root / "manifests" / "acquisition.jsonl"


class TestReceiptBinding:
    """Round-6 finding 1: Sol chained a receipt whose requested symbols,
    mapping, coverage, hash pointer, and counts described unrelated
    objects. Each element is now refused."""

    def test_sols_composite_reproduction_refused(self) -> None:
        record = valid_record(
            requested_symbols=["NQ.v.0"],  # mapping resolves ES.v.0
            end_utc="2023-01-01T00:00:00Z",  # coverage ends 2022-03-14
        )
        with pytest.raises(QlirError, match="do not equal the resolved"):
            validate_record(record)

    def test_mismatched_symbols_refused(self) -> None:
        with pytest.raises(QlirError, match="do not equal the resolved"):
            validate_record(valid_record(requested_symbols=["NQ.v.0"]))

    def test_incomplete_coverage_refused(self) -> None:
        """Attested range end beyond the mapping's coverage."""
        with pytest.raises(QlirError, match=r"short of the attested|coverage gap"):
            validate_record(valid_record(end_utc="2023-01-01T00:00:00Z"))

    def test_mutable_manifest_pathname_refused(self) -> None:
        """The round-5 `file_hashes` pointer field no longer exists."""
        record = valid_record()
        del record["files"]
        record["file_hashes"] = "manifests/files.sha256"
        with pytest.raises(QlirError, match="missing required fields"):
            validate_record(record)

    def test_files_must_be_typed_attestations(self) -> None:
        with pytest.raises(QlirError, match=r"files must be|attestation"):
            validate_record(valid_record(files="manifests/does-not-exist.sha256"))

    def test_record_count_must_reconcile_with_files(self) -> None:
        with pytest.raises(QlirError, match="does not equal the sum"):
            validate_record(valid_record(record_count=999_999))

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("request_cost_usd", -1.0),
            ("request_cost_usd", float("nan")),
            ("billable_size_bytes", -5),
        ],
    )
    def test_nonfinite_or_negative_economics_refused(self, field: str, value) -> None:
        with pytest.raises(QlirError, match=field):
            validate_record(valid_record(**{field: value}))

    def test_nonexistent_attested_file_refused_at_append(self, env) -> None:
        root, ledger = env
        record = valid_record()
        record["files"][0]["relative_path"] = "raw/GLBX.MDP3/trades/ES.v.0/2022-03-02.dbn.zst"
        with pytest.raises(QlirError, match="missing on disk"):
            append_acquisition(ledger, record, data_root=root)

    def test_unrelated_file_hash_refused_at_append(self, env) -> None:
        root, ledger = env
        record = valid_record()
        record["files"][0]["sha256"] = "0" * 64
        with pytest.raises(QlirError, match="hash mismatch"):
            append_acquisition(ledger, record, data_root=root)

    def test_size_mismatch_refused_at_append(self, env) -> None:
        """Consistent receipt (file+manifest agree) whose size disagrees
        with the DISK — caught by the append-time verification."""
        root, ledger = env
        record = valid_record()
        record["files"][0]["size_bytes"] = len(PAYLOAD) + 1
        record["server_manifest"][0]["size_bytes"] = len(PAYLOAD) + 1
        with pytest.raises(QlirError, match="size mismatch"):
            append_acquisition(ledger, record, data_root=root)

    def test_sols_absolute_path_refused(self) -> None:
        """Round-7 finding 3: an absolute Windows path masqueraded as a
        relative attestation and escaped data_root."""
        record = valid_record()
        record["files"][0]["relative_path"] = "C:/Users/justi/outside.dbn"
        with pytest.raises(QlirError, match="data_root-relative"):
            validate_record(record)

    @pytest.mark.parametrize(
        "path",
        ["/abs/posix.dbn", "\\\\server\\share\\f.dbn", "D:evil.dbn", "//srv/f.dbn"],
    )
    def test_escaping_path_forms_refused(self, path: str) -> None:
        record = valid_record()
        record["files"][0]["relative_path"] = path
        with pytest.raises(QlirError, match=r"data_root-relative|unsafe"):
            validate_record(record)

    def test_server_manifest_must_reconcile(self) -> None:
        record = valid_record()
        record["server_manifest"] = [{"filename": "other.dbn.zst", "size_bytes": 5}]
        with pytest.raises(QlirError, match="do not equal the server manifest"):
            validate_record(record)

    def test_server_manifest_size_must_match(self) -> None:
        record = valid_record()
        record["server_manifest"][0]["size_bytes"] = 999
        with pytest.raises(QlirError, match="does not match the server manifest"):
            validate_record(record)

    def test_missing_server_binding_refused(self) -> None:
        record = valid_record()
        record["files"][0]["server_filename"] = ""
        with pytest.raises(QlirError, match="server_filename"):
            validate_record(record)

    def test_bound_receipt_appends_and_reloads(self, env) -> None:
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        assert load_ledger(ledger)[0]["files"][0]["sha256"] == PAYLOAD_SHA


class TestSymbologyValidation:
    def test_invalid_direct_pairing_refused(self) -> None:
        record = valid_record(stype_out="raw_symbol", resolved_contracts="garbage")
        with pytest.raises(QlirError, match="unsupported symbology pair"):
            validate_record(record)

    def test_untyped_resolved_contracts_refused(self) -> None:
        with pytest.raises(QlirError, match="resolved_contracts"):
            validate_record(valid_record(resolved_contracts="garbage"))


class TestDateDerivedLock:
    def test_locked_period_refused_regardless_of_label(self) -> None:
        record = valid_record(
            start_utc="2025-01-01T00:00:00Z",
            end_utc="2027-01-01T00:00:00Z",
            split="development",
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
        with pytest.raises(QlirError, match="contradicts"):
            validate_record(valid_record(split="validation"))

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
                resolved_contracts=contracts_for("2024-01-01", "2025-01-01"),
            )
        )

    def test_naive_datetime_refused(self) -> None:
        with pytest.raises(QlirError, match="timezone-aware"):
            validate_record(valid_record(start_utc="2022-01-01T00:00:00"))

    def test_split_for_range_classifies(self) -> None:
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

    @pytest.mark.parametrize("missing", ["dataset", "request_cost_usd", "split", "files"])
    def test_missing_field_rejected(self, missing: str) -> None:
        record = valid_record()
        del record[missing]
        with pytest.raises(QlirError, match="missing required"):
            validate_record(record)

    def test_empty_symbols_rejected(self) -> None:
        with pytest.raises(QlirError, match="requested_symbols"):
            validate_record(valid_record(requested_symbols=[]))


class TestHashChainAndAnchor:
    def _two(self, env):
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        append_acquisition(ledger, valid_record(schema="tbbo"), data_root=root)
        return root, ledger

    def test_chain_links_and_loads(self, env) -> None:
        _, ledger = self._two(env)
        links = verify_ledger(ledger)
        assert links[0]["prev_hash"] == GENESIS
        assert links[1]["prev_hash"] == links[0]["record_hash"]
        assert links[1]["record_hash"] == _link_hash(links[0]["record_hash"], links[1]["record"])

    def test_append_is_pure_append(self, env) -> None:
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        before = ledger.read_bytes()
        append_acquisition(ledger, valid_record(schema="tbbo"), data_root=root)
        after = ledger.read_bytes()
        assert after[: len(before)] == before

    def test_tampered_record_detected(self, env) -> None:
        _, ledger = self._two(env)
        lines = ledger.read_text(encoding="utf-8").splitlines()
        link = json.loads(lines[0])
        link["record"]["request_cost_usd"] = 0.01
        lines[0] = json.dumps(link, sort_keys=True, separators=(",", ":"))
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(QlirError, match="hash mismatch"):
            load_ledger(ledger)

    def test_tail_line_removal_detected(self, env) -> None:
        _, ledger = self._two(env)
        lines = ledger.read_text(encoding="utf-8").splitlines()
        ledger.write_text(lines[0] + "\n", encoding="utf-8")
        with pytest.raises(QlirError, match="tail"):
            load_ledger(ledger)

    def test_whole_ledger_deletion_detected(self, env) -> None:
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        ledger.unlink()
        with pytest.raises(QlirError, match="tail truncation or ledger deletion"):
            load_ledger(ledger)

    def test_anchor_deletion_detected(self, env) -> None:
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        _anchor_path(ledger).unlink()
        with pytest.raises(QlirError, match="no anchor"):
            load_ledger(ledger)

    def test_invalid_append_leaves_ledger_untouched(self, env) -> None:
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        before = ledger.read_bytes()
        with pytest.raises(QlirError):
            append_acquisition(ledger, valid_record(split="locked_test"), data_root=root)
        assert ledger.read_bytes() == before


class TestRecoverableTransaction:
    """Round-6 finding 4: an interrupted append must be deterministically
    completable or rollback-able, never a permanent wedge."""

    def test_anchor_failure_recovers_forward(self, env, monkeypatch) -> None:
        """Sol's injection: anchor write fails after the ledger append.
        The ledger used to wedge permanently; now recovery completes the
        transaction and every read works."""
        import qlir.manifest as manifest_module

        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        original = manifest_module._write_anchor

        def boom(*args, **kwargs):
            raise OSError("injected anchor failure")

        monkeypatch.setattr(manifest_module, "_write_anchor", boom)
        with pytest.raises(OSError, match="injected"):
            append_acquisition(ledger, valid_record(schema="tbbo"), data_root=root)
        monkeypatch.setattr(manifest_module, "_write_anchor", original)
        # Unrecovered state: reads refuse with a recovery pointer.
        with pytest.raises(QlirError, match="pending"):
            load_ledger(ledger)
        recover_ledger(ledger)
        records = load_ledger(ledger)
        assert len(records) == 2  # rolled FORWARD

    def test_failure_before_ledger_append_rolls_back(self, env, monkeypatch) -> None:
        import qlir.manifest as manifest_module

        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        original_open = manifest_module.os.open
        pending = _pending_path(ledger)

        def boom(path, flags, *args):
            if str(path) == str(ledger) and flags & manifest_module.os.O_APPEND:
                raise OSError("injected append failure")
            return original_open(path, flags, *args)

        monkeypatch.setattr(manifest_module.os, "open", boom)
        with pytest.raises(OSError, match="injected append"):
            append_acquisition(ledger, valid_record(schema="tbbo"), data_root=root)
        monkeypatch.undo()
        assert pending.exists()
        recover_ledger(ledger)  # rolls BACK: nothing landed
        assert not pending.exists()
        assert len(load_ledger(ledger)) == 1

    def test_torn_final_line_rolls_back(self, env) -> None:
        """The one non-atomic step: a partial line with the journal
        present is stripped back to the journaled committed state."""
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        committed = ledger.read_text(encoding="utf-8")
        # Simulate: journal written, append tore mid-line.
        import qlir.manifest as manifest_module

        record = valid_record(schema="tbbo")
        links = verify_ledger(ledger)
        prev = links[-1]["record_hash"]
        line = json.dumps(
            {
                "prev_hash": prev,
                "record_hash": manifest_module._link_hash(prev, record),
                "record": record,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        manifest_module._atomic_json(
            _pending_path(ledger),
            {
                "prev_count": 1,
                "prev_terminal": prev,
                "line": line,
                "new_count": 2,
                "new_terminal": manifest_module._link_hash(prev, record),
            },
        )
        with open(ledger, "a", encoding="utf-8") as handle:
            handle.write(line[: len(line) // 2])  # torn
        recover_ledger(ledger)
        assert ledger.read_text(encoding="utf-8") == committed
        assert len(load_ledger(ledger)) == 1

    def test_next_append_recovers_automatically(self, env, monkeypatch) -> None:
        import qlir.manifest as manifest_module

        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        original = manifest_module._write_anchor

        def boom(*args, **kwargs):
            raise OSError("injected anchor failure")

        monkeypatch.setattr(manifest_module, "_write_anchor", boom)
        with pytest.raises(OSError):
            append_acquisition(ledger, valid_record(schema="tbbo"), data_root=root)
        monkeypatch.setattr(manifest_module, "_write_anchor", original)
        # The NEXT locked append recovers, then appends.
        append_acquisition(ledger, valid_record(schema="mbp-1"), data_root=root)
        assert len(load_ledger(ledger)) == 3


class TestWriterLock:
    def test_concurrent_writer_lock_times_out(self, tmp_path) -> None:
        from qlir.locks import ExclusiveLock

        path = tmp_path / "acquisition.jsonl"
        with (
            ExclusiveLock(path),
            pytest.raises(QlirError, match="locked by another LIVE writer"),
            ExclusiveLock(path, timeout_s=0.2),
        ):
            pass  # pragma: no cover

    def test_lock_released_after_append(self, env) -> None:
        """The lock FILE persists by design (only the OS lock matters);
        release is proven by immediate re-acquisition."""
        root, ledger = env
        append_acquisition(ledger, valid_record(), data_root=root)
        append_acquisition(ledger, valid_record(schema="tbbo"), data_root=root)
        assert len(load_ledger(ledger)) == 2
