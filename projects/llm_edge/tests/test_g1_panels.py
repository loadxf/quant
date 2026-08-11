import numpy as np
import pandas as pd
import pytest
from edgelab.g1_panels import _lag_condition


def test_lag_labels_use_the_close_t_return_as_lag_one():
    dates = pd.bdate_range("2026-02-02", periods=8)
    impulse = pd.DataFrame(0.0, index=dates, columns=["A", "B"])
    impulse.loc[dates[2], "A"] = 1.0

    lag1 = _lag_condition(impulse, 1)
    lag2 = _lag_condition(impulse, 2)
    assert lag1.loc[dates[2], "A"] == 1.0
    assert lag2.loc[dates[2], "A"] == 0.0
    assert lag2.loc[dates[3], "A"] == 1.0


@pytest.mark.parametrize("lag", [0, -1, 1.5, True])
def test_lag_condition_rejects_invalid_labels(lag):
    frame = pd.DataFrame(np.zeros((3, 2)))
    with pytest.raises(ValueError, match="positive integer"):
        _lag_condition(frame, lag)
