import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchCatalog,
  fetchCombined,
  updateTracker,
  type CatalogGroup,
  type PrimarySeries,
  type TrackerMeta,
} from "./api";
import { Catalog } from "./components/Catalog";
import { CompareChart } from "./components/CompareChart";
import { TrackerCard } from "./components/TrackerCard";

export default function App() {
  const [groups, setGroups] = useState<CatalogGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openIds, setOpenIds] = useState<string[]>([]); // ordered = panel order
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareSeries, setCompareSeries] = useState<PrimarySeries[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  const reloadCatalog = useCallback(async () => {
    try {
      setGroups(await fetchCatalog());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void reloadCatalog();
  }, [reloadCatalog]);

  // Re-fetch the compare overlay whenever the selection changes.
  useEffect(() => {
    if (compareIds.length === 0) {
      setCompareSeries([]);
      return;
    }
    fetchCombined(compareIds)
      .then(setCompareSeries)
      .catch((e) => setError(String(e)));
  }, [compareIds]);

  const byId = useMemo(() => {
    const m = new Map<string, TrackerMeta>();
    groups?.forEach((g) => g.trackers.forEach((t) => m.set(t.id, t)));
    return m;
  }, [groups]);

  const toggle = (setter: typeof setOpenIds) => (id: string) =>
    setter((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));

  const onUpdate = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await updateTracker(id, false);
      await reloadCatalog();
      if (compareIds.includes(id)) setCompareSeries(await fetchCombined(compareIds));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="layout">
      <main className="canvas">
        <header className="top">
          <h1>Chainwind</h1>
          <span className="muted">crypto trackers &amp; indicators</span>
        </header>
        {error && <div className="error">{error}</div>}

        <section className="card">
          <CompareChart series={compareSeries} />
        </section>

        {openIds.length === 0 && <p className="muted hint">Click a dataset in the catalog → to open its chart here.</p>}
        {openIds.map((id) => {
          const meta = byId.get(id);
          return meta ? <TrackerCard key={id} initial={meta} onClose={() => toggle(setOpenIds)(id)} /> : null;
        })}
      </main>

      {groups && (
        <Catalog
          groups={groups}
          openIds={new Set(openIds)}
          compareIds={new Set(compareIds)}
          busyId={busyId}
          onOpen={toggle(setOpenIds)}
          onCompare={toggle(setCompareIds)}
          onUpdate={onUpdate}
        />
      )}
    </div>
  );
}
