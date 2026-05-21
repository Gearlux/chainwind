"""Tests for :mod:`chainwind.coins`."""

import pytest

from chainwind.coins import BUILTIN_COINS, CoinSpec, get_coin, list_coins


def test_builtin_registry_is_non_empty() -> None:
    assert len(BUILTIN_COINS) >= 3
    symbols = {c.symbol for c in BUILTIN_COINS}
    assert {"BTC", "ETH", "SOL"}.issubset(symbols)


def test_list_coins_returns_immutable_tuple() -> None:
    result = list_coins()
    assert isinstance(result, tuple)
    assert result is BUILTIN_COINS


def test_get_coin_case_insensitive() -> None:
    btc_upper = get_coin("BTC")
    btc_lower = get_coin("btc")
    btc_padded = get_coin("  BtC  ")
    assert btc_upper is btc_lower is btc_padded
    assert btc_upper.coingecko_id == "bitcoin"
    assert btc_upper.default_pair == "BTC/USDT"


def test_get_coin_unknown_raises_keyerror_with_known_list() -> None:
    with pytest.raises(KeyError) as excinfo:
        get_coin("DOGE")
    msg = str(excinfo.value)
    assert "DOGE" in msg
    assert "BTC" in msg


def test_coin_spec_defaults() -> None:
    eth = get_coin("ETH")
    assert eth.default_exchange == "binance"
    assert eth.default_market_type == "spot"
    assert eth.name == "Ethereum"


def test_coin_spec_is_frozen() -> None:
    btc = get_coin("BTC")
    with pytest.raises(
        Exception
    ):  # dataclass(frozen=True) → FrozenInstanceError (Exception subclass)
        btc.symbol = "ETH"  # type: ignore[misc]


def test_coin_spec_construction() -> None:
    spec = CoinSpec(
        symbol="ADA", name="Cardano", coingecko_id="cardano", default_pair="ADA/USDT"
    )
    assert spec.default_exchange == "binance"
    assert spec.default_market_type == "spot"
