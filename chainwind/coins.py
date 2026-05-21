"""Coin registry — :class:`CoinSpec` and the builtin set used by the UI's coin picker.

A :class:`CoinSpec` is a lightweight description of a coin the UI knows how to fetch and display.
Symbol is the canonical id (uppercase ticker — ``"BTC"``); :attr:`coingecko_id` and
:attr:`default_pair` are the external identifiers downstream code uses to query CoinGecko and the
exchange APIs respectively.

The builtin list intentionally stays small — applications add their own coins by extending
:data:`BUILTIN_COINS` or building a YAML-driven registry on top.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CoinSpec:
    """Static metadata for a single coin."""

    symbol: str
    name: str
    coingecko_id: str
    default_pair: str
    default_exchange: str = "binance"
    default_market_type: str = "spot"


BUILTIN_COINS: tuple[CoinSpec, ...] = (
    CoinSpec(
        symbol="BTC", name="Bitcoin", coingecko_id="bitcoin", default_pair="BTC/USDT"
    ),
    CoinSpec(
        symbol="ETH", name="Ethereum", coingecko_id="ethereum", default_pair="ETH/USDT"
    ),
    CoinSpec(
        symbol="SOL", name="Solana", coingecko_id="solana", default_pair="SOL/USDT"
    ),
)


def list_coins() -> tuple[CoinSpec, ...]:
    """Return the builtin coin registry as an immutable tuple."""
    return BUILTIN_COINS


def get_coin(symbol: str) -> CoinSpec:
    """Look up a builtin coin by symbol (case-insensitive)."""
    target = symbol.strip().upper()
    for coin in BUILTIN_COINS:
        if coin.symbol == target:
            return coin
    raise KeyError(
        f"Unknown coin symbol {symbol!r}. Known: {[c.symbol for c in BUILTIN_COINS]}"
    )
