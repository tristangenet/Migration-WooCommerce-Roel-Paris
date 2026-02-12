#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour ajouter les colonnes de notes olfactives au CSV converti.
Découpe les notes en Tête/Cœur/Fond et les classe en _wizi (existant) ou _export (à créer).
"""

import csv
import re
import sys
import io
import argparse
from pathlib import Path

# Encodage UTF-8 pour Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Chemins des fichiers (structure ETL)
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
LOAD_INPUT = os.path.join(ROOT_DIR, "3-load", "input")

FILTRES_WIZI_CSV = os.path.join(LOAD_INPUT, 'filtres_wizishop.csv')
EXPORT_WOOCOMMERCE = os.path.join(ROOT_DIR, 'export_webtoffe_woocommerce.csv')  # CSV source à la racine
CSV_OUTPUT = os.path.join(LOAD_INPUT, 'woocommerce_converted_with_filters.csv')


def find_latest_converted_csv(load_input_dir):
    """Trouve le fichier woocommerce_converted_*.csv le plus récent."""
    candidates = [
        p for p in Path(load_input_dir).glob('woocommerce_converted_*.csv')
        if p.name != 'woocommerce_converted_with_filters.csv'
    ]
    if not candidates:
        return None
    return str(max(candidates, key=lambda p: p.stat().st_mtime))


def load_wizi_filters(filepath):
    """Charge les filtres WiziShop depuis le CSV."""
    filters = {'tete': set(), 'coeur': set(), 'fond': set()}

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('Tete'):
                filters['tete'].add(row['Tete'].lower().strip())
            if row.get('Coeur'):
                filters['coeur'].add(row['Coeur'].lower().strip())
            if row.get('Fond'):
                filters['fond'].add(row['Fond'].lower().strip())

    return filters


def load_woocommerce_notes_structure(filepath):
    """
    Charge la structure des notes depuis l'export WooCommerce original.
    Retourne un dict {nom_produit: {'tete': count, 'coeur': count, 'fond': count}}
    """
    structure = {}

    def count_ids(val):
        if not val:
            return 0
        return len(re.findall(r'"(\d+)"', val))

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('post_title', '').strip()
            if not name:
                continue

            nb_tete = count_ids(row.get('meta:notes_de_tete_0_notes', '')) + \
                      count_ids(row.get('meta:notes_de_tete_1_notes', ''))
            nb_coeur = count_ids(row.get('meta:notes_de_coeur_0_notes', '')) + \
                       count_ids(row.get('meta:notes_de_coeur_1_notes', ''))
            nb_fond = count_ids(row.get('meta:notes_de_fond_0_notes', '')) + \
                      count_ids(row.get('meta:notes_de_fond_1_notes', ''))

            if nb_tete + nb_coeur + nb_fond > 0:
                structure[name] = {
                    'tete': nb_tete,
                    'coeur': nb_coeur,
                    'fond': nb_fond
                }

    return structure


def classify_notes(notes_list, wizi_filters, notes_structure, product_name):
    """
    Classifie les notes d'un produit en 6 catégories.

    Returns:
        dict avec tete_wizi, tete_export, coeur_wizi, coeur_export, fond_wizi, fond_export
    """
    result = {
        'tete_wizi': [],
        'tete_export': [],
        'coeur_wizi': [],
        'coeur_export': [],
        'fond_wizi': [],
        'fond_export': []
    }

    if not notes_list:
        return result

    # Cas 1: On a la structure Tête/Cœur/Fond depuis WooCommerce
    if product_name in notes_structure:
        struct = notes_structure[product_name]
        nb_tete = struct['tete']
        nb_coeur = struct['coeur']
        nb_fond = struct['fond']

        total_expected = nb_tete + nb_coeur + nb_fond

        # Vérifier que le total correspond
        if total_expected == len(notes_list):
            # Découper selon l'ordre Tête -> Cœur -> Fond
            notes_tete = notes_list[:nb_tete]
            notes_coeur = notes_list[nb_tete:nb_tete + nb_coeur]
            notes_fond = notes_list[nb_tete + nb_coeur:]

            # Classifier chaque note
            for note in notes_tete:
                if note.lower().strip() in wizi_filters['tete']:
                    result['tete_wizi'].append(note)
                else:
                    result['tete_export'].append(note)

            for note in notes_coeur:
                if note.lower().strip() in wizi_filters['coeur']:
                    result['coeur_wizi'].append(note)
                else:
                    result['coeur_export'].append(note)

            for note in notes_fond:
                if note.lower().strip() in wizi_filters['fond']:
                    result['fond_wizi'].append(note)
                else:
                    result['fond_export'].append(note)

            return result

    # Cas 2: Pas de structure, on matche avec les filtres WiziShop existants
    for note in notes_list:
        note_lower = note.lower().strip()
        matched = False

        # Chercher dans Tête
        if note_lower in wizi_filters['tete']:
            result['tete_wizi'].append(note)
            matched = True
        # Chercher dans Cœur
        elif note_lower in wizi_filters['coeur']:
            result['coeur_wizi'].append(note)
            matched = True
        # Chercher dans Fond
        elif note_lower in wizi_filters['fond']:
            result['fond_wizi'].append(note)
            matched = True

        # Si pas trouvé, mettre dans _export (non classé = fond par défaut)
        if not matched:
            result['fond_export'].append(note)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Ajoute les colonnes de notes olfactives au CSV converti"
    )
    parser.add_argument(
        '--input',
        help='CSV converti en entrée (par défaut: dernier woocommerce_converted_*.csv)'
    )
    parser.add_argument(
        '--output',
        default=CSV_OUTPUT,
        help='CSV de sortie enrichi (défaut: 3-load/input/woocommerce_converted_with_filters.csv)'
    )
    parser.add_argument(
        '--filters',
        default=FILTRES_WIZI_CSV,
        help='CSV des filtres WiziShop (défaut: 3-load/input/filtres_wizishop.csv)'
    )
    parser.add_argument(
        '--source',
        default=EXPORT_WOOCOMMERCE,
        help='CSV source WooCommerce original (défaut: export_webtoffe_woocommerce.csv)'
    )
    args = parser.parse_args()

    csv_input = args.input or find_latest_converted_csv(LOAD_INPUT)
    if not csv_input:
        print("❌ Aucun CSV converti trouvé. Passez --input pour spécifier un fichier.")
        sys.exit(1)

    print("=" * 60)
    print("AJOUT DES COLONNES NOTES OLFACTIVES")
    print("=" * 60)
    print(f"CSV entrée  : {csv_input}")
    print(f"CSV sortie  : {args.output}")

    # Charger les filtres WiziShop
    print("\n1. Chargement des filtres WiziShop...")
    wizi_filters = load_wizi_filters(args.filters)
    print(f"   Tete: {len(wizi_filters['tete'])} valeurs")
    print(f"   Coeur: {len(wizi_filters['coeur'])} valeurs")
    print(f"   Fond: {len(wizi_filters['fond'])} valeurs")

    # Charger la structure des notes depuis WooCommerce
    print("\n2. Chargement structure notes WooCommerce...")
    notes_structure = load_woocommerce_notes_structure(args.source)
    print(f"   {len(notes_structure)} produits avec structure Tete/Coeur/Fond")

    # Lire le CSV converti
    print("\n3. Lecture du CSV converti...")
    rows = []
    with open(csv_input, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)
    print(f"   {len(rows)} produits charges")

    # Ajouter les nouvelles colonnes
    new_columns = ['tete_wizi', 'coeur_wizi', 'fond_wizi', 'tete_export', 'coeur_export', 'fond_export']
    fieldnames = list(fieldnames) + new_columns

    # Traiter chaque produit
    print("\n4. Classification des notes...")
    stats = {
        'with_structure': 0,
        'without_structure': 0,
        'no_notes': 0,
        'total_tete_wizi': 0,
        'total_coeur_wizi': 0,
        'total_fond_wizi': 0,
        'total_tete_export': 0,
        'total_coeur_export': 0,
        'total_fond_export': 0
    }

    for row in rows:
        product_name = row.get('Nom du produit', '').strip()
        notes_str = row.get('Notes olfactives', '')

        if not notes_str:
            stats['no_notes'] += 1
            for col in new_columns:
                row[col] = ''
            continue

        # Parser les notes
        notes_list = [n.strip() for n in notes_str.split(',') if n.strip()]

        # Classifier
        classified = classify_notes(notes_list, wizi_filters, notes_structure, product_name)

        # Stats
        if product_name in notes_structure:
            stats['with_structure'] += 1
        else:
            stats['without_structure'] += 1

        stats['total_tete_wizi'] += len(classified['tete_wizi'])
        stats['total_coeur_wizi'] += len(classified['coeur_wizi'])
        stats['total_fond_wizi'] += len(classified['fond_wizi'])
        stats['total_tete_export'] += len(classified['tete_export'])
        stats['total_coeur_export'] += len(classified['coeur_export'])
        stats['total_fond_export'] += len(classified['fond_export'])

        # Ajouter au row (format: note1, note2, note3)
        for col in new_columns:
            row[col] = ', '.join(classified[col])

    # Écrire le CSV de sortie
    print("\n5. Ecriture du CSV de sortie...")
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(args.output, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"   Fichier cree: {args.output}")

    # Afficher les stats
    print("\n" + "=" * 60)
    print("STATISTIQUES")
    print("=" * 60)
    print(f"Produits avec structure Tete/Coeur/Fond: {stats['with_structure']}")
    print(f"Produits sans structure (matching auto): {stats['without_structure']}")
    print(f"Produits sans notes: {stats['no_notes']}")
    print()
    print("Notes classifiees:")
    print(f"  tete_wizi:   {stats['total_tete_wizi']:4d} (existent sur WiziShop)")
    print(f"  tete_export: {stats['total_tete_export']:4d} (a creer)")
    print(f"  coeur_wizi:  {stats['total_coeur_wizi']:4d} (existent sur WiziShop)")
    print(f"  coeur_export:{stats['total_coeur_export']:4d} (a creer)")
    print(f"  fond_wizi:   {stats['total_fond_wizi']:4d} (existent sur WiziShop)")
    print(f"  fond_export: {stats['total_fond_export']:4d} (a creer)")
    print()
    total_wizi = stats['total_tete_wizi'] + stats['total_coeur_wizi'] + stats['total_fond_wizi']
    total_export = stats['total_tete_export'] + stats['total_coeur_export'] + stats['total_fond_export']
    print(f"TOTAL _wizi: {total_wizi} notes")
    print(f"TOTAL _export: {total_export} notes a creer")


if __name__ == '__main__':
    main()
