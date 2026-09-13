/**
 * Strings for the delivery replay demo.
 *
 * Deliberately kept out of `en.ts` / `fr.ts`: those declare `fr: Strings` against
 * an `as const` English object, which pins every value to its English *literal*
 * type. Adding a block there means every French string is a type error the build
 * happens not to surface. A plain interface implemented twice avoids that.
 *
 * `{placeholder}` tokens are substituted in DeliveryReplay.tsx.
 */

export interface DemoStrings {
  play: string;
  pause: string;
  restart: string;
  speed: string;
  elapsed: string;
  delivered: string;
  /** Labels under the four numbers above the map. They follow the tour on
   *  screen, so they moved out of the Astro page and into the island. */
  headline: { served: string; couriers: string; roadKm: string; reloads: string };
  /** The optional street map under the couriers. `attribution` is a licence
   *  term, not a caption: it shows whenever the layer does. */
  basemap: { label: string; on: string; off: string; attribution: string };
  /** Accessible names for Leaflet's own controls. The map is pannable and
   *  zoomable, and its buttons ship with English titles unless they are given
   *  ours. */
  map: { zoomIn: string; zoomOut: string };
  solve: {
    title: string;
    lede: string;
    customers: string;
    vehicles: string;
    hubs: string;
    capacity: string;
    advanced: string;
    timeWindows: string;
    on: string;
    off: string;
    budget: string;
    seconds: string;
    minutes: string;
    auto: string;
    rerun: string;
    show: string;
    modeReady: string;
    modeReadyHint: string;
    modeAbsent: string;
    modeFixed: string;
    rerunHint: string;
    fromBaked: string;
    autoChosen: string;
    autoInfoLabel: string;
    autoInfoTitle: string;
    autoInfoBody: string;
    autoInfoSource: string;
    run: string;
    cancel: string;
    reset: string;
    solvingTitle: string;
    solvingSteady: string;
    solvingMeta: string;
    readyTitle: string;
    summary: string;
    liveNote: string;
  };
  delta: { title: string; reference: string; unchanged: string };
  errors: {
    notConfigured: string;
    rateLimited: string;
    rateLimitedWait: string;
    dailyCap: string;
    upstream: string;
    timeout: string;
    badRequest: string;
    network: string;
    retry: string;
  };
  courier: string;
  courierServed: string;
  load: string;
  phase: { driving: string; serving: string; waiting: string; done: string; idle: string };
  legend: { depot: string; hub: string; pending: string; serving: string; delivered: string };
  events: string;
  eventStart: string;
  eventReload: string;
  eventHub: string;
  eventDone: string;
  stats: {
    title: string;
    roadKm: string;
    duration: string;
    cumulative: string;
    served: string;
    reloads: string;
    tardiness: string;
    hubs: string;
    hubsValue: string;
  };
  tooltip: { customer: string; window: string; servedBy: string; at: string; notYet: string };
  /** Formats the closing time of an all-day window. */
  allDay: string;
  reducedMotion: string;
  provenance: string;
}

export interface DemoPageStrings {
  eyebrow: string;
  title: string;
  lede: string;
  back: string;
  repo: string;
  hint: string;
  readTitle: string;
  read: string[];
  findingTitle: string;
  finding: string;
}

