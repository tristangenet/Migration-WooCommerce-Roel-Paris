#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire de caractéristiques (features) WiziShop
"""

import requests
import json
import time
from typing import Dict, Set, List, Optional, Tuple


class FeatureManager:
    """Gère les caractéristiques produits (features) de WiziShop"""

    def __init__(self, api_base_url: str, access_token: str):
        self.api_base_url = api_base_url
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        self.features_cache = {}  # {nom: id}

    def preload_all_features(self) -> Dict[str, int]:
        """
        Pré-charge toutes les features existantes depuis l'API
        Returns: dict {nom_feature: id}
        """
        print("\n🔧 Pré-chargement des caractéristiques existantes...")
        url = f"{self.api_base_url}/product-features"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                features = data.get('data', [])

                for feat in features:
                    name = feat.get('name')
                    feat_id = feat.get('id')
                    if name and feat_id:
                        self.features_cache[name] = feat_id

                print(f"✅ {len(self.features_cache)} caractéristiques pré-chargées")
                return self.features_cache
            else:
                print(f"⚠️ Erreur {response.status_code} lors du chargement des features")
                return {}

        except Exception as e:
            print(f"❌ Erreur préchargement features : {e}")
            return {}

    def create_feature(self, feature_name: str) -> Optional[int]:
        """
        Crée une nouvelle feature
        Returns: ID de la feature créée ou None
        """
        url = f"{self.api_base_url}/product-features"
        payload = {"name": feature_name}

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code == 201:
                feat_id = response.json().get('data', {}).get('id')
                if feat_id:
                    self.features_cache[feature_name] = feat_id
                    print(f"   ✅ Feature créée : {feature_name} (ID: {feat_id})")
                    return feat_id
            else:
                print(f"   ⚠️ Erreur {response.status_code} création feature '{feature_name}'")
                return None

        except Exception as e:
            print(f"   ❌ Erreur création feature '{feature_name}' : {e}")
            return None

    def ensure_features_exist(self, feature_names: Set[str]) -> Dict[str, int]:
        """
        S'assure que toutes les features existent, crée les manquantes
        Args:
            feature_names: Set de noms de features nécessaires
        Returns: dict {nom: id} de toutes les features
        """
        print(f"\n🔍 Vérification de {len(feature_names)} caractéristiques...")

        missing = [name for name in feature_names if name not in self.features_cache]

        if missing:
            print(f"📝 Création de {len(missing)} caractéristiques manquantes...")
            for name in missing:
                self.create_feature(name)
                time.sleep(0.2)  # Rate limiting léger
        else:
            print("✅ Toutes les caractéristiques existent déjà")

        return self.features_cache

    def build_features_payload(self, features_data: Dict[str, str]) -> List[Dict]:
        """
        Construit le payload features pour l'API produit
        Args:
            features_data: dict {nom_feature: valeur}
        Returns: Liste de features pour le payload API
        """
        features_list = []

        for feat_name, value in features_data.items():
            if not value:
                continue

            feat_id = self.features_cache.get(feat_name)
            if feat_id:
                features_list.append({
                    "feature_id": feat_id,
                    "value": value
                })

        return features_list

    def get_feature_id(self, feature_name: str) -> Optional[int]:
        """Retourne l'ID d'une feature par son nom"""
        return self.features_cache.get(feature_name)


def scan_csv_for_features(csv_path: str) -> Tuple[Set[str], Dict[str, Set[str]]]:
    """
    Scanne le CSV pour identifier toutes les features nécessaires
    Returns: (set de noms de features, dict {feature_name: set de valeurs})
    """
    import pandas as pd

    print(f"\n📊 Scan du CSV pour identifier les caractéristiques...")

    df = pd.read_csv(csv_path, dtype=str)

    feature_names = set()
    feature_values = {}

    # Notes olfactives
    if 'Notes olfactives' in df.columns:
        notes = df['Notes olfactives'].dropna()
        notes = notes[notes != '']
        if len(notes) > 0:
            feature_names.add('Notes olfactives')
            # Extraire toutes les valeurs uniques (séparées par ', ')
            all_notes = set()
            for note_str in notes:
                for note in note_str.split(', '):
                    note = note.strip()
                    if note:
                        all_notes.add(note)
            feature_values['Notes olfactives'] = all_notes
            print(f"   🌸 Notes olfactives : {len(all_notes)} valeurs uniques")

    # Contenance
    if 'Contenance' in df.columns:
        contenances = df['Contenance'].dropna()
        contenances = contenances[contenances != '']
        if len(contenances) > 0:
            feature_names.add('Contenance')
            all_cont = set()
            for cont_str in contenances:
                for cont in cont_str.split(', '):
                    cont = cont.strip()
                    if cont:
                        all_cont.add(cont)
            feature_values['Contenance'] = all_cont
            print(f"   📏 Contenance : {len(all_cont)} valeurs uniques")

    print(f"✅ {len(feature_names)} types de caractéristiques identifiés")

    return feature_names, feature_values
