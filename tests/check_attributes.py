#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd

df = pd.read_csv('export_webtoffe_woocommerce.csv', dtype=str)

print('=== Colonnes attributs ===')
attrs = [c for c in df.columns if 'attribute:pa_' in c or 'attribute_data:pa_' in c]
for attr in attrs:
    print(f"  - {attr}")

print('\n=== Exemples de données (produits avec attributs) ===')
for col in ['attribute:pa_notes', 'attribute_data:pa_notes', 'attribute:pa_contenance', 'attribute_data:pa_contenance']:
    if col in df.columns:
        print(f'\n{col}:')
        # Filtrer les valeurs non vides
        non_empty = df[df[col].notna() & (df[col] != '')]
        print(f"  {len(non_empty)} produits avec cette donnée")
        if len(non_empty) > 0:
            for i in range(min(3, len(non_empty))):
                val = non_empty.iloc[i][col]
                name = non_empty.iloc[i]['post_title'] if 'post_title' in non_empty.columns else 'N/A'
                print(f"  Exemple {i+1} ({name}): {val[:150]}")