const en: DemoStrings = {
  play: 'Play',
  pause: 'Pause',
  restart: 'Restart',
  speed: 'Playback speed',
  elapsed: 'Elapsed',
  delivered: 'Delivered',
  headline: {
    served: 'customers served',
    couriers: 'couriers',
    roadKm: 'of real streets',
    reloads: 'reloads',
  },
  basemap: {
    label: 'City map',
    on: 'On',
    off: 'Off',
    attribution: '© OpenStreetMap contributors',
  },
  map: {
    zoomIn: 'Zoom in',
    zoomOut: 'Zoom out',
  },
  solve: {
    title: 'Generate your own tour',
    lede: 'Set an instance, run the solver, compare what comes back with the reference round.',
    customers: 'Customers',
    vehicles: 'Couriers',
    hubs: 'Transfer hubs',
    capacity: 'Parcels per courier',
    advanced: 'Advanced',
    timeWindows: 'Time windows',
    on: 'On',
    off: 'Off',
    budget: 'Search budget',
    seconds: '{n} s',
    minutes: '{n} min',
    auto: 'Auto',
    rerun: 'Recalculate the result',
    show: 'Show result',
    modeReady: 'Already calculated',
    modeReadyHint: 'This result is stored, so it appears at once. Recalculating runs the solver again on the same settings and can give a different route.',
    modeAbsent: 'Not stored yet. The solver will run, about {n} s.',
    modeFixed: 'Fixed time. The solver will run for {n} s.',
    rerunHint: 'Run the solver again on these settings.',
    fromBaked: 'Previously computed result. No new search was needed.',
    autoChosen: 'Auto: {n} s for {customers} customers',
    autoInfoLabel: 'What a search budget buys',
    autoInfoTitle: 'Fitted to the instance',
    autoInfoBody:
      'The budget is a ceiling, not a stopping rule: the search keeps improving its best tour until the clock runs out. How long it needs varies enormously with size — ten customers settle in about two seconds, sixty still gain ground at forty-five. This setting asks for the measured time for the size you chose, so a small round stops paying for seconds it cannot use and a large one stops being cut off early.',
    autoInfoSource:
      'Read off convergence curves from {runs} solves: the smallest budget within 0.5% of a one-minute search for the typical instance, and 5% for three in four.',
    run: 'Generate',
    cancel: 'Cancel',
    reset: 'Reference tour',
    solvingTitle: 'Solving your instance',
    solvingSteady: 'Nothing on the map changes until the result lands.',
    solvingMeta: '{elapsed} s, budget {budget} s',
    readyTitle: 'New tour ready',
    summary: '{customers} customers, {vehicles} couriers, {capacity} parcels each',
    liveNote: 'Every combination of settings was calculated once in advance, so results appear instantly. The solver still runs whenever you ask it to recalculate.',
  },
  delta: {
    title: 'Against the reference',
    reference: 'Reference: {summary}',
    unchanged: 'unchanged',
  },
  errors: {
    notConfigured:
      'Live solving is switched off on this deployment. The tour on screen is unaffected.',
    rateLimited: 'Too many runs from this address.',
    rateLimitedWait: 'Try again in {n} s.',
    dailyCap:
      'The daily solver budget for this demo is spent. It resets tomorrow, and the tour on screen keeps playing.',
    upstream: 'The solver did not return a usable plan. Nothing on screen changed.',
    timeout: 'No answer within the {n} s budget. Try fewer customers, or a longer budget.',
    badRequest: 'The solver rejected those parameters. Adjust them and run again.',
    network: 'The request could not reach the solver. Check the connection and run again.',
    retry: 'Try again',
  },
  courier: 'Courier',
  courierServed: '{n} delivered',
  load: 'Load',
  phase: {
    driving: 'driving',
    serving: 'handing over',
    waiting: 'waiting',
    done: 'done',
    idle: 'idle',
  },
  legend: {
    depot: 'Depot',
    hub: 'Exchange point',
    pending: 'To deliver',
    serving: 'Unloading',
    delivered: 'Delivered',
  },
  events: 'Event log',
  eventStart: '{n} couriers leave the depot, {cap} parcels each',
  eventReload: 'Courier {v} reloads at the depot, going from {from} to {to} parcels',
  eventHub: 'Courier {v} passes a hub without transferring',
  eventDone: 'Courier {v} is back at the depot, {n} customers served',
  stats: {
    title: 'Solution',
    roadKm: 'Road distance',
    duration: 'Longest route',
    cumulative: 'Cumulative',
    served: 'Customers served',
    reloads: 'Mid-route reloads',
    tardiness: 'Total lateness',
    hubs: 'Hubs',
    // Kept to the bare fact: the editorial reading of it belongs to the
    // reference round, and this panel now also describes tours you generate.
    hubsValue: '{available} candidates, {activated} used',
  },
  tooltip: {
    customer: 'Customer {n}',
    window: 'Window {from} to {to}',
    servedBy: 'Courier {v}',
    at: 'Delivered at {time}',
    notYet: 'Scheduled for {time}',
  },
  reducedMotion:
    'Reduced motion is on, so playback starts paused. Press Play, or drag the timeline.',
  allDay: '24:00',
  provenance:
    'Solved once with {solver}, then frozen into a static file at build time. The round itself is served from this repository and replays without any network. Two things do reach outside the page: the city map loads tiles from OpenStreetMap, which is why the map button turns it off, and generating your own tour calls the solver.',
};

