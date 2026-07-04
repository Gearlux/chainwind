// Typed client for the chainwind FastAPI surface (chainwind/server.py).

export interface Zone {
  lo: number | null;
  hi: number | null;
  color: string;
  label: string;
}

export interface TrackerMeta {
  id: string;
  label: string;
  category: "price" | "indicator";
  chart_lib: "lightweight" | "echarts";
  chart_type: "candlestick" | "line";
  unit: string;
  description: string;
  coin: string | null;
  exists: boolean;
  last_ts: string | null;
  age_hours: number | null;
  stale: boolean;
  n_points: number;
  zones: Zone[];
  group: string;
  featured: boolean;
  updatable: boolean;
}

export interface CatalogGroup {
  name: string;
  trackers: TrackerMeta[];
}

export interface PrimarySeries {
  id: string;
  label: string;
  unit: string;
  exists: boolean;
  time: string[];
  values: (number | null)[];
}

export interface Series {
  id: string;
  label: string;
  exists: boolean;
  time: string[];
  columns: Record<string, (number | null)[]>;
  attrs: Record<string, unknown>;
  n_points: number;
  zones: Zone[];
  chart_lib: "lightweight" | "echarts";
  chart_type: "candlestick" | "line";
  unit: string;
}

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return (await resp.json()) as T;
}

export async function fetchTrackers(): Promise<TrackerMeta[]> {
  const data = await jsonOrThrow<{ trackers: TrackerMeta[] }>(await fetch("/api/trackers"));
  return data.trackers;
}

export async function fetchCatalog(): Promise<CatalogGroup[]> {
  const data = await jsonOrThrow<{ groups: CatalogGroup[] }>(await fetch("/api/catalog"));
  return data.groups;
}

export async function fetchSeries(id: string): Promise<Series> {
  return jsonOrThrow<Series>(await fetch(`/api/trackers/${encodeURIComponent(id)}/series`));
}

export async function fetchCombined(ids: string[]): Promise<PrimarySeries[]> {
  const q = encodeURIComponent(ids.join(","));
  const data = await jsonOrThrow<{ series: PrimarySeries[] }>(await fetch(`/api/combined?ids=${q}`));
  return data.series;
}

export async function updateTracker(id: string, force = false): Promise<TrackerMeta> {
  const resp = await fetch(`/api/trackers/${encodeURIComponent(id)}/update?force=${force}`, { method: "POST" });
  if (!resp.ok) {
    // Surface the server's reason (e.g. 400 view-only) rather than a bare status.
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return (await resp.json()) as TrackerMeta;
}
