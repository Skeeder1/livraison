import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
// `Map` is aliased: the icon would otherwise shadow the global Map constructor,
// which this file uses for the delivery lookups and the flash set.
import { ChevronDown, LoaderCircle, Map as MapIcon, Pause, Play, RotateCcw, Sparkles, TriangleAlert, X } from 'lucide-react';
// Types only, so nothing of Leaflet is pulled in while this island is rendered
// on the server. The library itself is imported dynamically on mount: it reads
// `document.documentElement.style` at module scope and throws in Node.
import type { Map as LeafletMap, TileLayer } from 'leaflet';
import 'leaflet/dist/leaflet.css';
// On the site these rules live in `src/styles/global.css`. Here they travel with
// the component, so the package renders on its own.
import './delivery-replay.css';
import type { DemoStrings } from './strings';
import type { Tour, Vehicle } from './tour';
import {
  BUDGET_CHOICES,
  CAPACITY,
  CUSTOMERS,
  DEFAULT_PARAMS,
  HUB_CHOICES,
  SolveError,
  TIMEOUT_GRACE_SECONDS,
  VEHICLE_CHOICES,
  createSolve,
  type SolveErrorCode,
  type SolveFn,
  type SolveParams,
} from './solve';

/*
 * Replays one solved CVRPTW instance over a Leaflet map.
 *
 * The tour on screen starts as `src/data/delivery-tour.json`, frozen at build
 * time by `scripts/build-delivery-demo-data.py` from the OR-Tools solver output.
 * Replaying it fetches nothing: the road network *is* the solution geometry.
 *
 * Leaflet owns the map. It holds the projection, the OpenStreetMap tile layer,
 * and every interaction: drag, wheel, pinch, double click, the zoom buttons and
 * the scale bar. This file owns one canvas laid over the map container, redrawn
 * every animation frame, which asks Leaflet where each coordinate currently sits
 * (`latLngToContainerPoint`) and paints the routes, the couriers and the stops
 * there. Nothing here knows what Web Mercator is any more.
 *
 * The visitor can also compose an instance and have it solved (`lib/delivery/
 * solve.ts`). That swaps the tour under the same renderer, which is why the data
 * is component state rather than a module constant: every memo below is keyed on
 * it. The frozen tour stays in memory as the reference, both to return to and to
 * measure a fresh solution against.
 */

// ─── Palette ─────────────────────────────────────────────────────────────────

// The solver ships matplotlib's tab10 (`#1f77b4`, `#8c564b`, `#17becf`); the brown
// is unreadable on both site backgrounds. These separate on hue *and* lightness,
// and each courier also carries a number so colour is never the only channel
// distinguishing them. Six of them because a generated instance can ask for six
// couriers; the first three are the frozen tour's and are unchanged.
const COURIER_COLORS = ['#22d3ee', '#fbbf24', '#c084fc', '#4ade80', '#fb7185', '#60a5fa'] as const;

const SPEEDS = [60, 120, 240, 480] as const;
const DEFAULT_SPEED_INDEX = 1;

// ─── Geometry ────────────────────────────────────────────────────────────────

const EARTH_R = 6_371_000;

function metersBetween(a: [number, number], b: [number, number]): number {
  const lat0 = ((a[0] + b[0]) / 2) * (Math.PI / 180);
  const dx = (b[1] - a[1]) * (Math.PI / 180) * EARTH_R * Math.cos(lat0);
  const dy = (b[0] - a[0]) * (Math.PI / 180) * EARTH_R;
  return Math.hypot(dx, dy);
}

/** Cumulative metric length along a polyline, so a vehicle covers ground at a
 *  constant real-world speed rather than a constant *vertex* rate. */
function cumulative(pts: [number, number][]): { cum: number[]; total: number } {
  const cum = [0];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    total += metersBetween(pts[i - 1], pts[i]);
    cum.push(total);
  }
  return { cum, total };
}

function pointAt(
  pts: [number, number][],
  cum: number[],
  total: number,
  fraction: number
): [number, number] {
  if (pts.length < 2 || total === 0) return pts[0];
  const target = Math.min(Math.max(fraction, 0), 1) * total;
  let lo = 0;
  let hi = cum.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (cum[mid] <= target) lo = mid;
    else hi = mid;
  }
  const span = cum[hi] - cum[lo];
  const f = span > 0 ? (target - cum[lo]) / span : 0;
  return [pts[lo][0] + f * (pts[hi][0] - pts[lo][0]), pts[lo][1] + f * (pts[hi][1] - pts[lo][1])];
}

// ─── Basemap ─────────────────────────────────────────────────────────────────

/* The one third party this page contacts. Leaflet fetches, positions, caches and
 * prunes these tiles; the layer is added to the map when the visitor wants a city
 * under the couriers and removed when they do not, which is the whole of the map
 * button's job. */
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_MAX_Z = 19;
/** Where the credit points. Crediting OpenStreetMap is an ODbL condition, not a
 *  caption, and the guidelines ask for a link: the only way to be rid of it
 *  would be to stop using their tiles. */
const TILE_LICENCE_URL = 'https://www.openstreetmap.org/copyright';
/** Remembers the visitor's answer, so the layer they asked for survives a
 *  reload and the layer they did not ask for is never fetched. */
const TILE_STORAGE_KEY = 'dr-basemap';

/** Padding between the fitted round and the edge of the stage, in pixels. The
 *  narrow stage gets less of it because there is less to give. */
const fitPadding = (width: number) => (width < 520 ? 26 : 44);

/** Graticule spacing, in degrees, chosen so the visible span carries a readable
 *  number of lines at any zoom. Only drawn when there is no city underneath. */
const GRID_STEPS = [1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001] as const;

// ─── Vehicle state at a given simulated time ─────────────────────────────────

type Phase = 'idle' | 'serving' | 'waiting' | 'driving' | 'done';

interface VehicleState {
  phase: Phase;
  lat: number;
  lng: number;
  load: number;
  /** Index of the leg being driven, or the stop being serviced. */
  legIndex: number;
  legFraction: number;
  stopIndex: number;
}

function vehicleStateAt(
  v: Vehicle,
  legMetrics: { cum: number[]; total: number }[],
  t: number
): VehicleState {
  const stops = v.stops;
  const last = stops.length - 1;

  if (t >= stops[last].arrive) {
    const s = stops[last];
    return {
      phase: 'done',
      lat: s.lat,
      lng: s.lng,
      load: s.load,
      legIndex: v.legs.length - 1,
      legFraction: 1,
      stopIndex: last,
    };
  }

  // Locate the segment: stops[i].arrive <= t < stops[i+1].arrive.
  let i = 0;
  let hi = last;
  while (i < hi - 1) {
    const mid = (i + hi) >> 1;
    if (stops[mid].arrive <= t) i = mid;
    else hi = mid;
  }
  if (stops[i + 1] && t >= stops[i + 1].arrive) i = Math.min(i + 1, last - 1);

  const s = stops[i];
  const leg = v.legs[i];

  if (t < s.arrive + s.service) {
    return {
      phase: 'serving',
      lat: s.lat,
      lng: s.lng,
      load: s.load,
      legIndex: i,
      legFraction: 0,
      stopIndex: i,
    };
  }
  if (t < s.depart) {
    return {
      phase: 'waiting',
      lat: s.lat,
      lng: s.lng,
      load: s.load,
      legIndex: i,
      legFraction: 0,
      stopIndex: i,
    };
  }

  const travel = leg.arrive - s.depart;
  const fraction = travel > 0 ? (t - s.depart) / travel : 1;
  const m = legMetrics[i];
  const [lat, lng] = pointAt(leg.pts, m.cum, m.total, fraction);
  return {
    phase: 'driving',
    lat,
    lng,
    load: s.load,
    legIndex: i,
    legFraction: Math.min(Math.max(fraction, 0), 1),
    stopIndex: i,
  };
}

