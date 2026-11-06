# Measurement environments

Python environments for marketing mix modelling and geo experiments. There are two because Meridian and CausalPy need different versions of ArviZ, so they can't share one.

| Environment | Python | Use it for |
|---|---|---|
| `meridian/.venv/bin/python` | 3.12 | Marketing mix models (Meridian) and geo experiment design (GeoX) |
| `causal/.venv/bin/python` | 3.12 | Synthetic control, geo-lift analysis and placebo checks (CausalPy) |

## Build

```sh
cd measurement
for e in causal meridian; do
  uv venv --python 3.12 $e/.venv
  uv pip install --python $e/.venv/bin/python -r $e/requirements.lock
done
```

## Check that they work

```sh
causal/.venv/bin/python smoke_test.py causal
meridian/.venv/bin/python smoke_test.py meridian
```

Both use synthetic data and should end with `ALL PASS`. The CausalPy test should recover a known lift of about 20.

NumPy is pinned below 2.4 for CausalPy because a dependency still calls `numpy.row_stack`, which newer NumPy removed.
