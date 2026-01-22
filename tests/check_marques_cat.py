import json
import pandas as pd

log = json.load(open('output/wizi_products_log_2026-01-22_14-47-01.json', encoding='utf-8'))
df = pd.read_csv('input/woocommerce_converted_with_filters_enrichi.csv')

# Mapping CSV line -> marque dans WiziShop
csv_to_brand = {}
for p in log:
    if '_csv_line' in p and 'brand' in p:
        csv_to_brand[p['_csv_line']] = p['brand']

# Produits dans catégorie "Marques"
marques_cat = []
for idx, row in df.iterrows():
    csv_line = idx + 2
    main_cat = str(row.get('Catégorie principale', '')).strip()

    if main_cat.lower() == 'marques':
        nom = row.get('Nom du produit', '')
        sub_cat = row.get('Catégorie secondaire', '')
        brand_wizi = csv_to_brand.get(csv_line, 'NOT_FOUND')
        marques_cat.append((csv_line, nom, sub_cat, brand_wizi))

print(f'Produits dans categorie Marques: {len(marques_cat)}')
print('\nExemples (20 premiers):')
for line, nom, cat, brand in marques_cat[:20]:
    status = 'OK' if brand == cat else 'KO'
    print(f'  [{status}] Ligne {line}: {nom[:35]:35} | Cat: {cat:20} | Marque: {brand}')

# Compter combien ont la bonne marque
correct = sum(1 for _, _, cat, brand in marques_cat if brand == cat)
print(f'\nResume: {correct}/{len(marques_cat)} ont la bonne marque')
