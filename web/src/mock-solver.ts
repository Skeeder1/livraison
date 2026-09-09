/**
 * Development stand-in for `POST /api/solve`, loaded only when a solver is
 * built with `{ mock: true }` (see `solve.ts`). Never bundled otherwise.
 *
 * It is not a solver: it builds a *plausible* tour with a sweep plus nearest
 * neighbour, which is enough to exercise every path the UI has to survive, and
 * enough to make the numbers move in believable directions (more couriers
 * shortens the longest route, a smaller capacity adds reloads, time windows
 * introduce lateness). The geometry is synthetic too: real legs come from OSRM,
 * these are rotated staircases that merely read as streets at this zoom.
 *
 * Two things it does share with the real endpoint, deliberately, because they
 * are what the UI is being built against: the exact JSON shape (checked by
 * `validateTour` on the way out, same as a real response) and a realistic delay.
 *
 * Error states are reachable with `?solve=<code>` on the demo URL, which is how
 * the Playwright suite drives them. The parameter does nothing once the real
 * endpoint is switched on.
 */

import { SolveError, type SolveParams, type SolveErrorCode } from './solve';
import type { Leg, Stop, Tour, Vehicle } from './tour';

/** Metres per second. The frozen tour averages 6.6, cargo bikes on open streets. */
const DRIVE_SPEED = 6.6;
/** Seconds spent handing over one parcel, and reloading a full vehicle. */
const SERVICE_SECONDS = 5;
const RELOAD_SECONDS = 50;
const METERS_PER_LAT_DEGREE = 111_320;

// ─── Randomness ──────────────────────────────────────────────────────────────

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ─── Geometry ────────────────────────────────────────────────────────────────

type Point = [number, number];

function lngMeters(lat: number): number {
  return METERS_PER_LAT_DEGREE * Math.cos((lat * Math.PI) / 180);
}

function metersBetween(a: Point, b: Point): number {
  const kx = lngMeters((a[0] + b[0]) / 2);
  return Math.hypot((b[1] - a[1]) * kx, (b[0] - a[0]) * METERS_PER_LAT_DEGREE);
}

function polylineMeters(pts: Point[]): number {
  let total = 0;
  for (let i = 1; i < pts.length; i++) total += metersBetween(pts[i - 1], pts[i]);
  return total;
}

/** Splits `total` into `n` positive parts of random size. */
function splitRandom(total: number, n: number, rng: () => number): number[] {
  const weights = Array.from({ length: n }, () => rng() + 0.35);
  const sum = weights.reduce((a, b) => a + b, 0);
  return weights.map((w) => (w / sum) * total);
}

/**
 * A path from `a` to `b` that reads as streets rather than a ruler line: a
 * staircase walked in a randomly rotated frame, so the turns land on a plausible
 * diagonal grid instead of a Manhattan one. Length comes out 15 % to 40 % above
 * the straight line, which is roughly the detour factor of a real city.
 */
function roadPolyline(a: Point, b: Point, rng: () => number): Point[] {
  const midLat = (a[0] + b[0]) / 2;
  const kx = lngMeters(midLat);
  const dx = (b[1] - a[1]) * kx;
  const dy = (b[0] - a[0]) * METERS_PER_LAT_DEGREE;
  if (Math.hypot(dx, dy) < 40) return [a, b];

  const theta = (rng() - 0.5) * 0.9;
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  // Displacement expressed in the rotated frame.
  const u = dx * cos + dy * sin;
  const v = -dx * sin + dy * cos;

  const turns = 3 + Math.floor(rng() * 3);
  const us = splitRandom(u, turns, rng);
  const vs = splitRandom(v, turns, rng);

  const pts: Point[] = [a];
  let fx = 0;
  let fy = 0;
  const push = (jitter: number) => {
    // Back to world axes, plus a little wobble so corners are not perfect.
    const wx = fx * cos - fy * sin + (rng() - 0.5) * jitter;
    const wy = fx * sin + fy * cos + (rng() - 0.5) * jitter;
    pts.push([a[0] + wy / METERS_PER_LAT_DEGREE, a[1] + wx / kx]);
  };

  for (let i = 0; i < turns; i++) {
    fx += us[i];
    push(30);
    fy += vs[i];
    if (i < turns - 1) push(30);
  }
  pts.push(b);
  return pts;
}

// ─── Instance ────────────────────────────────────────────────────────────────

interface Customer {
  node: number;
  lat: number;
  lng: number;
  twEnd: number;
}

const ALL_DAY = 86400;

