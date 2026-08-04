# AI Quant Lab

LLM/ML-driven quant strategy research for the Korean stock market (KRX).
**MVP scope: backtest only.** See [`docs/PRD.md`](docs/PRD.md) for the full product spec.

> ⚠️ Research tool, not investment advice. Backtest results are not indicative of
> future returns.

---

## What this is

Turn a natural-language strategy idea into a **leak-proof factor expression**,
optionally boost it with a **cross-sectional ML rank model**, backtest it against
**point-in-time KRX data**, and get a report with **multiple-testing-aware**
performance metrics (Deflated Sharpe, shuffle control) — all from the CLI.

The guiding constraint: the biggest risk isn't bugs, it's **self-deception** from
running many strategies. So look-ahead is prevented *by design*, and research
integrity (trial logging, DSR, holdout locking) is enforced *by structure*, not
discipline. See PRD §0.

## Status

| Milestone | Scope | State |
|-----------|-------|-------|
| **M0** | Repo skeleton, `DataSource` abstraction, pykrx source, raw+factor cache, PIT universe, data-integrity filters | ✅ done |
| **M1** | Leak-proof primitives, target-weight backtest engine (validated), research-integrity infra (DSR/shuffle/trial-log/holdout), 7 hand-crafted strategies | ✅ done |
| **M2** | LLM → factor DSL (whitelist AST over the primitive registry), YAML 2-layer config, rebalance cadence | ✅ done |
| M3 | ML rank prediction (LightGBM) | ⬜ next |

Engine validation gate (F4.7) is green: golden-value arithmetic + exact
cap-weighted index reconstruction. Run `quantlab demo` for the M1 pipeline or
`quantlab strategy examples/momentum_volume.yaml` for the M2 DSL path — both on
synthetic data. 82 tests, network-free.

## Layout

```
src/quantlab/
  config.py            settings, cost model (F4.2)
  types.py             Market, UniverseSpec, date helpers
  data/                # M0
    source.py          DataSource ABC (F1.3) — vendor-agnostic
    pykrx_source.py    live KRX impl (F1.1)
    adjust.py          raw + factor adjustment (DQ.1)
    filters.py         preferred/spac/reit/etf exclusion (DQ.3)
    cache.py           parquet cache + read-through PriceStore (F1.2/F1.4)
    universe.py        point-in-time universe reconstruction (§11)
  factors/             # M1 core — the shared leak-proof primitives
    primitives.py      point-in-time ts/cross-sectional operators
    portfolio.py       alpha -> long-only target weights
  backtest/            # M1
    engine.py          target-weight matrix engine, t+1, drift, cost (F4)
    metrics.py         CAGR/MDD/Sharpe/Sortino + Rank IC (F5.1/F3.5)
    result.py          BacktestResult
  integrity/           # M1 — research integrity (F7)
    dsr.py             Deflated Sharpe + effective-N clustering (F7.2)
    shuffle.py         shuffle control / empirical p-value (F7.4)
    trials.py          automatic trial logging (F7.1)
    holdout.py         holdout vault + audit log (F7.5)
  strategies/          # M1 — 7 hand-crafted factors -> DSL vocabulary
  dsl/                 # M2 — natural language -> factor DSL
    parser.py          whitelist AST interpreter (F2.3/F2.4) — look-ahead impossible
    config.py          YAML 2-layer StrategyConfig (F2.1), content hash (F2.5)
    runner.py          config -> target weights (rebalance cadence)
    llm.py             NL -> DSL via Anthropic (lazy), validate-and-retry
  demo.py              full-pipeline demo on synthetic data
  cli.py               `quantlab` CLI (F6)
tests/                 network-free (Fake data + scripted LLM), 82 tests
```

## Install

```bash
uv venv --python 3.11 .venv
uv pip install -e ".[dev]"          # core + test deps
uv pip install -e ".[data]"         # + pykrx / FinanceDataReader (live KRX)
```

## Use

```bash
.venv/bin/quantlab info                          # show settings & cost model
.venv/bin/quantlab demo --strategy momentum_volume_combo   # full M1 pipeline, synthetic data
.venv/bin/quantlab data universe 2024-03-15 \    # PIT universe for a date (needs [data])
    --top 300 --min-turnover 5e8
```

`demo` runs a hand-crafted strategy end-to-end (weights → backtest → metrics →
shuffle control → trial log). On synthetic random data every strategy is
correctly **discarded** by the shuffle test (p ≥ 0.05) — the integrity layer
refusing to bless noise is the point.

## Test

```bash
.venv/bin/pytest          # runs without network (FakeDataSource)
```
