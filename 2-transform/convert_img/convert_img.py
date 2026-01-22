import pandas as pd
import os
import sys
import requests
import argparse
import re
from urllib.parse import urlparse
from pathlib import Path
from PIL import Image
from io import BytesIO
from ftplib import FTP
import glob

# Configuration Windows UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
LOCAL_TEMP_DIR = os.path.join(SCRIPT_DIR, "images_temp")
# Chargement des variables d'environnement
try:
    from dotenv import load_dotenv
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
except ImportError:
    pass

FTP_HOST = os.getenv("FTP_HOST", "")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASS = os.getenv("FTP_PASS", "")
REMOTE_BASE_DIR = os.getenv("FTP_REMOTE_DIR", "/dme")
URL_BASE = os.getenv("FTP_URL_BASE", "")

# --- UTILS ---
def is_webp_url(url):
    """Vérifie si une URL pointe vers une image WebP"""
    if not url or pd.isna(url):
        return False
    url_str = str(url).strip().lower()
    return url_str.endswith('.webp') or '.webp?' in url_str

def clean_shop_name(url):
    """
    Extrait et nettoie le nom de la boutique depuis l'URL pour créer un nom de dossier FTP
    Ex: https://boutique.les-delices-de-nos-regions.com/ -> les-delices-de-nos-regions
    Ex: https://roelparis.com/ -> roelparis
    """
    if not url:
        return "boutique-inconnue"

    # Extraire le domaine
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Enlever www. et boutique. si présents
    domain = re.sub(r'^(www\.|boutique\.)', '', domain)

    # Enlever l'extension (.com, .fr, etc.)
    domain = re.sub(r'\.[a-z]+$', '', domain)

    # Nettoyer les caractères spéciaux
    cleaned = re.sub(r'[^a-z0-9-]', '-', domain)
    cleaned = re.sub(r'-+', '-', cleaned)  # Éviter doubles tirets
    cleaned = cleaned.strip('-')

    return cleaned or "boutique-inconnue"

def slugify(text):
    """Convertit un texte en slug pour les noms de fichiers"""
    if pd.isna(text):
        return "unnamed"
    return "".join(c if c.isalnum() or c in '-_' else "-" for c in str(text).lower())[:80].strip("-")

def download_and_convert_image(url, filename_slug):
    """Télécharge et convertit une image en PNG"""
    try:
        response = requests.get(url, timeout=15, verify=False)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))

        filename = f"{filename_slug}.png"
        local_path = os.path.join(LOCAL_TEMP_DIR, filename)

        # Conversion en RGBA pour la transparence
        if img.mode != 'RGBA':
            img = img.convert("RGBA")

        img.save(local_path, "PNG")
        return filename, local_path
    except Exception as e:
        print(f"❌ Erreur image : {url} -> {e}")
        return None, None

def upload_file(ftp, local_path, remote_filename):
    """Upload un fichier sur le serveur FTP"""
    try:
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_filename}", f)
        print(f"✅ Uploadé : {remote_filename}")
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
            print(f"ℹ️ Dossier FTP existe déjà : {directory}")
        else:
            print(f"❌ Erreur création dossier FTP : {directory} -> {e}")

def detect_csv_files():
    """Détecte les fichiers CSV dans le dossier input"""
    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    return csv_files

def get_shop_url_from_csv(csv_path, df=None):
    """Extrait l'URL de la boutique depuis le CSV ou le nom du fichier"""
    # Méthode 1: Lire la première URL produit du CSV (format WiziShop)
    if df is not None and 'URL produit' in df.columns:
        first_url = df['URL produit'].dropna().iloc[0] if len(df['URL produit'].dropna()) > 0 else None
        if first_url:
            parsed = urlparse(first_url)
            return f"{parsed.scheme}://{parsed.netloc}/"

    # Méthode 2: Pattern depuis le nom du fichier (format Ted's CMS)
    filename = os.path.basename(csv_path)
    match = re.search(r'boutique_([^_]+)_([^_]+)', filename)
    if match:
        domain_part = match.group(1).replace('-', '.')
        tld = match.group(2)
        return f"https://boutique.{domain_part}.{tld}/"

    return None

