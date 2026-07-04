// Right-hand catalog sidebar: every downloaded dataset, grouped + searchable, each row with a
// freshness dot, an Update button (disabled when view-only), an "open panel" toggle and a
// "compare" checkbox. This is the "see what we have / what we can update" surface.
import { useMemo, useState } from "react";
import type { CatalogGroup, TrackerMeta } from "../api";

function dotClass(t: TrackerMeta): string {
  if (!t.exists) return "dot dot-missing";
  return t.stale ? "dot dot-stale" : "dot dot-fresh";
}

function Row({
  t,
  open,
  inCompare,
  busy,
  onOpen,
  onCompare,
  onUpdate,
}: {
  t: TrackerMeta;
  open: boolean;
  inCompare: boolean;
  busy: boolean;
  onOpen: () => void;
  onCompare: () => void;
  onUpdate: () => void;
}) {
  return (
    <div className={`cat-row${open ? " cat-row-open" : ""}`}>
      <span className={dotClass(t)} title={t.exists ? (t.stale ? "stale" : "fresh") : "missing"} />
      <button className="cat-label" onClick={onOpen} title="Open / close panel">
        {t.label}
      </button>
      <label className="cat-cmp" title="Add to compare overlay">
        <input type="checkbox" checked={inCompare} onChange={onCompare} />
      </label>
      <button
        className="cat-upd"
        disabled={busy || !t.updatable}
        title={t.updatable ? "Download latest" : "View-only (no downloader)"}
        onClick={onUpdate}
      >
        {busy ? "…" : t.updatable ? "↻" : "—"}
      </button>
    </div>
  );
}

export function Catalog({
  groups,
  openIds,
  compareIds,
  busyId,
  onOpen,
  onCompare,
  onUpdate,
}: {
  groups: CatalogGroup[];
  openIds: Set<string>;
  compareIds: Set<string>;
  busyId: string | null;
  onOpen: (id: string) => void;
  onCompare: (id: string) => void;
  onUpdate: (id: string) => void;
}) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return groups;
    return groups
      .map((g) => ({
        ...g,
        trackers: g.trackers.filter(
          (t) => t.label.toLowerCase().includes(needle) || t.id.toLowerCase().includes(needle),
        ),
      }))
      .filter((g) => g.trackers.length > 0);
  }, [groups, q]);

  const total = groups.reduce((n, g) => n + g.trackers.length, 0);

  return (
    <aside className="catalog">
      <div className="catalog-head">
        <strong>Catalog</strong>
        <span className="muted">{total} datasets</span>
      </div>
      <input className="catalog-search" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="catalog-groups">
        {filtered.map((g) => (
          <details key={g.name} open>
            <summary>
              {g.name} <span className="muted">({g.trackers.length})</span>
            </summary>
            {g.trackers.map((t) => (
              <Row
                key={t.id}
                t={t}
                open={openIds.has(t.id)}
                inCompare={compareIds.has(t.id)}
                busy={busyId === t.id}
                onOpen={() => onOpen(t.id)}
                onCompare={() => onCompare(t.id)}
                onUpdate={() => onUpdate(t.id)}
              />
            ))}
          </details>
        ))}
      </div>
    </aside>
  );
}
