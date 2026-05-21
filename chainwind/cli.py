"""Chainwind CLI.

v0.1.0 scaffold — exposes the ``list-coins`` command. Crypto-specific data verbs (``freshness``,
``update``) and the ``serve`` command are added as the corresponding subsystems land.

NOTE: do not add ``from __future__ import annotations`` here — liquifai's DI inspects the actual
class objects from parameter annotations and PEP 563 string annotations break that lookup.
"""

from chainwind.coins import list_coins
from liquifai import LiquifyApp
from logflow import get_logger

logger = get_logger(__name__)

app = LiquifyApp(name="chainwind", description="crypto-coin data viewer.")


@app.script_command(name="list-coins")
def list_coins_cmd() -> None:
    """Print the builtin coin registry."""
    coins = list_coins()
    width = max(len(c.symbol) for c in coins)
    print(f"{'symbol'.ljust(width)}  name           default_pair       coingecko_id")
    print(f"{'-' * width}  -------------  -----------------  -------------")
    for coin in coins:
        print(
            f"{coin.symbol.ljust(width)}  {coin.name:<13}  {coin.default_pair:<17}  {coin.coingecko_id}"
        )
    print()
    print(f"{len(coins)} coin(s) registered.")


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
