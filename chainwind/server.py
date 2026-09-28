"""Local FastAPI server for the chainwind trackers & indicators UI.

Serves a small JSON API over the tracker registry plus the built React SPA, same-origin:

* ``GET  /api/trackers``                  → registry + per-tracker freshness + zones
* ``GET  /api/trackers/{id}``             → one tracker's freshness + zones
* ``GET  /api/trackers/{id}/series``      → JSON series (``?from=&to=`` epoch-ms bounds)
* ``POST /api/trackers/{id}/update``      → fetch latest values (``?force=`` re-fetches)
* ``POST /api/update``                    → update every tracker

Per chainwind's local-only mandate :func:`serve` binds to ``127.0.0.1`` and opens the
local browser — never ``0.0.0.0``. Requires the ``[http]`` extra (``fastapi`` + ``uvicorn``).
The data/update endpoints reuse :mod:`chainwind.series` and :mod:`chainwind.update`; this
module adds no business logic of its own.
"""

import os
import threading
import webbrowser
from pathlib import Path
from typing import Any, Optional

from loggair import get_logger

from chainwind.series import read_primary_series, read_series, tracker_freshness, zones_payload
from chainwind.trackers import catalog, get_catalog_tracker, is_updatable, list_trackers
from chainwind.update import update_all, update_tracker

logger = get_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770


def _default_web_dist() -> Optional[Path]:
    """Return the built SPA directory if it exists (``chainwind/frontend/dist`` at the repo root).

    Mirrors navigaitor's ``navigaitor/frontend/dist`` convention — the SPA source lives
    beside the package, not inside it, so ``parent.parent`` from this module. The dir name
    ``frontend`` matches the auto-generated CI's ``verify-frontend`` detection.
    """
    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    return dist if dist.is_dir() else None


def _spec_meta(spec: Any) -> dict:
    """Freshness + display metadata for one tracker spec (the per-card / catalog-row payload)."""
    meta = tracker_freshness(spec)
    meta["zones"] = zones_payload(spec)
    meta["group"] = spec.group
    meta["featured"] = spec.featured
    meta["updatable"] = is_updatable(spec)
    return meta


def _tracker_meta(tracker_id: str) -> dict:
    """Freshness + metadata for one tracker, resolved across the full catalog."""
    return _spec_meta(get_catalog_tracker(tracker_id))


def build_app(web_dist: Optional[Path] = None) -> Any:
    """Build the FastAPI app. Pass ``web_dist`` to mount a built SPA at ``/``.

    Mirrors navigaitor's ``build_http_app``: permissive CORS for the Vite dev server, and a
    catch-all static mount registered AFTER the API routes so ``/api/*`` is never shadowed.
    """
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.staticfiles import StaticFiles

    app = FastAPI(title="Chainwind", description="Crypto trackers & indicators viewer.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/trackers")
    def api_trackers() -> dict:
        return {"trackers": [_spec_meta(spec) for spec in list_trackers()]}

    @app.get("/api/catalog")
    def api_catalog() -> dict:
        """Everything discovered on disk + curated, grouped for the sidebar (freshness + updatable)."""
        groups: dict[str, list] = {}
        order: list[str] = []
        for spec in catalog():
            grp = spec.group or "Other"
            if grp not in groups:
                groups[grp] = []
                order.append(grp)
            groups[grp].append(_spec_meta(spec))
        return {"groups": [{"name": g, "trackers": groups[g]} for g in order]}

    @app.get("/api/combined")
    def api_combined(ids: str = Query(""), start_ms: Optional[int] = Query(None, alias="from")) -> dict:
        """Batched primary series for the compare overlay (``?ids=a,b,c``)."""
        out = []
        for tid in [t for t in ids.split(",") if t.strip()]:
            try:
                spec = get_catalog_tracker(tid.strip())
            except KeyError:
                continue
            out.append(read_primary_series(spec, start_ms=start_ms))
        return {"series": out}

    @app.get("/api/trackers/{tracker_id}")
    def api_tracker(tracker_id: str) -> dict:
        try:
            return _tracker_meta(tracker_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/trackers/{tracker_id}/series")
    def api_series(
        tracker_id: str,
        start_ms: Optional[int] = Query(None, alias="from"),
        end_ms: Optional[int] = Query(None, alias="to"),
    ) -> dict:
        try:
            spec = get_catalog_tracker(tracker_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        payload = read_series(spec, start_ms=start_ms, end_ms=end_ms)
        payload["zones"] = zones_payload(spec)
        payload["chart_lib"] = spec.chart_lib
        payload["chart_type"] = spec.chart_type
        payload["unit"] = spec.unit
        return payload

    @app.post("/api/trackers/{tracker_id}/update")
    def api_update_one(tracker_id: str, force: bool = False) -> dict:
        try:
            return update_tracker(tracker_id, force=force)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:  # view-only tracker
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/update")
    def api_update_all(force: bool = False) -> dict:
        return {"trackers": update_all(force=force)}

    if web_dist is None:
        web_dist = _default_web_dist()
    if web_dist is not None:
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
    else:

        @app.get("/")
        def _no_spa() -> dict:
            return {
                "message": "Chainwind API is running. Build the UI with "
                "`cd chainwind/frontend && npm ci && npm run build`, then restart.",
                "api": ["/api/trackers", "/api/trackers/{id}/series"],
            }

    return app


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Run the local UI server (blocking). Binds to ``127.0.0.1`` and opens the browser.

    Host/port also fall back to ``CHAINWIND_HTTP_HOST`` / ``CHAINWIND_HTTP_PORT``.
    """
    import uvicorn

    host = os.environ.get("CHAINWIND_HTTP_HOST", host)
    port = int(os.environ.get("CHAINWIND_HTTP_PORT", str(port)))
    if _default_web_dist() is None:
        logger.warning(
            "[serve] no built SPA at chainwind/frontend/dist — serving API only; "
            "run `npm run build` in chainwind/frontend"
        )
    if open_browser:
        url = f"http://{host}:{port}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    logger.info(f"[serve] chainwind UI on http://{host}:{port}")
    uvicorn.run(build_app(), host=host, port=port)
