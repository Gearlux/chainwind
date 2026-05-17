"""Tests for :mod:`chainwind.cli`."""

from chainwind.cli import app, list_coins_cmd


def test_list_coins_cmd_prints_registry(capsys) -> None:  # type: ignore[no-untyped-def]
    list_coins_cmd()
    captured = capsys.readouterr().out
    assert "BTC" in captured
    assert "ETH" in captured
    assert "SOL" in captured
    assert "bitcoin" in captured
    assert "coin(s) registered" in captured


def test_app_registered_with_correct_name() -> None:
    assert app.name == "chainwind"
