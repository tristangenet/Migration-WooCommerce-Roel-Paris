#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prétraitement des images WebP dans le CSV WooCommerce source.
Convertit les images WebP en PNG, les upload sur FTP OVH, et remplace les URLs dans le CSV.
"""

import pandas as pd
import os
import sys
import requests
import argparse
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
from ftplib import FTP

# Configuration Windows UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # Remonte à woo_migration/
CSV_PATH = os.path.join(SCRIPT_DIR, 'input', 'copie-export_webtoffe_woocommerce.csv')
LOCAL_TEMP_DIR = os.path.join(SCRIPT_DIR, 'images_temp_webp')

# Chargement des variables d'environnement
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
except ImportError:
    pass

# Configuration FTP depuis .env
FTP_HOST = os.getenv("FTP_HOST", "")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASS = os.getenv("FTP_PASS", "")
REMOTE_BASE_DIR = os.getenv("FTP_REMOTE_DIR", "/dme")
URL_BASE = os.getenv("FTP_URL_BASE", "")

# --- UTILS (réutilisées depuis convert_img.py) ---
def is_webp_url(url):
    """Vérifie si une URL pointe vers une image WebP"""
    if not url or pd.isna(url):
        return False
    url_str = str(url).strip().lower()
    return url_str.endswith('.webp') or '.webp?' in url_str

def clean_shop_name(url):
    """
    Extrait et nettoie le nom de la boutique depuis l'URL
    Ex: https://roelparis.com/ -> roelparis
    """
    if not url:
        return "boutique-inconnue"

    import re
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    domain = re.sub(r'^(www\.|boutique\.)', '', domain)
    domain = re.sub(r'\.[a-z]+$', '', domain)
    cleaned = re.sub(r'[^a-z0-9-]', '-', domain)
    cleaned = re.sub(r'-+', '-', cleaned)
    cleaned = cleaned.strip('-')

    return cleaned or "boutique-inconnue"

def slugify(text):
    """Convertit un texte en slug pour les noms de fichiers"""
    if pd.isna(text):
        return "unnamed"
    return "".join(c if c.isalnum() or c in '-_' else "-" for c in str(text).lower())[:80].strip("-")

def download_and_convert_image(url, filename):
    """Télécharge et convertit une image en PNG"""
    try:
        response = requests.get(url, timeout=15, verify=False)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))

        png_filename = filename if filename.endswith('.png') else f"{filename}.png"
        local_path = os.path.join(LOCAL_TEMP_DIR, png_filename)

        if img.mode != 'RGBA':
            img = img.convert("RGBA")

        img.save(local_path, "PNG")
        return png_filename, local_path
    except Exception as e:
        print(f"❌ Erreur téléchargement image : {url[:80]} -> {e}")
        return None, None

def upload_file(ftp, local_path, remote_filename):
    """Upload un fichier sur le serveur FTP"""
    try:
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_filename}", f)
        return True
    except Exception as e:
        print(f"❌ Upload échoué : {remote_filename} -> {e}")
        return False

def create_ftp_directory(ftp, directory):
    """Crée un dossier sur le serveur FTP s'il n'existe pas"""
    try:
        ftp.mkd(directory)
        print(f"✅ Dossier FTP créé : {directory}")
    except Exception as e:
        if "File exists" in str(e) or "550" in str(e):
            pass  # Dossier existe déjà
        else:
            print(f"❌ Erreur création dossier FTP : {directory} -> {e}")

# --- PARSING FORMAT WOOCOMMERCE ---
def parse_woocommerce_images_column(images_string):
    """
    Parse le format WooCommerce: URL ! alt : text ! title : text | URL2 | URL3
    Returns: [(url1, metadata1), (url2, metadata2), ...]
    """
    if not images_string or pd.isna(images_string):
        return []

    # Split par |
    image_blocks = str(images_string).split('|')
    results = []

    for block in image_blocks:
        block = block.strip()
        if not block:
            continue

        if '!' in block:
            # Extraire URL (avant le premier !)
            url = block.split('!')[0].strip()
            # Garder les métadonnées (après le premier !)
            metadata = ' !' + '!'.join(block.split('!')[1:])
        else:
            url = block
            metadata = ''

        results.append((url, metadata))

    return results

def rebuild_woocommerce_images_column(image_tuples):
    """
    Reconstruit le format WooCommerce: URL ! alt : text | URL2 ! alt2
    """
    rebuilt = []
    for url, metadata in image_tuples:
        if metadata:
            rebuilt.append(url + metadata)
        else:
            rebuilt.append(url)

    return ' | '.join(rebuilt)

# --- MAIN PROCESSING ---
def process_woocommerce_csv(limit=None):
    """Traite le CSV WooCommerce et convertit les WebP"""

    print(f"\n🔄 Traitement du CSV WooCommerce")
    print(f"📁 Fichier : {CSV_PATH}")

    # Vérifier que le fichier existe
    if not os.path.exists(CSV_PATH):
        print(f"❌ Fichier introuvable : {CSV_PATH}")
        print(f"💡 Assurez-vous que la copie existe dans convert_img/input/")
        return

    # Créer le dossier temporaire
    os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)

    # Charger le CSV
    df = pd.read_csv(CSV_PATH, dtype=str)
    print(f"✅ {len(df)} lignes chargées")

    if limit:
        df = df.head(limit)
        print(f"⚠️  Limitation à {limit} lignes pour test")

    # Détecter l'URL de la boutique depuis la première ligne
    shop_url = None
    if 'product_page_url' in df.columns:
        first_url = df['product_page_url'].dropna().iloc[0] if len(df['product_page_url'].dropna()) > 0 else None
        if first_url:
            parsed = urlparse(first_url)
            shop_url = f"{parsed.scheme}://{parsed.netloc}/"

    if not shop_url:
        shop_url = "https://roelparis.com/"  # Fallback

    shop_name = clean_shop_name(shop_url)
    shop_url_base = f"{URL_BASE}{shop_name}/"
    print(f"🏪 Boutique : {shop_name} ({shop_url})")

    # Connexion FTP
    try:
        ftp = FTP()
        ftp.connect(FTP_HOST, 21)
        ftp.login(FTP_USER, FTP_PASS)

        remote_shop_dir = f"{REMOTE_BASE_DIR}/{shop_name}"
        create_ftp_directory(ftp, remote_shop_dir)
        ftp.cwd(remote_shop_dir)
        print(f"✅ Connecté au FTP : {remote_shop_dir}")
    except Exception as e:
        print(f"❌ Erreur connexion FTP : {e}")
        return

    # Identifier toutes les colonnes d'images
    image_columns = [col for col in df.columns if 'image' in col.lower()]
    print(f"📋 Colonnes d'images trouvées : {len(image_columns)}")
    print(f"   {', '.join(image_columns[:5])}...")

    # Statistiques
    webp_converted = 0
    webp_failed = 0
    images_skipped = 0
    image_counter = {}

    # Traiter chaque ligne
    for index, row in df.iterrows():
        product_slug = slugify(row.get('post_title', f'product-{index}'))
        image_counter[index] = 1

        # Traiter la colonne 'images' (format spécial WooCommerce)
        if 'images' in df.columns and pd.notna(row['images']) and str(row['images']).strip():
            image_tuples = parse_woocommerce_images_column(row['images'])
            new_tuples = []

            for url, metadata in image_tuples:
                if is_webp_url(url):
                    filename = f"{product_slug}-image-{image_counter[index]}.png"
                    png_filename, local_path = download_and_convert_image(url, filename)

                    if png_filename and upload_file(ftp, local_path, png_filename):
                        new_url = shop_url_base + png_filename
                        new_tuples.append((new_url, metadata))
                        webp_converted += 1
                        image_counter[index] += 1
                        print(f"  ✓ {product_slug} : {filename}")
                    else:
                        new_tuples.append((url, metadata))  # Garder original
                        webp_failed += 1
                else:
                    new_tuples.append((url, metadata))
                    images_skipped += 1

            # Reconstruire la colonne
            df.at[index, 'images'] = rebuild_woocommerce_images_column(new_tuples)

        # Traiter les autres colonnes (format simple URL)
        for col in image_columns:
            if col == 'images':
                continue  # Déjà traité

            if pd.notna(row[col]) and str(row[col]).strip():
                if is_webp_url(row[col]):
                    filename = f"{product_slug}-image-{image_counter[index]}.png"
                    png_filename, local_path = download_and_convert_image(row[col], filename)

                    if png_filename and upload_file(ftp, local_path, png_filename):
                        new_url = shop_url_base + png_filename
                        df.at[index, col] = new_url
                        webp_converted += 1
                        image_counter[index] += 1
                        print(f"  ✓ {product_slug} [{col}] : {filename}")
                    else:
                        webp_failed += 1
                else:
                    images_skipped += 1

    # Fermeture FTP
    ftp.quit()

    # Sauvegarder le CSV modifié (IN-PLACE)
    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')

    print(f"\n✅ Traitement terminé :")
    print(f"   - Images WebP converties : {webp_converted}")
    print(f"   - Images échouées : {webp_failed}")
    print(f"   - Images ignorées (non-WebP) : {images_skipped}")
    print(f"   - CSV modifié : {CSV_PATH}")

    # Nettoyage
    try:
        import shutil
        shutil.rmtree(LOCAL_TEMP_DIR)
        print(f"🗑️  Dossier temporaire nettoyé")
    except:
        pass

def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(description="Conversion des images WebP dans le CSV WooCommerce")
    parser.add_argument("--limit", type=int, help="Nombre de lignes à traiter (test)")
    args = parser.parse_args()

    process_woocommerce_csv(limit=args.limit)

if __name__ == "__main__":
    main()
