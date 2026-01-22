#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire de filtres (filters/facets) WiziShop
Version simplifiée avec cache pour minimiser les appels API
"""

import time
from threading import Lock
from typing import Dict, List, Optional


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
                if self.filters_cache:
                    # Afficher le nombre de facettes totales
                    total_facets = sum(len(f['facets']) for f in self.filters_cache.values())
                    print(f"   📊 {total_facets} facettes au total")
                return True
            else:
                print(f"⚠️ Impossible de charger les filtres (status {response.status_code})")
                return False

        except Exception as e:
            print(f"⚠️ Erreur chargement filtres: {e}")
            return False

    def ensure_filter_exists(self, filter_label: str) -> Optional[int]:
        """
        S'assure qu'un filtre existe, le crée si nécessaire (thread-safe)
        Args:
            filter_label: Nom du filtre
        Returns: ID du filtre ou None
        """
        with self.lock:
            label_lower = filter_label.lower()

            # Déjà dans le cache
            if label_lower in self.filters_cache:
                return self.filters_cache[label_lower]['id']

            # Créer le filtre
            print(f"  🆕 Création du filtre '{filter_label}'...")
            try:
                response = self.wizi_api.session.post(
                    f"{self.wizi_api.base_url}/product-filters/label",
                    headers=self.wizi_api.headers,
                    json={"label": filter_label},
                    timeout=30
                )

                if response.status_code == 201:
                    data = response.json()
                    filter_id = data.get('id')

                    # Ajouter au cache
                    self.filters_cache[label_lower] = {
                        'id': filter_id,
                        'label': filter_label,
                        'facets': {}
                    }

                    print(f"  ✅ Filtre créé (ID: {filter_id})")
                    return filter_id
                else:
                    print(f"  ❌ Erreur création filtre: {response.status_code}")
                    return None

            except Exception as e:
                print(f"  ❌ Exception création filtre: {e}")
                return None

    def ensure_facet_exists(self, filter_label: str, facet_value: str) -> Optional[int]:
        """
        S'assure qu'une facette existe pour un filtre, la crée si nécessaire (thread-safe)
        Args:
            filter_label: Nom du filtre
            facet_value: Valeur de la facette
        Returns: ID de la facette ou None
        """
        with self.lock:
            label_lower = filter_label.lower()
            value_lower = facet_value.lower()

            # Vérifier que le filtre existe
            if label_lower not in self.filters_cache:
                filter_id = self.ensure_filter_exists(filter_label)
                if not filter_id:
                    return None
            else:
                filter_id = self.filters_cache[label_lower]['id']

            # Vérifier si la facette existe déjà
            if value_lower in self.filters_cache[label_lower]['facets']:
                return self.filters_cache[label_lower]['facets'][value_lower]['id']

            # Créer la facette
            try:
                response = self.wizi_api.session.post(
                    f"{self.wizi_api.base_url}/product-filters/label/{filter_id}/facets",
                    headers=self.wizi_api.headers,
                    json={"value": facet_value},
                    timeout=30
                )

                if response.status_code == 201:
                    data = response.json()
                    facet_id = data.get('id')

                    # Ajouter au cache
                    self.filters_cache[label_lower]['facets'][value_lower] = {
                        'id': facet_id,
                        'value': facet_value
                    }

                    return facet_id
                else:
                    return None

            except Exception as e:
                return None

    def associate_filters_to_product(self, product_id: int, filters_data: Dict[str, List[str]]) -> bool:
        """
        Associe des filtres à un produit
        Args:
            product_id: ID du produit
            filters_data: dict comme {"Notes olfactives": ["Vanille", "Rose"]}
        Returns: True si succès
        """
        try:
            # Construire le payload selon l'API WiziShop
            product_filters = []

            for filter_label, facet_values in filters_data.items():
                # S'assurer que le filtre existe
                filter_id = self.ensure_filter_exists(filter_label)
                if not filter_id:
                    continue

                # S'assurer que toutes les facettes existent
                facets_list = []
                for facet_value in facet_values:
                    facet_id = self.ensure_facet_exists(filter_label, facet_value)
                    if facet_id:
                        facets_list.append({
                            "id": facet_id,
                            "value": facet_value,
                            "position": 0
                        })

                if facets_list:
                    product_filters.append({
                        "id": filter_id,
                        "label": filter_label,
                        "values": facets_list
                    })

            if not product_filters:
                return True  # Rien à associer

            # Associer les filtres au produit
            response = self.wizi_api.session.put(
                f"{self.wizi_api.base_url}/products/{product_id}/filters",
                headers=self.wizi_api.headers,
                json={"productFilters": product_filters},
                timeout=30
            )

            if response.status_code == 200:
                return True
            else:
                print(f"  ⚠️ Erreur association filtres (status {response.status_code})")
                return False

        except Exception as e:
            print(f"  ⚠️ Exception association filtres: {e}")
            return False

    def get_stats(self) -> Dict:
        """Retourne des stats sur les filtres en cache"""
        total_facets = sum(len(f['facets']) for f in self.filters_cache.values())
        return {
            'filters_count': len(self.filters_cache),
            'facets_count': total_facets
        }
