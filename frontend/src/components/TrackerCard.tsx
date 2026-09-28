// One tracker panel: title + freshness badge + Update button + its chart.
// Honors chainwind's per-coin freshness UX mandate (badge + one-click download).
import { useCallback, useEffect, useState } from "react";
import { fetchSeries, updateTracker, type Series, type TrackerMeta } from "../api";
import { PriceChart } from "./PriceChart";
import { IndicatorChart } from "./IndicatorChart";

function Badge({ meta }: { meta: TrackerMeta }) {
  const [text, cls] = !meta.exists
    ? ["missing", "badge badge-missing"]
    : meta.stale
      ? ["stale", "badge badge-stale"]
      : ["fresh", "badge badge-fresh"];
  return <span className={cls}>{text}</span>;
}

export function TrackerCard({ initial, onClose }: { initial: TrackerMeta; onClose?: () => void }) {
  const [meta, setMeta] = useState<TrackerMeta>(initial);
  const [series, setSeries] = useState<Series | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSeries(await fetchSeries(meta.id));
    } catch (e) {
      setError(String(e));
    }
  }, [meta.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const onUpdate = async () => {
    setBusy(true);
    setError(null);
    try {
      setMeta(await updateTracker(meta.id, false));
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>{meta.label}</h2>
          <p className="muted">{meta.description}</p>
        </div>
        <div className="card-actions">
          <Badge meta={meta} />
          <button onClick={onUpdate} disabled={busy || !meta.updatable} title={meta.updatable ? "" : "view-only"}>
            {busy ? "Updating…" : meta.updatable ? "Update" : "view-only"}
          </button>
          {onClose && (
            <button className="card-close" onClick={onClose} title="Close panel">
              ✕
            </button>
          )}
        </div>
      </header>
      <div className="card-meta muted">
        {meta.n_points} points{meta.last_ts ? ` · last ${meta.last_ts.slice(0, 10)}` : ""} · {meta.chart_lib}
      </div>
      {error && <div className="error">{error}</div>}
      {series &&
        (series.chart_lib === "echarts" ? <IndicatorChart series={series} /> : <PriceChart series={series} />)}
    </section>
  );
}
