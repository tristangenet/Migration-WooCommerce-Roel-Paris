import json
import pandas as pd

# Charger les données
log = json.load(open(r'c:\Users\Loic Blanc\Documents\dev\woo_migration\3-load\output\wizi_products_log_2026-01-22_14-47-01.json', encoding='utf-8'))
df = pd.read_csv(r'c:\Users\Loic Blanc\Documents\dev\woo_migration\3-load\input\woocommerce_converted_with_filters_enrichi.csv')

# Créer mapping CSV line -> info
csv_to_info = {}
for idx, row in df.iterrows():
    csv_line = idx + 2
    main_cat = str(row.get('Catégorie principale', '')).strip()
    sub_cat = str(row.get('Catégorie secondaire', '')).strip()
    brand_csv = str(row.get('Marque', '')).strip() if pd.notna(row.get('Marque')) else ''

    # Déterminer la marque attendue
    if main_cat.lower() == 'marques' and sub_cat:
        expected_brand = sub_cat
    elif brand_csv:
        expected_brand = brand_csv
    else:
        expected_brand = 'Roel Paris'

    csv_to_info[csv_line] = {
        'expected_brand': expected_brand,
        'brand_csv': brand_csv,
        'main_cat': main_cat,
        'sub_cat': sub_cat
    }

# Analyser les produits importés
roel_count = 0
discrepancies = []
brands_in_log = {}

for p in log:
    if '_csv_line' in p and 'brand' in p:
        csv_line = p['_csv_line']
        current_brand = p['brand']

        brands_in_log[current_brand] = brands_in_log.get(current_brand, 0) + 1

        if current_brand == 'Roel Paris':
            roel_count += 1

        if csv_line in csv_to_info:
            expected = csv_to_info[csv_line]['expected_brand']
            if current_brand != expected:
                discrepancies.append({
                    'name': p.get('name', ''),
                    'current': current_brand,
                    'expected': expected,
                    'csv_line': csv_line
                })

print("Analyse des marques :")
print("\n1. Marques dans les logs WiziShop :")
for brand, count in sorted(brands_in_log.items(), key=lambda x: x[1], reverse=True):
    print(f"   - {brand}: {count} produits")

print(f"\n2. Produits avec marque 'Roel Paris': {roel_count}")
print(f"3. Produits avec divergence marque: {len(discrepancies)}")

if discrepancies:
    print("\n4. Exemples de divergences (premiers 20):")
    for d in discrepancies[:20]:
        print(f"   - {d['name']}: '{d['current']}' devrait etre '{d['expected']}'")
