"""Payout policy engine + extraction mode (M11.c)."""

from __future__ import annotations

import pytest

from quantlab.errors import QuantLabError
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.policies import compute_policy_grid
from quantlab.prop.registry import load_firm

from ..conftest import random_log
from .conftest import day_trades, simple


class TestKeepBuffer:
    def test_zero_buffer_is_bit_identical_to_asap(self) -> None:
        # The default policy must be EXACTLY the pre-M11 behavior.
        firm = load_firm("topstep_50k")
        log = random_log(n_days=80, mean=40.0, std=300.0, seed=7)
        a = run_monte_carlo(log, firm, MCConfig(n_paths=300, seed=2)).to_json_dict()
        b = run_monte_carlo(
            log, firm, MCConfig(n_paths=300, seed=2, payout_policy="keep_buffer", keep_buffer=0.0)
        ).to_json_dict()
        # The CONFIG record legitimately differs (policy block names the
        # knobs); normalize it — the test pins behavioral identity.
        b["sizing"] = a["sizing"]
        b["policy"] = a["policy"]
        import json

        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_buffer_shrinks_short_horizon_withdrawals(self) -> None:
        # Deterministic +200/day XFA over a 10-day funded horizon: keeping
        # $800 working must strictly shrink what gets withdrawn. (At long
        # horizons cap-driven withdrawal equilibria absorb the buffer —
        # the short horizon exposes the mechanics.)
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(200)]] * 60)
        asap = run_monte_carlo(
            log, firm, MCConfig(n_paths=20, seed=1, funded_horizon_days=10)
        ).economics
        kept = run_monte_carlo(
            log,
            firm,
            MCConfig(
                n_paths=20,
                seed=1,
                funded_horizon_days=10,
                payout_policy="keep_buffer",
                keep_buffer=800.0,
            ),
        ).economics
        assert kept.expected_gross_payout < asap.expected_gross_payout

    def test_buffer_tradeoff_on_marginal_log(self) -> None:
        # The honest finding the grid exists to show: leaving money
        # working COMPOUNDS (higher long-run EV) but delays the first
        # payout, so ruin-before-any-payout RISES. Pinned regression of
        # engine behavior on a fixed seed, CRN across cells.
        firm = load_firm("topstep_50k")
        log = random_log(n_days=90, mean=30.0, std=350.0, seed=5)
        results = []
        for buffer in (0.0, 3000.0):
            run = run_monte_carlo(
                log,
                firm,
                MCConfig(
                    n_paths=800,
                    seed=3,
                    payout_policy="keep_buffer" if buffer else "asap",
                    keep_buffer=buffer,
                ),
            )
            results.append(run.economics)
        assert results[1].expected_net > results[0].expected_net
        assert results[1].risk_of_ruin_funded > results[0].risk_of_ruin_funded

    def test_validation(self) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(n_days=40, seed=1)
        with pytest.raises(QuantLabError, match="payout policy"):
            run_monte_carlo(log, firm, MCConfig(n_paths=10, seed=1, payout_policy="typo"))
        with pytest.raises(QuantLabError, match="keep-buffer"):
            run_monte_carlo(
                log,
                firm,
                MCConfig(n_paths=10, seed=1, payout_policy="keep_buffer", keep_buffer=-5.0),
            )


class TestExtraction:
    def test_extraction_weight_validated(self) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(n_days=40, seed=1)
        with pytest.raises(QuantLabError, match="extract-weight"):
            run_monte_carlo(log, firm, MCConfig(n_paths=10, seed=1, extract_weight=1.5))
        with pytest.raises(QuantLabError, match="extract-weight"):
            run_monte_carlo(log, firm, MCConfig(n_paths=10, seed=1, extract_weight=0.0))

    def test_extraction_shrinks_first_payout(self) -> None:
        # Apex EOD +500/day (1-lot log, so the firm's half-size rule never
        # binds a 1-contract trader): qualifying banks day 5; extraction
        # halves day 6, so the first payout is smaller ($650 vs $900) but
        # still lands — the banked cycle is protected at a price.
        firm = load_firm("apex40_50k_eod")
        log = day_trades([[simple(500)]] * 80)
        h10_plain = run_monte_carlo(
            log, firm, MCConfig(n_paths=20, seed=1, funded_horizon_days=10)
        ).economics
        h10_extract = run_monte_carlo(
            log, firm, MCConfig(n_paths=20, seed=1, funded_horizon_days=10, extract_weight=0.5)
        ).economics
        assert h10_plain.expected_gross_payout == pytest.approx(900.0)
        assert h10_extract.expected_gross_payout == pytest.approx(650.0)

    def test_extraction_neutral_when_no_qualifying_rule(self) -> None:
        # FTMO 1-Step has no qualifying-day requirement: extraction has
        # nothing to key on and must change nothing.
        firm = load_firm("ftmo_1step_100k")
        assert firm.payout.qualifying_days.count == 0
        log = random_log(n_days=80, mean=60.0, std=300.0, seed=9)
        a = run_monte_carlo(log, firm, MCConfig(n_paths=200, seed=4)).economics
        b = run_monte_carlo(log, firm, MCConfig(n_paths=200, seed=4, extract_weight=0.5)).economics
        assert a.expected_net == b.expected_net