function buildCustomers(p: SolveParams, rng: () => number, reference: Tour): Customer[] {
  const pool = reference.customers;
  const shuffled = pool.map((_, i) => i);
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }

  const { minLat, maxLat, minLng, maxLng } = reference.bounds;
  const out: Customer[] = [];
  for (let i = 0; i < p.customers; i++) {
    const seed = pool[shuffled[i % shuffled.length]];
    // Past the 45 real addresses, extra customers are jittered clones kept well
    // inside the frame so the fitted view never changes between runs.
    const extra = i >= pool.length;
    const lat = extra ? seed.lat + (rng() - 0.5) * 0.02 : seed.lat;
    const lng = extra ? seed.lng + (rng() - 0.5) * 0.03 : seed.lng;
    out.push({
      node: i + 1,
      lat: Math.min(Math.max(lat, minLat + 0.004), maxLat - 0.004),
      lng: Math.min(Math.max(lng, minLng + 0.004), maxLng - 0.004),
      // Windows are only assigned to some customers: a demo where everything is
      // urgent shows nothing about which constraint bites.
      twEnd: p.timeWindows && rng() < 0.55 ? 2700 + Math.floor(rng() * 5400) : ALL_DAY,
    });
  }
  return out;
}

function buildHubs(p: SolveParams, reference: Tour): Tour['hubs'] {
  const spots = [
    ...reference.hubs.map((h) => ({ lat: h.lat, lng: h.lng })),
    { lat: 48.8695, lng: 2.3105 },
  ];
  return spots.slice(0, p.hubs).map((s, i) => ({ node: 10_000 + i, lat: s.lat, lng: s.lng }));
}

/** Sweep around the depot, then hand each courier one contiguous wedge. Wedges
 *  keep routes from crossing, which is what a good CVRP solution looks like. */
function assign(customers: Customer[], vehicles: number, depot: Point, rng: () => number): Customer[][] {
  const kx = lngMeters(depot[0]);
  const bearing = (c: Customer) =>
    Math.atan2((c.lat - depot[0]) * METERS_PER_LAT_DEGREE, (c.lng - depot[1]) * kx);
  const sorted = [...customers].sort((a, b) => bearing(a) - bearing(b));

  const offset = Math.floor(rng() * sorted.length);
  const rotated = [...sorted.slice(offset), ...sorted.slice(0, offset)];

  const groups: Customer[][] = Array.from({ length: vehicles }, () => []);
  const per = Math.ceil(rotated.length / vehicles);
  rotated.forEach((c, i) => groups[Math.min(Math.floor(i / per), vehicles - 1)].push(c));
  return groups;
}

/** Nearest neighbour from the depot, biased towards tight windows when they are
 *  switched on. Crude, but it means an urgent customer is not left for last. */
function order(group: Customer[], depot: Point, timeWindows: boolean): Customer[] {
  const remaining = [...group];
  const out: Customer[] = [];
  let from: Point = depot;

  while (remaining.length > 0) {
    let best = 0;
    let bestCost = Infinity;
    for (let i = 0; i < remaining.length; i++) {
      const c = remaining[i];
      const km = metersBetween(from, [c.lat, c.lng]) / 1000;
      const urgency = timeWindows && c.twEnd < ALL_DAY ? c.twEnd / 3600 : 6;
      const cost = km + (timeWindows ? urgency * 0.45 : 0);
      if (cost < bestCost) {
        bestCost = cost;
        best = i;
      }
    }
    const [next] = remaining.splice(best, 1);
    out.push(next);
    from = [next.lat, next.lng];
  }
  return out;
}

function buildRoute(
  id: number,
  route: Customer[],
  p: SolveParams,
  depot: Point,
  rng: () => number
): { vehicle: Vehicle; reloads: { at: number; from: number; to: number }[]; lateness: number } {
  const stops: Stop[] = [];
  const legs: Leg[] = [];
  const reloads: { at: number; from: number; to: number }[] = [];
  let lateness = 0;

  let load = p.capacity;
  let t = 0;
  let at: Point = depot;

  const drive = (to: Point) => {
    const pts = roadPolyline(at, to, rng);
    const meters = Math.round(polylineMeters(pts));
    const leg: Leg = {
      depart: t,
      arrive: t + Math.max(20, Math.round(meters / DRIVE_SPEED)),
      meters,
      // Synthetic geometry, not an OSRM match. The renderer ignores the flag;
      // it is here so a mock tour is never mistaken for a routed one.
      road: false,
      pts,
    };
    legs.push(leg);
    t = leg.arrive;
    at = to;
  };

  stops.push({
    node: 0,
    kind: 'depot',
    lat: depot[0],
    lng: depot[1],
    arrive: 0,
    service: 0,
    depart: 0,
    load,
    twEnd: ALL_DAY,
  });

  for (const c of route) {
    if (load === 0) {
      drive(depot);
      const before = load;
      load = p.capacity;
      stops.push({
        node: 0,
        kind: 'reload',
        lat: depot[0],
        lng: depot[1],
        arrive: t,
        service: RELOAD_SECONDS,
        depart: t + RELOAD_SECONDS,
        load,
        twEnd: ALL_DAY,
      });
      reloads.push({ at: t, from: before, to: load });
      t += RELOAD_SECONDS;
    }

    drive([c.lat, c.lng]);
    load -= 1;
    if (c.twEnd < ALL_DAY && t > c.twEnd) lateness += t - c.twEnd;
    stops.push({
      node: c.node,
      kind: 'customer',
      lat: c.lat,
      lng: c.lng,
      arrive: t,
      service: SERVICE_SECONDS,
      depart: t + SERVICE_SECONDS,
      load,
      twEnd: c.twEnd,
    });
    t += SERVICE_SECONDS;
  }

  drive(depot);
  stops.push({
    node: 0,
    kind: 'depot',
    lat: depot[0],
    lng: depot[1],
    arrive: t,
    service: 0,
    depart: t,
    load,
    twEnd: ALL_DAY,
  });

  return {
    vehicle: { id, capacity: p.capacity, served: route.length, start: 0, end: t, stops, legs },
    reloads,
    lateness,
  };
}

