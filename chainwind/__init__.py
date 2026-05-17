"""Chainwind — crypto-coin data viewer.

Extends :mod:`traidwind`'s market-agnostic visualization layer with:

- crypto-specific downloaders (CoinGecko, fear/greed, DeFiLlama, Farside ETF flows, MVRV Z-score),
- per-coin metadata (:class:`CoinSpec`) and a builtin registry,
- a freshness reporter that walks the on-disk data tree and lists what is missing or stale,
- a FastAPI extension that mounts coin/freshness/overlay routes onto traidwind's server,
- a React UI with a per-coin tab (OHLCV + indicators + overlays + freshness widget + backtest panel)
  and a portfolio-tab scaffold.

This v0.1.0 release ships only the project scaffolding; downloaders, server routes, and UI follow.
"""

__version__ = "0.1.0"

from chainwind.coins import BUILTIN_COINS, CoinSpec, get_coin, list_coins

__all__ = [
    "CoinSpec",
    "BUILTIN_COINS",
    "get_coin",
    "list_coins",
]
