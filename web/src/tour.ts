/**
 * Shape of one solved CVRPTW instance, plus the invariant check the replay needs.
 *
 * These types used to live inside `DeliveryReplay.tsx`, which was fine while the
 * only tour was the one frozen into `src/data/delivery-tour.json`. Now that a
 * tour can also arrive from `POST /api/solve`, the shape is a contract between
 * three places (the renderer, the transport, the mock) and belongs on its own.
 *
 * `validateTour` exists because the renderer trusts this data completely: it
 * indexes `legMetrics[v.id]`, assumes `stops[].arrive` is sorted so it can binary
 * search, and divides by `horizon`. A malformed payload does not throw, it draws
 * a blank or frozen canvas, which is the worst possible failure for a demo. So
 * the payload is checked once, before it ever reaches the canvas.
 */

export type StopKind = 'depot' | 'customer' | 'hub' | 'reload';

export interface Stop {
  node: number;
  kind: StopKind;
  lat: number;
  lng: number;
  arrive: number;
  service: number;
  depart: number;
  load: number;
  twEnd: number;
}

export interface Leg {
  depart: number;
  arrive: number;
  meters: number;
  road: boolean;
  pts: [number, number][];
}

export interface Vehicle {
  id: number;
  capacity: number;
  served: number;
  start: number;
  end: number;
  stops: Stop[];
  legs: Leg[];
}

export interface TourStats {
  customers: number;
  customersServed: number;
  vehicles: number;
  capacity: number;
  roadKm: number;
  horizon: number;
  cumulativeDriveTime: number;
  tardinessMinutes: number;
  hubsAvailable: number;
  hubsActivated: number;
  reloads: number;
  hubFlybys: number;
  timeWindowsBinding: boolean;
}

export interface Tour {
  meta: Record<string, string | number>;
  bounds: { minLat: number; maxLat: number; minLng: number; maxLng: number };
  depot: { lat: number; lng: number };
  hubs: { node: number; lat: number; lng: number }[];
  customers: { node: number; lat: number; lng: number; twEnd: number }[];
  vehicles: Vehicle[];
  horizon: number;
  stats: TourStats;
  reloadEvents: { vehicle: number; at: number; from: number; to: number }[];
}

/** `horizon` and `max(vehicle.end)` may disagree by this much and still be fine:
 *  a second of dead air at the end of the replay is invisible. */
const HORIZON_TOLERANCE_SECONDS = 2;

const STAT_KEYS = [
  'customers',
  'customersServed',
  'vehicles',
  'capacity',
  'roadKm',
  'horizon',
  'cumulativeDriveTime',
  'tardinessMinutes',
  'hubsAvailable',
  'hubsActivated',
  'reloads',
] as const;

function num(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Returns `null` when the payload can safely be handed to the renderer, or a
 * short reason why it cannot. The reason is developer-facing: the UI reports a
 * generic solver failure and keeps the tour already on screen.
 */
export function validateTour(value: unknown): string | null {
  if (!value || typeof value !== 'object') return 'not an object';
  const t = value as Partial<Tour>;

  const b = t.bounds;
  if (!b || !num(b.minLat) || !num(b.maxLat) || !num(b.minLng) || !num(b.maxLng)) {
    return 'bounds missing';
  }
  if (b.maxLat <= b.minLat || b.maxLng <= b.minLng) return 'degenerate bounds';

  if (!t.depot || !num(t.depot.lat) || !num(t.depot.lng)) return 'depot missing';
  if (!Array.isArray(t.hubs)) return 'hubs missing';
  if (!Array.isArray(t.customers) || t.customers.length === 0) return 'no customers';
  if (!Array.isArray(t.vehicles) || t.vehicles.length === 0) return 'no vehicles';
  if (!Array.isArray(t.reloadEvents)) return 'reloadEvents missing';

  const stats = t.stats as Record<string, unknown> | undefined;
  if (!stats) return 'stats missing';
  for (const key of STAT_KEYS) if (!num(stats[key])) return `stats.${key} not a number`;

  const served = new Set<number>();
  let maxEnd = 0;

  for (let i = 0; i < t.vehicles.length; i++) {
    const v = t.vehicles[i];
    // The renderer indexes `legMetrics[v.id]`, so ids must be positional.
    if (v.id !== i) return `vehicle ${i} has id ${v.id}`;
    if (!num(v.capacity) || v.capacity <= 0) return `vehicle ${i} capacity`;
    if (!Array.isArray(v.stops) || v.stops.length < 2) return `vehicle ${i} needs 2 stops`;
    if (!Array.isArray(v.legs) || v.legs.length !== v.stops.length - 1) {
      return `vehicle ${i} legs do not match stops`;
    }

    let previousArrive = -Infinity;
    for (const s of v.stops) {
      if (!num(s.arrive) || !num(s.lat) || !num(s.lng) || !num(s.load)) {
        return `vehicle ${i} malformed stop`;
      }
      // Binary search in `vehicleStateAt` requires this ordering.
      if (s.arrive < previousArrive) return `vehicle ${i} stops out of order`;
      previousArrive = s.arrive;
      if (s.kind === 'customer') served.add(s.node);
    }

    for (const leg of v.legs) {
      if (!Array.isArray(leg.pts) || leg.pts.length === 0) return `vehicle ${i} empty leg`;
      const p = leg.pts[0];
      if (!Array.isArray(p) || !num(p[0]) || !num(p[1])) return `vehicle ${i} malformed leg point`;
    }

    if (!num(v.end)) return `vehicle ${i} end`;
    maxEnd = Math.max(maxEnd, v.end);
  }

  if (!num(t.horizon) || t.horizon <= 0) return 'horizon missing';
  if (Math.abs(t.horizon - maxEnd) > HORIZON_TOLERANCE_SECONDS) {
    return `horizon ${t.horizon} but last vehicle ends at ${maxEnd}`;
  }

  // A customer nobody visits is a legitimate result (an infeasible instance drops
  // some), and the map draws it as pending, which is the honest picture. What is
  // *not* survivable is a customer list that matches no stop at all: that means
  // the nodes are keyed differently and every dot would stay grey forever.
  for (const c of t.customers) {
    if (!num(c.node) || !num(c.lat) || !num(c.lng)) return 'malformed customer';
  }
  if (served.size > 0 && !t.customers.some((c) => served.has(c.node))) {
    return 'customer nodes match no stop';
  }

  return null;
}
