#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de conversion WooCommerce vers format WiziShop
Convertit l'export WooCommerce (Webtoffee) vers le format attendu par wizi_import.py
"""

import pandas as pd
import re
import os
from datetime import datetime
from html import unescape
import argparse


# --- CONFIGURATION ---
# Structure ETL : extract/ génère dans 3-load/input/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(ROOT_DIR, "3-load", "input")


def clean_html(html_content):
    """Nettoie le HTML et retire les balises superflues"""
    if pd.isna(html_content) or not html_content:
        return ""

    # Décoder les entités HTML
    text = unescape(str(html_content))

    # Supprimer les styles CSS inline
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Supprimer les commentaires HTML
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # Garder uniquement les balises essentielles : p, br, h1-h6, ul, ol, li, strong, em
    # Supprimer les autres balises mais garder leur contenu
    text = re.sub(r'<(?!/?(?:p|br|h[1-6]|ul|ol|li|strong|em|b|i)\b)[^>]+>', '', text, flags=re.IGNORECASE)

    # Nettoyer les sauts de ligne multiples
    text = re.sub(r'\n\s*\n', '\n', text)

    # Nettoyer les espaces multiples
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def parse_woocommerce_images(images_string):
    """
    Parse le format d'images WooCommerce
    Format: "URL ! alt : text ! title : text ! desc : text ! caption : text | URL2 | ..."
    Retourne une liste d'URLs
    """
    if pd.isna(images_string) or not images_string:
        return []

    images = []
    # Séparer par le pipe |
    parts = str(images_string).split('|')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extraire l'URL (avant le premier '!')
        if '!' in part:
            url = part.split('!')[0].strip()
        else:
            url = part.strip()

        # Vérifier que c'est une URL valide
        if url.startswith('http'):
            images.append(url)

    return images


def parse_category_hierarchy(category_string):
    """
    Parse la hiérarchie de catégories WooCommerce
    Formats possibles :
    - "Cat1|Cat2" : plusieurs catégories au même niveau
    - "Cat1 > Cat2 > Cat3" : hiérarchie à 3 niveaux
    - "Cat1 > Cat2|Cat3 > Cat4" : plusieurs catégories avec hiérarchie

    Retourne: (categorie_principale, sous_categorie)

    Gère les limitations WiziShop :
    - Maximum 2 niveaux de profondeur
    - Les produits doivent toujours avoir une sous-catégorie
    """
    if pd.isna(category_string) or not category_string:
        return "Non classé", "Produits"

    cat_str = str(category_string).strip()

    # Étape 1 : Si plusieurs catégories séparées par |, prendre la première
    # Ex: "Parfums > Familles Olfactives > Épicé|Parfums > Marques > Xerjoff"
    if '|' in cat_str and '>' in cat_str:
        # Format mixte : plusieurs catégories avec hiérarchie
        categories = [c.strip() for c in cat_str.split('|')]
        # Prendre la première catégorie (généralement la plus pertinente)
        cat_str = categories[0]
        if len(categories) > 1:
            print(f"   ℹ️ Plusieurs catégories détectées, utilisation de : {cat_str}")

    # Étape 2 : Parser la hiérarchie avec >
    if '>' in cat_str:
        parts = [p.strip() for p in cat_str.split('>')]
    # Ou avec | si pas de > (ancien format)
    elif '|' in cat_str:
        parts = [p.strip() for p in cat_str.split('|')]
    else:
        parts = [cat_str]

    # Filtrer les parties vides
    parts = [p for p in parts if p]

    if len(parts) == 0:
        return "Non classé", "Produits"
    elif len(parts) == 1:
        # Une seule catégorie : dupliquer pour avoir 2 niveaux
        # Évite l'erreur "Category is parent with id"
        print(f"   ℹ️ Catégorie unique, création de sous-catégorie : {parts[0]} > {parts[0]}")
        return parts[0], parts[0]
    elif len(parts) == 2:
        # Deux niveaux : parfait pour WiziShop
        return parts[0], parts[1]
    else:
        # Plus de 2 niveaux : aplatir en prenant les 2 derniers
        # Ex: "Parfums > Familles Olfactives > Ambré" -> "Familles Olfactives" > "Ambré"
        # Évite l'erreur "Can't add category to a child category"
        print(f"   ⚠️ Catégorie à {len(parts)} niveaux : {cat_str}")
        print(f"      Aplatissement : '{parts[-2]}' > '{parts[-1]}'")
        return parts[-2], parts[-1]


def extract_attribute_name_from_excerpt(excerpt):
    """
    Extrait le nom de l'attribut depuis post_excerpt
    Format: "attribute: value" -> "attribute"
    """
    if pd.isna(excerpt) or not excerpt:
        return None

    excerpt_str = str(excerpt).strip()

    # Format: "color: Black" -> "color"
    if ':' in excerpt_str:
        attr_name = excerpt_str.split(':')[0].strip()
        return attr_name

    return None


def extract_attribute_value_from_excerpt(excerpt):
    """
    Extrait la valeur de l'attribut depuis post_excerpt
    Format: "attribute: value" -> "value"
    """
    if pd.isna(excerpt) or not excerpt:
        return None

    excerpt_str = str(excerpt).strip()

    # Format: "color: Black" -> "Black"
    if ':' in excerpt_str:
        attr_value = excerpt_str.split(':', 1)[1].strip()
        return attr_value

    return None


def safe_get(row, col):
    """Récupère une valeur de façon sécurisée"""
    val = row.get(col, "")
    return str(val).strip() if pd.notna(val) else ""


def convert_woocommerce_to_wizi(woo_csv_path, output_csv_path=None):
    """
    Convertit l'export WooCommerce vers le format WiziShop
    """
    print(f"\n🔄 Conversion WooCommerce → WiziShop")
    print(f"📁 Fichier source : {os.path.basename(woo_csv_path)}")

    # Lecture du CSV WooCommerce
    try:
        # Essayer d'abord avec UTF-8
        try:
            df_woo = pd.read_csv(woo_csv_path, dtype=str, encoding='utf-8')
            print(f"✅ {len(df_woo)} lignes chargées depuis WooCommerce (UTF-8)")
        except UnicodeDecodeError:
            # Fallback sur latin1 si UTF-8 échoue
            df_woo = pd.read_csv(woo_csv_path, dtype=str, encoding='latin1')
            print(f"✅ {len(df_woo)} lignes chargées depuis WooCommerce (Latin-1)")
    except Exception as e:
        print(f"❌ Erreur lecture CSV WooCommerce : {e}")
        return None

    # Préparer la structure de sortie
    wizi_products = []

    # Statistiques
    stats = {
        'produits_simples': 0,
        'produits_variables': 0,
        'variations_traitees': 0,
        'produits_ignores': 0,
        'erreurs': 0
    }

    # Identifier les produits parents (sans post_parent)
    parent_products = df_woo[df_woo['post_parent'].isna() | (df_woo['post_parent'] == '')].copy()

    print(f"\n📦 Traitement de {len(parent_products)} produits...")

    for idx, parent_row in parent_products.iterrows():
        try:
            product_id = safe_get(parent_row, 'ID')
            product_name = safe_get(parent_row, 'post_title')
            product_type = safe_get(parent_row, 'tax:product_type')

            if not product_name:
                stats['produits_ignores'] += 1
                continue

            print(f"\n--- Produit {stats['produits_simples'] + stats['produits_variables'] + 1} : {product_name} ---")

            # Extraire les données de base
            description = clean_html(safe_get(parent_row, 'post_content'))
            short_description = safe_get(parent_row, 'post_excerpt')
            prix_base = safe_get(parent_row, 'regular_price')
            product_url = safe_get(parent_row, 'product_page_url')

            # Images du produit parent
            images_string = safe_get(parent_row, 'images')
            images_list = parse_woocommerce_images(images_string)

            # Catégories
            category_string = safe_get(parent_row, 'tax:product_cat')
            main_cat, sub_cat = parse_category_hierarchy(category_string)

            # Extraire données supplémentaires
            sku = safe_get(parent_row, 'sku')
            stock_qty = safe_get(parent_row, 'stock')
            stock_status = safe_get(parent_row, 'stock_status')
            tags_string = safe_get(parent_row, 'tax:product_tag')
            tags = tags_string.replace('|', ', ') if tags_string else ''

            # Marque (priorité: yith_product_brand > product_brand > pwb-brand)
            brand = (safe_get(parent_row, 'tax:yith_product_brand') or
                    safe_get(parent_row, 'tax:product_brand') or
                    safe_get(parent_row, 'tax:pwb-brand'))

            # Attributs personnalisés (caractéristiques produit)
            notes_olfactives = safe_get(parent_row, 'attribute:pa_notes')
            # Convertir le format WooCommerce (|) en format lisible (, )
            if notes_olfactives:
                notes_olfactives = notes_olfactives.replace('|', ', ')
                print(f"   🌸 Notes olfactives : {notes_olfactives}")

            contenance = safe_get(parent_row, 'attribute:pa_contenance')
            if contenance:
                contenance = contenance.replace('|', ', ')
                print(f"   📏 Contenance : {contenance}")

            # Préparer la ligne de sortie
            output_row = {
                'Nom du produit': product_name,
                'Description': description,
                'Prix TTC': prix_base,
                'URL produit': product_url,
                'Référence (SKU)': sku,
                'Marque': brand,
                'Stock': stock_qty,
                'Disponibilité': stock_status,
                'Tags': tags,
                'Notes olfactives': notes_olfactives,
                'Contenance': contenance,
                'Meta title': '',  # À remplir via IA si nécessaire
                'Meta description': '',  # À remplir via IA si nécessaire
                'Catégorie principale': main_cat,
                'Catégorie secondaire': sub_cat,
            }

            # Ajouter les images (jusqu'à 5)
            for i in range(5):
                if i < len(images_list):
                    output_row[f'Image {i+1}'] = images_list[i]
                else:
                    output_row[f'Image {i+1}'] = ''

            # Gérer les variations si produit variable
            if product_type == 'variable':
                stats['produits_variables'] += 1

                # Trouver les variations enfants
                variations = df_woo[df_woo['post_parent'] == product_id].copy()

                if len(variations) > 0:
                    print(f"   🔀 {len(variations)} variations trouvées")

                    # Déterminer le nom de l'attribut depuis la première variation
                    first_variation = variations.iloc[0]
                    attr_name = extract_attribute_name_from_excerpt(safe_get(first_variation, 'post_excerpt'))

                    if attr_name:
                        print(f"   📝 Attribut détecté : {attr_name}")

                        # Ajouter le nom de l'attribut
                        output_row['Attribut 1 Nom'] = attr_name.capitalize()

                        # Traiter chaque variation
                        for var_idx, (_, var_row) in enumerate(variations.iterrows(), 1):
                            if var_idx > 7:  # Limite à 7 variations (max du format Wizi)
                                print(f"   ⚠️ Plus de 7 variations, les suivantes sont ignorées")
                                break

                            var_value = extract_attribute_value_from_excerpt(safe_get(var_row, 'post_excerpt'))
                            var_price = safe_get(var_row, 'regular_price')
                            var_stock = safe_get(var_row, 'stock')
                            var_images_string = safe_get(var_row, 'images')
                            var_images = parse_woocommerce_images(var_images_string)
                            var_image = var_images[0] if var_images else ''

                            # Ajouter la variation
                            output_row[f'Attribut 1 Valeur {var_idx}'] = var_value
                            output_row[f'Attribut 1 Prix {var_idx}'] = var_price
                            output_row[f'Attribut 1 Stock {var_idx}'] = var_stock
                            output_row[f'Attribut 1 Photo {var_idx}'] = var_image

                            stats['variations_traitees'] += 1
                    else:
                        print(f"   ⚠️ Impossible de déterminer le nom de l'attribut")
            else:
                stats['produits_simples'] += 1

            wizi_products.append(output_row)

        except Exception as e:
            print(f"❌ Erreur traitement produit '{product_name}' : {e}")
            stats['erreurs'] += 1
            import traceback
            traceback.print_exc()

    # Créer le DataFrame de sortie
    df_wizi = pd.DataFrame(wizi_products)

    # Générer le nom de fichier de sortie si non spécifié
    if not output_csv_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_filename = f"woocommerce_converted_{timestamp}.csv"
        output_csv_path = os.path.join(OUTPUT_DIR, output_filename)
    elif not os.path.isabs(output_csv_path):
        # Si chemin relatif, le mettre dans OUTPUT_DIR
        output_csv_path = os.path.join(OUTPUT_DIR, output_csv_path)

    # Créer le dossier de sortie si nécessaire
    output_dir = os.path.dirname(output_csv_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Sauvegarder le CSV
    try:
        df_wizi.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        print(f"\n✅ Conversion réussie !")
        print(f"📄 Fichier généré : {output_csv_path}")
    except Exception as e:
        print(f"❌ Erreur sauvegarde CSV : {e}")
        return None

    # Afficher les statistiques
    print(f"\n📊 Statistiques de conversion :")
    print(f"   ✅ Produits simples : {stats['produits_simples']}")
    print(f"   🔀 Produits variables : {stats['produits_variables']}")
    print(f"   📦 Variations traitées : {stats['variations_traitees']}")
    print(f"   ⏭️  Produits ignorés : {stats['produits_ignores']}")
    print(f"   ❌ Erreurs : {stats['erreurs']}")
    print(f"\n💡 Vous pouvez maintenant importer ce fichier avec wizi_import.py")

    return output_csv_path


def main():
    """Point d'entrée principal"""
    # Configurer l'encodage de sortie pour Windows
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="Convertit un export WooCommerce vers le format WiziShop"
    )
    parser.add_argument(
        "input_csv",
        nargs="?",
        help="Fichier CSV WooCommerce à convertir"
    )
    parser.add_argument(
        "-o", "--output",
        help="Fichier CSV de sortie (optionnel)"
    )
    args = parser.parse_args()

    # Déterminer le fichier d'entrée
    if args.input_csv:
        input_path = args.input_csv
        if not os.path.isabs(input_path):
            input_path = os.path.join(SCRIPT_DIR, input_path)
    else:
        # Chercher le fichier par défaut
        default_file = os.path.join(SCRIPT_DIR, "export_webtoffe_woocommerce.csv")
        if os.path.exists(default_file):
            input_path = default_file
            print(f"📁 Utilisation du fichier par défaut : {os.path.basename(default_file)}")
        else:
            print("❌ Aucun fichier spécifié et pas de fichier par défaut trouvé")
            print("💡 Usage : python woocommerce_to_wizi.py <fichier_woocommerce.csv>")
            return

    if not os.path.exists(input_path):
        print(f"❌ Fichier introuvable : {input_path}")
        return

    # Lancer la conversion
    convert_woocommerce_to_wizi(input_path, args.output)


if __name__ == "__main__":
    main()
