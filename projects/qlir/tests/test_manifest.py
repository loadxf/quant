"""Acquisition-manifest validation and append-only behavior."""

from __future__ import annotations

import json

import pytest
from qlir import QlirError
from qlir.manifest import append_acquisition, load_manifest, validate_record


def valid_record(**overrides):
    record = {
        "dataset": "GLBX.MDP3",
        "schema": "trades",
        "requested_symbols": ["ES.v.0", "NQ.v.0"],
        "stype_in": "continuous",
        "stype_out": "raw_symbol",
        "resolved_contracts": {"ES.v.0": ["ESH2", "ESM2"]},
        "start_utc": "2022-01-01T00:00:00Z",
        "end_utc": "2023-01-01T00:00:00Z",
        "request_cost_usd": 123.45,
        "record_count": 1_000_000,
        "billable_size_bytes": 48_000_000,
        "client_version": "databento 0.83.0",
        "file_hashes": "manifests/files.sha256",
        "dataset_conditions": {"2022-01-03": "available"},
        "derivation_code_commit": "d21bb62",
        "split": "development",
    }
    record.update(overrides)
    return record


class TestValidation:
    def test_valid_record_passes(self) -> None:
        validate_record(valid_record())

    @pytest.mark.parametrize("missing", ["dataset", "request_cost_usd", "split", "file_hashes"])
    def test_missing_field_rejected(self, missing: str) -> None:
        record = valid_record()
        del record[missing]
        with pytest.raises(QlirError, match="missing required"):
            validate_record(record)

    def test_unknown_split_rejected(self) -> None:
        with pytest.raises(QlirError, match="split"):
            validate_record(valid_record(split="test"))

    def test_locked_test_acquisition_prohibited(self) -> None:
        """2025+ purchases stay forbidden until validation is frozen."""
        with pytest.raises(QlirError, match="locked_test"):
            validate_record(valid_record(split="locked_test"))

    def test_empty_symbols_rejected(self) -> None:
        with pytest.raises(QlirError, match="requested_symbols"):
            validate_record(valid_record(requested_symbols=[]))


class TestAppendOnly:
    def test_append_preserves_existing(self, tmp_path) -> None:
        path = tmp_path / "acquisition.json"
        first = valid_record()
        append_acquisition(path, first)
        second = valid_record(schema="tbbo", split="validation")
        result = append_acquisition(path, second)
        assert result[0] == first  # verbatim preservation
        assert len(load_manifest(path)) == 2

    def test_invalid_append_leaves_file_untouched(self, tmp_path) -> None:
        path = tmp_path / "acquisition.json"
        append_acquisition(path, valid_record())
        before = path.read_text(encoding="utf-8")
        with pytest.raises(QlirError):
            append_acquisition(path, valid_record(split="locked_test"))
        assert path.read_text(encoding="utf-8") == before

    def test_corrupt_existing_manifest_fails_closed(self, tmp_path) -> None:
        path = tmp_path / "acquisition.json"
        bad = valid_record()
        del bad["split"]
        path.write_text(json.dumps([bad]), encoding="utf-8")
        with pytest.raises(QlirError, match=r"corrupt|invalid"):
            append_acquisition(path, valid_record())

    def test_non_list_manifest_rejected(self, tmp_path) -> None:
        path = tmp_path / "acquisition.json"
        path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with pytest.raises(QlirError, match="JSON list"):
            load_manifest(path)
