#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire de filtres (filters/facets) WiziShop
Version simplifiée avec cache pour minimiser les appels API
"""

import time
from threading import Lock
from typing import Dict, Set, List, Optional


class FilterManager:
    """Gère les filtres produits (sidebar e-commerce) de WiziShop"""

    def __init__(self, wizi_api):
        """
        Args:
            wizi_api: Instance de WiziShopAPI
        """
        self.wizi_api = wizi_api
        self.filters_cache = {}  # {label_lower: {id: int, label: str, facets: {value_lower: {id: int, value: str}}}}
        self.lock = Lock()

    def load_existing_filters(self) -> bool:
        """
        Charge tous les filtres existants en un seul appel API
        Returns: True si succès
        """
        print("\n🔍 Chargement des filtres existants...")
        try:
            response = self.wizi_api.session.get(
                f"{self.wizi_api.base_url}/product-filters/label",
                headers=self.wizi_api.headers,
                timeout=30
            )

            if response.status_code == 200:
                filters_data = response.json()

                for filter_item in filters_data:
                    filter_id = filter_item.get('id')
                    filter_label = filter_item.get('label', '')

                    # Cache les facettes de ce filtre
                    facets = {}
                    for facet in filter_item.get('values', []):
                        facet_value = facet.get('value', '')
                        facets[facet_value.lower()] = {
                            'id': facet.get('id'),
                            'value': facet_value
                        }

                    self.filters_cache[filter_label.lower()] = {
                        'id': filter_id,
                        'label': filter_label,
                        'facets': facets
                    }

                print(f"✅ {len(self.filters_cache)} filtres chargés")
                return True
            else:
                print(f"⚠️ Impossible de charger les filtres (status {response.status_code})")
                return False

        except Exception as e:
            print(f"⚠️ Erreur chargement filtres: {e}")
            return False

    def preload_facets_for_filter(self, filter_id: int) -> Dict[str, int]:
        """
        Pré-charge toutes les facets d'un filtre
        Returns: dict {value: facet_id}
        """
        url = f"{self.api_base_url}/product-filters/label/{filter_id}"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                facets = data.get('data', {}).get('facets', [])

                facets_dict = {}
                for facet in facets:
                    value = facet.get('value')
                    facet_id = facet.get('id')
                    if value and facet_id:
                        self.facets_cache[(filter_id, value)] = facet_id
                        facets_dict[value] = facet_id

                return facets_dict
            else:
                return {}

        except Exception as e:
            print(f"   ⚠️ Erreur chargement facets filtre {filter_id} : {e}")
            return {}

    def create_filter(self, label: str, position: int = 1) -> Optional[int]:
        """
        Crée un nouveau filtre
        Returns: ID du filtre créé ou None
        """
        url = f"{self.api_base_url}/product-filters/label"
        payload = {
            "label": label,
            "position": position
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code == 201:
                filt_id = response.json().get('data', {}).get('id')
                if filt_id:
                    self.filters_cache[label] = filt_id
                    print(f"   ✅ Filtre créé : {label} (ID: {filt_id})")
                    return filt_id
            else:
                print(f"   ⚠️ Erreur {response.status_code} création filtre '{label}'")
                return None

        except Exception as e:
            print(f"   ❌ Erreur création filtre '{label}' : {e}")
            return None

    def create_facet(self, filter_id: int, value: str) -> Optional[int]:
        """
        Crée une nouvelle facet pour un filtre
        Returns: ID de la facet créée ou None
        """
        url = f"{self.api_base_url}/product-filters/label/{filter_id}/facets"
        payload = {"value": value}

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code == 201:
                facet_id = response.json().get('data', {}).get('id')
                if facet_id:
                    self.facets_cache[(filter_id, value)] = facet_id
                    return facet_id
            else:
                return None

        except Exception as e:
            return None

    def ensure_filters_and_facets_exist(self, filters_data: Dict[str, Set[str]]):
        """
        S'assure que tous les filtres et leurs facets existent
        Args:
            filters_data: dict {filter_label: set de valeurs}
        """
        print(f"\n🔍 Vérification de {len(filters_data)} filtres...")

        for label, values in filters_data.items():
            # Créer le filtre si nécessaire
            if label not in self.filters_cache:
                print(f"📝 Création du filtre : {label}")
                filter_id = self.create_filter(label)
                time.sleep(0.2)
            else:
                filter_id = self.filters_cache[label]
                print(f"✅ Filtre existant : {label} (ID: {filter_id})")

            if not filter_id:
                continue

            # Pré-charger les facets existantes
            existing_facets = self.preload_facets_for_filter(filter_id)

            # Créer les facets manquantes
            missing_values = [v for v in values if v not in existing_facets]
            if missing_values:
                print(f"   📝 Création de {len(missing_values)} facets pour '{label}'...")
                for value in missing_values:
                    self.create_facet(filter_id, value)
                    time.sleep(0.1)  # Rate limiting
            else:
                print(f"   ✅ Toutes les facets existent ({len(values)} valeurs)")

    def build_filters_payload(self, product_filters: Dict[str, List[str]]) -> Dict:
        """
        Construit le payload filters pour associer au produit
        Args:
            product_filters: dict {filter_label: [valeurs]}
        Returns: Payload pour PUT /products/{id}/filters
        """
        filters_list = []

        for label, values in product_filters.items():
            filter_id = self.filters_cache.get(label)
            if not filter_id or not values:
                continue

            facet_values = []
            for value in values:
                facet_id = self.facets_cache.get((filter_id, value))
                if facet_id:
                    facet_values.append({
                        "id": facet_id,
                        "value": value
                    })

            if facet_values:
                filters_list.append({
                    "filter_id": filter_id,
                    "facet_values": facet_values
                })

        return {"product_filters": filters_list}

    def associate_filters_to_product(self, product_id: int, filters_payload: Dict) -> bool:
        """
        Associe les filtres à un produit
        Returns: True si succès
        """
        url = f"{self.api_base_url}/products/{product_id}/filters"

        try:
            response = requests.put(url, headers=self.headers, json=filters_payload, timeout=30)
            return response.status_code in [200, 201, 204]

        except Exception as e:
            print(f"   ⚠️ Erreur association filtres produit {product_id} : {e}")
            return False
