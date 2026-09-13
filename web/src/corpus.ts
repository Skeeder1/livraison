/**
 * The pre-solved corpus, read from the visitor's side.
 *
 * Every configuration the panel can compose is stored at all four budgets,
 * as one file per configuration plus one geometry pack per customer count.
 * Assembling a drawable tour is a merge: the file's stops, times and stats for
 * the chosen budget, the file's customers/depot/hubs, and each leg's points
 * looked up in the pack by the coordinates of its endpoints.
 *
 * The result is byte-for-byte the document the map already draws, so nothing
 * downstream knows the corpus exists. That includes fields this module does
 * not itself interpret (build provenance, future stats): a stored tour is
 * spread through rather than rebuilt field by field, so nothing the bake adds
 * later gets silently dropped here.
 */
import type { Leg, Tour, Vehicle } from './tour';
import { validateTour } from './tour';

export const CORPUS_BASE = '/demos/delivery/corpus';

export interface StoredLeg extends Omit<Leg, 'pts'> { key: string }
export interface StoredVehicle extends Omit<Vehicle, 'legs'> { legs: StoredLeg[] }
export interface StoredTour {
  vehicles: StoredVehicle[];
  horizon: number;
  bounds: Tour['bounds'];
  stats: Tour['stats'];
  reloadEvents: Tour['reloadEvents'];
  serviceTimePerUnit?: number;
  /** Fields neither this module nor `Tour` names (e.g. build provenance) but
   *  which the reference document carries and must survive assembly untouched. */
  [key: string]: unknown;
}
export interface CorpusFile {
  format: 2;
  meta: Record<string, unknown>;
  depot: Tour['depot'];
  customers: Tour['customers'];
  hubs: Tour['hubs'];
  curve: [number, number][];
  budgets: Record<'5' | '15' | '30' | '60', StoredTour | null>;
}
export interface GeometryPack {
  format: 2;
  customers: number;
  legs: Record<string, [number, number][]>;
}

/** Same rule as `corpus.keys.config_key` in the bake, single courier included. */
export function corpusKey(p: {
  customers: number; vehicles: number; hubs: number; capacity: number; timeWindows: boolean;
}): string {
  const hubs = p.vehicles === 1 ? 0 : p.hubs;
  return `c${p.customers}-v${p.vehicles}-h${hubs}-k${p.capacity}-tw${p.timeWindows ? 1 : 0}`;
}

/** Marker the assembled tour carries, so the panel can say "read from store". */
export function isFromCorpus(t: Tour): boolean {
  return (t.meta as Record<string, unknown>)?.corpus === true;
}

export function assembleTour(file: CorpusFile, budget: number, pack: GeometryPack): Tour | null {
  const stored = file.budgets[String(budget) as keyof CorpusFile['budgets']];
  if (!stored) return null;
  const { vehicles: storedVehicles, ...rest } = stored;
  const vehicles: Vehicle[] = storedVehicles.map((v) => ({
    ...v,
    legs: v.legs.map((leg, i): Leg => {
      const pts = pack.legs[leg.key];
      const { key, ...legRest } = leg;
      if (pts && pts.length >= 2) return { ...legRest, pts };
      // Not in the pack: a straight line, and honest about it — the same
      // degradation the live path uses for a leg the router could not snap.
      const a = v.stops[i], b = v.stops[i + 1];
      return { ...legRest, road: false, pts: [[a.lat, a.lng], [b.lat, b.lng]] };
    }),
  }));
  const tour: Tour = {
    ...rest,
    meta: { ...(file.meta as Record<string, string | number>), corpus: true as unknown as number, budgetSeconds: budget },
    depot: file.depot,
    hubs: file.hubs,
    customers: file.customers,
    vehicles,
  } as Tour;
  return validateTour(tour) ? null : tour;
}

const packs = new Map<number, Promise<GeometryPack | null>>();

/** One pack per customer count, fetched once and shared by every configuration of that size. */
export function fetchPack(customers: number, signal?: AbortSignal): Promise<GeometryPack | null> {
  let p = packs.get(customers);
  if (!p) {
    p = fetch(`${CORPUS_BASE}/geometry/c${customers}.json`, { signal })
      .then(async (r) => (r.ok ? ((await r.json()) as GeometryPack) : null))
      .catch(() => null)
      .then((pack) => (pack && pack.format === 2 ? pack : null));
    packs.set(customers, p);
    // A failed fetch must not poison the cache for the rest of the session.
    p.then((pack) => { if (!pack) packs.delete(customers); });
  }
  return p;
}

export async function fetchCorpusFile(
  p: { customers: number; vehicles: number; hubs: number; capacity: number; timeWindows: boolean },
  signal?: AbortSignal,
): Promise<CorpusFile | null> {
  try {
    const r = await fetch(`${CORPUS_BASE}/${corpusKey(p)}.json`, { signal });
    if (!r.ok) return null;
    const file = (await r.json()) as CorpusFile;
    return file.format === 2 && file.budgets ? file : null;
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') throw cause;
    return null;
  }
}