def process_images(csv_file, limit=None):
    """Traite les images d'un fichier CSV"""
    print(f"\n🔄 Traitement du fichier : {csv_file}")
    
    # Créer le dossier temporaire pour les images
    os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)
    
    # Lire le CSV
    df = pd.read_csv(csv_file, encoding='utf-8-sig')
    if limit:
        df = df.head(limit)

    # Détecter l'URL de la boutique
    shop_url = get_shop_url_from_csv(csv_file, df)
    if not shop_url:
        print("❌ Impossible de détecter l'URL de la boutique depuis le CSV ou le nom du fichier")
        print("💡 Assurez-vous que le CSV contient une colonne 'URL produit'")
        return
    
    shop_name = clean_shop_name(shop_url)
    print(f"🏪 Boutique détectée : {shop_name} ({shop_url})")
    
    # Configuration FTP
    remote_shop_dir = f"{REMOTE_BASE_DIR}/{shop_name}"
    shop_url_base = f"{URL_BASE}{shop_name}/"
    
    # Connexion FTP
    try:
        ftp = FTP()
        ftp.connect(FTP_HOST, 21)
        ftp.login(FTP_USER, FTP_PASS)
        
        # Créer le dossier de la boutique
        create_ftp_directory(ftp, remote_shop_dir)
        ftp.cwd(remote_shop_dir)
        
    except Exception as e:
        print(f"❌ Erreur connexion FTP : {e}")
        return
    
    # Traitement des images
    images_processed = 0
    images_failed = 0
    images_skipped = 0

    for index, row in df.iterrows():
        product_slug = slugify(row.get("Nom du produit", f"produit-{index}"))

        # Images principales (Image 1 à Image 5) - Uniquement WebP
        for i in range(1, 6):
            col = f"Image {i}"
            if col in df.columns and pd.notna(row[col]) and str(row[col]).strip():
                url = str(row[col]).strip()

                # Filtrer uniquement les WebP
                if not is_webp_url(url):
                    images_skipped += 1
                    continue

                filename_slug = f"{product_slug}-photo-principale-{i}"
                filename, local_path = download_and_convert_image(url, filename_slug)
                if filename:
                    if upload_file(ftp, local_path, filename):
                        df.at[index, col] = shop_url_base + filename
                        images_processed += 1
                    else:
                        images_failed += 1
                else:
                    images_failed += 1

        # Images des attributs (Attribut 1 Photo 1 à Attribut 1 Photo 7) - Format WiziShop
        for j in range(1, 8):
            photo_col = f"Attribut 1 Photo {j}"
            val_col = f"Attribut 1 Valeur {j}"

            if photo_col in df.columns and pd.notna(row[photo_col]) and str(row[photo_col]).strip():
                url = str(row[photo_col]).strip()

                # Filtrer uniquement les WebP
                if not is_webp_url(url):
                    images_skipped += 1
                    continue

                # Nom de l'attribut depuis "Attribut 1 Nom"
                attr_name = "attr"
                attr_name_col = "Attribut 1 Nom"
                if attr_name_col in df.columns and pd.notna(row[attr_name_col]):
                    attr_name = slugify(row[attr_name_col])

                # Valeur de l'attribut
                val = slugify(row[val_col]) if val_col in df.columns and pd.notna(row[val_col]) else f"val{j}"

                filename_slug = f"{product_slug}-{attr_name}-{val}"
                filename, local_path = download_and_convert_image(url, filename_slug)
                if filename:
                    if upload_file(ftp, local_path, filename):
                        df.at[index, photo_col] = shop_url_base + filename
                        images_processed += 1
                    else:
                        images_failed += 1
                else:
                    images_failed += 1
    
    # Fermeture FTP
    ftp.quit()
    
    # Sauvegarde du CSV mis à jour
    output_filename = f"{shop_name}_images_processed_{pd.Timestamp.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    
    print(f"\n✅ Traitement terminé :")
    print(f"   - Images WebP converties : {images_processed}")
    print(f"   - Images échouées : {images_failed}")
    print(f"   - Images ignorées (non-WebP) : {images_skipped}")
    print(f"   - CSV finalisé : {output_path}")
    
    # Nettoyage des fichiers temporaires
    try:
        import shutil
        shutil.rmtree(LOCAL_TEMP_DIR)
        print(f"🗑️ Dossier temporaire nettoyé : {LOCAL_TEMP_DIR}")
    except:
        pass

def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(description="Conversion et upload d'images depuis CSV de scraping")
    parser.add_argument("--csv", help="Fichier CSV spécifique à traiter")
    parser.add_argument("--limit", type=int, help="Nombre de produits à traiter (par défaut : tous)")
    parser.add_argument("--list", action="store_true", help="Lister les fichiers CSV disponibles")
    args = parser.parse_args()
    
    # Créer les dossiers s'ils n'existent pas
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    if args.list:
        csv_files = detect_csv_files()
        if csv_files:
            print("📁 Fichiers CSV disponibles dans le dossier input :")
            for i, file in enumerate(csv_files, 1):
                print(f"   {i}. {os.path.basename(file)}")
        else:
            print("❌ Aucun fichier CSV trouvé dans le dossier input")
        return
    
    if args.csv:
        csv_path = os.path.join(INPUT_DIR, args.csv) if not os.path.isabs(args.csv) else args.csv
        if os.path.exists(csv_path):
            process_images(csv_path, limit=args.limit)
        else:
            print(f"❌ Fichier CSV introuvable : {csv_path}")
    else:
        csv_files = detect_csv_files()
        if not csv_files:
            print("❌ Aucun fichier CSV trouvé dans le dossier input")
            print("💡 Placez vos fichiers CSV de scraping dans le dossier 'input'")
            return
        
        if len(csv_files) == 1:
            print(f"📁 Traitement automatique du seul fichier trouvé : {os.path.basename(csv_files[0])}")
            process_images(csv_files[0], limit=args.limit)
        else:
            print("📁 Plusieurs fichiers CSV trouvés. Utilisez --csv pour spécifier lequel traiter.")
            print("   Ou --list pour voir la liste complète.")
            for i, file in enumerate(csv_files, 1):
                print(f"   {i}. {os.path.basename(file)}")

if __name__ == "__main__":
    main()