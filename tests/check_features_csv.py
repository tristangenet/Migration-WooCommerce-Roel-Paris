#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd

df = pd.read_csv('wizi_import/input/woocommerce_converted_2025-12-02_17-02-26.csv', dtype=str)

print('=== Produits avec Notes olfactives ===')
notes = df[df['Notes olfactives'].notna() & (df['Notes olfactives'] != '')]
for i in range(min(5, len(notes))):
    row = notes.iloc[i]
    print(f"  Ligne {notes.index[i]+2}: {row['Nom du produit'][:40]}")
    print(f"     Notes: {row['Notes olfactives'][:80]}")
    if pd.notna(row['Contenance']) and row['Contenance']:
        print(f"     Contenance: {row['Contenance']}")
    print()
