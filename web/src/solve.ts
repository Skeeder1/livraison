/**
 * Client side of the "solve your own instance" action on /demos/delivery.
 *
 * The endpoint is a plain POST returning the exact JSON shape of
 * `src/data/delivery-tour.json`, or an error body `{ error, code,
 * retryAfterSeconds? }` matching the Clothify demo's convention.
 *
 * Until `POST /api/solve` ships, development runs against `mock-solver.ts`,
 * which builds a real (synthetic) tour in the browser after a realistic delay.
 * `createSolve({ mock: true, reference })` is the entire switch, and the mock is
 * loaded with a dynamic import so it never reaches a production bundle that does
 * not ask for it.
 */

import { validateTour, type Tour } from './tour';

// ─── Parameters ──────────────────────────────────────────────────────────────

export interface SolveParams {
  customers: number;
  vehicles: number;
  hubs: number;
  capacity: number;
  timeWindows: boolean;
  /** Search budget handed to the solver. Capped, never free text. */
  budgetSeconds: number;
  /** Where `budgetSeconds` came from.
   *
   *  `'fixed'` means the visitor picked one of `BUDGET_CHOICES`. `'fitted'`
   *  means `budgetForInstance` derived it from the customer count, in which case
   *  `budgetSeconds` still carries the resolved number — the panel, the client
   *  deadline and the request body all want a value, not a mode. Keeping the
   *  resolved seconds in the same field is what stops the mode from leaking into
   *  every message and timeout that already reads it. */
  budgetMode: 'fixed' | 'fitted';
}

export const CUSTOMERS = { min: 10, max: 60, step: 5 } as const;
export const CAPACITY = { min: 5, max: 20, step: 1 } as const;
export const VEHICLE_CHOICES = [1, 2, 3, 4, 5, 6] as const;
export const HUB_CHOICES = [0, 1, 2, 3] as const;
/** Durées de recherche proposées, en secondes.
 *
 *  Mesuré : sur une instance à 45 clients, la dernière amélioration d'une
 *  recherche de 10 s tombe à 9 996 ms — elle progressait encore quand le temps
 *  s'est arrêté. Les budgets courts ne convergent pas, et rien ne le disait au
 *  visiteur. */
export const BUDGET_CHOICES = [5, 15, 30, 60] as const;

/** Budgets mesurés, par nombre de clients, en secondes.
 *
 *  Mesuré, pas supposé : 180 résolutions, quatre tailles x trois flottes x trois
 *  capacites x cinq graines, chacune sous un plafond d'une minute, avec la
 *  trajectoire complete des solutions ameliorantes enregistree
 *  (`experiments/convergence.py`, journal dans `experiments/out/`).
 *
 *  Chaque budget est le plus petit dont l'ecart a ce que trouve une recherche
 *  d'une minute reste sous 0,5 % en mediane et sous 5 % au quantile 0,75, pour
 *  **toutes** les flottes et capacites mesurees a cette taille. Le critere porte
 *  sur l'ecart d'objectif et non sur la date de la derniere amelioration : le
 *  visiteur ne demande pas si la recherche a fini, il demande a combien de la
 *  meilleure tournee connue il se trouve.
 *
 *  Le resultat contredit ce que le budget par defaut supposait. Ce ne sont pas
 *  les grandes instances qui sont trop servies, ce sont les petites : dix
 *  clients convergent en deux secondes, quinze en depensent sept fois trop,
 *  tandis que soixante clients en demandent quarante-cinq et n'en recevaient
 *  que quinze.
 *
 *  La difficulte n'est indexee que sur le nombre de clients, et c'est la mesure
 *  qui l'impose : la flotte ne l'ordonne pas. A 45 clients, deux livreurs sont
 *  plus faciles que trois — moins de tournees, donc un espace de recherche plus
 *  petit — alors que l'intuition dit l'inverse. */
const BUDGET_MEASURED: ReadonlyArray<readonly [customers: number, seconds: number]> = [
  [10, 2],
  [25, 20],
  [45, 30],
  [60, 45],
];

