"""Immutability and hash-manifest guarantees of the raw store."""

from __future__ import annotations

import pytest
from qlir import QlirError
from qlir.store import RawStore, sha256_file


@pytest.fixture
def store(tmp_path):
    return RawStore(tmp_path / "q_lir")


PAYLOAD = b"synthetic-dbn-bytes-v1"


class TestImmutability:
    def test_write_then_verify_clean(self, store) -> None:
        path = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        assert path.exists()
        assert store.verify() == []

    def test_identical_rewrite_is_idempotent(self, store) -> None:
        store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        assert store.verify() == []

    def test_different_bytes_refused(self, store) -> None:
        store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        with pytest.raises(QlirError, match="IMMUTABLE"):
            store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", b"different")

    def test_delete_then_different_write_refused(self, store) -> None:
        """Round-4 blocker 2: the MANIFEST identity survives file
        deletion — delete-then-rewrite must not silently mutate raw
        history with a clean verify()."""
        path = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        path.unlink()
        with pytest.raises(QlirError, match="was deleted"):
            store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", b"payload-B")
        # The identity is intact and verify still reports the loss.
        problems = store.verify()
        assert len(problems) == 1 and problems[0].startswith("MISSING")

    def test_delete_then_identical_write_restores(self, store) -> None:
        path = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        path.unlink()
        restored = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        assert restored.read_bytes() == PAYLOAD
        assert store.verify() == []

    def test_untracked_file_with_different_bytes_refused(self, store) -> None:
        target = store.path_for("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pre-existing-unknown")
        with pytest.raises(QlirError, match="untracked file"):
            store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)

    def test_untracked_identical_file_adopted(self, store) -> None:
        target = store.path_for("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(PAYLOAD)
        store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        assert store.verify() == []

    def test_atomic_install_leaves_no_temp_files(self, store) -> None:
        path = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        leftovers = [p for p in path.parent.iterdir() if ".tmp-" in p.name]
        assert leftovers == []


class TestConcurrentWriters:
    """Round-5 defect 2: the read-check-install-record sequence must be
    ONE transaction. Sol's reproduction had two racing writers of
    different payloads both succeed with a clean verify()."""

    def test_same_path_different_digest_exactly_one_succeeds(self, store) -> None:
        import threading

        barrier = threading.Barrier(2)
        results: dict[str, str] = {}

        def writer(name: str, payload: bytes) -> None:
            barrier.wait()
            try:
                store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", payload)
                results[name] = "ok"
            except QlirError as exc:
                results[name] = f"refused: {exc}"

        threads = [
            threading.Thread(target=writer, args=("A", b"payload-A")),
            threading.Thread(target=writer, args=("B", b"payload-B")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        outcomes = sorted(results.values())
        assert sum(value == "ok" for value in results.values()) == 1, outcomes
        assert any("IMMUTABLE" in value for value in results.values()), outcomes
        # The surviving state is consistent: manifest matches the file.
        assert store.verify() == []
        winner_payload = store.path_for("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01").read_bytes()
        assert winner_payload in (b"payload-A", b"payload-B")

    def test_concurrent_distinct_paths_both_recorded(self, store) -> None:
        import threading

        barrier = threading.Barrier(2)
        errors: list[str] = []

        def writer(symbol: str, payload: bytes) -> None:
            barrier.wait()
            try:
                store.write_raw("GLBX.MDP3", "trades", symbol, "2022-03-01", payload)
            except QlirError as exc:  # pragma: no cover - failure is the assertion
                errors.append(str(exc))

        threads = [
            threading.Thread(target=writer, args=("ES.v.0", b"payload-ES")),
            threading.Thread(target=writer, args=("NQ.v.0", b"payload-NQ")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert errors == []
        entries = store._read_manifest()
        assert len(entries) == 2  # neither manifest entry was lost
        assert store.verify() == []

    def test_empty_payload_refused(self, store) -> None:
        with pytest.raises(QlirError, match="empty"):
            store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", b"")

    def test_unsafe_path_components_refused(self, store) -> None:
        with pytest.raises(QlirError, match="unsafe"):
            store.path_for("GLBX.MDP3", "trades", "../evil", "2022-03-01")


class TestHashManifest:
    def test_tampered_file_detected(self, store) -> None:
        path = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        path.write_bytes(b"tampered")
        problems = store.verify()
        assert len(problems) == 1 and "HASH MISMATCH" in problems[0]

    def test_missing_file_detected(self, store) -> None:
        path = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        path.unlink()
        problems = store.verify()
        assert len(problems) == 1 and problems[0].startswith("MISSING")

    def test_untracked_file_detected(self, store) -> None:
        store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        rogue = store.raw_dir / "GLBX.MDP3" / "trades" / "ES.v.0" / "2022-03-02.dbn.zst"
        rogue.write_bytes(b"rogue")
        problems = store.verify()
        assert len(problems) == 1 and problems[0].startswith("UNTRACKED")

    def test_manifest_sorted_and_unique(self, store) -> None:
        store.write_raw("GLBX.MDP3", "trades", "NQ.v.0", "2022-03-02", PAYLOAD)
        store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        lines = store.manifest_path.read_text(encoding="utf-8").splitlines()
        assert lines == sorted(lines)
        assert len(lines) == len({line.split("  ", 1)[1] for line in lines})

    def test_sha256_file_matches_payload(self, store) -> None:
        import hashlib

        path = store.write_raw("GLBX.MDP3", "trades", "ES.v.0", "2022-03-01", PAYLOAD)
        assert sha256_file(path) == hashlib.sha256(PAYLOAD).hexdigest()
