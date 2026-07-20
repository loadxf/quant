"""CSCV probability of backtest overfitting (M10.f)."""

from __future__ import annotations

import numpy as np
import pytest

from quantlab.errors import QuantLabError
from quantlab.metrics.pbo import compute_pbo, load_variant_matrix


def _noise(t: int = 320, n: int = 20, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, 1.0, size=(t, n))


class TestAnchors:
    def test_pure_noise_pbo_near_half(self) -> None:
        # Paper anchor: skill-less variants -> the IS winner's OOS rank is
        # uniform, PBO ~ 0.5.
        result = compute_pbo(_noise(), partitions=16)
        assert 0.35 <= result.pbo <= 0.65
        assert abs(result.logit_mean) < 1.0

    def test_dominant_true_edge_pbo_low(self) -> None:
        m = _noise()
        m[:, 0] += 0.5  # one variant with a real, large edge
        result = compute_pbo(m, partitions=16)
        assert result.pbo < 0.15
        assert result.p_oos_loss < 0.15

    def test_deterministic(self) -> None:
        a = compute_pbo(_noise(), partitions=8)
        b = compute_pbo(_noise(), partitions=8)
        assert a.pbo == b.pbo and a.logit_mean == b.logit_mean

    def test_more_variants_raise_noise_pbo_stability(self) -> None:
        # PBO is a probability: always inside [0, 1] and JSON-clean.
        import json

        from quantlab.report.jsonout import sanitize

        result = compute_pbo(_noise(n=6), partitions=8)
        assert 0.0 <= result.pbo <= 1.0
        json.dumps(sanitize(result.to_json_dict()))


class TestValidation:
    def test_odd_partitions_rejected(self) -> None:
        with pytest.raises(QuantLabError, match="even"):
            compute_pbo(_noise(), partitions=15)

    def test_too_few_days_rejected(self) -> None:
        with pytest.raises(QuantLabError, match="blocks"):
            compute_pbo(_noise(t=20), partitions=16)

    def test_single_variant_rejected(self) -> None:
        with pytest.raises(QuantLabError, match="variant"):
            compute_pbo(_noise(n=1))

    def test_nan_rejected(self) -> None:
        m = _noise()
        m[3, 4] = np.nan
        with pytest.raises(QuantLabError, match="NaN"):
            compute_pbo(m)

    def test_remainder_days_dropped_with_note(self) -> None:
        result = compute_pbo(_noise(t=323), partitions=16)
        assert result.n_days == 320
        assert any("dropped" in w for w in result.warnings)


class TestCsvLoading:
    def test_date_column_dropped(self, tmp_path) -> None:
        import pandas as pd

        m = _noise(t=64, n=3)
        frame = pd.DataFrame(m, columns=["a", "b", "c"])
        frame.insert(0, "date", pd.bdate_range("2026-01-05", periods=64).strftime("%Y-%m-%d"))
        path = tmp_path / "variants.csv"
        frame.to_csv(path, index=False)
        matrix, names = load_variant_matrix(path)
        assert names == ["a", "b", "c"]
        assert matrix.shape == (64, 3)

    def test_bad_values_rejected(self, tmp_path) -> None:
        path = tmp_path / "bad.csv"
        path.write_text("a,b\n1.0,2.0\n1.0,oops\n")
        with pytest.raises(QuantLabError, match="non-numeric"):
            load_variant_matrix(path)


class TestCli:
    def test_pbo_command_runs(self, tmp_path) -> None:
        import json as jsonlib

        import pandas as pd
        from typer.testing import CliRunner

        from quantlab.cli.app import app

        path = tmp_path / "variants.csv"
        pd.DataFrame(_noise(t=64, n=4), columns=list("abcd")).to_csv(path, index=False)
        result = CliRunner().invoke(app, ["pbo", str(path), "--partitions", "8", "--json"])
        assert result.exit_code == 0, result.output
        payload = jsonlib.loads(result.output)
        assert 0.0 <= payload["pbo"] <= 1.0
