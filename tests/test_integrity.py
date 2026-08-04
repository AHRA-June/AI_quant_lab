"""Research-integrity infrastructure (F7)."""

import numpy as np
import pandas as pd
import pytest

from quantlab.integrity.dsr import (
    deflated_sharpe_ratio,
    effective_num_trials,
    expected_max_sharpe,
)
from quantlab.integrity.holdout import HoldoutAccessError, HoldoutVault
from quantlab.integrity.shuffle import shuffle_pvalue
from quantlab.integrity.trials import TrialLog


# --- DSR (F7.2) ------------------------------------------------------------


def test_expected_max_sharpe_grows_with_trials():
    lo = expected_max_sharpe(var_sharpe=0.01, n_trials=10)
    hi = expected_max_sharpe(var_sharpe=0.01, n_trials=1000)
    assert 0 < lo < hi  # more trials -> higher expected max under the null


def test_dsr_penalizes_more_trials():
    common = dict(var_sharpe=0.01, n_obs=1000, skew=0.0, kurtosis=3.0)
    few = deflated_sharpe_ratio(0.12, n_trials=5, **common)
    many = deflated_sharpe_ratio(0.12, n_trials=5000, **common)
    assert few > many  # same Sharpe is less impressive after many trials


def test_effective_num_trials_collapses_correlated():
    idx = pd.RangeIndex(200)
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(size=200), index=idx)
    df = pd.DataFrame(
        {
            "a": base,
            "a_dup": base + rng.normal(0, 1e-3, size=200),  # ~identical to a
            "b": pd.Series(rng.normal(size=200), index=idx),  # independent
        }
    )
    # 3 raw trials, but a/a_dup collapse -> 2 effective.
    assert effective_num_trials(df, corr_threshold=0.7) == 2


# --- shuffle control (F7.4) -----------------------------------------------


def test_shuffle_detects_real_vs_noise_signal():
    idx = pd.bdate_range("2024-01-01", periods=60)
    cols = [f"S{i}" for i in range(20)]
    rng = np.random.default_rng(1)
    fwd = pd.DataFrame(rng.normal(size=(60, 20)), index=idx, columns=cols)

    # A genuinely predictive signal: correlated with forward returns.
    real = fwd + rng.normal(0, 0.5, size=(60, 20))
    # A pure-noise signal.
    noise = pd.DataFrame(rng.normal(size=(60, 20)), index=idx, columns=cols)

    def mean_ic(sig):
        ic = sig.corrwith(fwd, axis=1)
        return float(ic.mean())

    real_res = shuffle_pvalue(real, mean_ic, n_shuffles=50, seed=0)
    noise_res = shuffle_pvalue(noise, mean_ic, n_shuffles=50, seed=0)

    assert real_res.survives  # p < 0.05
    assert not noise_res.survives  # indistinguishable from shuffled null


# --- trial logging (F7.1) -------------------------------------------------


def test_trial_log_counts_success_and_failure(tmp_path):
    log = TrialLog(tmp_path / "trials.jsonl", clock=lambda: "T")

    with log.run("hash1") as r:
        r["metrics"] = {"sharpe": 1.2}

    with pytest.raises(ValueError):
        with log.run("hash2"):
            raise ValueError("boom")

    assert log.count() == 2  # failure still counted (matters for DSR N)
    records = log.load()
    assert records[0]["status"] == "ok" and records[0]["metrics"]["sharpe"] == 1.2
    assert records[1]["status"] == "failed" and "boom" in records[1]["error"]


# --- holdout vault (F7.5) -------------------------------------------------


def test_holdout_guard_blocks_normal_path(tmp_path):
    vault = HoldoutVault("2024-01-01", "2024-06-30", tmp_path / "audit.jsonl")
    vault.guard("2020-01-01", "2023-12-31")  # before holdout: fine
    with pytest.raises(HoldoutAccessError):
        vault.guard("2023-06-01", "2024-02-01")  # overlaps holdout: blocked


def test_holdout_unlock_audits_and_warns_on_repeat(tmp_path):
    audit = tmp_path / "audit.jsonl"
    vault = HoldoutVault("2024-01-01", "2024-06-30", audit)

    vault.unlock("stratX", "final validation")
    assert len(vault._audit()) == 1

    with pytest.warns(UserWarning):
        vault.unlock("stratX", "peeking again")
    records = vault._audit()
    assert records[-1]["access_index"] == 2
