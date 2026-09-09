# `@skeeder/delivery-replay`

Le rejeu animé d'une tournée CVRPTW sur carte Leaflet, en composant React.

C'est **la même interface que celle du site portfolio** (`/demos/delivery`),
extraite ici pour que ce dépôt en soit propriétaire. Elle remplace
`vrp_visualization.html`, la page Leaflet claire générée par folium.

Le paquet ne transporte **aucune donnée** : la tournée à rejouer est une prop, et
le solveur est une option. `demo/tour.json` est le choix de l'application de
démo, pas une dépendance de la bibliothèque.

## Lancer la démo en local

```bash
cd web
npm install
npm run dev          # http://localhost:5173
```

La page rejoue `demo/tour.json`. Le panneau « Générez votre propre tournée »
fonctionne hors ligne : la démo branche le solveur simulé (`mock-solver.ts`), qui
construit une tournée synthétique dans le navigateur. Le fond de carte télécharge
des tuiles OpenStreetMap ; le bouton carte le coupe.

## Scripts

| Commande             | Effet                                                        |
| -------------------- | ------------------------------------------------------------ |
| `npm run dev`        | Serveur de développement sur `demo/`                          |
| `npm run build`      | `tsc --noEmit` puis build bibliothèque → `dist/`               |
| `npm run build:demo` | Build de la page de démo → `dist-demo/`                        |
| `npm run preview`    | Sert le build produit                                          |
| `npm run typecheck`  | `tsc --noEmit` seul                                            |

Le build bibliothèque produit `dist/delivery-replay.js` (ESM),
`dist/delivery-replay.umd.cjs` (UMD), `dist/delivery-replay.css` et les fichiers
de déclaration. React et React-DOM restent externes : c'est l'application hôte
qui les fournit.

## Utilisation

```tsx
import {
  DeliveryReplay,
  demoStrings,
  validateTour,
  type Tour,
} from '@skeeder/delivery-replay';
import '@skeeder/delivery-replay/style.css'; // uniquement si vous consommez dist/

import tourJson from './ma-tournee.json';

const tour = tourJson as unknown as Tour;
const reason = validateTour(tour);
if (reason) throw new Error(`tournée invalide : ${reason}`);

<DeliveryReplay tour={tour} strings={demoStrings.fr} locale="fr" />;
```

### Props

| Prop            | Type                | Défaut         | Rôle                                                                             |
| --------------- | ------------------- | -------------- | -------------------------------------------------------------------------------- |
| `tour`          | `Tour`              | —              | La tournée chargée à l'arrivée, et la référence à laquelle une tournée générée est comparée. |
| `strings`       | `DemoStrings`       | —              | Tous les libellés. `demoStrings.en` / `demoStrings.fr` sont fournis.              |
| `locale`        | `'en' \| 'fr'`      | —              | Formatage des nombres et attribut `lang`.                                        |
| `solveEndpoint` | `string`            | `'/api/solve'` | Où vit le solveur réel. Ignoré si `solve` est fourni.                             |
| `solve`         | `SolveFn`           | POST endpoint  | Solveur prêt à l'emploi (simulé, transport maison…).                              |

### Solveur

```ts
import { createSolve } from '@skeeder/delivery-replay';

// Le vrai endpoint
const solve = createSolve({ endpoint: '/api/solve' });

// Le simulateur, pour développer sans backend. `reference` lui donne la
// géométrie qu'il emprunte (dépôt, cadre, adresses).
const mock = createSolve({ mock: true, reference: tour });
```

`createSolve` valide toujours la réponse avec `validateTour` avant de la rendre :
un solveur qui régresse son format de sortie remonte comme une erreur explicite
plutôt qu'en toile blanche.

## Format de la tournée

`src/tour.ts` décrit la forme complète (`Tour`, `Vehicle`, `Stop`, `Leg`,
`TourStats`) et `validateTour` vérifie les invariants dont dépend le rendu :
identifiants de véhicules positionnels, arrêts triés par heure d'arrivée, un
segment par paire d'arrêts, `horizon` cohérent avec la fin de la dernière
tournée. À utiliser sur toute tournée produite par l'optimiseur du dépôt avant de
la passer au composant.

## Provenance

| Fichier                 | Origine (`Github/portfolio`)         |
| ----------------------- | ------------------------------------ |
| `src/DeliveryReplay.tsx`| `src/components/DeliveryReplay.tsx`  |
| `src/tour.ts`           | `src/lib/delivery/tour.ts`           |
| `src/solve.ts`          | `src/lib/delivery/solve.ts`          |
| `src/mock-solver.ts`    | `src/lib/delivery/mock-solver.ts`    |
| `src/strings.ts`        | `src/i18n/delivery-demo.ts`          |
| `src/delivery-replay.css` | les deux sections `.dr-*` de `src/styles/global.css` |
| `demo/tour.json`        | `src/data/delivery-tour.json`        |

L'esthétique est reprise telle quelle et sera retravaillée plus tard.