// ─── Formatting ──────────────────────────────────────────────────────────────

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

function hoursMinutes(seconds: number): string {
  // Round to whole minutes *before* splitting, otherwise 7178 s rounds its
  // remainder up to 60 and prints "1 h 60".
  const totalMinutes = Math.round(seconds / 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return h > 0 ? `${h} h ${String(m).padStart(2, '0')}` : `${m} min`;
}

// ─── Component ───────────────────────────────────────────────────────────────

/** The reference tour described in the same terms as the panel, so the delta
 *  card can say what it is comparing against. Read from the tour, not retyped. */
function referenceParams(reference: Tour): SolveParams {
  return {
    customers: reference.stats.customers,
    vehicles: reference.stats.vehicles,
    hubs: reference.stats.hubsAvailable,
    capacity: reference.stats.capacity,
    timeWindows: reference.stats.timeWindowsBinding,
    budgetSeconds: DEFAULT_PARAMS.budgetSeconds,
  };
}

/** How long the canvas dips while one tour is exchanged for another. Long enough
 *  to read as a deliberate transition, short enough not to be a wait. */
const SWAP_FADE_MS = 220;
/** How long the "new tour ready" note stays over the map. */
const READY_NOTE_MS = 3600;

interface Props {
  strings: DemoStrings;
  locale: 'en' | 'fr';
  /** The tour that loads on arrival, and what a generated tour is measured
   *  against. Never mutated. Supplied by the host so the library carries no
   *  data of its own. */
  tour: Tour;
  /** Where `POST /api/solve` lives. Ignored when `solve` is given. */
  solveEndpoint?: string;
  /** A ready-made solver, for hosts that want the mock or their own transport. */
  solve?: SolveFn;
}

interface Failure {
  code: SolveErrorCode;
  /** Seconds left before a rate limit lifts, counted down in the panel. */
  retryAfter?: number;
  /** Budget of the run that timed out, so the message quotes what was asked. */
  budget?: number;
}

function describeFailure(f: Failure, fallbackBudget: number, strings: DemoStrings): string {
  const e = strings.errors;
  switch (f.code) {
    case 'not_configured':
      return e.notConfigured;
    case 'rate_limited':
      return f.retryAfter
        ? `${e.rateLimited} ${e.rateLimitedWait.replace('{n}', String(f.retryAfter))}`
        : e.rateLimited;
    case 'daily_cap':
      return e.dailyCap;
    case 'timeout':
      return e.timeout.replace('{n}', String(f.budget ?? fallbackBudget));
    case 'bad_request':
      return e.badRequest;
    case 'network':
      return e.network;
    default:
      return e.upstream;
  }
}

interface DeltaRow {
  label: string;
  value: string;
  delta: string;
  tone: 'good' | 'bad' | 'flat';
}

/** Numbers only. This is what separates "a nice animation" from "a solver ran":
 *  the same five figures, side by side with the frozen round. */
function buildDeltas(ref: Tour['stats'], now: Tour['stats'], strings: DemoStrings): DeltaRow[] {
  const row = (
    label: string,
    before: number,
    after: number,
    unit: string,
    digits = 0,
    /** Set when the panel below prints the same figure differently, so the two
     *  cards never show one number in two shapes. */
    value?: string
  ): DeltaRow => {
    const diff = after - before;
    const flat = Math.abs(diff) < (digits > 0 ? 0.05 : 0.5);
    const show = (n: number) => (digits > 0 ? n.toFixed(digits) : String(Math.round(n)));
    return {
      label,
      value: value ?? `${show(after)}${unit}`,
      delta: flat ? strings.delta.unchanged : `${diff > 0 ? '+' : ''}${show(diff)}${unit}`,
      // Every metric here is a cost, so less of it is the good direction.
      tone: flat ? 'flat' : diff < 0 ? 'good' : 'bad',
    };
  };

  return [
    row(strings.stats.roadKm, ref.roadKm, now.roadKm, ' km', 1),
    row(
      strings.stats.duration,
      ref.horizon / 60,
      now.horizon / 60,
      ' min',
      0,
      hoursMinutes(now.horizon)
    ),
    row(
      strings.stats.cumulative,
      ref.cumulativeDriveTime / 60,
      now.cumulativeDriveTime / 60,
      ' min',
      0,
      hoursMinutes(now.cumulativeDriveTime)
    ),
    row(strings.stats.reloads, ref.reloads, now.reloads, ''),
    row(strings.stats.tardiness, ref.tardinessMinutes, now.tardinessMinutes, ' min'),
  ];
}

interface FeedEvent {
  at: number;
  vehicle: number | null;
  text: string;
}

export default function DeliveryReplay({
  strings,
  locale,
  tour: reference,
  solveEndpoint,
  solve: solveProp,
}: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const solve = useMemo<SolveFn>(
    () => solveProp ?? createSolve({ endpoint: solveEndpoint, reference }),
    [solveProp, solveEndpoint, reference]
  );
  const REFERENCE_PARAMS = useMemo(() => referenceParams(reference), [reference]);

  const [data, setData] = useState<Tour>(reference);
  const [playing, setPlaying] = useState(false);
  const [speedIndex, setSpeedIndex] = useState<number>(DEFAULT_SPEED_INDEX);
  const [focused, setFocused] = useState<number | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; lines: string[] } | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);
  /** On by arrival: the couriers ride through a real city, and recognising it is
   *  most of what makes the replay readable. The cost is honest and stated in the
   *  provenance line: the page fetches tiles from OpenStreetMap on load. The
   *  button turns them off, and that choice is remembered. */
  const [basemap, setBasemap] = useState(true);

  // ─── Live solve ────────────────────────────────────────────────────────────

  const [params, setParams] = useState<SolveParams>(DEFAULT_PARAMS);
  const [advanced, setAdvanced] = useState(false);
  const [solving, setSolving] = useState(false);
  const [solveSeconds, setSolveSeconds] = useState(0);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [swapping, setSwapping] = useState(false);
  const [ready, setReady] = useState(false);
  /** Parameters of the tour currently on screen, or null while it is the frozen
   *  reference. Doubles as the "show me the delta" flag. */
  const [applied, setApplied] = useState<SolveParams | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const deadlineRef = useRef(false);
  const swapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Simulated time lives in a ref so the 60 Hz canvas loop never re-renders React.
  // `tick` mirrors it into state at ~12 Hz, which is plenty for text panels whose
  // values are integers or clock strings.
  const timeRef = useRef(0);
  const [tick, setTick] = useState(0);

  const playingRef = useRef(playing);
  const speedRef = useRef<number>(SPEEDS[DEFAULT_SPEED_INDEX]);
  const focusedRef = useRef<number | null>(null);
  const basemapRef = useRef(false);

  // `playing` is deliberately absent here: the render body runs a few frames
  // after the click, which let the clock keep advancing visibly past a Pause.
  // `setPlayback` writes the ref eagerly instead, so the very next frame obeys.
  speedRef.current = SPEEDS[speedIndex];
  focusedRef.current = focused;
  basemapRef.current = basemap;

  const setPlayback = useCallback((next: boolean) => {
    playingRef.current = next;
    setPlaying(next);
  }, []);

  // The stored choice is applied after mount rather than read while rendering:
  // the island is server rendered, and a render body that reads storage would
  // hydrate a different tree than the HTML that shipped.
  useEffect(() => {
    try {
      if (window.localStorage.getItem(TILE_STORAGE_KEY) === 'off') setBasemap(false);
    } catch {
      // Storage can be blocked outright. The layer simply stays on.
    }
  }, []);

  const setBasemapVisible = useCallback((next: boolean) => {
    setBasemap(next);
    try {
      window.localStorage.setItem(TILE_STORAGE_KEY, next ? 'on' : 'off');
    } catch {
      // Same as above: the preference is a convenience, not a dependency.
    }
  }, []);

  // Metric arc-lengths: viewport-independent, so they are computed once.
  const legMetrics = useMemo(
    () => data.vehicles.map((v) => v.legs.map((leg) => cumulative(leg.pts))),
    [data]
  );

  const events = useMemo<FeedEvent[]>(() => {
    const out: FeedEvent[] = [
      {
        at: 0,
        vehicle: null,
        text: strings.eventStart
          .replace('{n}', String(data.stats.vehicles))
          .replace('{cap}', String(data.stats.capacity)),
      },
    ];
    for (const r of data.reloadEvents) {
      out.push({
        at: r.at,
        vehicle: r.vehicle,
        text: strings.eventReload
          .replace('{v}', String(r.vehicle + 1))
          .replace('{from}', String(r.from))
          .replace('{to}', String(r.to)),
      });
    }
    for (const v of data.vehicles) {
      for (const s of v.stops) {
        if (s.kind === 'hub') {
          out.push({
            at: s.arrive,
            vehicle: v.id,
            text: strings.eventHub.replace('{v}', String(v.id + 1)),
          });
        }
      }
      out.push({
        at: v.end,
        vehicle: v.id,
        text: strings.eventDone
          .replace('{v}', String(v.id + 1))
          .replace('{n}', String(v.served)),
      });
    }
    return out.sort((a, b) => a.at - b.at);
  }, [data, strings]);

  // Delivery timestamps, sorted, for an O(log n) "how many delivered by t".
  const deliveryTimes = useMemo(() => {
    const times: number[] = [];
    for (const v of data.vehicles) {
      for (const s of v.stops) if (s.kind === 'customer') times.push(s.arrive);
    }
    return times.sort((a, b) => a - b);
  }, [data]);

  // Which courier serves each customer, and when — used for the map colouring
  // and the hover tooltip.
  const customerInfo = useMemo(() => {
    const map = new Map<number, { vehicle: number; at: number }>();
    for (const v of data.vehicles) {
      for (const s of v.stops) {
        if (s.kind === 'customer') map.set(s.node, { vehicle: v.id, at: s.arrive });
      }
    }
    return map;
  }, [data]);

  const deliveredBy = useCallback(
    (t: number) => {
      let lo = 0;
      let hi = deliveryTimes.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (deliveryTimes[mid] <= t) lo = mid + 1;
        else hi = mid;
      }
      return lo;
    },
    [deliveryTimes]
  );

  // ─── Reduced motion ────────────────────────────────────────────────────────

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const syncMotion = () => setReducedMotion(mq.matches);
    syncMotion();
    mq.addEventListener('change', syncMotion);

    return () => {
      mq.removeEventListener('change', syncMotion);
    };
  }, []);

  // Autoplay unless the visitor asked for less motion — the replay is the whole
  // point of the page, so it should be moving when they arrive.
  //
  // The query is read here rather than through `reducedMotion`: that state is
  // still `false` when the effects of this first commit run, so reading it would
  // start the animation for exactly the people who asked for none, and only the
  // note underneath would ever admit it.
  useEffect(() => {
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) setPlayback(true);
  }, [setPlayback]);

  // ─── The map, and the canvas laid over it ──────────────────────────────────

  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 });
  const mapHostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const tileLayerRef = useRef<TileLayer | null>(null);
  /** Whether any tile has actually landed. While the layer is empty the
   *  graticule stands in for it, exactly as it did before Leaflet. */
  const tilesPaintedRef = useRef(false);
  /** Flipped once the map exists, so the effects that need it can wait for the
   *  dynamic import rather than race it. */
  const [mapReady, setMapReady] = useState(false);
  /** True for the length of an animated zoom, while the overlay is being scaled
   *  by CSS rather than redrawn. */
  const zoomingRef = useRef(false);
  /** The centre and zoom the canvas was last painted for, which is what an
   *  incoming zoom has to be measured against. */
  const drawnViewRef = useRef<{ center: ReturnType<LeafletMap['getCenter']>; zoom: number } | null>(null);

  const stringsRef = useRef(strings);
  stringsRef.current = strings;

  // The tour on screen decides the framing, so a solved instance in a different
  // corner of the city is fitted the way the frozen one was.
  const bounds = data.bounds;
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;

  useEffect(() => {
    const host = mapHostRef.current;
    if (!host) return;

    let map: LeafletMap | null = null;
    let cancelled = false;

    /* Taking the map down. It runs from the effect cleanup, and also from
     * `astro:before-swap`: the ClientRouter replaces the whole body, and React
     * never unmounts an island that had the ground pulled from under it, so the
     * cleanup alone would leave Leaflet's document-level drag listeners and this
     * map's event handlers alive behind a detached container. */
    const teardown = () => {
      document.removeEventListener('astro:before-swap', teardown);
      setMapReady(false);
      tileLayerRef.current = null;
      tilesPaintedRef.current = false;
      mapRef.current = null;
      map?.remove();
      map = null;
    };

    import('leaflet').then(({ default: L }) => {
      if (cancelled || !mapHostRef.current) return;

      // Read straight from the query rather than from `reducedMotion`: that
      // state is still false when the effects of this first commit run.
      const quiet = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      map = L.map(mapHostRef.current, {
        zoomAnimation: !quiet,
        fadeAnimation: !quiet,
        inertia: !quiet,
        /* Continuous zoom rather than Leaflet's whole levels.
         *
         * It is what keeps the first paint framed as it was before there was a
         * map at all: the old fit was one uniform scale computed from `bounds`,
         * and rounding that down to a whole level would draw the round at ~60 %
         * of the size it has always had, with most of the stage empty. The wheel
         * also reads as one movement instead of a stack of jump cuts.
         *
         * The price is a known artefact, and it is worth stating plainly: on a
         * fractional level every tile is resampled, and `invert()` in the dark
         * theme turns the half-covered pixel along each tile edge into a faint
         * dark line, so the city wears a 1px grid at 256px intervals. Setting
         * this to 1 removes it completely, at the cost of the framing above. */
        zoomSnap: 0,
        zoomDelta: 0.4,
        minZoom: 3,
        maxZoom: TILE_MAX_Z,
        // The credit is a licence condition, so it is Leaflet's job rather than
        // ours: the tile layer carries it, this control renders it in the map's
        // bottom right corner, and both appear and disappear with the layer.
        attributionControl: true,
        zoomControl: false,
        // The arrow keys scrub the timeline on this page, and the page says so.
        // A focusable map that swallowed them would be a worse map.
        keyboard: false,
      });

      // Only the OpenStreetMap credit, which is the part a licence asks for.
      // Leaflet's own "Leaflet" prefix is a courtesy its MIT licence does not
      // require, and this corner should carry as little as it honestly can.
      map.attributionControl.setPrefix(false);

      L.control
        .zoom({
          position: 'topright',
          zoomInTitle: stringsRef.current.map.zoomIn,
          zoomOutTitle: stringsRef.current.map.zoomOut,
        })
        .addTo(map);
      // Replaces the fixed "2 km" bar the canvas used to draw: that one was only
      // ever right at one scale, and there is no longer only one scale.
      L.control.scale({ position: 'bottomright', imperial: false, maxWidth: 110 }).addTo(map);

      const layer = L.tileLayer(TILE_URL, {
        maxZoom: TILE_MAX_Z,
        // Not `detectRetina`: it would quadruple the tiles fetched to sharpen a
        // sheet that is drawn under half opacity behind a grayscale filter.
        className: 'dr-tiles',
        // The credit travels with the tiles, which is what ties it to them:
        // adding the layer puts it on screen, removing the layer takes it away,
        // and there is no second piece of state that could disagree. Markup
        // because the guidelines ask for a link, and it is our own string.
        attribution: `<a href="${TILE_LICENCE_URL}" target="_blank" rel="noopener noreferrer">${stringsRef.current.basemap.attribution}</a>`,
      });
      layer.on('tileload', () => {
        tilesPaintedRef.current = true;
      });
      tileLayerRef.current = layer;

      /* Zoom animation, and the one place the overlay is not simply redrawn.
       *
       * Leaflet's animated zoom is a CSS transition on the tile pane, but the
       * map's own coordinates jump to the target the moment the animation
       * starts. Redrawing through them mid-flight would put the routes at the
       * new scale over a city still sliding towards it. So the overlay stops
       * redrawing and is scaled by the same transition instead: whatever it last
       * drew is a view with a known centre and zoom, and the whole of it maps to
       * the incoming view by one scale about one point.
       *
       * Only the animated path gets here. A pinch drives `_move` frame by frame,
       * which the ordinary redraw already follows exactly. */
      map.on('zoomanim', (e) => {
        const canvas = canvasRef.current;
        const view = drawnViewRef.current;
        if (!canvas || !view || !map) return;
        zoomingRef.current = true;

        const scale = map.getZoomScale(e.zoom, view.zoom);
        const half = map.getSize().divideBy(2);
        // Where the incoming centre sits on the canvas as it stands. Projecting
        // both centres at the drawn zoom keeps this independent of whatever the
        // map's live coordinates have already moved on to.
        const focus = half.add(map.project(e.center, view.zoom).subtract(map.project(view.center, view.zoom)));
        canvas.style.transform = `translate(${half.x - scale * focus.x}px, ${half.y - scale * focus.y}px) scale(${scale})`;
      });

      const settle = () => {
        const canvas = canvasRef.current;
        zoomingRef.current = false;
        if (canvas) canvas.style.transform = '';
      };
      map.on('zoomend', settle);
      map.on('viewreset', settle);

      const b = boundsRef.current;
      const pad = fitPadding(map.getSize().x);
      map.fitBounds(
        [
          [b.minLat, b.minLng],
          [b.maxLat, b.maxLng],
        ],
        { padding: [pad, pad], animate: false }
      );

      mapRef.current = map;
      setMapReady(true);
    });

    document.addEventListener('astro:before-swap', teardown);
    return () => {
      cancelled = true;
      teardown();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const pad = fitPadding(sizeRef.current.w || map.getSize().x);
    map.fitBounds(
      [
        [bounds.minLat, bounds.minLng],
        [bounds.maxLat, bounds.maxLng],
      ],
      { padding: [pad, pad], animate: false }
    );
  }, [bounds, mapReady]);

  // The map button is now one `addLayer`/`removeLayer`. Nothing is fetched while
  // the layer is off, and Leaflet drops the tiles it held when it goes.
  useEffect(() => {
    const map = mapRef.current;
    const layer = tileLayerRef.current;
    if (!map || !layer) return;
    if (basemap) {
      if (!map.hasLayer(layer)) layer.addTo(map);
    } else if (map.hasLayer(layer)) {
      map.removeLayer(layer);
      tilesPaintedRef.current = false;
    }
  }, [basemap, mapReady]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const stage = stageRef.current;
    if (!canvas || !stage) return;

    const resize = () => {
      const rect = stage.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      // The overlay is device-pixel sized and the context is scaled by the same
      // factor, so the routes stay sharp on a retina screen at every zoom level.
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      sizeRef.current = { w: rect.width, h: rect.height, dpr };
      mapRef.current?.invalidateSize({ animate: false });
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(stage);
    return () => ro.disconnect();
  }, [mapReady]);

  /* One loop, one repaint per frame. Everything that can move the geometry moves
   * it here: the clock, a drag, the wheel, the zoom buttons, a window resize. The
   * overlay is redrawn from whatever Leaflet says the view is at that instant, so
   * there is no `move` or `zoom` handler to keep in step with it and no way for
   * the routes to lag the city by a frame. */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let raf = 0;
    let lastFrame = performance.now();
    let lastTickPush = 0;
    // Delivery "pops" decay in wall-clock time so they stay visible at 480×.
    const flashes = new Map<number, number>();
    let prevSimTime = timeRef.current;

    const loop = (now: number) => {
      const dt = Math.min((now - lastFrame) / 1000, 0.1);
      lastFrame = now;

      if (playingRef.current) {
        timeRef.current += dt * speedRef.current;
        if (timeRef.current >= data.horizon) {
          timeRef.current = data.horizon;
          playingRef.current = false;
          setPlaying(false);
        }
      }

      const t = timeRef.current;

      // Register deliveries crossed since the previous frame (either direction
      // of scrubbing simply resets the set).
      if (t < prevSimTime) flashes.clear();
      else if (t > prevSimTime) {
        for (const [node, info] of customerInfo) {
          if (info.at > prevSimTime && info.at <= t) flashes.set(node, now);
        }
      }
      prevSimTime = t;
      for (const [node, at] of flashes) if (now - at > 900) flashes.delete(node);

      render(ctx, t, now, flashes);

      if (now - lastTickPush > 80) {
        lastTickPush = now;
        setTick(t);
      }
      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    // The ClientRouter swaps the body without unmounting React, so the loop has
    // to be told to stop as well as cleaned up.
    const stop = () => cancelAnimationFrame(raf);
    document.addEventListener('astro:before-swap', stop);
    return () => {
      document.removeEventListener('astro:before-swap', stop);
      cancelAnimationFrame(raf);
    };
    // `render` is stable via refs; re-running the loop on every state change
    // would reset the frame clock and stutter the animation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerInfo, data]);

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, t: number, now: number, flashes: Map<number, number>) => {
      const map = mapRef.current;
      const { w, h, dpr } = sizeRef.current;
      // Nothing is drawn during an animated zoom: the CSS transition set up in
      // `zoomanim` is carrying what is already on the canvas.
      if (!map || w === 0 || zoomingRef.current) return;
      drawnViewRef.current = { center: map.getCenter(), zoom: map.getZoom() };

      // The only projection in this file: whatever Leaflet says, right now.
      // Pan, wheel, pinch and the zoom buttons all reach the drawing through it.
      const project = (lat: number, lng: number): [number, number] => {
        const p = map.latLngToContainerPoint({ lat, lng });
        return [p.x, p.y];
      };

      const colors = COURIER_COLORS;
      const focus = focusedRef.current;

      const grid = 'rgba(255,255,255,0.045)';
      const network = 'rgba(255,255,255,0.10)';
      const pending = 'rgba(255,255,255,0.28)';
      const surface = '#0d0d0d';

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Cleared, never filled: the tiles are DOM elements underneath this canvas
      // now, and a surface colour over them would hide the city entirely. With
      // the layer off, the stage's own card background shows through instead.
      ctx.clearRect(0, 0, w, h);

      const city = basemapRef.current && tilesPaintedRef.current;

      // Graticule — enough to read as a map, faint enough never to compete with
      // the routes. Over real streets it would only add a second, fictional
      // grid, so it stands down once the tiles are up. The spacing follows the
      // zoom, and the lines span the visible map rather than the tour's bbox:
      // both of those used to be fixed and no longer are.
      if (!city) {
        const view = map.getBounds();
        const west = view.getWest();
        const east = view.getEast();
        const south = view.getSouth();
        const north = view.getNorth();
        // Coarsest spacing that still lays at least six lines across the view.
        const step = GRID_STEPS.find((s) => (east - west) / s >= 6) ?? GRID_STEPS[GRID_STEPS.length - 1];

        ctx.strokeStyle = grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let lng = Math.ceil(west / step) * step; lng <= east; lng += step) {
          const [x] = project(south, lng);
          ctx.moveTo(x, 0);
          ctx.lineTo(x, h);
        }
        for (let lat = Math.ceil(south / step) * step; lat <= north; lat += step) {
          const [, y] = project(lat, west);
          ctx.moveTo(0, y);
          ctx.lineTo(w, y);
        }
        ctx.stroke();
      }

      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      // Pass 1 — the whole planned network, dimmed. With no basemap under it,
      // this is what makes the view legible as a city on its own.
      ctx.strokeStyle = network;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      for (const v of data.vehicles) {
        for (const leg of v.legs) {
          const [sx, sy] = project(leg.pts[0][0], leg.pts[0][1]);
          ctx.moveTo(sx, sy);
          for (let i = 1; i < leg.pts.length; i++) {
            const [x, y] = project(leg.pts[i][0], leg.pts[i][1]);
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();

      // Pass 2 — the distance already covered, in each courier's colour.
      for (const v of data.vehicles) {
        const dimmed = focus !== null && focus !== v.id;
        const state = vehicleStateAt(v, legMetrics[v.id], t);

        ctx.globalAlpha = dimmed ? 0.15 : 1;
        ctx.strokeStyle = colors[v.id % colors.length];
        ctx.lineWidth = focus === v.id ? 3 : 2.1;
        ctx.beginPath();

        for (let li = 0; li <= state.legIndex && li < v.legs.length; li++) {
          const leg = v.legs[li];
          const partial = li === state.legIndex && state.phase !== 'done';
          const m = legMetrics[v.id][li];
          const limit = partial ? state.legFraction * m.total : m.total;

          const [sx, sy] = project(leg.pts[0][0], leg.pts[0][1]);
          ctx.moveTo(sx, sy);
          for (let i = 1; i < leg.pts.length; i++) {
            if (m.cum[i] >= limit) {
              const [lat, lng] = pointAt(leg.pts, m.cum, m.total, limit / (m.total || 1));
              const [x, y] = project(lat, lng);
              ctx.lineTo(x, y);
              break;
            }
            const [x, y] = project(leg.pts[i][0], leg.pts[i][1]);
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      // Pass 3 — customers.
      for (const c of data.customers) {
        const info = customerInfo.get(c.node);
        const done = info ? info.at <= t : false;
        const dimmed = focus !== null && info?.vehicle !== focus;
        const [x, y] = project(c.lat, c.lng);

        ctx.globalAlpha = dimmed ? 0.2 : 1;
        if (done && info) {
          const flash = flashes.get(c.node);
          const color = colors[info.vehicle % colors.length];
          if (flash !== undefined) {
            const k = 1 - (now - flash) / 900;
            ctx.beginPath();
            ctx.arc(x, y, 4 + 14 * (1 - k), 0, Math.PI * 2);
            ctx.strokeStyle = color;
            ctx.globalAlpha = (dimmed ? 0.2 : 1) * k * 0.7;
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.globalAlpha = dimmed ? 0.2 : 1;
          }
          ctx.beginPath();
          ctx.arc(x, y, 3.6, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
        } else {
          ctx.beginPath();
          ctx.arc(x, y, 2.8, 0, Math.PI * 2);
          ctx.strokeStyle = pending;
          ctx.lineWidth = 1.4;
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }

      // Pass 4 — hubs (diamond) and depot (square). Both drawn above the routes
      // because they anchor the whole scene.
      for (const hub of data.hubs) {
        const [x, y] = project(hub.lat, hub.lng);
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(Math.PI / 4);
        ctx.strokeStyle = 'rgba(255,255,255,0.45)';
        ctx.lineWidth = 1.6;
        ctx.setLineDash([3, 2]);
        ctx.strokeRect(-5, -5, 10, 10);
        ctx.restore();
      }
      ctx.setLineDash([]);

      const [dx, dy] = project(data.depot.lat, data.depot.lng);
      ctx.beginPath();
      ctx.arc(dx, dy, 13, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(114,255,255,0.10)';
      ctx.fill();
      ctx.fillStyle = '#72ffff';
      ctx.fillRect(dx - 4.5, dy - 4.5, 9, 9);
      ctx.strokeStyle = surface;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(dx - 4.5, dy - 4.5, 9, 9);

      // Pass 5 — couriers.
      for (const v of data.vehicles) {
        const dimmed = focus !== null && focus !== v.id;
        const state = vehicleStateAt(v, legMetrics[v.id], t);
        const [x, y] = project(state.lat, state.lng);
        const color = colors[v.id % colors.length];

        ctx.globalAlpha = dimmed ? 0.25 : 1;

        if (state.phase === 'serving') {
          // Breathing ring while parcels change hands.
          const pulse = 0.5 + 0.5 * Math.sin(now / 160);
          ctx.beginPath();
          ctx.arc(x, y, 11 + 5 * pulse, 0, Math.PI * 2);
          ctx.strokeStyle = color;
          ctx.globalAlpha = (dimmed ? 0.25 : 1) * (0.5 - 0.3 * pulse);
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.globalAlpha = dimmed ? 0.25 : 1;
        }

        ctx.beginPath();
        ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = surface;
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = '#0d0d0d';
        ctx.font = '700 10px ui-monospace, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(v.id + 1), x, y + 0.5);

        // Load gauge riding just under each courier.
        const gw = 26;
        const filled = (state.load / v.capacity) * gw;
        ctx.fillStyle = 'rgba(255,255,255,0.16)';
        ctx.fillRect(x - gw / 2, y + 13, gw, 3);
        ctx.fillStyle = color;
        ctx.fillRect(x - gw / 2, y + 13, filled, 3);

        ctx.globalAlpha = 1;
      }

      // The scale bar is Leaflet's own control now: the view has a zoom, so a
      // bar hard-coded to one distance would be wrong at every other one.

      ctx.restore();
    },
    [customerInfo, data, legMetrics]
  );

  // Repaint immediately when a non-animated input changes (theme, focus, the
  // basemap, a scrub while paused) so the canvas never lags a frame behind the
  // controls.
  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) render(ctx, timeRef.current, performance.now(), new Map());
  }, [basemap, focused, tick, render]);

  // ─── Interaction ───────────────────────────────────────────────────────────

  const seek = useCallback(
    (value: number) => {
      timeRef.current = Math.min(Math.max(value, 0), data.horizon);
      setTick(timeRef.current);
    },
    [data]
  );

  const restart = useCallback(() => {
    seek(0);
    setPlayback(true);
  }, [seek, setPlayback]);

  // ─── Swapping one tour for another ─────────────────────────────────────────

  /**
   * The canvas must never blank. The current tour keeps animating right up to
   * this call; here it dims for a beat, the new tour takes its place with the
   * clock back at zero, and playback resumes. With reduced motion the dip is
   * skipped and the swap is instant.
   */
  const showTour = useCallback(
    (next: Tour, from: SolveParams | null) => {
      const commit = () => {
        swapTimerRef.current = null;
        setData(next);
        setApplied(from);
        timeRef.current = 0;
        setTick(0);
        setFocused(null);
        setHover(null);
        setSwapping(false);
        setPlayback(!reducedMotion);
      };

      if (swapTimerRef.current) clearTimeout(swapTimerRef.current);
      if (reducedMotion) {
        commit();
        return;
      }
      setSwapping(true);
      swapTimerRef.current = setTimeout(commit, SWAP_FADE_MS);
    },
    [reducedMotion, setPlayback]
  );

  const runSolve = useCallback(async () => {
    if (abortRef.current) return;

    setFailure(null);
    setReady(false);
    setSolving(true);
    setSolveSeconds(0);
    deadlineRef.current = false;

    const controller = new AbortController();
    abortRef.current = controller;
    // The server owns the search budget; this is only the client's patience.
    const deadline = setTimeout(
      () => {
        deadlineRef.current = true;
        controller.abort();
      },
      (params.budgetSeconds + TIMEOUT_GRACE_SECONDS) * 1000
    );
    const asked = params;

    try {
      const next = await solve(asked, controller.signal);
      showTour(next, asked);
      setReady(true);
    } catch (cause) {
      if (cause instanceof SolveError) {
        setFailure({ code: cause.code, retryAfter: cause.retryAfterSeconds });
      } else if ((cause as Error)?.name === 'AbortError') {
        // A deadline is worth reporting; a cancel is the visitor's own doing.
        if (deadlineRef.current) setFailure({ code: 'timeout', budget: asked.budgetSeconds });
      } else {
        setFailure({ code: 'network' });
      }
    } finally {
      clearTimeout(deadline);
      abortRef.current = null;
      setSolving(false);
    }
  }, [params, showTour, solve]);

  const cancelSolve = useCallback(() => abortRef.current?.abort(), []);

  const showReference = useCallback(() => {
    setFailure(null);
    setReady(false);
    showTour(reference, null);
  }, [showTour, reference]);

  // Elapsed counter under the banner: a run with no visible progress reads as a
  // hang, whatever the copy says.
  useEffect(() => {
    if (!solving) return;
    const id = setInterval(() => setSolveSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [solving]);

  useEffect(() => {
    if (!ready) return;
    const id = setTimeout(() => setReady(false), READY_NOTE_MS);
    return () => clearTimeout(id);
  }, [ready]);

  // A 429 hands back a retry delay; count it down rather than let the visitor
  // guess when the button is worth pressing again.
  useEffect(() => {
    if (!failure?.retryAfter) return;
    const id = setInterval(() => {
      setFailure((f) => {
        if (!f?.retryAfter) return f;
        const left = f.retryAfter - 1;
        return left > 0 ? { ...f, retryAfter: left } : { code: f.code };
      });
    }, 1000);
    return () => clearInterval(id);
  }, [failure?.retryAfter]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      if (swapTimerRef.current) clearTimeout(swapTimerRef.current);
    },
    []
  );

  const togglePlay = useCallback(() => {
    const next = !playingRef.current;
    // Pressing play at the very end should replay rather than sit still.
    if (next && timeRef.current >= data.horizon) timeRef.current = 0;
    setPlayback(next);
  }, [data, setPlayback]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Space and the arrows belong to whatever control has focus. Without the
      // button case, Space on the Play button toggled twice: once here on the
      // way up the tree, once as the button's own activation.
      const target = e.target as HTMLElement | null;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLButtonElement ||
        target instanceof HTMLSelectElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      ) {
        return;
      }
      if (e.key === ' ' || e.key === 'k') {
        e.preventDefault();
        togglePlay();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        seek(timeRef.current + 120);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        seek(timeRef.current - 120);
      }
    },
    [seek, togglePlay]
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const map = mapRef.current;
      const canvas = canvasRef.current;
      if (!map || !canvas) return;
      // The canvas covers the map container exactly, so its client rectangle and
      // Leaflet's container coordinates are the same frame of reference.
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      let best: { d: number; lines: string[] } | null = null;
      const consider = (lat: number, lng: number, lines: string[]) => {
        const p = map.latLngToContainerPoint({ lat, lng });
        const d = Math.hypot(p.x - px, p.y - py);
        if (d < 13 && (!best || d < best.d)) best = { d, lines };
      };

      const t = timeRef.current;
      for (const c of data.customers) {
        const info = customerInfo.get(c.node);
        const lines = [strings.tooltip.customer.replace('{n}', String(c.node))];
        if (info) {
          lines.push(strings.tooltip.servedBy.replace('{v}', String(info.vehicle + 1)));
          lines.push(
            info.at <= t
              ? strings.tooltip.at.replace('{time}', clock(info.at))
              : strings.tooltip.notYet.replace('{time}', clock(info.at))
          );
        }
        lines.push(
          strings.tooltip.window
            .replace('{from}', '00:00')
            .replace('{to}', c.twEnd >= 86400 ? strings.allDay : clock(c.twEnd))
        );
        consider(c.lat, c.lng, lines);
      }
      consider(data.depot.lat, data.depot.lng, [strings.legend.depot]);
      for (const hub of data.hubs) consider(hub.lat, hub.lng, [strings.legend.hub]);

      setHover(best ? { x: px, y: py, lines: (best as { lines: string[] }).lines } : null);
    },
    [customerInfo, data, strings]
  );

  // ─── Derived values for the panels ─────────────────────────────────────────

  const t = tick;
  const delivered = deliveredBy(t);
  const colors = COURIER_COLORS;
  const states = data.vehicles.map((v) => vehicleStateAt(v, legMetrics[v.id], t));
  const visibleEvents = events.filter((e) => e.at <= t).slice(-40).reverse();

  const s = data.stats;

  // The four numbers above the map used to be computed in the Astro page from
  // the frozen file, which no longer describes what is on screen.
  const headline: { value: string; label: string }[] = [
    { value: `${s.customersServed}`, label: strings.headline.served },
    { value: `${s.vehicles}`, label: strings.headline.couriers },
    { value: `${s.roadKm} km`, label: strings.headline.roadKm },
    { value: `${s.reloads}`, label: strings.headline.reloads },
  ];

  const summarise = (p: SolveParams) =>
    strings.solve.summary
      .replace('{customers}', String(p.customers))
      .replace('{vehicles}', String(p.vehicles))
      .replace('{capacity}', String(p.capacity));

  const deltas = applied ? buildDeltas(reference.stats, s, strings) : null;
  const failureText = failure ? describeFailure(failure, params.budgetSeconds, strings) : null;
  const blocked = failure?.retryAfter !== undefined;

  return (
    <div
      className="dr-root"
      tabIndex={0}
      onKeyDown={onKeyDown}
      // Deliberately not role="application": that would take the whole subtree
      // out of a screen reader's browse mode, including the aria-live event log
      // that is this canvas's only text alternative. A group keeps the label
      // without swallowing the reading experience; the controls inside are
      // native buttons that already handle their own keys.
      role="group"
      aria-label={strings.stats.title}
      aria-busy={solving}
    >
      <div className="dr-headline">
        {headline.map((h) => (
          <div key={h.label} className="dr-headline-item">
            <span className="dr-headline-value">{h.value}</span>
            <span className="dr-headline-label">{h.label}</span>
          </div>
        ))}
      </div>

      <div className="dr-main">
        <div
          ref={stageRef}
          className={`dr-stage${swapping ? ' is-swapping' : ''}${basemap ? ' has-basemap' : ''}`}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
        >
          {/* Leaflet's container. It holds the tiles, the zoom buttons and the
              scale bar, and it takes every pointer gesture: the canvas above it
              never intercepts one. */}
          <div ref={mapHostRef} className="dr-map" />
          <canvas ref={canvasRef} className="dr-canvas" aria-hidden="true" />

          <div className="dr-hud">
            <div className="dr-hud-item">
              <span className="dr-hud-label">{strings.elapsed}</span>
              <span className="dr-hud-value">{clock(t)}</span>
            </div>
            <div className="dr-hud-item">
              <span className="dr-hud-label">{strings.delivered}</span>
              <span className="dr-hud-value">
                {delivered}
                <span className="dr-hud-total">/{s.customers}</span>
              </span>
            </div>
          </div>

          <div className="dr-legend">
            <span className="dr-lg"><i className="dr-sw dr-sw--depot" />{strings.legend.depot}</span>
            <span className="dr-lg"><i className="dr-sw dr-sw--hub" />{strings.legend.hub}</span>
            <span className="dr-lg"><i className="dr-sw dr-sw--pending" />{strings.legend.pending}</span>
            <span className="dr-lg"><i className="dr-sw dr-sw--done" />{strings.legend.delivered}</span>
          </div>

          {hover && (
            <div
              className="dr-tip"
              style={{
                left: `${hover.x}px`,
                top: `${hover.y}px`,
                // Flip the tooltip inward near the right/bottom edges.
                transform: `translate(${hover.x > (sizeRef.current.w || 0) - 180 ? '-100%' : '12px'}, ${
                  hover.y > (sizeRef.current.h || 0) - 90 ? 'calc(-100% - 10px)' : '10px'
                })`,
              }}
            >
              {hover.lines.map((line, i) => (
                <div key={i} className={i === 0 ? 'dr-tip-head' : undefined}>
                  {line}
                </div>
              ))}
            </div>
          )}

          {/* The only thing that changes on the stage while a solve is in
              flight: the round underneath keeps driving. */}
          {(solving || ready) && (
            <div className={`dr-banner${ready ? ' dr-banner--ready' : ''}`} role="status">
              <span className="dr-banner-icon" aria-hidden="true">
                {solving ? <LoaderCircle size={15} className="dr-spinner" /> : <Sparkles size={15} />}
              </span>
              <span className="dr-banner-text">
                <b>{solving ? strings.solve.solvingTitle : strings.solve.readyTitle}</b>
                <span>
                  {solving
                    ? strings.solve.solvingSteady
                    : applied
                      ? summarise(applied)
                      : strings.solve.solvingSteady}
                </span>
                {solving && (
                  <span className="dr-banner-meta">
                    {strings.solve.solvingMeta
                      .replace('{elapsed}', String(solveSeconds))
                      .replace('{budget}', String(params.budgetSeconds))}
                  </span>
                )}
              </span>
              {solving && (
                <button
                  type="button"
                  className="dr-banner-cancel"
                  onClick={cancelSolve}
                  aria-label={strings.solve.cancel}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          )}
        </div>

        <div className="dr-controls">
          <button
            type="button"
            className="dr-btn dr-btn--primary"
            onClick={togglePlay}
            aria-label={playing ? strings.pause : strings.play}
          >
            {playing ? <Pause size={15} /> : <Play size={15} />}
            <span>{playing ? strings.pause : strings.play}</span>
          </button>

          <button type="button" className="dr-btn" onClick={restart} aria-label={strings.restart}>
            <RotateCcw size={15} />
          </button>

          <input
            className="dr-scrub"
            type="range"
            min={0}
            max={data.horizon}
            step={1}
            value={Math.round(t)}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label={strings.elapsed}
            aria-valuetext={clock(t)}
            style={{ ['--dr-progress' as string]: `${(t / data.horizon) * 100}%` }}
          />

          <div className="dr-speeds" role="group" aria-label={strings.speed}>
            {SPEEDS.map((sp, i) => (
              <button
                key={sp}
                type="button"
                className={`dr-speed${i === speedIndex ? ' is-active' : ''}`}
                onClick={() => setSpeedIndex(i)}
                aria-pressed={i === speedIndex}
              >
                ×{sp}
              </button>
            ))}
          </div>

          {/* The layer is the one thing on this page that reaches a third party,
              so the control that turns it off sits with the playback controls.

              The credit does not: it belongs to the map, and it is carried by
              the tile layer itself, so Leaflet puts it in the map's bottom right
              corner and takes it away with the layer. Nothing to keep in sync
              here, and nothing left in this row but the button. */}
          <div className="dr-mapctl">
            {/* One icon, pressed or not. The label lives in the accessible name
                rather than on screen: the map is either under the couriers or it
                is not, and the canvas answers that faster than a caption. */}
            <button
              type="button"
              className={`dr-btn dr-mapbtn${basemap ? ' is-active' : ''}`}
              aria-pressed={basemap}
              aria-label={strings.basemap.label}
              title={strings.basemap.label}
              onClick={() => setBasemapVisible(!basemap)}
            >
              <MapIcon size={15} aria-hidden="true" />
            </button>
          </div>
        </div>

        {reducedMotion && <p className="dr-note">{strings.reducedMotion}</p>}

        {/* ── Compose an instance and solve it ── */}
        <section className="dr-solve" aria-labelledby="dr-solve-title">
          <div className="dr-solve-head">
            <h2 className="dr-side-title" id="dr-solve-title">
              {strings.solve.title}
            </h2>
            <p className="dr-solve-lede">{strings.solve.lede}</p>
          </div>

          <div className="dr-solve-grid">
            <div className="dr-field">
              <label className="dr-field-label" htmlFor="dr-customers">
                {strings.solve.customers}
                <span className="dr-field-value">{params.customers}</span>
              </label>
              <input
                id="dr-customers"
                className="dr-range"
                type="range"
                min={CUSTOMERS.min}
                max={CUSTOMERS.max}
                step={CUSTOMERS.step}
                value={params.customers}
                disabled={solving}
                onChange={(e) => setParams((p) => ({ ...p, customers: Number(e.target.value) }))}
                style={{
                  ['--dr-progress' as string]: `${
                    ((params.customers - CUSTOMERS.min) / (CUSTOMERS.max - CUSTOMERS.min)) * 100
                  }%`,
                }}
              />
            </div>

            <div className="dr-field">
              <label className="dr-field-label" htmlFor="dr-capacity">
                {strings.solve.capacity}
                <span className="dr-field-value">{params.capacity}</span>
              </label>
              <input
                id="dr-capacity"
                className="dr-range"
                type="range"
                min={CAPACITY.min}
                max={CAPACITY.max}
                step={CAPACITY.step}
                value={params.capacity}
                disabled={solving}
                onChange={(e) => setParams((p) => ({ ...p, capacity: Number(e.target.value) }))}
                style={{
                  ['--dr-progress' as string]: `${
                    ((params.capacity - CAPACITY.min) / (CAPACITY.max - CAPACITY.min)) * 100
                  }%`,
                }}
              />
            </div>

            <div className="dr-field">
              <span className="dr-field-label" id="dr-vehicles-label">
                {strings.solve.vehicles}
              </span>
              <div className="dr-seg" role="group" aria-labelledby="dr-vehicles-label">
                {VEHICLE_CHOICES.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`dr-segbtn${n === params.vehicles ? ' is-active' : ''}`}
                    aria-pressed={n === params.vehicles}
                    disabled={solving}
                    onClick={() => setParams((p) => ({ ...p, vehicles: n }))}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            <div className="dr-field">
              <span className="dr-field-label" id="dr-hubs-label">
                {strings.solve.hubs}
              </span>
              <div className="dr-seg" role="group" aria-labelledby="dr-hubs-label">
                {HUB_CHOICES.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`dr-segbtn${n === params.hubs ? ' is-active' : ''}`}
                    aria-pressed={n === params.hubs}
                    disabled={solving}
                    onClick={() => setParams((p) => ({ ...p, hubs: n }))}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <button
            type="button"
            className={`dr-disclosure${advanced ? ' is-open' : ''}`}
            aria-expanded={advanced}
            aria-controls="dr-advanced"
            onClick={() => setAdvanced((a) => !a)}
          >
            <ChevronDown size={14} aria-hidden="true" />
            {strings.solve.advanced}
          </button>

          {advanced && (
            <div className="dr-solve-grid" id="dr-advanced">
              <div className="dr-field">
                <span className="dr-field-label" id="dr-tw-label">
                  {strings.solve.timeWindows}
                </span>
                <div className="dr-seg" role="group" aria-labelledby="dr-tw-label">
                  {[true, false].map((on) => (
                    <button
                      key={String(on)}
                      type="button"
                      className={`dr-segbtn${on === params.timeWindows ? ' is-active' : ''}`}
                      aria-pressed={on === params.timeWindows}
                      disabled={solving}
                      onClick={() => setParams((p) => ({ ...p, timeWindows: on }))}
                    >
                      {on ? strings.solve.on : strings.solve.off}
                    </button>
                  ))}
                </div>
              </div>

              <div className="dr-field">
                <span className="dr-field-label" id="dr-budget-label">
                  {strings.solve.budget}
                </span>
                <div className="dr-seg" role="group" aria-labelledby="dr-budget-label">
                  {BUDGET_CHOICES.map((n) => (
                    <button
                      key={n}
                      type="button"
                      className={`dr-segbtn${n === params.budgetSeconds ? ' is-active' : ''}`}
                      aria-pressed={n === params.budgetSeconds}
                      disabled={solving}
                      onClick={() => setParams((p) => ({ ...p, budgetSeconds: n }))}
                    >
                      {strings.solve.seconds.replace('{n}', String(n))}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="dr-actions">
            <button
              type="button"
              className="dr-btn dr-btn--primary"
              onClick={runSolve}
              disabled={solving || blocked}
            >
              <Sparkles size={15} aria-hidden="true" />
              <span>{strings.solve.run}</span>
            </button>

            <button
              type="button"
              className="dr-btn"
              onClick={showReference}
              disabled={solving || applied === null}
            >
              <RotateCcw size={15} aria-hidden="true" />
              <span>{strings.solve.reset}</span>
            </button>

            <p className="dr-solve-note">{strings.solve.liveNote}</p>
          </div>

          {/* Failures stay next to the button that caused them, and never touch
              the map: whatever was playing is still playing. */}
          <div className="dr-alert-slot" role="status" aria-live="polite">
            {failureText && (
              <p className="dr-alert">
                <TriangleAlert size={15} aria-hidden="true" />
                <span>{failureText}</span>
              </p>
            )}
          </div>
        </section>
      </div>

      <aside className="dr-side">
        <div className="dr-couriers">
          {data.vehicles.map((v) => {
            const st = states[v.id];
            const color = colors[v.id % colors.length];
            const active = focused === v.id;
            return (
              <button
                key={v.id}
                type="button"
                className={`dr-courier${active ? ' is-focused' : ''}`}
                onClick={() => setFocused(active ? null : v.id)}
                aria-pressed={active}
              >
                <span className="dr-courier-top">
                  <span className="dr-chip" style={{ background: color }}>{v.id + 1}</span>
                  <span className="dr-courier-name">
                    {strings.courier} {v.id + 1}
                  </span>
                  <span className={`dr-phase dr-phase--${st.phase}`}>{strings.phase[st.phase]}</span>
                </span>
                <span className="dr-gauge" aria-hidden="true">
                  <span
                    className="dr-gauge-fill"
                    style={{ width: `${(st.load / v.capacity) * 100}%`, background: color }}
                  />
                </span>
                <span className="dr-courier-meta">
                  <span>
                    {strings.load} <b>{st.load}</b>/{v.capacity}
                  </span>
                  <span>{strings.courierServed.replace('{n}', String(v.served))}</span>
                </span>
              </button>
            );
          })}
        </div>

        {deltas && applied && (
          <div className="dr-stats dr-delta">
            <h2 className="dr-side-title">{strings.delta.title}</h2>
            <dl>
              {deltas.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>
                    {row.value}
                    <span className={`dr-d dr-d--${row.tone}`}>{row.delta}</span>
                  </dd>
                </div>
              ))}
            </dl>
            <p className="dr-delta-ref">
              {strings.delta.reference.replace('{summary}', summarise(REFERENCE_PARAMS))}
            </p>
          </div>
        )}

        <div className="dr-stats">
          <h2 className="dr-side-title">{strings.stats.title}</h2>
          <dl>
            <div><dt>{strings.stats.served}</dt><dd>{s.customersServed}/{s.customers}</dd></div>
            <div><dt>{strings.stats.roadKm}</dt><dd>{s.roadKm} km</dd></div>
            <div><dt>{strings.stats.duration}</dt><dd>{hoursMinutes(s.horizon)}</dd></div>
            <div><dt>{strings.stats.cumulative}</dt><dd>{hoursMinutes(s.cumulativeDriveTime)}</dd></div>
            <div><dt>{strings.stats.reloads}</dt><dd>{s.reloads}</dd></div>
            <div><dt>{strings.stats.tardiness}</dt><dd>{s.tardinessMinutes} min</dd></div>
            <div className="dr-stat-wide">
              <dt>{strings.stats.hubs}</dt>
              <dd>
                {strings.stats.hubsValue
                  .replace('{available}', String(s.hubsAvailable))
                  .replace('{activated}', String(s.hubsActivated))}
              </dd>
            </div>
          </dl>
        </div>

        <div className="dr-feed">
          <h2 className="dr-side-title">{strings.events}</h2>
          <ul aria-live="polite">
            {visibleEvents.map((e, i) => (
              <li key={`${e.at}-${i}`}>
                <span className="dr-feed-time">{clock(e.at)}</span>
                {e.vehicle !== null && (
                  <i className="dr-feed-dot" style={{ background: colors[e.vehicle % colors.length] }} />
                )}
                <span>{e.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <p className="dr-provenance" lang={locale}>
        {strings.provenance.replace('{solver}', String(data.meta.solver))}
      </p>
    </div>
  );
}
