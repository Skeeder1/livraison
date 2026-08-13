"""
Invariants du document de tournée, partagés par plusieurs tests.

Le consommateur web suppose ces sept propriétés et n'en vérifie aucune. Elles
sont donc affirmées à deux endroits : sur un document construit à la main
(`tests/unit/test_tour_format.py`, instantané) et sur une vraie résolution
(`tests/integration/test_scenario.py`). Une seule implémentation, pour que les
deux vérifient exactement le même contrat.
"""


def assert_tour_invariants(tour):
    """
    Vérifie les sept invariants attendus par le consommateur.

    :param tour: Document retourné par `optimizer.tour_format.build_tour`
    """
    assert tour['vehicles'], "un document sans véhicule n'est pas rejouable"

    for i, vehicle in enumerate(tour['vehicles']):
        assert vehicle['id'] == i, (
            f"vehicles[{i}].id vaut {vehicle['id']} : le consommateur indexe par position"
        )
        assert len(vehicle['legs']) == len(vehicle['stops']) - 1, (
            f"véhicule {i} : {len(vehicle['legs'])} segments pour {len(vehicle['stops'])} arrêts ; "
            "l'animation associe chaque segment au couple d'arrêts qui l'encadre"
        )

        arrivals = [stop['arrive'] for stop in vehicle['stops']]
        assert arrivals == sorted(arrivals), (
            f"véhicule {i} : heures d'arrivée non croissantes {arrivals}"
        )

        for j, leg in enumerate(vehicle['legs']):
            assert leg['pts'], (
                f"véhicule {i}, segment {j} : polyligne vide, le véhicule n'aurait "
                "aucune position à interpoler"
            )

    assert tour['horizon'] == max(v['end'] for v in tour['vehicles']), (
        "horizon doit être la fin de la dernière tournée : c'est la borne du curseur temporel"
    )
    assert tour['horizon'] > 0, "un horizon nul rendrait l'animation immobile"

    customer_nodes = {c['node'] for c in tour['customers']}
    served_nodes = {
        stop['node']
        for vehicle in tour['vehicles']
        for stop in vehicle['stops']
        if stop['kind'] == 'customer'
    }
    assert served_nodes <= customer_nodes, (
        f"arrêts clients hors de la liste des clients : {sorted(served_nodes - customer_nodes)}"
    )

    bounds = tour['bounds']
    assert bounds['minLat'] != bounds['maxLat'], "emprise dégénérée en latitude"
    assert bounds['minLng'] != bounds['maxLng'], "emprise dégénérée en longitude"
