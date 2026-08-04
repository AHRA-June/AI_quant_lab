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

## Status — M0 (data layer scaffolding)

| Milestone | Scope | State |
|-----------|-------|-------|
| **M0** | Repo skeleton, `DataSource` abstraction, pykrx source, raw+factor cache, PIT universe, data-integrity filters | ✅ in progress |
| M1 | Leak-proof primitives, target-weight backtest engine, research-integrity infra | ⬜ |
| M2 | LLM → factor DSL | ⬜ |
| M3 | ML rank prediction (LightGBM) | ⬜ |

## Layout

```
src/quantlab/
  config.py            settings, cost model (F4.2)
  types.py             Market, UniverseSpec, date helpers
  data/
    source.py          DataSource ABC (F1.3) — vendor-agnostic
    pykrx_source.py    live KRX impl (F1.1)
    adjust.py          raw + factor adjustment (DQ.1)
    filters.py         preferred/spac/reit/etf exclusion (DQ.3)
    cache.py           parquet cache + read-through PriceStore (F1.2/F1.4)
    universe.py        point-in-time universe reconstruction (§11)
  cli.py               `quantlab` CLI (F6)
tests/                 network-free (FakeDataSource)
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
.venv/bin/quantlab data universe 2024-03-15 \    # PIT universe for a date (needs [data])
    --top 300 --min-turnover 5e8
```

## Test

```bash
.venv/bin/pytest          # runs without network (FakeDataSource)
```
