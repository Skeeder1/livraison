"""
Script de test pour trouver les positions optimales de hubs.

Ce script teste différentes positions de hub dans une grille et trouve
la position qui minimise le temps total de livraison.

Usage:
    python -m optimizer.tests.hub_optimization.test_hub_positions
"""

import os
import sys
import json
import copy
import numpy as np
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from optimizer.config import Config
from optimizer.data_loader import load_data
from optimizer.solver import solve_vrp_with_optimal_hubs
from optimizer.create_toy_data import create_toy_data


class HubPositionOptimizer:
    """Classe pour optimiser les positions de hubs par grid search."""

    def __init__(self, num_customers=45, num_vehicles=3, grid_resolution=10):
        """
        Initialise l'optimiseur de positions de hubs.

        :param num_customers: Nombre de clients
        :param num_vehicles: Nombre de véhicules
        :param grid_resolution: Résolution de la grille (nombre de positions par dimension)
        """
        self.num_customers = num_customers
        self.num_vehicles = num_vehicles
        self.grid_resolution = grid_resolution

        # Configuration de la grille de recherche
        self.position_range_min = Config.POSITION_RANGE_MIN
        self.position_range_max = Config.POSITION_RANGE_MAX

        # Résultats
        self.results = []
        self.best_result = None

        # Fichier de log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = f"optimizer/tests/hub_optimization/hub_optimization_{timestamp}.txt"

    def log(self, message):
        """Écrit un message dans le fichier de log et l'affiche."""
        print(message)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(message + '\n')

    def generate_grid_positions(self):
        """
        Génère une grille de positions possibles pour le hub.

        :return: Liste de positions (lat, lon)
        """
        lat_values = np.linspace(self.position_range_min, self.position_range_max, self.grid_resolution)
        lon_values = np.linspace(self.position_range_min, self.position_range_max, self.grid_resolution)

        positions = []
        for lat in lat_values:
            for lon in lon_values:
                positions.append((float(lat), float(lon)))

        return positions

    def test_hub_position(self, hub_position, test_num, total_tests):
        """
        Teste une position de hub spécifique.

        :param hub_position: Tuple (lat, lon) de la position du hub
        :param test_num: Numéro du test en cours
        :param total_tests: Nombre total de tests
        :return: Dictionnaire avec les résultats du test
        """
        self.log(f"\n{'='*80}")
        self.log(f"TEST {test_num}/{total_tests} - Position du hub: {hub_position}")
        self.log(f"{'='*80}")

        # Créer les données de test avec cette position de hub
        Config.update(NUM_CUSTOMERS=self.num_customers, NUM_VEHICLES=self.num_vehicles, NUM_HUBS=1)

        # Générer les données de base
        create_toy_data()

        # Charger les données
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'toy_data')
        data = load_data(data_dir)

        # Modifier la position du hub
        if len(data['hubs']) > 0:
            data['hubs'][0]['position'] = list(hub_position)
            # Mettre à jour les locations dans les données étendues
            hub_index = 1 + self.num_customers  # Premier hub après les clients
            if hub_index < len(data['locations']):
                data['locations'][hub_index] = list(hub_position)

        try:
            # Résoudre avec cette configuration
            manager, routing, solution, results, hubs_used = solve_vrp_with_optimal_hubs(data)

            if solution is None:
                self.log("❌ Aucune solution trouvée pour cette position")
                return None

            # Extraire les métriques
            total_time = results['indicators']['total_time_all_vehicles']
            total_distance = results['indicators']['total_distance']
            activated_hubs = results['indicators']['activated_hubs']

            result = {
                'hub_position': hub_position,
                'total_time_seconds': total_time,
                'total_time_hours': total_time / 3600.0,
                'total_distance': total_distance,
                'hubs_used': hubs_used,
                'activated_hubs': activated_hubs
            }

            self.log(f"✅ Temps total: {total_time/3600:.2f}h ({total_time:.0f}s)")
            self.log(f"   Distance totale: {total_distance:.2f}")
            self.log(f"   Hub utilisé: {'Oui' if hubs_used else 'Non'}")

            return result

        except Exception as e:
            self.log(f"❌ Erreur lors du test: {str(e)}")
            return None

    def optimize(self):
        """
        Lance l'optimisation complète sur toutes les positions de la grille.
        """
        self.log("\n" + "="*80)
        self.log("OPTIMISATION DES POSITIONS DE HUB")
        self.log("="*80)
        self.log(f"Configuration:")
        self.log(f"  - Clients: {self.num_customers}")
        self.log(f"  - Véhicules: {self.num_vehicles}")
        self.log(f"  - Résolution de la grille: {self.grid_resolution}x{self.grid_resolution}")
        self.log(f"  - Plage de positions: [{self.position_range_min}, {self.position_range_max}]")
        self.log(f"  - Fichier de log: {self.log_file}")

        # Générer les positions à tester
        positions = self.generate_grid_positions()
        total_tests = len(positions)

        self.log(f"\nNombre total de positions à tester: {total_tests}")
        self.log(f"\nDébut des tests...\n")

        # Tester chaque position
        for i, position in enumerate(positions, 1):
            result = self.test_hub_position(position, i, total_tests)
            if result:
                self.results.append(result)

                # Mettre à jour le meilleur résultat
                if self.best_result is None or result['total_time_seconds'] < self.best_result['total_time_seconds']:
                    self.best_result = result
                    self.log(f"\n🏆 NOUVEAU MEILLEUR RÉSULTAT!")
                    self.log(f"   Position: {result['hub_position']}")
                    self.log(f"   Temps: {result['total_time_hours']:.2f}h")

        # Résumé final
        self.generate_summary()

    def generate_summary(self):
        """Génère un résumé des résultats."""
        self.log("\n" + "="*80)
        self.log("RÉSUMÉ DE L'OPTIMISATION")
        self.log("="*80)

        if not self.results:
            self.log("❌ Aucun résultat valide trouvé")
            return

        # Statistiques globales
        total_tests = len(self.results)
        hubs_used_count = sum(1 for r in self.results if r['hubs_used'])

        self.log(f"\nTests réussis: {total_tests}")
        self.log(f"Hub utilisé dans: {hubs_used_count}/{total_tests} cas ({hubs_used_count/total_tests*100:.1f}%)")

        # Meilleur résultat
        if self.best_result:
            self.log(f"\n🏆 MEILLEURE POSITION DE HUB:")
            self.log(f"   Position: {self.best_result['hub_position']}")
            self.log(f"   Temps total: {self.best_result['total_time_hours']:.2f}h ({self.best_result['total_time_seconds']:.0f}s)")
            self.log(f"   Distance totale: {self.best_result['total_distance']:.2f}")
            self.log(f"   Hub utilisé: {'Oui' if self.best_result['hubs_used'] else 'Non'}")

        # Top 5 des meilleures positions
        self.log(f"\n📊 TOP 5 DES MEILLEURES POSITIONS:")
        sorted_results = sorted(self.results, key=lambda x: x['total_time_seconds'])
        for i, result in enumerate(sorted_results[:5], 1):
            self.log(f"   {i}. Position {result['hub_position']}: {result['total_time_hours']:.2f}h (hub {'utilisé' if result['hubs_used'] else 'non utilisé'})")

        # Pire position
        worst_result = sorted_results[-1]
        self.log(f"\n📊 PIRE POSITION:")
        self.log(f"   Position {worst_result['hub_position']}: {worst_result['total_time_hours']:.2f}h")

        # Différence entre meilleur et pire
        time_diff = worst_result['total_time_hours'] - self.best_result['total_time_hours']
        improvement_pct = (time_diff / worst_result['total_time_hours']) * 100
        self.log(f"\n📈 AMÉLIORATION POSSIBLE:")
        self.log(f"   Gain de temps: {time_diff:.2f}h ({improvement_pct:.1f}% d'amélioration)")

        # Sauvegarder les résultats en JSON
        json_file = self.log_file.replace('.txt', '.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                'configuration': {
                    'num_customers': self.num_customers,
                    'num_vehicles': self.num_vehicles,
                    'grid_resolution': self.grid_resolution,
                    'position_range': [self.position_range_min, self.position_range_max]
                },
                'best_result': self.best_result,
                'all_results': self.results
            }, f, indent=2)

        self.log(f"\n💾 Résultats sauvegardés dans:")
        self.log(f"   - Logs: {self.log_file}")
        self.log(f"   - JSON: {json_file}")
        self.log("\n" + "="*80)


def main():
    """Point d'entrée principal du script."""
    print("🚀 Démarrage de l'optimisation des positions de hubs...\n")

    # Configuration du test
    # Pour un test rapide, utiliser une grille 5x5 (25 positions)
    # Pour un test complet, utiliser une grille 10x10 (100 positions)
    optimizer = HubPositionOptimizer(
        num_customers=30,      # Réduire pour tests plus rapides
        num_vehicles=3,
        grid_resolution=5      # 5x5 = 25 positions à tester
    )

    # Lancer l'optimisation
    optimizer.optimize()

    print("\n✅ Optimisation terminée!")


if __name__ == '__main__':
    main()
