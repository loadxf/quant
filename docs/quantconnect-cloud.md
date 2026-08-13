# QuantConnect Cloud deployment runbook

This is the supported way to run the repository's strategies when
QuantConnect REST API access and the lean CLI are unavailable.

## What runs where

| Component | Runtime |
| --- | --- |
| `cloud/strategies/*/main.py` | QuantConnect Cloud web IDE and hosted LEAN |
| Backtest build, market data, orders, trades, charts | QuantConnect Cloud |
| `quant cloud results`, metrics, prop simulation, reports | Local Python environment |

The full `src/quantlab` package is not a `QCAlgorithm`. It depends on a local
Python CLI and libraries such as pandas and pyarrow, so do not paste it into a
Cloud project. The handoff is QuantConnect's downloaded backtest result JSON.

## Prerequisites

- A QuantConnect account and an organization with a Cloud backtest node.
- A supported browser and access to Algorithm Lab.
- A local Python 3.11 or newer environment only if you want quantlab's reports.
- No QuantConnect API token, lean CLI, Docker, or local LEAN installation.

QuantConnect currently gives a new Free organization one B-MICRO backtest
node. Free Cloud projects have a 32 KB per-file limit. All shipped `main.py`
files are checked against that limit in the local test suite.

## Choose a project

### Built-in-data projects

These are the no-API, no-Object-Store choices:

- `cloud/strategies/sma_cross_futures/main.py`: continuous ES futures, minute
  resolution, SMA crossover, rollover reconciliation, and a session flatten.
- `cloud/strategies/orb_equity/main.py`: SPY opening-range breakout, protective
  bracket reconciliation, and end-of-day flattening.

Both files use QuantConnect Dataset Market data inside Cloud. Each is a single,
self-contained Python source file with one `QCAlgorithm` subclass.

### Custom-data project

`cloud/strategies/custom_data_demo/main.py` reads a normalized CSV through
QuantConnect Object Store and trades SPY as a liquid proxy. QuantConnect's
current documentation limits Object Store to paid organizations. Manual upload
does not use the REST API, but it still requires a paid organization and the
appropriate storage permission.

If you have a Free organization, use one of the built-in-data projects. Do not
expect the custom-data project to run until the storage requirement is met.

## Create the Cloud project

