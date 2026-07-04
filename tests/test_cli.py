"""Tests for :mod:`chainwind.cli`."""

import chainwind.cli as cli_mod
from chainwind.cli import app, catalog_cmd, freshness_cmd, list_coins_cmd, list_trackers_cmd, update_cmd


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


def test_list_trackers_cmd_prints_registry(capsys) -> None:  # type: ignore[no-untyped-def]
    list_trackers_cmd()
    out = capsys.readouterr().out
    assert "btc_ohlcv" in out
    assert "mvrv_zscore" in out
    assert "tracker(s) registered" in out


def test_freshness_cmd_prints_table(data_root, capsys) -> None:  # type: ignore[no-untyped-def]
    freshness_cmd()
    out = capsys.readouterr().out
    assert "id" in out
    assert "btc_ohlcv" in out
    assert "last_ts" in out
    assert "update" in out  # updatable column


def test_catalog_cmd_groups_and_counts(data_root, capsys) -> None:  # type: ignore[no-untyped-def]
    catalog_cmd()
    out = capsys.readouterr().out
    assert "## " in out  # group headers
    assert "btc_ohlcv" in out
    assert "updatable" in out  # the summary footer


def test_update_cmd_named_tracker(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls: dict = {}

    def fake_update(tracker_id: str, force: bool = False) -> dict:
        calls["id"] = tracker_id
        calls["force"] = force
        return {"id": tracker_id, "exists": True, "stale": False, "n_points": 1, "last_ts": None}

    monkeypatch.setattr(cli_mod, "update_tracker", fake_update)
    update_cmd(tracker_id="mvrv_zscore", force=True)
    assert calls == {"id": "mvrv_zscore", "force": True}
    assert "mvrv_zscore" in capsys.readouterr().out


def test_update_cmd_all(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        cli_mod,
        "update_all",
        lambda force=False: [{"id": "a", "exists": True, "stale": False, "n_points": 1, "last_ts": None}],
    )
    update_cmd()
    assert "a" in capsys.readouterr().out


def test_serve_cmd_invokes_server(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from chainwind.cli import serve_cmd

    captured: dict = {}
    monkeypatch.setattr(
        "chainwind.server.serve",
        lambda host="127.0.0.1", port=8770, open_browser=True: captured.update(
            host=host, port=port, open_browser=open_browser
        ),
    )
    serve_cmd(host="127.0.0.1", port=9001, no_browser=True)
    assert captured == {"host": "127.0.0.1", "port": 9001, "open_browser": False}
