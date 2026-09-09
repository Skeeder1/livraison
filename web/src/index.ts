/**
 * Public surface of `@skeeder/delivery-replay`.
 *
 * The package owns the replay UI shown on the portfolio site, extracted so the
 * `livraison` repo renders exactly the same map without depending on Astro or
 * on anything else site-specific. It ships no data: the tour to replay is a
 * prop, and the solver endpoint is an option.
 */

export { default as DeliveryReplay } from './DeliveryReplay';

export { validateTour } from './tour';
export type { Tour, TourStats, Vehicle, Stop, Leg, StopKind } from './tour';

export {
  BUDGET_CHOICES,
  CAPACITY,
  CUSTOMERS,
  DEFAULT_PARAMS,
  HUB_CHOICES,
  SOLVE_ENDPOINT,
  SolveError,
  TIMEOUT_GRACE_SECONDS,
  VEHICLE_CHOICES,
  createSolve,
  solve,
} from './solve';
export type { SolveErrorCode, SolveFn, SolveOptions, SolveParams } from './solve';

export { demoStrings, demoPageStrings } from './strings';
export type { DemoStrings, DemoPageStrings } from './strings';
