#!/usr/bin/env bash
#
# Contrôle complet du dépôt, exécuté en local.
#
# Ce script tient lieu d'intégration continue. GitHub Actions n'est pas
# disponible sur ce compte, et une CI qui ne peut pas démarrer ne produit que
# des croix rouges : mieux vaut une porte qui tourne vraiment, ici, avant que
# le code ne parte.
#
#   scripts/check.sh           tout : lint, tests, types, interface
#   scripts/check.sh --rapide  sans les tests lents ni l'interface (~1 min)
#
# Le crochet pre-push appelle la variante rapide. La variante complète est à
# lancer avant une étiquette de version ou après un changement de modèle.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
RACINE=$(pwd)
RAPIDE=0
[ "${1:-}" = "--rapide" ] && RAPIDE=1

VERT=$'\033[32m'; ROUGE=$'\033[31m'; GRIS=$'\033[90m'; GRAS=$'\033[1m'; ZERO=$'\033[0m'
ECHECS=()

titre() { printf '\n%s──  %s%s\n' "$GRAS" "$1" "$ZERO"; }
etape() {
  local nom=$1; shift
  local debut; debut=$(date +%s)
  if "$@" > /tmp/check-$$.log 2>&1; then
    printf '  %s✓%s %-34s %s%ss%s\n' "$VERT" "$ZERO" "$nom" "$GRIS" "$(( $(date +%s) - debut ))" "$ZERO"
  else
    printf '  %s✗%s %-34s %s%ss%s\n' "$ROUGE" "$ZERO" "$nom" "$GRIS" "$(( $(date +%s) - debut ))" "$ZERO"
    sed 's/^/      /' /tmp/check-$$.log | tail -25
    ECHECS+=("$nom")
  fi
  rm -f /tmp/check-$$.log
}

PY="$RACINE/.venv/bin/python"
if [ ! -x "$PY" ]; then
  printf '%s✗%s Aucun environnement en .venv. Créer avec :\n' "$ROUGE" "$ZERO"
  printf '    uv venv && uv pip install -e ".[dev]"\n'
  exit 1
fi

titre "Python"
etape "ruff" "$PY" -m ruff check optimizer tests experiments
if [ "$RAPIDE" = 1 ]; then
  etape "pytest (sans les lents)" "$PY" -m pytest -q -m "not slow"
else
  etape "pytest (suite complète)" "$PY" -m pytest -q
fi

if [ "$RAPIDE" = 0 ]; then
  titre "Interface web"
  if [ -d web/node_modules ]; then
    etape "tsc --noEmit" npm --prefix web run typecheck
    etape "build" npm --prefix web run build
  else
    printf '  %s—%s %-34s %snpm ci --prefix web pour l activer%s\n' "$GRIS" "$ZERO" "ignorée" "$GRIS" "$ZERO"
  fi
fi

printf '\n'
if [ ${#ECHECS[@]} -eq 0 ]; then
  printf '%s✓ tout passe%s\n' "$VERT$GRAS" "$ZERO"
  exit 0
fi
printf '%s✗ %d étape(s) en échec : %s%s\n' "$ROUGE$GRAS" "${#ECHECS[@]}" "${ECHECS[*]}" "$ZERO"
exit 1
