/**
 * Standalone page for the delivery replay.
 *
 * This replaces `vrp_visualization.html`, the folium-generated Leaflet page the
 * repo used to ship: same data, same map library underneath, but the UI is now
 * the one the portfolio site shows, owned here as `@skeeder/delivery-replay`.
 *
 * The page picks the two things the library deliberately does not carry: the
 * tour to replay (`demo/tour.json`) and a solver. Here the solver is the mock,
 * which builds a synthetic tour in the browser so the "generate your own tour"
 * panel works with no backend running. Point it at the real endpoint with
 * `createSolve({ endpoint: '/api/solve' })` — or just drop the `solve` prop,
 * which is what the component defaults to.
 */

import { StrictMode, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';

import {
  DeliveryReplay,
  createSolve,
  demoPageStrings,
  demoStrings,
  validateTour,
  type Tour,
} from '../src/index';

import tourJson from './tour.json';

const tour = tourJson as unknown as Tour;

const reason = validateTour(tour);
if (reason) {
  // Better a loud console than a canvas that silently stays blank.
  throw new Error(`demo/tour.json is not replayable: ${reason}`);
}

type Locale = 'en' | 'fr';

function App() {
  const [locale, setLocale] = useState<Locale>('fr');
  const page = demoPageStrings[locale];

  // The mock stands in for `POST /api/solve` so the panel is usable offline.
  const solve = useMemo(() => createSolve({ mock: true, reference: tour }), []);

  return (
    <>
      <header className="demo-head">
        <h1>{page.title}</h1>
        <p>{page.lede}</p>
        <div className="demo-locale">
          {(['fr', 'en'] as const).map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={locale === l}
              onClick={() => setLocale(l)}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </header>

      <DeliveryReplay
        key={locale}
        tour={tour}
        strings={demoStrings[locale]}
        locale={locale}
        solve={solve}
      />
    </>
  );
}

const host = document.getElementById('app');
if (!host) throw new Error('#app is missing from index.html');

createRoot(host).render(
  <StrictMode>
    <App />
  </StrictMode>
);