/** Budget de recherche ajusté à l'instance, en secondes.
 *
 *  Entre deux tailles mesurées, une interpolation linéaire. Au-delà des bornes,
 *  la valeur de la borne : extrapoler affirmerait quelque chose qui n'a pas été
 *  mesuré, et le panneau ne sort de toute façon pas de 10–60 clients.
 *
 *  Les durées viennent d'un processeur de portable sous profil « économie
 *  d'énergie », pas de la machine qui sert la démonstration. Un coude est une
 *  durée : sur un processeur deux fois plus lent il tombe deux fois plus tard.
 *  Le chiffre est donc un ordre de grandeur mesuré, pas une garantie. */
export function budgetForInstance(customers: number): number {
  const table = BUDGET_MEASURED;
  if (customers <= table[0][0]) return table[0][1];
  const last = table[table.length - 1];
  if (customers >= last[0]) return last[1];
  for (let i = 1; i < table.length; i += 1) {
    const [hiC, hiS] = table[i];
    if (customers <= hiC) {
      const [loC, loS] = table[i - 1];
      return Math.round(loS + ((hiS - loS) * (customers - loC)) / (hiC - loC));
    }
  }
  return last[1];
}


/** The reference instance, so an untouched panel describes what is on screen
 *  when the visitor arrives.
 *
 *  `hubs` is the one field that deliberately does NOT mirror the frozen round.
 *  That round was offered two hubs and used neither, and the endpoint cannot
 *  reproduce "offered but unused": it solves the configuration it is asked for,
 *  and a hub above zero means couriers actually transfer parcels there. On this
 *  data the detour costs far more than the rebalancing saves, measured at 481 km
 *  against 113 km for the same instance without hubs, so defaulting to 2 would
 *  make every visitor's first click look three times worse than the reference it
 *  is compared against. The control still goes up to 3: that trade is worth
 *  discovering, it is just not worth pre-selecting. */
export const DEFAULT_PARAMS: SolveParams = {
  customers: 45,
  vehicles: 3,
  hubs: 0,
  capacity: 10,
  timeWindows: false,
  // Fitted by default. Two reasons, and the second is the stronger: it is the
  // budget the measurements say this instance needs, and it is the only mode the
  // pre-solved corpus can answer — so a first click returns a real tour
  // instantly, spends no CPU, and costs the demo's daily budget nothing.
  budgetMode: 'fitted',
  // Ni le minimum ni le maximum : à 5 s la recherche n'a pas convergé, et la
  // comparaison avec la tournée de référence accablerait le solveur pour une
  // raison qui tient au budget et non au modèle.
  // Kept in step with `budgetMode` above: this is what `budgetForInstance`
  // returns for 45 customers, so the panel is honest before anything is solved.
  budgetSeconds: 30,
};

/** Wall-clock slack on top of the search budget before the client gives up.
 *  Covers cold starts and the round trip without letting a hung request hang
 *  the panel forever. */
export const TIMEOUT_GRACE_SECONDS = 6;

// ─── Errors ──────────────────────────────────────────────────────────────────

export type SolveErrorCode =
  | 'not_configured'
  | 'bad_request'
  | 'rate_limited'
  | 'daily_cap'
  | 'upstream_error'
  | 'timeout'
  | 'network';

export class SolveError extends Error {
  readonly code: SolveErrorCode;
  readonly retryAfterSeconds?: number;