export function buildMockTour(p: SolveParams, seed: number, reference: Tour): Tour {
  const rng = mulberry32(seed);
  const depot: Point = [reference.depot.lat, reference.depot.lng];

  const customers = buildCustomers(p, rng, reference);
  const hubs = buildHubs(p, reference);
  const groups = assign(customers, p.vehicles, depot, rng);

  const vehicles: Vehicle[] = [];
  const reloadEvents: Tour['reloadEvents'] = [];
  let meters = 0;
  let driveSeconds = 0;
  let lateSeconds = 0;

  groups.forEach((group, id) => {
    const built = buildRoute(id, order(group, depot, p.timeWindows), p, depot, rng);
    vehicles.push(built.vehicle);
    for (const r of built.reloads) reloadEvents.push({ vehicle: id, ...r });
    for (const leg of built.vehicle.legs) {
      meters += leg.meters;
      driveSeconds += leg.arrive - leg.depart;
    }
    lateSeconds += built.lateness;
  });

  reloadEvents.sort((a, b) => a.at - b.at);
  const horizon = Math.max(...vehicles.map((v) => v.end));

  return {
    meta: {
      ...reference.meta,
      solver: 'Google OR-Tools 9.15, RoutingModel (CVRPTW)',
      generatedFrom: 'mock-solver.ts',
    },
    bounds: reference.bounds,
    depot: reference.depot,
    hubs,
    customers: customers.map((c) => ({ node: c.node, lat: c.lat, lng: c.lng, twEnd: c.twEnd })),
    vehicles,
    horizon,
    stats: {
      customers: customers.length,
      customersServed: customers.length,
      vehicles: p.vehicles,
      capacity: p.capacity,
      roadKm: Math.round(meters / 100) / 10,
      horizon,
      cumulativeDriveTime: driveSeconds,
      tardinessMinutes: Math.round(lateSeconds / 60),
      hubsAvailable: p.hubs,
      // The mock always reloads at the depot, so hubs stay candidates. Only the
      // real solver gets to decide whether a transfer pays for itself.
      hubsActivated: 0,
      reloads: reloadEvents.length,
      hubFlybys: 0,
      timeWindowsBinding: p.timeWindows,
    },
    reloadEvents,
  };
}

// ─── Scenarios and delay ─────────────────────────────────────────────────────

const SCENARIO_CODES: SolveErrorCode[] = [
  'not_configured',
  'bad_request',
  'rate_limited',
  'daily_cap',
  'upstream_error',
];

function scenario(): string | null {
  if (typeof location === 'undefined') return null;
  return new URLSearchParams(location.search).get('solve');
}

function abortError(): DOMException {
  return new DOMException('Aborted', 'AbortError');
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(abortError());
    const id = setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(id);
        reject(abortError());
      },
      { once: true }
    );
  });
}

export async function mockSolve(
  params: SolveParams,
  signal: AbortSignal,
  reference: Tour
): Promise<Tour> {
  const want = scenario();

  // Never resolves: the caller's own deadline is what should fire.
  if (want === 'timeout') {
    await wait(10 * 60 * 1000, signal);
  }

  await wait(700 + params.budgetSeconds * 250, signal);

  if (want && SCENARIO_CODES.includes(want as SolveErrorCode)) {
    throw new SolveError(want as SolveErrorCode, `mock ${want}`, want === 'rate_limited' ? 42 : undefined);
  }
  // Proves the response check in `solve()` actually guards the canvas.
  if (want === 'malformed') return { ...buildMockTour(params, Date.now(), reference), horizon: 0 };

  return buildMockTour(
    params,
    Date.now() ^ (params.customers * 7919 + params.vehicles * 104_729),
    reference
  );
}
