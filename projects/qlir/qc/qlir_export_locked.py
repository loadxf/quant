# Q-LIR Gate II locked-data export - paste as ONE QC Research notebook cell.
#
# Run only after qlir_macro_exclusion_audit.py prints PASS. This cell validates
# the frozen retained-count fingerprint and exports the rows without calculating
# or printing any outcome statistic.

import gzip
from base64 import b64encode
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

EXPORT_FILE = Path("qlir_gate2_locked_2021_2024.csv.gz")
EXPECTED_ROWS = 135_252
EXPECTED_RETAINED = {
    (2021, "ES", "A_00_30"): 2_754,
    (2021, "ES", "B_15_45"): 3_227,
    (2021, "ES", "placebo"): 11_006,
    (2021, "NQ", "A_00_30"): 2_754,
    (2021, "NQ", "B_15_45"): 3_227,
    (2021, "NQ", "placebo"): 11_006,
    (2022, "ES", "A_00_30"): 2_751,
    (2022, "ES", "B_15_45"): 3_214,
    (2022, "ES", "placebo"): 10_986,
    (2022, "NQ", "A_00_30"): 2_751,
    (2022, "NQ", "B_15_45"): 3_214,
    (2022, "NQ", "placebo"): 10_986,
    (2023, "ES", "A_00_30"): 2_724,
    (2023, "ES", "B_15_45"): 3_190,
    (2023, "ES", "placebo"): 10_880,
    (2023, "NQ", "A_00_30"): 2_724,
    (2023, "NQ", "B_15_45"): 3_190,
    (2023, "NQ", "placebo"): 10_880,
    (2024, "ES", "A_00_30"): 2_740,
    (2024, "ES", "B_15_45"): 3_202,
    (2024, "ES", "placebo"): 10_952,
    (2024, "NQ", "A_00_30"): 2_740,
    (2024, "NQ", "B_15_45"): 3_202,
    (2024, "NQ", "placebo"): 10_952,
}
REQUIRED_COLUMNS = {
    "date",
    "instrument",
    "boundary_ct",
    "boundary_class",
    "is_quarter",
    "resolution_used",
    "ret_fwd_60s",
    "ret_fwd_120s",
    "ret_fwd_300s",
    "vol_pre_60s",
    "vol_fwd_60s",
    "prevol_5m",
    "postvol_5m",
}

if "locked_events_excluded" not in globals():
    raise RuntimeError("Run the macro-exclusion audit first; its filtered frame is missing.")

export_frame = globals()["locked_events_excluded"].copy()
missing = REQUIRED_COLUMNS - set(export_frame.columns)
if missing:
    raise RuntimeError(f"Filtered frame lacks columns: {sorted(missing)}")
if len(export_frame) != EXPECTED_ROWS:
    raise RuntimeError(f"Expected {EXPECTED_ROWS:,} rows, found {len(export_frame):,}")

export_frame["date"] = export_frame["date"].astype(str)
export_frame["_year"] = pd.to_datetime(
    export_frame["date"], format="%Y-%m-%d", errors="raise"
).dt.year
if set(export_frame["_year"]) != {2021, 2022, 2023, 2024}:
    raise RuntimeError("Export contains a year outside the locked 2021-2024 sample")
if export_frame.duplicated(
    ["date", "instrument", "boundary_ct", "boundary_class"]
).any():
    raise RuntimeError("Export contains duplicate instrument-boundary identities")

actual_retained = export_frame.groupby(
    ["_year", "instrument", "boundary_class"]
).size().to_dict()
if actual_retained != EXPECTED_RETAINED:
    raise RuntimeError(
        "Retained-count fingerprint changed. Refusing export.\n"
        f"Expected: {EXPECTED_RETAINED}\nFound: {actual_retained}"
    )

numeric = export_frame.select_dtypes(include=[np.number])
if not np.isfinite(numeric.to_numpy(dtype="float64")).all():
    raise RuntimeError("Export contains a non-finite numeric value")

export_frame = export_frame.drop(columns="_year").sort_values(
    ["date", "instrument", "boundary_ct"], kind="mergesort"
)
csv_bytes = export_frame.to_csv(
    index=False, lineterminator="\n", float_format="%.17g"
).encode("utf-8")
compressed = gzip.compress(csv_bytes, compresslevel=9, mtime=0)
EXPORT_FILE.write_bytes(compressed)

raw_digest = sha256(csv_bytes).hexdigest()
gzip_digest = sha256(compressed).hexdigest()
print("--- LOCKED EXPORT COMPLETE ---")
print("file:", EXPORT_FILE)
print("rows:", len(export_frame))
print("sessions:", export_frame["date"].nunique())
print("uncompressed bytes:", len(csv_bytes))
print("compressed bytes:", len(compressed))
print("csv sha256:", raw_digest)
print("gzip sha256:", gzip_digest)

try:
    from IPython.display import HTML, display

    download_payload = b64encode(compressed).decode("ascii")
    button_id = "qlir-gate2-download"
    display(
        HTML(
            f'''<button id="{button_id}" type="button">
Download {EXPORT_FILE.name} to this computer
</button>
<span id="{button_id}-status"></span>
<script>
(() => {{
  const button = document.getElementById("{button_id}");
  const status = document.getElementById("{button_id}-status");
  button.onclick = (event) => {{
    event.preventDefault();
    event.stopImmediatePropagation();
    status.textContent = " Preparing download...";
    const binary = atob("{download_payload}");
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {{
      bytes[i] = binary.charCodeAt(i);
    }}
    const blob = new Blob([bytes], {{type: "application/gzip"}});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "{EXPORT_FILE.name}";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    status.textContent = " Download requested.";
  }};
}})();
</script>'''
        )
    )
except ImportError:
    print("Notebook download control unavailable; the export remains at:", EXPORT_FILE)
