"""Prove the measurement stack fits real models on synthetic data.

Run with: causal/.venv/bin/python smoke_test.py causal
and: meridian/.venv/bin/python smoke_test.py meridian
"""
import os
import warnings

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd


def causalpy_geo_lift():
    """Synthetic control on made-up markets with a known 20-unit lift. It should recover about 20."""
    import causalpy as cp

    rng = np.random.default_rng(7)
    n, start = 100, 70
    base = np.cumsum(rng.normal(0, 1, n)) + 100
    df = pd.DataFrame({f"m{i}": base * (0.8 + 0.1 * i) + rng.normal(0, 1, n) for i in range(4)})
    df["treated"] = base + rng.normal(0, 1, n)
    df.loc[start:, "treated"] += 20
    result = cp.SyntheticControl(
        df,
        start,
        control_units=[f"m{i}" for i in range(4)],
        treated_units=["treated"],
        model=cp.pymc_models.WeightedSumFitter(
            sample_kwargs={"draws": 1000, "tune": 1000, "chains": 2, "progressbar": False, "random_seed": 7, "target_accept": 0.9}
        ),
    )
    lift = float(result.post_impact.mean().item())
    assert 10 < lift < 30, f"expected about 20, got {lift:.1f}"
    print(f"CausalPy {cp.__version__}: PASS, true lift 20, estimated {lift:.1f}")


def meridian_mmm():
    """A tiny Meridian model on the library's sample data. It tests that fitting runs, not model quality."""
    import meridian
    from meridian.analysis import analyzer
    from meridian.data import test_utils
    from meridian.model import model, spec

    data = test_utils.sample_input_data_revenue(n_geos=5, n_times=30, n_media_times=30, n_media_channels=2, seed=0)
    mmm = model.Meridian(input_data=data, model_spec=spec.ModelSpec())
    mmm.sample_prior(20)
    mmm.sample_posterior(n_chains=1, n_adapt=50, n_burnin=20, n_keep=20, seed=1)
    roi = analyzer.Analyzer(mmm).roi()
    assert np.asarray(roi).size > 0, "no ROI output"
    print(f"Meridian {meridian.__version__}: PASS, fitted a {mmm.n_geos}-geo model and computed ROI")


def geox_import():
    import meridian_geox

    print(f"Meridian GeoX {getattr(meridian_geox, '__version__', 'installed')}: PASS, import only")


if __name__ == "__main__":
    import sys

    steps = {"causal": (causalpy_geo_lift,), "meridian": (meridian_mmm, geox_import)}[sys.argv[1]]
    failed = []
    for step in steps:
        try:
            step()
        except Exception as exc:
            failed.append(step.__name__)
            print(f"{step.__name__}: FAIL, {type(exc).__name__}: {str(exc)[:400]}")
    print("ALL PASS" if not failed else f"FAILED: {', '.join(failed)}")
    raise SystemExit(1 if failed else 0)