1. Open [QuantConnect Algorithm Lab](https://www.quantconnect.com/terminal).
2. Select **Projects**, then **Create New Algorithm**.
3. Confirm the project language is Python.
4. Open the repository strategy you selected and copy all of its `main.py`.
5. Replace the generated Cloud project's `main.py` with that source.
6. Do not copy the adjacent `config.json`. It is LEAN CLI project metadata;
   `.json` is not a supported Cloud source-file type. Set the description,
   parameters, package environment, and LEAN version in the Cloud Project
   panel instead.
7. Save and click **Build**.

The shipped strategies import only the Python standard library and
`AlgorithmImports`; no third-party package selection should be necessary. If
you extend them with external packages, select a QuantConnect Python Foundation
environment that contains the exact package/version. A local `pip install`
does not install anything on a Cloud node.

## Run and inspect the backtest

1. After Build succeeds, click **Backtest**.
2. Wait for the hosted run to reach a completed state. Closing or refreshing
   the browser does not stop a Cloud backtest.
3. Check **Logs** for runtime exceptions and data-subscription errors.
4. Check **Orders** for rejected, invalid, unexpectedly open, or duplicate
   orders.
5. Check **Trades** for closed trades. The local importer intentionally fails
   if the backtest has no closed trades.
6. Check **Overview** for the expected date range, starting equity, fees,
   drawdown, and total orders.

Do not treat a successful Build as a successful backtest. Build verifies the
hosted compiler; the completed run verifies initialization, data access, and
runtime behavior.

## Download and import results without API access

1. Open the completed backtest's **Overview** tab.
2. Click **Download Results** and save the JSON file locally.
3. Do not substitute **Download Trades**. That CSV omits the full charts and
   metadata used by `--chart` and `--firm`.
4. In this repository's local environment, run:

```bash
quant cloud results \
  --downloaded-results /path/to/downloaded-backtest.json \
  --output trades.parquet \
  --chart
```

On PowerShell:

```powershell
quant cloud results `
  --downloaded-results C:\Users\you\Downloads\backtest.json `
  --output trades.parquet `
  --chart
```

Then generate the analysis:

```bash
quant report trades.parquet --firm topstep_50k -o report.html
```

`--from-json` is an alias for `--downloaded-results`. The import path never
constructs the REST client and does not read `QC_USER_ID` or `QC_API_TOKEN`.

When `--chart` is present, the importer reads the embedded **Strategy Equity**
chart and writes `<output>.equity.csv`. `--firm <preset>` implies `--chart` and
runs the open-equity rule check. QuantConnect limits chart data points by
organization tier, so this series may be sampled. A violation between retained
points cannot be detected; the local output reports that fidelity boundary.

## Custom Object Store data without the API

This section is only for a paid organization.

1. Normalize the local CSV:

   ```bash
   quant ingest ohlcv my-bars.csv --symbol demo --tz America/Chicago
   ```

2. In Algorithm Lab, open **Organization → Object Store**.
3. Upload the normalized file under `quantlab/demo.csv`.
4. If you choose another key, change `OBJECT_STORE_KEY` in
   `custom_data_demo/main.py` before copying the file into Cloud.
5. Build and Backtest, then use **Overview → Download Results**. The result
   download does not depend on downloading the source CSV from Object Store.

Keep individual objects below 50 MB for live access. Object Store is shared at
the organization level, so use project-specific keys for production work to
avoid collisions.

## Project parameters

The examples have runnable defaults in source. To make a value configurable:

1. Add it with **Add New Parameter** in the Cloud Project panel.
2. Read it in `initialize` with `self.get_parameter("name", typed_default)`.
3. Stop, change the parameter, and redeploy. Cloud project parameters are
   injected at deployment and do not change during a running algorithm.

Avoid optimizing on the same period used to make a final performance claim.

## Paper and live deployment boundary

Cloud backtesting does not prove brokerage compatibility or live safety. Before
real-money deployment:

1. Use a paid organization with an appropriate live node, brokerage, and data
   subscription.
2. Deploy to QuantConnect Paper Trading first.
3. Verify startup holdings, open-order reconciliation, time zone, scheduled
   events, market-hours behavior, contract mapping, fees, slippage, and restart
   behavior.
4. Confirm all positions and orders are flat when the deployment is stopped.
5. Only then configure a real brokerage deployment through the Cloud UI.

No live or real-money deployment is performed or validated by this repository's
local tests.

The checked-in result fixture is a sanitized schema model built from LEAN's
documented backtest fields, not a freshly captured browser download. A real
**Overview → Download Results** file must pass the importer before release; this
detects any hosted serializer wrapper or field change that local tests cannot.

## Release checklist

- [ ] Correct standalone `main.py` copied into a Python Cloud project.
- [ ] Exactly one `QCAlgorithm` subclass in the project.
- [ ] No local paths, subprocesses, local services, or environment secrets.
- [ ] Build completes on the current hosted LEAN version.
- [ ] Backtest reaches Completed with no runtime error.
- [ ] Orders and closed trades match the intended strategy.
- [ ] No unexpected holdings or open orders remain at the end.
- [ ] Overview → Download Results produces JSON.
- [ ] `quant cloud results --downloaded-results ... --chart` succeeds locally.
- [ ] The generated report opens and its fidelity warnings are reviewed.
- [ ] Custom-data project uses a paid organization and valid Object Store key.
- [ ] Paper deployment passes before any real brokerage deployment.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `AlgorithmImports` or LEAN type errors | Confirm the Cloud project language is Python and the code is in `main.py`. |
| Build succeeds but run fails | Read the first runtime exception in Logs; verify date range and data subscription. |
| No closed trades | Inspect Orders and strategy conditions; the importer will not fabricate an empty trade log. |
| Import says no Strategy Equity chart | Download from Backtest **Overview → Download Results**, not Download Trades. |
| Object Store permission error | The organization is Free or the member lacks storage permission; use a built-in-data project or upgrade/adjust permission. |
| File rejected for size | Keep each source file below the tier's project-file quota; Free is currently 32 KB. |
| Local importer asks for credentials | Use `--downloaded-results`; `--project-id/--backtest-id` selects the optional REST path. |

## Official QuantConnect references

- [Create and configure Cloud projects](https://www.quantconnect.com/docs/v2/cloud-platform/projects/getting-started)
- [Cloud project files and size quotas](https://www.quantconnect.com/docs/v2/cloud-platform/projects/files)
- [Cloud backtest deployment](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/deployment)
- [Backtest results and Download Results](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results)
- [Organization tier features](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/tier-features)
- [Cloud Object Store access and storage](https://www.quantconnect.com/docs/v2/cloud-platform/object-store)
- [Algorithm Object Store API](https://www.quantconnect.com/docs/v2/writing-algorithms/object-store)
- [Algorithm parameters](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters)
- [Cloud package environments](https://www.quantconnect.com/docs/v2/cloud-platform/projects/package-environments)
- [QuantConnect Paper Trading](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/quantconnect-paper-trading)