const fr: DemoStrings = {
  play: 'Lecture',
  pause: 'Pause',
  restart: 'Recommencer',
  speed: 'Vitesse de lecture',
  elapsed: 'Écoulé',
  delivered: 'Livrés',
  headline: {
    served: 'clients servis',
    couriers: 'coursiers',
    roadKm: 'de rues réelles',
    reloads: 'rechargements',
  },
  basemap: {
    label: 'Fond de carte',
    on: 'Oui',
    off: 'Non',
    attribution: '© les contributeurs OpenStreetMap',
  },
  map: {
    zoomIn: 'Zoomer',
    zoomOut: 'Dézoomer',
  },
  solve: {
    title: 'Générez votre propre tournée',
    lede:
      'Composez une instance, lancez le solveur, comparez le résultat à la tournée de référence.',
    customers: 'Clients',
    vehicles: 'Coursiers',
    hubs: 'Hubs de transfert',
    capacity: 'Colis par coursier',
    advanced: 'Avancé',
    timeWindows: 'Fenêtres horaires',
    on: 'Oui',
    off: 'Non',
    budget: 'Budget de recherche',
    seconds: '{n} s',
    minutes: '{n} min',
    auto: 'Auto',
    rerun: 'Recalculer le résultat',
    show: 'Afficher le résultat',
    modeReady: 'Déjà calculée',
    modeReadyHint: 'Ce résultat est enregistré, il apparaît donc aussitôt. Recalculer relance le solveur sur les mêmes réglages et peut donner un autre trajet.',
    modeAbsent: 'Pas encore enregistrée. Le solveur tournera, environ {n} s.',
    modeFixed: 'Durée fixe. Le solveur tournera {n} s.',
    rerunHint: 'Relancer le solveur sur ces réglages.',
    fromBaked: 'Résultat déjà calculé. Aucune nouvelle recherche nécessaire.',
    autoChosen: 'Auto : {n} s pour {customers} clients',
    autoInfoLabel: 'Ce qu\'achète un budget de recherche',
    autoInfoTitle: 'Ajusté à l\'instance',
    autoInfoBody:
      'Le budget est un plafond, pas un critère d\'arrêt : la recherche améliore sa meilleure tournée jusqu\'à la fin du temps imparti. Le temps qu\'il lui faut varie énormément avec la taille — dix clients sont réglés en deux secondes environ, soixante gagnent encore du terrain à quarante-cinq. Ce réglage demande le temps mesuré pour la taille choisie : une petite tournée cesse de payer des secondes inutilisables, une grande cesse d\'être coupée trop tôt.',
    autoInfoSource:
      'Lu sur les courbes de convergence de {runs} résolutions : le plus petit budget à 0,5 % d\'une recherche d\'une minute pour l\'instance typique, et à 5 % pour trois sur quatre.',
    run: 'Générer',
    cancel: 'Annuler',
    reset: 'Tournée de référence',
    solvingTitle: 'Résolution de votre instance',
    solvingSteady: 'Rien ne change sur la carte tant que le résultat n’est pas arrivé.',
    solvingMeta: '{elapsed} s, budget {budget} s',
    readyTitle: 'Nouvelle tournée prête',
    summary: '{customers} clients, {vehicles} coursiers, {capacity} colis chacun',
    liveNote: 'Chaque combinaison de réglages a été calculée une fois à l’avance, les résultats apparaissent donc instantanément. Le solveur tourne dès que vous demandez à recalculer.',
  },
  delta: {
    title: 'Face à la référence',
    reference: 'Référence : {summary}',
    unchanged: 'identique',
  },
  errors: {
    notConfigured:
      'La résolution en direct est désactivée sur ce déploiement. La tournée affichée n’est pas touchée.',
    rateLimited: 'Trop de lancements depuis cette adresse.',
    rateLimitedWait: 'Réessayez dans {n} s.',
    dailyCap:
      'Le budget quotidien du solveur pour cette démo est épuisé. Il repart demain, et la tournée affichée continue de tourner.',
    upstream: 'Le solveur n’a pas renvoyé de plan exploitable. Rien n’a changé à l’écran.',
    timeout:
      'Aucune réponse dans le budget de {n} s. Essayez moins de clients, ou un budget plus long.',
    badRequest: 'Le solveur a refusé ces paramètres. Ajustez-les et relancez.',
    network: 'La requête n’a pas pu atteindre le solveur. Vérifiez la connexion et relancez.',
    retry: 'Réessayer',
  },
  courier: 'Coursier',
  courierServed: '{n} livrés',
  load: 'Charge',
  phase: {
    driving: 'en route',
    serving: 'en livraison',
    waiting: 'en attente',
    done: 'terminé',
    idle: 'à l’arrêt',
  },
  legend: {
    depot: 'Dépôt',
    hub: 'Point d\u2019échange',
    pending: 'À livrer',
    serving: 'Déchargement',
    delivered: 'Livré',
  },
  events: 'Journal',
  eventStart: '{n} coursiers quittent le dépôt, {cap} colis chacun',
  eventReload: 'Coursier {v} se recharge au dépôt, de {from} à {to} colis',
  eventHub: 'Coursier {v} passe devant un hub sans transférer',
  eventDone: 'Coursier {v} est rentré au dépôt, {n} clients servis',
  stats: {
    title: 'Solution',
    roadKm: 'Distance routière',
    duration: 'Tournée la plus longue',
    cumulative: 'Temps cumulé',
    served: 'Clients servis',
    reloads: 'Rechargements',
    tardiness: 'Retard total',
    hubs: 'Hubs',
    hubsValue: '{available} candidats, {activated} utilisé',
  },
  tooltip: {
    customer: 'Client {n}',
    window: 'Fenêtre de {from} à {to}',
    servedBy: 'Coursier {v}',
    at: 'Livré à {time}',
    notYet: 'Prévu à {time}',
  },
  reducedMotion:
    'Animations réduites : la lecture démarre en pause. Appuyez sur Lecture, ou déplacez la timeline.',
  allDay: '24:00',
  provenance:
    'Résolu une fois avec {solver}, puis figé dans un fichier statique à la compilation. La tournée elle-même est servie depuis ce dépôt et se rejoue sans aucun réseau. Deux choses sortent bien de la page : le fond de carte charge des tuiles OpenStreetMap, ce que le bouton carte permet de couper, et générer votre propre tournée appelle le solveur.',
};

