#!/usr/bin/env python3
"""
Script pour mettre à jour les marques des produits WiziShop déjà importés
Utilise les logs d'import pour récupérer les IDs et met à jour via l'API
"""

import json
import pandas as pd
from pathlib import Path
from wizishop_api import WiziShopAPI

def load_config():
    """Charge la config API depuis config.json"""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    print("🔄 Mise à jour des marques des produits WiziShop\n")

    # Chargement de la config
    config = load_config()
    wizi_api = WiziShopAPI(
        store_id=config['wizishop']['store_id'],
        api_key=config['wizishop']['api_key']
    )

    # Chemins
    csv_path = Path(__file__).parent / "input" / "woocommerce_converted_with_filters_enrichi.csv"
    log_path = Path(__file__).parent / "output" / "wizi_products_log_2026-01-22_14-47-01.json"

    # Lecture du CSV
    print(f"📄 Lecture du CSV : {csv_path.name}")
    df = pd.read_csv(csv_path)

    # Lecture des logs
    print(f"📄 Lecture des logs : {log_path.name}")
    with open(log_path, 'r', encoding='utf-8') as f:
        products_log = json.load(f)

    # Créer un mapping CSV line -> WiziShop ID
    csv_to_wizi = {}
    for p in products_log:
        if '_csv_line' in p and '_api_response' in p and 'id' in p['_api_response']:
            csv_line = p['_csv_line']
            wizi_id = p['_api_response']['id']
            current_brand = p.get('brand', '')
            csv_to_wizi[csv_line] = {
                'wizi_id': wizi_id,
                'name': p.get('name', ''),
                'current_brand': current_brand
            }

    print(f"✅ {len(csv_to_wizi)} produits trouvés dans les logs\n")

    # Identifier les produits à mettre à jour
    updates_needed = []

    for idx, row in df.iterrows():
        csv_line = idx + 2  # +2 car ligne 1 = header, index commence à 0
        main_cat = str(row.get('Catégorie principale', '')).strip()
        sub_cat = str(row.get('Catégorie secondaire', '')).strip()
        brand_csv = str(row.get('Marque', '')).strip() if pd.notna(row.get('Marque')) else ''
        product_name = row.get('Nom du produit', '')

        # Si la catégorie principale est "Marques", la vraie marque est la sous-catégorie
        if main_cat.lower() == 'marques' and sub_cat:
            correct_brand = sub_cat
        elif brand_csv:
            correct_brand = brand_csv
        else:
            continue  # Pas de mise à jour nécessaire

        # Vérifier si ce produit est dans les logs
        if csv_line in csv_to_wizi:
            wizi_info = csv_to_wizi[csv_line]
            current_brand = wizi_info['current_brand']

            # Mise à jour nécessaire si la marque actuelle n'est pas la bonne
            if current_brand != correct_brand:
                updates_needed.append({
                    'wizi_id': wizi_info['wizi_id'],
                    'name': product_name,
                    'current_brand': current_brand,
                    'correct_brand': correct_brand,
                    'csv_line': csv_line
                })

    print(f"🔍 {len(updates_needed)} produits nécessitent une mise à jour de marque\n")

    if not updates_needed:
        print("✅ Aucune mise à jour nécessaire !")
        return

    # Afficher les mises à jour prévues
    print("📋 Mises à jour prévues :")
    for u in updates_needed[:10]:
        print(f"  • {u['name']}: '{u['current_brand']}' → '{u['correct_brand']}'")
    if len(updates_needed) > 10:
        print(f"  ... et {len(updates_needed) - 10} autres")

    # Demander confirmation
    print(f"\n⚠️ Voulez-vous mettre à jour ces {len(updates_needed)} produits ? (y/n): ", end='')
    confirm = input().strip().lower()

    if confirm != 'y':
        print("❌ Mise à jour annulée")
        return

    # Effectuer les mises à jour
    print(f"\n🚀 Mise à jour en cours...\n")
    success_count = 0
    error_count = 0

    for u in updates_needed:
        try:
            # Mise à jour via l'API
            payload = {'brand': u['correct_brand']}
            response = wizi_api.update_product(u['wizi_id'], payload)

            if response.get('id'):
                print(f"✅ {u['name']}: marque mise à jour → {u['correct_brand']}")
                success_count += 1
            else:
                print(f"❌ {u['name']}: échec - {response}")
                error_count += 1

        except Exception as e:
            print(f"❌ {u['name']}: erreur - {str(e)}")
            error_count += 1

    # Résumé
    print(f"\n📊 Résumé des mises à jour :")
    print(f"   ✅ Succès : {success_count}")
    print(f"   ❌ Erreurs : {error_count}")

if __name__ == "__main__":
    main()
