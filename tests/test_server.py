"""Tests for the FastAPI server (routes over the tracker registry)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chainwind.server as server_mod
from chainwind.server import build_app
from tests.conftest import WriteZarr


@pytest.fixture
def client(data_root: Path) -> TestClient:  # data_root writes fresh zarrs under tmp $DATA_ROOT
    return TestClient(build_app(web_dist=None))


def test_list_trackers(client: TestClient) -> None:
    resp = client.get("/api/trackers")
    assert resp.status_code == 200
    trackers = resp.json()["trackers"]
    ids = {t["id"] for t in trackers}
    assert {"btc_ohlcv", "mvrv_zscore", "btc_price"} <= ids
    mvrv = next(t for t in trackers if t["id"] == "mvrv_zscore")
    assert len(mvrv["zones"]) == 4
    assert mvrv["exists"] is True


def test_get_one_tracker(client: TestClient) -> None:
    resp = client.get("/api/trackers/mvrv_zscore")
    assert resp.status_code == 200
    assert resp.json()["id"] == "mvrv_zscore"
    assert "zones" in resp.json()


def test_get_unknown_tracker_404(client: TestClient) -> None:
    assert client.get("/api/trackers/nope").status_code == 404


def test_series_endpoint(client: TestClient) -> None:
    resp = client.get("/api/trackers/mvrv_zscore/series")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_points"] == 1
    assert body["chart_lib"] == "echarts"
    assert len(body["zones"]) == 4


def test_series_unknown_404(client: TestClient) -> None:
    assert client.get("/api/trackers/nope/series").status_code == 404


def test_series_time_window(client: TestClient) -> None:
    # The single fresh point is "now"; an all-past window excludes it.
    resp = client.get("/api/trackers/mvrv_zscore/series", params={"from": 0, "to": 1000})
    assert resp.status_code == 200
    assert resp.json()["n_points"] == 0


def test_update_one_route(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_update(tracker_id: str, force: bool = False) -> dict:
        from chainwind.trackers import get_tracker

        get_tracker(tracker_id)  # raises KeyError on unknown -> 404
        return {"id": tracker_id, "forced": force, "exists": True}

    monkeypatch.setattr(server_mod, "update_tracker", fake_update)
    resp = client.post("/api/trackers/mvrv_zscore/update?force=true")
    assert resp.status_code == 200
    assert resp.json() == {"id": "mvrv_zscore", "forced": True, "exists": True}


def test_update_one_route_unknown_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_update(tracker_id: str, force: bool = False) -> dict:
        from chainwind.trackers import get_tracker

        get_tracker(tracker_id)
        return {}

    monkeypatch.setattr(server_mod, "update_tracker", fake_update)
    assert client.post("/api/trackers/nope/update").status_code == 404


def test_update_all_route(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_mod, "update_all", lambda force=False: [{"id": "x", "forced": force}])
    resp = client.post("/api/update?force=true")
    assert resp.status_code == 200
    assert resp.json() == {"trackers": [{"id": "x", "forced": True}]}


def test_root_without_spa_returns_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the no-SPA path even when a real build exists in the working tree.
    monkeypatch.setattr(server_mod, "_default_web_dist", lambda: None)
    resp = TestClient(build_app(web_dist=None)).get("/")
    assert resp.status_code == 200
    assert "Chainwind API" in resp.json()["message"]


def test_root_serves_spa_when_present(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>spa</title>")
    resp = TestClient(build_app(web_dist=dist)).get("/")
    assert resp.status_code == 200
    assert "spa" in resp.text


def test_catalog_endpoint(client: TestClient) -> None:
    groups = client.get("/api/catalog").json()["groups"]
    assert groups, "catalog should be non-empty"
    all_rows = [t for g in groups for t in g["trackers"]]
    ids = {t["id"] for t in all_rows}
    assert "btc_ohlcv" in ids and "mvrv_zscore" in ids
    # every row carries the catalog metadata the sidebar needs
    row = next(t for t in all_rows if t["id"] == "btc_ohlcv")
    assert {"group", "featured", "updatable", "exists", "stale"} <= set(row)
    assert row["updatable"] is True


def test_combined_endpoint(client: TestClient) -> None:
    body = client.get("/api/combined", params={"ids": "btc_ohlcv,mvrv_zscore"}).json()
    series = body["series"]
    assert {s["id"] for s in series} == {"btc_ohlcv", "mvrv_zscore"}
    for s in series:
        assert len(s["time"]) == len(s["values"])


def test_combined_skips_unknown_ids(client: TestClient) -> None:
    body = client.get("/api/combined", params={"ids": "btc_ohlcv,nope"}).json()
    assert [s["id"] for s in body["series"]] == ["btc_ohlcv"]


def test_update_view_only_returns_400(client: TestClient, data_root: Path, write_zarr: WriteZarr) -> None:
    # Seed a derived (view-only) dataset, then attempt to update it.
    zp = data_root / "traidwind" / "macro" / "dominance" / "btc_dominance.zarr"
    write_zarr(zp, [[55.0]], [1_700_000_000_000], ["dominance"])
    resp = client.post("/api/trackers/dominance-btc_dominance/update")
    assert resp.status_code == 400
    assert "view-only" in resp.json()["detail"]


def test_serve_invokes_uvicorn(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    captured: dict = {}

    def fake_run(app: object, host: str = "", port: int = 0) -> None:
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    server_mod.serve(host="127.0.0.1", port=8799, open_browser=False)
    assert captured == {"host": "127.0.0.1", "port": 8799}