  constructor(code: SolveErrorCode, message: string, retryAfterSeconds?: number) {
    super(message || code);
    this.name = 'SolveError';
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

interface SolveErrorResponse {
  error?: string;
  code?: string;
  retryAfterSeconds?: number;
}

const KNOWN_CODES = new Set<SolveErrorCode>([
  'not_configured',
  'bad_request',
  'rate_limited',
  'daily_cap',
  'upstream_error',
]);

/** What an HTTP status means when the body carries no usable `code`. 404 counts
 *  as "not configured": on a static deployment the route simply is not there. */
function codeForStatus(status: number): SolveErrorCode {
  if (status === 503 || status === 404) return 'not_configured';
  if (status === 429) return 'rate_limited';
  if (status === 400 || status === 422) return 'bad_request';
  return 'upstream_error';
}

// ─── Transport ───────────────────────────────────────────────────────────────

export const SOLVE_ENDPOINT = '/api/solve';

/** `force` skips the pre-solved corpus and makes the solver run. It is what the
 *  "run the solver" action passes, and the only way to get a fresh search for a
 *  configuration that is already baked. */
export interface SolveRunOptions {
  force?: boolean;
}

export type SolveFn = (
  params: SolveParams,
  signal: AbortSignal,
  options?: SolveRunOptions,
) => Promise<Tour>;

const postSolve =
  (endpoint: string): SolveFn =>
  async (params, signal) => {
  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      // `budgetMode` stays on the client: the endpoint is handed a number of
      // seconds and has no use for where it came from. Sending it would put a
      // field in the contract that nothing reads.
      body: JSON.stringify({ ...params, budgetMode: undefined }),
    });
  } catch (cause) {
    // An abort is the caller's business (cancel or timeout), so it is rethrown
    // untouched; anything else here is a transport failure.
    if ((cause as Error)?.name === 'AbortError') throw cause;
    throw new SolveError('network', String((cause as Error)?.message ?? cause));
  }

  // A 500 from a proxy can be HTML, and an empty 503 has no body at all.
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const body = (payload ?? {}) as SolveErrorResponse;
    const code =
      body.code && KNOWN_CODES.has(body.code as SolveErrorCode)
        ? (body.code as SolveErrorCode)
        : codeForStatus(response.status);
    const header = Number(response.headers.get('Retry-After'));
    throw new SolveError(
      code,
      body.error ?? `HTTP ${response.status}`,
      body.retryAfterSeconds ?? (Number.isFinite(header) && header > 0 ? header : undefined)
    );
  }

  return payload as Tour;
};

export interface SolveOptions {
  /** Where the real solver lives. Defaults to `SOLVE_ENDPOINT`. */
  endpoint?: string;
  /** THE SWITCH. `true` builds a synthetic tour in the browser instead of
   *  calling the endpoint. Requires `reference`. */
  mock?: boolean;
  /** Geometry the mock borrows (depot, bounds, address pool). Only read when
   *  `mock` is on; this is what keeps the frozen tour out of the library. */
  reference?: Tour;
}

/** Where the pre-solved corpus is served from. Written by
 *  `scripts/bake-delivery-configs.py` in the portfolio, one file per
 *  configuration. */
const BAKED_BASE = '/demos/delivery/baked';

/** Filename for one configuration's pre-solved tour.
 *
 *  Mirrors `cle()` in `scripts/bake-delivery-configs.py`, including the rule
 *  that a single courier cannot use a hub: a hub exists so two couriers can hand
 *  parcels over, so the endpoint drops the hubs in that case and the key has to
 *  drop them too, or a visitor asking for one courier and two hubs would read a
 *  different tour depending on where it came from.
 *
 *  `budgetSeconds` is deliberately absent. Every baked tour was solved at the
 *  fitted budget, so the corpus may only answer a request that asked for the
 *  fitted budget. Putting the budget in the key would suggest the corpus covers
 *  the four fixed durations, which it does not. */
export function bakedKey(params: SolveParams): string {
  const hubs = params.vehicles === 1 ? 0 : params.hubs;
  return `c${params.customers}-v${params.vehicles}-h${hubs}-k${params.capacity}-tw${
    params.timeWindows ? 1 : 0
  }`;
}

/** Whether the pre-solved corpus can answer the configuration on screen.
 *
 *  `'absent'` is a perfectly normal state, not a fault: 54 of the 7 392
 *  configurations were refused at bake time because the tour they produce is one
 *  the canvas could not draw, and any configuration can be widened into the plan
 *  later. What it must never be is a surprise — a visitor pressing a button
 *  labelled "show" and waiting thirty seconds has been lied to. */