class TestPolicyGrid:
    def test_grid_first_cell_matches_plain_run(self) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(n_days=70, mean=40.0, std=300.0, seed=7)
        cfg = MCConfig(n_paths=200, seed=5)
        grid = compute_policy_grid(
            log, firm, mc_cfg=cfg, buffers=(0.0, 1000.0), extract_weights=(None,)
        )
        plain = run_monte_carlo(log, firm, cfg).economics
        first = next(c for c in grid.cells if c.keep_buffer == 0 and c.extract_weight is None)
        assert first.expected_net == plain.expected_net
        assert first.label == "asap"

    def test_grid_labels_and_picks(self) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(n_days=70, mean=40.0, std=300.0, seed=7)
        grid = compute_policy_grid(
            log,
            firm,
            mc_cfg=MCConfig(n_paths=150, seed=5),
            buffers=(0.0, 2000.0),
            extract_weights=(None, 0.5),
        )
        assert len(grid.cells) == 4
        labels = {c.label for c in grid.cells}
        assert "asap" in labels and "keep $2,000 + extract 0.5x" in labels
        assert grid.best_net_label in labels
        assert grid.lowest_ruin_label in labels

    def test_no_qualifying_firm_drops_extraction_cells(self) -> None:
        firm = load_firm("ftmo_1step_100k")
        log = random_log(n_days=70, mean=60.0, std=300.0, seed=9)
        grid = compute_policy_grid(
            log,
            firm,
            mc_cfg=MCConfig(n_paths=100, seed=5),
            buffers=(0.0,),
            extract_weights=(None, 0.5),
        )
        assert all(c.extract_weight is None for c in grid.cells)

    def test_json_serializable(self) -> None:
        import json

        from quantlab.report.jsonout import sanitize

        firm = load_firm("topstep_50k")
        log = random_log(n_days=60, mean=40.0, std=300.0, seed=7)
        grid = compute_policy_grid(
            log, firm, mc_cfg=MCConfig(n_paths=80, seed=5), buffers=(0.0,), extract_weights=(None,)
        )
        json.dumps(sanitize(grid.to_json_dict()))

    def test_bad_buffers_raise(self) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(n_days=60, seed=7)
        with pytest.raises(QuantLabError, match="buffers"):
            compute_policy_grid(log, firm, buffers=(-100.0,))


class TestCli:
    def test_policies_command_runs(self, tmp_path) -> None:
        import json as jsonlib

        from typer.testing import CliRunner

        from quantlab.cli.app import app
        from quantlab.schema.io import write_trade_log

        parquet = tmp_path / "t.parquet"
        write_trade_log(random_log(n_days=60, mean=40.0, std=300.0, seed=7), parquet)
        out = tmp_path / "grid.json"
        result = CliRunner().invoke(
            app,
            [
                "prop",
                "policies",
                str(parquet),
                "--firm",
                "topstep_50k",
                "--paths",
                "80",
                "--buffers",
                "0,1000",
                "--json",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = jsonlib.loads(out.read_text())
        assert len(payload["cells"]) == 4
        assert "Funded-phase policy grid" in result.output


class TestSchemaV4:
    def test_policy_block_in_json(self) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(n_days=50, mean=40.0, std=300.0, seed=7)
        payload = run_monte_carlo(
            log,
            firm,
            MCConfig(
                n_paths=50,
                seed=1,
                payout_policy="keep_buffer",
                keep_buffer=1500.0,
                extract_weight=0.5,
            ),
        ).to_json_dict()
        assert payload["schema_version"] == 4
        assert payload["policy"]["payout_policy"] == "keep_buffer"
        assert payload["policy"]["keep_buffer"] == 1500.0
        assert payload["policy"]["extract_weight"] == 0.5
        assert payload["policy"]["base_contracts"] == 1.0  # log's max position


class TestInertExtractionWarning:
    def test_topstep_inert_axis_flagged(self) -> None:
        # Topstep XFA: the payout lands the same close the 5th qualifying
        # day banks, so extraction never activates — the grid must say so.
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(200)]] * 60)
        grid = compute_policy_grid(
            log,
            firm,
            mc_cfg=MCConfig(n_paths=50, seed=1),
            buffers=(0.0, 1000.0),
            extract_weights=(None, 0.5),
        )
        assert any("inert" in w for w in grid.warnings)
