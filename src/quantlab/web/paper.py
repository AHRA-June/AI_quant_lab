"""Paper trading — track a strategy/screen's target weights forward.

A **paper portfolio** freezes a set of target holdings (ticker, name, weight,
entry price) at an entry date and a notional cash amount, sizes them into
(fractional) shares as a fully-invested equal-weight book, and then *marks to
market* on demand by re-querying prices from an injectable :class:`DataSource`.

This reuses the same seams as the rest of the web layer:

* the source is injectable, so tests drive a fake and stay network-free;
* CSV-originated portfolios **pin** their source file (copy + sha256) so marking
  is fully offline and reproducible — exactly like :func:`quantlab.web.repro.pin_file`;
* KRX-originated portfolios re-query live pykrx (the holdings *are* the basket).

Marking is buy-and-hold: value = Σ shares·price, so position weights drift with
prices — the honest behaviour of a real held book, not a re-balanced index.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

# Default book size: 10,000,000 KRW (1천만원) — a round, relatable amount.
DEFAULT_NOTIONAL = 10_000_000.0
PIN_DIR = "pinned"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class PaperHolding:
    """One position in a paper book, sized at entry and (optionally) marked."""

    ticker: str
    name: str
    weight: float                # target weight at entry (sums to ~1 across holdings)
    entry_price: float           # adjusted close at the entry date
    shares: float                # notional * weight / entry_price (fractional allowed)
    # mark-to-market state (filled by mark_paper; None until first marked)
    last_price: float | None = None
    priced: bool = True          # False when the mark found no data for this ticker

    @property
    def entry_value(self) -> float:
        return self.shares * self.entry_price

    @property
    def market_value(self) -> float:
        """Current position value; falls back to entry value when unpriced."""
        px = self.last_price if (self.last_price is not None) else self.entry_price
        return self.shares * px

    @property
    def pnl_pct(self) -> float | None:
        if self.last_price is None or self.entry_price <= 0:
            return None
        return self.last_price / self.entry_price - 1.0


@dataclass
class PaperPortfolio:
    """A forward-tracked paper book. Mutable (marks overwrite) — UX state, not an
    integrity-critical log, so rewriting its JSON in place is fine."""

    id: str
    created_at: str
    name: str
    kind: str                    # "csv" | "krx" — how to reconstruct a price source
    origin_run_id: str           # the screen run this book was opened from
    entry_date: str              # YYYY-MM-DD (the screen's reference date)
    notional: float
    holdings: list[PaperHolding]
    note: str = ""
    data_ref: str | None = None  # pinned CSV filename (csv only)
    ticker_col: str = "Name"
    # mark-to-market state
    marked_at: str | None = None
    mark_date: str | None = None

    # --- derived ----------------------------------------------------------
    @property
    def market_value(self) -> float:
        return sum(h.market_value for h in self.holdings)

    @property
    def pnl_pct(self) -> float | None:
        if self.marked_at is None or self.notional <= 0:
            return None
        return self.market_value / self.notional - 1.0

    @property
    def n_holdings(self) -> int:
        return len(self.holdings)

    # --- (de)serialisation ------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)             # dataclass → nested dicts (holdings included)
        return d

    @staticmethod
    def from_dict(d: dict) -> "PaperPortfolio":
        holdings = [PaperHolding(**h) for h in d.get("holdings", [])]
        d = {**d, "holdings": holdings}
        return PaperPortfolio(**d)

    @staticmethod
    def new_id(created_at: str) -> str:
        # A short random suffix keeps ids unique even when two books are opened
        # within the same second (the timestamp is second-resolution).
        import uuid

        stamp = (created_at.replace("-", "").replace(":", "")
                 .replace("+0000", "").replace("T", "-"))
        return f"{stamp}-{uuid.uuid4().hex[:6]}-paper"[:64]


class PaperStore:
    """Filesystem registry of paper portfolios under ``<base>/paper/<id>/``.

    Unlike the append-only run/trial logs, a portfolio is *mutable* (marking
    updates it), so each one is a standalone ``portfolio.json`` rewritten in
    place; the list is a glob over those files.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self.base = Path(base_dir)
        self.root = self.base / "paper"
        self.root.mkdir(parents=True, exist_ok=True)

    def dir(self, pid: str) -> Path:
        d = self.root / pid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _file(self, pid: str) -> Path:
        return self.root / pid / "portfolio.json"

    def save(self, p: PaperPortfolio) -> None:
        self.dir(p.id)
        self._file(p.id).write_text(
            json.dumps(p.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, pid: str) -> PaperPortfolio | None:
        f = self._file(pid)
        if not f.exists():
            return None
        return PaperPortfolio.from_dict(json.loads(f.read_text(encoding="utf-8")))

    def list(self) -> list[PaperPortfolio]:
        """All portfolios, newest first."""
        out: list[PaperPortfolio] = []
        for f in self.root.glob("*/portfolio.json"):
            try:
                out.append(PaperPortfolio.from_dict(json.loads(f.read_text(encoding="utf-8"))))
            except Exception:  # noqa: BLE001 — skip a corrupt file rather than break the list
                continue
        out.sort(key=lambda p: p.created_at, reverse=True)
        return out

    def delete(self, pid: str) -> bool:
        d = self.root / pid
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True


def open_from_screen(
    run_store,
    paper_store: PaperStore,
    run_id: str,
    *,
    notional: float = DEFAULT_NOTIONAL,
    name: str | None = None,
    kind: str = "csv",
    csv_path: str | Path | None = None,
    ticker_col: str = "Name",
) -> PaperPortfolio:
    """Open a paper book from a screen run's matching stocks (equal-weight).

    Reads the persisted ``screen.json`` snapshot (ticker, name, entry close at the
    reference date), sizes each match to ``notional / n`` at its entry price, and
    persists a :class:`PaperPortfolio`. For ``kind == "csv"`` the source CSV is
    pinned into the portfolio dir so future marks need no external file.
    """
    from quantlab.web.service import read_screen

    rec = run_store.get(run_id)
    snap = read_screen(run_store, run_id)
    if rec is None or snap is None:
        raise ValueError("종목 찾기 결과를 찾을 수 없습니다")
    matches = [m for m in snap.get("matches", []) if float(m.get("close") or 0) > 0]
    if not matches:
        raise ValueError("담을 종목이 없습니다 (매칭 종목이 없거나 진입가가 없습니다)")

    n = len(matches)
    w = 1.0 / n
    holdings = [
        PaperHolding(
            ticker=str(m["ticker"]),
            name=str(m.get("name") or m["ticker"]),
            weight=w,
            entry_price=float(m["close"]),
            shares=(notional * w) / float(m["close"]),
        )
        for m in matches
    ]

    created = _now_iso()
    pid = PaperPortfolio.new_id(created)
    portfolio = PaperPortfolio(
        id=pid, created_at=created,
        name=name or (rec.strategy or "종이 포트폴리오"),
        kind=kind, origin_run_id=run_id,
        entry_date=str(snap.get("ref_date") or ""),
        notional=float(notional), holdings=holdings,
        note=str(snap.get("expr") or ""), ticker_col=ticker_col,
    )

    if kind == "csv":
        if not csv_path or not Path(csv_path).exists():
            raise ValueError("CSV 원본을 찾을 수 없어 종이 포트폴리오를 만들 수 없습니다 "
                             "(마킹에 필요) — 스크린을 다시 실행해 주세요.")
        pin_dir = paper_store.dir(pid) / PIN_DIR
        pin_dir.mkdir(parents=True, exist_ok=True)
        dest = pin_dir / Path(csv_path).name
        shutil.copyfile(csv_path, dest)
        portfolio.data_ref = dest.name

    paper_store.save(portfolio)
    return portfolio


def _build_source(paper_store: PaperStore, p: PaperPortfolio):
    """Reconstruct a price :class:`DataSource` for marking, by kind.

    ``csv`` rebuilds a :class:`CsvDataSource` from the pinned copy (offline).
    ``krx`` needs live pykrx — importable only when the ``data`` extra is present.
    """
    if p.kind == "csv":
        from quantlab.data.csv_source import CsvDataSource

        if not p.data_ref:
            raise ValueError("핀된 CSV가 없어 마킹할 수 없습니다")
        pinned = paper_store.root / p.id / PIN_DIR / p.data_ref
        if not pinned.exists():
            raise ValueError("핀된 CSV 파일을 찾을 수 없습니다")
        return CsvDataSource.from_csv(pinned, ticker_col=p.ticker_col)
    if p.kind == "krx":
        from quantlab.data.pykrx_source import PykrxDataSource

        return PykrxDataSource()
    raise ValueError(f"알 수 없는 데이터 종류: {p.kind!r}")


def mark_paper(
    paper_store: PaperStore,
    pid: str,
    *,
    source=None,
    mark_date: date | str | None = None,
) -> PaperPortfolio:
    """Mark a paper book to market by re-querying adjusted prices.

    For each holding the latest adjusted close on/before ``mark_date`` (default:
    the last available date) becomes ``last_price``; a ticker with no data is left
    unpriced (held flat at entry) and flagged. ``source`` is injectable — tests
    pass a fake; the web layer passes a live/pinned source (see :func:`_build_source`).
    Persists and returns the updated portfolio.
    """
    p = paper_store.get(pid)
    if p is None:
        raise ValueError("종이 포트폴리오를 찾을 수 없습니다")
    if source is None:
        source = _build_source(paper_store, p)

    entry = date.fromisoformat(p.entry_date) if p.entry_date else date(1990, 1, 1)
    if mark_date is None:
        end = date.today()
    elif isinstance(mark_date, str):
        end = date.fromisoformat(mark_date)
    else:
        end = mark_date
    if end < entry:
        raise ValueError("평가일이 진입일보다 앞설 수 없습니다")

    for h in p.holdings:
        try:
            s = source.get_adjusted_close(h.ticker, entry, end)
        except Exception:  # noqa: BLE001 — a dead/halted ticker just stays unpriced
            s = None
        if s is not None and len(s.dropna()) > 0:
            h.last_price = float(s.dropna().iloc[-1])
            h.priced = True
        else:
            h.last_price = None
            h.priced = False

    p.marked_at = _now_iso()
    p.mark_date = f"{end:%Y-%m-%d}"
    paper_store.save(p)
    return p