export type BakedState = 'checking' | 'ready' | 'absent' | 'fixed-budget';

/** Asks whether the corpus holds this configuration, without downloading it.
 *
 *  A `HEAD` request rather than a manifest, and the choice is deliberate. A
 *  manifest of 7 392 keys is 130 KB every visitor would pay for on arrival, and
 *  it would be a second thing to keep in step with the corpus — a stale entry
 *  would make the panel promise an instant answer it cannot give. Asking the
 *  server is a few hundred bytes, needs nothing kept in sync, and is right by
 *  construction.
 *
 *  Any failure reads as `'absent'`. Being wrong in that direction costs a label
 *  that undersells; being wrong the other way promises an instant tour and then
 *  makes the visitor wait. */
export async function bakedState(
  params: SolveParams,
  signal?: AbortSignal,
): Promise<BakedState> {
  // The corpus is solved exclusively at the fitted budget, so a visitor who
  // picked one of the four fixed durations is asking for a search, full stop.
  if (params.budgetMode !== 'fitted') return 'fixed-budget';
  try {
    const response = await fetch(`${BAKED_BASE}/${bakedKey(params)}.json`, {
      method: 'HEAD',
      signal,
    });
    return response.ok ? 'ready' : 'absent';
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') throw cause;
    return 'absent';
  }
}

/** True when this tour came out of the pre-solved corpus rather than a solver
 *  run just now. Read from the document, so it cannot disagree with it. */
export function isBaked(tour: Tour): boolean {
  return Boolean((tour.meta as Record<string, unknown> | undefined)?.baked);
}

/** Fetches the pre-solved tour for a configuration, or `null` if there is none.
 *
 *  A missing configuration is a 404 and nothing more: the corpus is built in
 *  priority order and is useful at every prefix, so "not baked yet" is a normal
 *  state rather than a fault. That is also why there is no manifest — the
 *  presence of the file IS the manifest. A malformed or truncated file is
 *  treated like a missing one: fall through to the solver rather than show a
 *  broken round. */
async function fetchBaked(params: SolveParams, signal: AbortSignal): Promise<Tour | null> {
  let response: Response;
  try {
    response = await fetch(`${BAKED_BASE}/${bakedKey(params)}.json`, { signal });
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') throw cause;
    return null;
  }
  if (!response.ok) return null;
  try {
    const tour = (await response.json()) as Tour;
    return validateTour(tour) ? null : tour;
  } catch {
    return null;
  }
}

/**
 * Builds a solver. It runs one solve and guarantees the result is safe to
 * render: both paths go through `validateTour`, so a solver that regresses its
 * output format surfaces as an honest error instead of a blank canvas.
 */
export function createSolve(options: SolveOptions = {}): SolveFn {
  const endpoint = options.endpoint ?? SOLVE_ENDPOINT;
  const reference = options.reference;

  return async (params, signal, runOptions) => {
    // The corpus only answers for the fitted budget, and only when the visitor
    // has not asked for a fresh run. Serving a baked 30 s tour to someone who
    // picked "5 s" would answer a question they did not ask, and the delta card
    // would compare against a budget that was never spent.
    if (params.budgetMode === 'fitted' && !runOptions?.force && !options.mock) {
      const baked = await fetchBaked(params, signal);
      if (baked) return baked;
    }

    let tour: Tour;
    if (options.mock) {
      if (!reference) {
        throw new SolveError('not_configured', 'mock solver needs a reference tour');
      }
      tour = await (await import('./mock-solver')).mockSolve(params, signal, reference);
    } else {
      tour = await postSolve(endpoint)(params, signal);
    }

    const reason = validateTour(tour);
    if (reason) throw new SolveError('upstream_error', `malformed tour: ${reason}`);
    return tour;
  };
}

/** The default solver: `POST /api/solve`, no mock. */
export const solve: SolveFn = createSolve();