const pageEn: DemoPageStrings = {
  eyebrow: 'Interactive demo',
  title: 'Replaying an optimised delivery round',
  lede:
    'Three couriers, 45 customers, 10 parcels of capacity each. Google OR-Tools planned the routes; this page replays the solution it produced, second by second, on the real Paris street network. Change the instance below the map and the solver runs again on demand.',
  back: 'Back to projects',
  repo: 'Solver source',
  hint: 'Space to play or pause, ← → to scrub, drag or zoom the map, click a courier to isolate their round.',
  readTitle: 'How to read it',
  read: [
    'Each courier leaves the depot loaded with 10 parcels. The gauge under the marker drains with every delivery, which is the capacity constraint doing its work.',
    'When a gauge hits zero the courier must return to the depot to reload before continuing. Three such reloads happen; watch the load snap back to 10.',
    'Routes follow genuine road geometry from OSRM, not straight lines between customers, so the distances on screen are road distances rather than crow flies.',
  ],
  findingTitle: 'The result worth pointing at',
  finding:
    'Two shared hubs are drawn on the map, and this round uses neither. A hub is not a refuelling stop: it is a place where one courier leaves a parcel for another to pick up, so it only pays when the handover saves more than the detour costs. Restocking is a different thing entirely, and it happens back at the depot, which is what the three reloads in this round are. This snapshot was frozen before a fix to how the solver handles hubs, so read the two it rides past as a property of this recording rather than as a verdict on hubs.',
};

const pageFr: DemoPageStrings = {
  eyebrow: 'Démo interactive',
  title: 'Rejouer une tournée de livraison optimisée',
  lede:
    'Trois coursiers, 45 clients, 10 colis de capacité chacun. Google OR-Tools a planifié les tournées ; cette page rejoue la solution obtenue, seconde par seconde, sur le vrai réseau de rues parisien. Modifiez l’instance sous la carte et le solveur repart à la demande.',
  back: 'Retour aux projets',
  repo: 'Code du solveur',
  hint: 'Espace pour lancer ou mettre en pause, ← → pour naviguer, déplacez ou zoomez la carte, cliquez un coursier pour isoler sa tournée.',
  readTitle: 'Comment lire la carte',
  read: [
    'Chaque coursier quitte le dépôt chargé de 10 colis. La jauge sous le marqueur se vide à chaque livraison : c’est la contrainte de capacité à l’œuvre.',
    'Quand une jauge atteint zéro, le coursier doit repasser au dépôt pour se recharger avant de continuer. Trois rechargements ont lieu ; la charge remonte alors d’un coup à 10.',
    'Les tournées suivent la géométrie routière réelle fournie par OSRM, et non des lignes droites entre clients : les distances affichées sont des distances par la route, pas à vol d’oiseau.',
  ],
  findingTitle: 'Le résultat qui mérite d’être souligné',
  finding:
    'Deux hubs partagés sont tracés sur la carte, et cette tournée n’en utilise aucun. Un hub n’est pas une station de rechargement : c’est un endroit où un coursier dépose un colis qu’un autre viendra prendre, et il ne vaut le coup que si le transfert fait gagner plus que le détour ne coûte. Le rechargement, lui, est autre chose et se fait au dépôt : ce sont les trois rechargements de cette tournée. Cet instantané a été figé avant un correctif sur la façon dont le solveur traite les hubs, donc les deux qu’il dépasse sont une propriété de cet enregistrement, pas un verdict sur les hubs.',
};

export const demoStrings = { en, fr } as const;
export const demoPageStrings = { en: pageEn, fr: pageFr } as const;
