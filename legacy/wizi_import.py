import pandas as pd
import json
import random
import string
import requests
import time
import argparse
import os
import re
from datetime import datetime
from urllib.parse import urlparse
from filter_manager import FilterManager

# Chargement des variables d'environnement
try:
    from dotenv import load_dotenv
    # .env est à la racine du projet (un niveau au-dessus de load/)
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
    ENV_AVAILABLE = True
except ImportError:
    ENV_AVAILABLE = False
    print("⚠️ Package python-dotenv non installé. Utilise: pip install python-dotenv")
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# --- CONFIGURATION ---
# Structure ETL : input/ et output/ sont dans 3-load/
INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

# --- UTILS ---
def slugify(text):
    """Convertit un texte en slug pour les URLs"""
    if pd.isna(text):
        return "category"
    return "".join(c if c.isalnum() or c in '-_' else "-" for c in str(text).lower())[:50].strip("-")

def generate_sku(prefix="SKU"):
    """Génère un SKU unique"""
    # Nettoyer le préfixe : supprimer accents et caractères spéciaux
    import unicodedata
    prefix_clean = unicodedata.normalize('NFD', prefix)
    prefix_clean = ''.join(c for c in prefix_clean if unicodedata.category(c) != 'Mn')  # Supprimer accents
    prefix_clean = ''.join(c if c.isalnum() else '-' for c in prefix_clean)  # Garder que alphanumériques et tirets
    prefix_clean = prefix_clean[:10]  # Limiter longueur
    
    return prefix_clean + "-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def safe_get(row, col):
    """Récupère une valeur de façon sécurisée"""
    val = row.get(col, "")
    return str(val).strip() if pd.notna(val) else ""

def clean_price_ttc_to_ht(value, tva):
    """Convertit prix TTC en HT"""
    try:
        price_float = float(str(value).replace(",", "."))
        return round(price_float / (1 + tva / 100), 6) 
    except (ValueError, TypeError):
        return 0.0

def clean_value_label(val):
    """Nettoie les labels de valeurs d'attributs"""
    return re.sub(r"\(\+.*?\)", "", val).lstrip(", ").strip()

def get_tva_profiles():
    """Retourne les profils TVA prédéfinis"""
    return {
        'alimentaire': {
            'name': 'Alimentaire/Spiritueux',
            'food_5_5': ['fromage', 'charcuterie', 'pain', 'baguette', 'confiture', 'miel', 
                         'huile', 'vinaigre', 'farine', 'sucre', 'sel', 'épice', 'aromate',
                         'fruits', 'légumes', 'légume', 'epicerie', 'conserve', 'pâte',
                         'riz', 'céréale', 'biscuit', 'gâteau', 'chocolat', 'bonbon', 'nougat',
                         'yaourt', 'lait', 'beurre', 'crème', 'oeuf', 'plateau'],
            'alcohol_20': ['vin', 'champagne', 'bière', 'spiritueux', 'whisky', 'rhum',
                          'vodka', 'gin', 'cognac', 'armagnac', 'liqueur', 'apéritif',
                          'eau-de-vie', 'calvados', 'digestif', 'alcool', 'muscatine',
                          'oli', 'elsass', 'arrangé', 'mirabelle'],
            'non_food_20': ['carte cadeau', 'accessoire', 'ustensile', 'verre', 'bouteille vide']
        },
        'librairie': {
            'name': 'Librairie/Papeterie',
            'books_5_5': ['livre', 'manuel', 'guide', 'bd', 'roman', 'magazine', 'journal'],
            'stationery_20': ['stylo', 'cahier', 'classeur', 'trousse', 'règle', 'gomme'],
            'other_20': ['jeu', 'puzzle', 'carte', 'poster']
        },
        'textile': {
            'name': 'Mode/Textile',
            'all_20': ['*']  # Tout à 20%
        },
        'pharmacie': {
            'name': 'Pharmacie/Parapharmacie',
            'medicine_2_1': ['médicament', 'paracétamol', 'doliprane', 'ibuprofène'],
            'books_5_5': ['livre', 'guide santé'],
            'cosmetic_20': ['crème', 'shampoing', 'savon', 'parfum', 'maquillage']
        },
        'hightech': {
            'name': 'High-tech/Informatique',
            'all_20': ['*']  # Tout à 20%
        }
    }

def detect_tva_rate(product_name, description, category, tva_config):
    """Détecte le taux de TVA basé sur le contenu du produit"""
    if tva_config['mode'] == 'fixed':
        return tva_config['rate']
    
    if tva_config['mode'] == 'teds':
        # Utiliser le mapping depuis l'export Ted's CMS
        tva_mapping = tva_config.get('tva_mapping', {})
        default_rate = tva_config.get('default', 20.0)
        return get_tva_from_teds_mapping(product_name, tva_mapping, default_rate)
    
    if tva_config['mode'] == 'profile':
        profile = tva_config['profile_data']
        content = f"{product_name} {description} {category}".lower()
        
        # Parcourir les catégories du profil par ordre de priorité
        for rate_key, keywords in profile.items():
            if rate_key == 'name':
                continue
                
            # Extraire le taux de la clé (ex: "food_5_5" -> 5.5)
            if '_' in rate_key:
                try:
                    rate_str = rate_key.split('_')[-1].replace('_', '.')
                    rate = float(rate_str)
                except:
                    continue
                
                # Vérifier si '*' (tout correspond)
                if '*' in keywords:
                    print(f"  💰 TVA {rate}% (profil: tout) pour: {product_name}")
                    return rate
                
                # Vérifier les mots-clés
                if any(keyword in content for keyword in keywords):
                    category_name = rate_key.split('_')[0]
                    print(f"  💰 TVA {rate}% (profil: {category_name}) pour: {product_name}")
                    return rate
        
        # Pas de match dans le profil, utiliser le défaut
        default_rate = tva_config.get('default', 20.0)
        print(f"  💰 TVA {default_rate}% par défaut pour: {product_name}")
        return default_rate
    
    # Mode auto original (compatibilité)
    content = f"{product_name} {description} {category}".lower()
    profiles = get_tva_profiles()
    alimentaire_profile = profiles['alimentaire']
    
    if any(keyword in content for keyword in alimentaire_profile['alcohol_20']):
        print(f"  💰 TVA 20% détectée (alcool) pour: {product_name}")
        return 20.0
    elif any(keyword in content for keyword in alimentaire_profile['non_food_20']):
        print(f"  💰 TVA 20% détectée (non-alimentaire) pour: {product_name}")
        return 20.0
    elif any(keyword in content for keyword in alimentaire_profile['food_5_5']):
        print(f"  💰 TVA 5.5% détectée (alimentaire) pour: {product_name}")
        return 5.5
    
    # Pas de match, utiliser le défaut
    default_rate = tva_config.get('default', 20.0)
    print(f"  💰 TVA {default_rate}% par défaut pour: {product_name}")
    return default_rate

class WiziShopAPI:
    def __init__(self, access_token, store_id):
        self.access_token = access_token
        self.store_id = store_id
        self.base_url = f"https://api.wizishop.com/v3/shops/{store_id}"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        self.categories_cache = None
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_categories(self):
        """Récupère toutes les catégories existantes"""
        if self.categories_cache is not None:
            return self.categories_cache
        
        try:
            response = requests.get(f"{self.base_url}/categories", headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                # La structure est différente : data.results contient les catégories
                results = data.get('results', [])
                
                # Aplatir la structure hiérarchique pour inclure tous les enfants
                all_categories = []
                
                def extract_categories(categories_list):
                    for cat in categories_list:
                        all_categories.append(cat)
                        # Récursivement extraire les enfants
                        if 'children' in cat and cat['children']:
                            extract_categories(cat['children'])
                
                extract_categories(results)
                
                self.categories_cache = all_categories
                print(f"✅ {len(self.categories_cache)} catégories récupérées depuis Wizi (incluant sous-catégories)")
                return self.categories_cache
            else:
                print(f"❌ Erreur récupération catégories : {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"❌ Erreur API catégories : {e}")
            return []
    
    def find_category_by_name(self, name, parent_id=None):
        """Trouve une catégorie par son nom et optionnellement son parent"""
        categories = self.get_categories()
        name_lower = name.lower().strip()
        
        matches = []
        for cat in categories:
            if cat.get('name', '').lower().strip() == name_lower:
                matches.append(cat)
        
        if not matches:
            return None
        
        # Si parent_id est spécifié, chercher la correspondance exacte
        if parent_id is not None:
            for cat in matches:
                # Récupérer l'ID parent depuis l'API ou la structure hiérarchique
                cat_parent_id = self._get_parent_id_from_category(cat)
                if cat_parent_id == parent_id:
                    return cat
        
        # Sinon retourner la première correspondance
        return matches[0]
    
    def _get_parent_id_from_category(self, category):
        """Récupère l'ID parent d'une catégorie depuis la structure hiérarchique"""
        # Dans la structure hiérarchique, on doit déterminer le parent
        # En parcourant toutes les catégories pour voir où cette catégorie apparaît comme enfant
        all_categories = self.get_categories()
        
        for parent_cat in all_categories:
            if 'children' in parent_cat:
                for child in parent_cat['children']:
                    if child.get('id') == category.get('id'):
                        return parent_cat.get('id')
        
        # Si pas trouvé dans les enfants, c'est une catégorie racine
        return 0
    
    def create_category(self, name, parent_id=0, visible=True):
        """Crée une nouvelle catégorie"""
        try:
            url_slug = slugify(name)
            payload = {
                "id_parent": parent_id,
                "name": name,
                "url": url_slug,
                "menu_title": name,
                "visible": visible,
                "meta": {
                    "title": name,
                    "description": f"Catégorie {name}"
                }
            }
            
            print(f"🔧 Payload création catégorie : {json.dumps(payload, indent=2)}")
            
            response = requests.post(f"{self.base_url}/categories", headers=self.headers, json=payload)
            
            print(f"🔧 Réponse API création catégorie - Status: {response.status_code}")
            print(f"🔧 Réponse API création catégorie - Contenu: {response.text}")
            
            if response.status_code == 201:
                data = response.json()
                # Selon la doc, la structure peut être différente
                new_cat = data.get('data', data)  # Fallback sur data directement
                category_id = new_cat.get('id')
                
                print(f"✅ Catégorie créée : {name} (ID: {category_id})")
                
                # Invalider le cache pour forcer la récupération lors du prochain appel
                self.categories_cache = None
                
                # Ajouter à la nouvelle catégorie des infos pour le log
                new_cat['_created_new'] = True
                return new_cat
            else:
                print(f"❌ Erreur création catégorie '{name}' : {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Erreur création catégorie '{name}' : {e}")
            return None
    
    def get_or_create_category(self, name, parent_id=0):
        """Récupère ou crée une catégorie"""
        # Chercher d'abord avec le parent spécifique pour éviter les doublons
        existing = self.find_category_by_name(name, parent_id)
        if existing:
            print(f"ℹ️ Catégorie existante trouvée : {name} (ID: {existing.get('id')}, Parent: {existing.get('parent_id', 0)})")
            existing['_created_new'] = False
            return existing
        
        print(f"🔄 Création de la catégorie : {name} (Parent ID: {parent_id})")
        new_cat = self.create_category(name, parent_id)
        if new_cat:
            new_cat['_created_new'] = True
        return new_cat
    
    def create_product(self, product_data):
        """Crée un produit"""
        try:
            print(f"🔧 Debug - URL: {self.base_url}/products")
            print(f"🔧 Debug - Headers: {self.headers}")
            print(f"🔧 Debug - Payload size: {len(str(product_data))} chars")
            
            response = requests.post(f"{self.base_url}/products", headers=self.headers, json=product_data)
            print(f"🔧 Debug - Request successful, status: {response.status_code}")
            
            # Si erreur serveur, afficher la réponse pour debug
            if response.status_code >= 400:
                print(f"🔧 Debug - Error response: {response.text}")
            
            return response
        except Exception as e:
            print(f"❌ Erreur création produit : {e}")
            import traceback
            traceback.print_exc()
            return None

class CategoryMapper:
    def __init__(self, wizi_api):
        self.wizi_api = wizi_api
        self.mapping_cache = {}
        self.creation_log = []
    
    def get_category_id(self, main_category, sub_category=""):
        """Récupère ou crée l'ID de catégorie Wizi pour les catégories Teds"""
        cache_key = (main_category.lower().strip(), sub_category.lower().strip())
        
        if cache_key in self.mapping_cache:
            return self.mapping_cache[cache_key]
        
        main_cat_clean = main_category.strip()
        sub_cat_clean = sub_category.strip()
        
        print(f"\n🔍 Mapping catégorie : '{main_cat_clean}' -> '{sub_cat_clean}'")
        
        # 1. Chercher d'abord la catégorie principale
        main_cat_obj = self.wizi_api.get_or_create_category(main_cat_clean)
        if not main_cat_obj:
            print(f"❌ Impossible de créer la catégorie principale : {main_cat_clean}")
            return None
        
        main_cat_id = main_cat_obj.get('id')
        
        # Log de la catégorie principale
        self.creation_log.append({
            "type": "main_category",
            "name": main_cat_clean,
            "id": main_cat_id,
            "parent_id": 0,
            "created_new": main_cat_obj.get('_created_new', False)
        })
        
        # 2. Si pas de sous-catégorie, retourner l'ID de la catégorie principale
        if not sub_cat_clean:
            self.mapping_cache[cache_key] = main_cat_id
            return main_cat_id
        
        # 3. Chercher ou créer la sous-catégorie
        sub_cat_obj = self.wizi_api.get_or_create_category(sub_cat_clean, parent_id=main_cat_id)
        if not sub_cat_obj:
            print(f"❌ Impossible de créer la sous-catégorie : {sub_cat_clean}")
            # Fallback sur la catégorie principale
            self.mapping_cache[cache_key] = main_cat_id
            return main_cat_id
        
        sub_cat_id = sub_cat_obj.get('id')
        
        # Log de la sous-catégorie
        self.creation_log.append({
            "type": "sub_category",
            "name": sub_cat_clean,
            "id": sub_cat_id,
            "parent_id": main_cat_id,
            "created_new": sub_cat_obj.get('_created_new', False)
        })
        
        self.mapping_cache[cache_key] = sub_cat_id
        return sub_cat_id
    
    def get_creation_log(self):
        """Retourne le log des catégories créées"""
        return self.creation_log

def detect_csv_files():
    """Détecte les fichiers CSV dans le dossier input"""
    if not os.path.exists(INPUT_DIR):
        return []
    
    import glob
    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    return csv_files

def detect_teds_export_files():
    """Détecte les fichiers d'export Ted's CMS dans le dossier export_teds"""
    if not os.path.exists(EXPORT_TEDS_DIR):
        return []
    
    import glob
    export_files = glob.glob(os.path.join(EXPORT_TEDS_DIR, "*.csv"))
    return export_files

def load_teds_tva_mapping(export_file):
    """Charge les taux de TVA depuis l'export Ted's CMS"""
    try:
        # Essayer avec séparateur point-virgule d'abord (format Ted's CMS)
        try:
            df_teds = pd.read_csv(export_file, sep=';')
            print(f"✅ Export Ted's chargé : {len(df_teds)} produits (format point-virgule)")
        except:
            # Fallback avec virgule standard
            df_teds = pd.read_csv(export_file)
            print(f"✅ Export Ted's chargé : {len(df_teds)} produits (format virgule)")
        
        # Créer un dictionnaire de mapping nom -> TVA
        tva_mapping = {}
        
        # Colonnes possibles pour le nom du produit
        name_columns = ['nom du produit', 'Nom du produit', 'nom', 'name', 'title', 'titre']
        name_col = None
        for col in name_columns:
            if col in df_teds.columns:
                name_col = col
                break
        
        # Colonnes possibles pour la TVA
        tva_columns = ['TVA', 'tva', 'tax', 'taxe', 'Tax Rate', 'tax_rate']
        tva_col = None
        for col in tva_columns:
            if col in df_teds.columns:
                tva_col = col
                break
        
        if not name_col or not tva_col:
            print(f"❌ Colonnes requises non trouvées dans l'export Ted's")
            print(f"   Colonnes disponibles : {list(df_teds.columns)}")
            print(f"   Nom trouvé : {name_col}, TVA trouvée : {tva_col}")
            return {}
        
        print(f"✅ Colonnes détectées - Nom: '{name_col}', TVA: '{tva_col}'")
        
        for _, row in df_teds.iterrows():
            name = safe_get(row, name_col)
            tva_value = safe_get(row, tva_col)
            
            if name and tva_value:
                try:
                    # Nettoyer la valeur TVA (enlever %, convertir en float)
                    tva_clean = str(tva_value).replace('%', '').replace(',', '.').strip()
                    tva_rate = float(tva_clean)
                    
                    # Normaliser le nom pour la recherche
                    name_normalized = name.lower().strip()
                    tva_mapping[name_normalized] = tva_rate
                    
                except ValueError:
                    print(f"⚠️ TVA invalide pour '{name}': '{tva_value}'")
                    continue
        
        print(f"✅ {len(tva_mapping)} taux de TVA chargés depuis Ted's")
        return tva_mapping
        
    except Exception as e:
        print(f"❌ Erreur lecture export Ted's : {e}")
        return {}

def get_tva_from_teds_mapping(product_name, tva_mapping, default_rate=20.0):
    """Récupère le taux de TVA depuis le mapping Ted's"""
    if not tva_mapping:
        return default_rate
    
    # Normaliser le nom pour la recherche
    name_normalized = product_name.lower().strip()
    
    # Recherche exacte
    if name_normalized in tva_mapping:
        rate = tva_mapping[name_normalized]
        print(f"  💰 TVA {rate}% trouvée dans Ted's pour: {product_name}")
        return rate
    
    # Recherche approximative (contient)
    for teds_name, rate in tva_mapping.items():
        if teds_name in name_normalized or name_normalized in teds_name:
            print(f"  💰 TVA {rate}% trouvée (approx) dans Ted's pour: {product_name}")
            return rate
    
    # Pas trouvé
    print(f"  💰 TVA {default_rate}% par défaut (non trouvé dans Ted's) pour: {product_name}")
    return default_rate

def get_shop_credentials():
    """Demande les identifiants de la boutique Wizi"""
    print("🔐 Configuration de la boutique WiziShop")
    print("=" * 50)
    
    # Essayer de charger depuis .env
    access_token = os.getenv('WIZI_ACCESS_TOKEN', '').strip() if ENV_AVAILABLE else ''
    store_id = os.getenv('WIZI_STORE_ID', '').strip() if ENV_AVAILABLE else ''
    
    if access_token and store_id:
        print(f"✅ Identifiants chargés depuis .env")
        print(f"   Store ID: {store_id}")
        print(f"   Token: {access_token[:20]}...")
        
        confirm = input("Utiliser ces identifiants ? (O/n) : ").strip().lower()
        if confirm in ['', 'o', 'oui', 'y', 'yes']:
            pass  # Utiliser les identifiants du .env
        else:
            access_token = store_id = ''  # Demander manuellement
    
    if not access_token:
        access_token = input("Access Token WiziShop : ").strip()
        if not access_token:
            print("❌ Access token requis")
            return None, None, None, None
    
    if not store_id:
        store_id = input("Store ID WiziShop : ").strip()
        if not store_id:
            print("❌ Store ID requis")
            return None, None, None, None
    
    # Demande du nombre de produits à importer
    print("\n📊 Nombre de produits à importer")
    print("-" * 35)
    limit_input = input("Nombre de produits (appuyez sur Entrée pour tous) : ").strip()
    
    limit = None
    if limit_input:
        try:
            limit = int(limit_input)
            if limit <= 0:
                print("❌ Le nombre doit être positif")
                return None, None, None, None
            print(f"ℹ️ Import limité à {limit} produits")
        except ValueError:
            print("❌ Veuillez entrer un nombre valide")
            return None, None, None, None
    else:
        print("ℹ️ Import de tous les produits")
    
    # Configuration de la marque globale
    print("\n🏷️ Marque des produits")
    print("-" * 25)
    global_brand = input("Marque globale pour tous les produits (optionnel) : ").strip()
    if global_brand:
        print(f"✅ Marque configurée : {global_brand}")
    else:
        print("ℹ️ Aucune marque définie")
    
    # Options de génération par IA
    print("\n🤖 Options de génération par IA")
    print("-" * 35)
    print("1. Métadonnées SEO (title, description)")
    print("2. Description courte")
    print("3. Description longue")
    print("4. Balise alt des images")
    print("5. Mots-clés produit")
    print("6. Suggestions de vente croisée")
    
    ai_options_input = input("\nSélectionnez les options (ex: 1,3,4) ou Entrée pour aucune : ").strip()
    ai_options = []
    openai_key = None
    
    if ai_options_input:
        try:
            ai_options = [int(x.strip()) for x in ai_options_input.split(',') if x.strip().isdigit()]
            ai_options = [x for x in ai_options if 1 <= x <= 6]  # Valider les options
            
            if ai_options:
                # Charger la clé OpenAI
                openai_key = os.getenv('OPENAI_API_KEY', '').strip() if ENV_AVAILABLE else ''
                
                if not openai_key:
                    openai_key = input("Clé API OpenAI requise : ").strip()
                
                if not openai_key:
                    print("❌ Clé OpenAI requise pour utiliser l'IA")
                    ai_options = []
                else:
                    option_names = {
                        1: "Métadonnées SEO",
                        2: "Description courte", 
                        3: "Description longue",
                        4: "Balise alt des images",
                        5: "Mots-clés produit",
                        6: "Suggestions de vente croisée"
                    }
                    selected_names = [option_names[opt] for opt in ai_options]
                    print(f"✅ Options IA activées : {', '.join(selected_names)}")
        except ValueError:
            print("❌ Format invalide, IA désactivée")
            ai_options = []
    
    if not ai_options:
        print("ℹ️ Génération IA désactivée")
    
    # Configuration TVA
    print("\n💰 Gestion de la TVA")
    print("-" * 25)
    print("1. Ted's CMS - Taux exacts depuis export (recommandé)")
    print("2. Auto-détection alimentaire/spiritueux")
    print("3. Profil Librairie/Papeterie")
    print("4. Profil Mode/Textile (tout 20%)")
    print("5. Profil Pharmacie/Parapharmacie")
    print("6. Profil High-tech (tout 20%)")
    print("7. TVA fixe 20% pour tous")
    print("8. TVA fixe 5.5% pour tous")
    
    tva_choice = input("Choix (1-8, défaut=1) : ").strip() or "1"
    
    profiles = get_tva_profiles()
    
    tva_config = None
    
    if tva_choice == '1':
        # Mode Ted's CMS
        os.makedirs(EXPORT_TEDS_DIR, exist_ok=True)
        export_files = detect_teds_export_files()
        
        if not export_files:
            print("❌ Aucun export Ted's trouvé dans export_teds/")
            print("💡 Exportez les produits depuis Ted's CMS et placez le fichier dans export_teds/")
            print("🔄 Basculement automatique vers auto-détection")
            tva_config = {'mode': 'auto', 'default': 20.0}
        else:
            if len(export_files) == 1:
                export_file = export_files[0]
                print(f"📁 Export Ted's détecté : {os.path.basename(export_file)}")
            else:
                print("📁 Plusieurs exports Ted's trouvés :")
                for i, file in enumerate(export_files, 1):
                    print(f"   {i}. {os.path.basename(file)}")
                
                try:
                    choice = int(input("Choisissez le numéro de l'export : ")) - 1
                    if 0 <= choice < len(export_files):
                        export_file = export_files[choice]
                    else:
                        print("❌ Choix invalide, utilisation du premier fichier")
                        export_file = export_files[0]
                except ValueError:
                    print("❌ Choix invalide, utilisation du premier fichier")
                    export_file = export_files[0]
            
            # Charger le mapping TVA
            tva_mapping = load_teds_tva_mapping(export_file)
            if tva_mapping:
                tva_config = {
                    'mode': 'teds',
                    'tva_mapping': tva_mapping,
                    'default': 20.0,
                    'export_file': export_file
                }
                print(f"✅ TVA configurée : Ted's CMS ({len(tva_mapping)} produits)")
            else:
                print("🔄 Erreur chargement Ted's, basculement vers auto-détection")
                tva_config = {'mode': 'auto', 'default': 20.0}
    else:
        # Autres modes
        tva_config_map = {
            '2': {'mode': 'auto', 'default': 20.0},
            '3': {'mode': 'profile', 'profile_data': profiles['librairie'], 'default': 20.0},
            '4': {'mode': 'profile', 'profile_data': profiles['textile'], 'default': 20.0},
            '5': {'mode': 'profile', 'profile_data': profiles['pharmacie'], 'default': 20.0},
            '6': {'mode': 'profile', 'profile_data': profiles['hightech'], 'default': 20.0},
            '7': {'mode': 'fixed', 'rate': 20.0},
            '8': {'mode': 'fixed', 'rate': 5.5}
        }
        
        tva_config = tva_config_map.get(tva_choice, {'mode': 'auto', 'default': 20.0})
        
        if tva_config['mode'] == 'profile':
            profile_name = tva_config['profile_data']['name']
            print(f"✅ TVA configurée : Profil {profile_name}")
        else:
            print(f"✅ TVA configurée : {tva_config}")
    
    # Synchronisation des stocks avec Ted's
    print("\n📦 Synchronisation des stocks")
    print("-" * 30)
    sync_stock_input = input("Synchroniser les stocks avec l'export Ted's ? (o/N) : ").strip().lower()
    sync_stock = sync_stock_input in ['o', 'oui', 'y', 'yes']
    
    if sync_stock:
        print("✅ Synchronisation des stocks activée")
    else:
        print("ℹ️ Synchronisation des stocks désactivée")
    
    ai_config = {
        'options': ai_options,
        'openai_key': openai_key
    }
    
    stock_config = {
        'sync_enabled': sync_stock
    }
    
    return access_token, store_id, limit, global_brand, ai_config, tva_config, stock_config

def generate_ai_content(description, name, ai_config=None):
    """Génère du contenu avec OpenAI selon les options sélectionnées"""
    # Configuration par défaut si aucune option IA n'est sélectionnée
    default_content = {
        "description_html": f"<p>{description.strip()}</p>" if description else f"<p>Produit {name} de qualité</p>",
        "short_description": description[:200] + "..." if len(description) > 200 else description or f"Produit {name} de qualité",
        "meta_title": name,
        "meta_description": description[:160] + "..." if len(description) > 160 else description or f"Découvrez {name}",
        "alt_text": f"Image du produit {name}",
        "keywords": [],
        "cross_selling_suggestions": []
    }
    
    if not ai_config or not ai_config.get('options') or not ai_config.get('openai_key'):
        return default_content
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=ai_config['openai_key'])
        
        # Construire le prompt selon les options sélectionnées
        ai_options = ai_config['options']
        tasks = []
        
        if 1 in ai_options:  # Métadonnées SEO
            tasks.append("1. Un meta title optimisé SEO (max 60 caractères)")
            tasks.append("2. Une meta description SEO (max 160 caractères)")
        
        if 2 in ai_options:  # Description courte
            tasks.append("3. Une description courte attrayante (max 150 caractères)")
        
        if 3 in ai_options:  # Description longue
            tasks.append("4. Une description HTML complète et détaillée (max 500 mots)")
        
        if 4 in ai_options:  # Balise alt des images
            tasks.append("5. Une balise alt descriptive pour les images")
        
        if 5 in ai_options:  # Mots-clés produit
            tasks.append("6. Une liste de mots-clés pertinents (5-8 mots)")
        
        if 6 in ai_options:  # Suggestions de vente croisée
            tasks.append("7. Des suggestions de produits complémentaires (3-5 suggestions)")
        
        tasks_text = "\n".join(tasks)
        
        prompt = f"""
        Améliore cette fiche produit pour un site e-commerce :
        
        Nom du produit : {name}
        Description actuelle : {description}
        
        Génère les éléments suivants :
        {tasks_text}
        
        Réponds en JSON avec cette structure exacte :
        {{
            "meta_title": "...",
            "meta_description": "...",
            "short_description": "...",
            "description_html": "<p>...</p>",
            "alt_text": "...",
            "keywords": ["mot1", "mot2", "mot3"],
            "cross_selling_suggestions": ["produit1", "produit2", "produit3"]
        }}
        
        Notes importantes :
        - Respecte les limites de caractères
        - Utilise un français naturel et engageant
        - Optimise pour le SEO e-commerce
        - Si une option n'est pas demandée, mets une valeur vide appropriée
        """
        
        response = client.chat.completions.create(
            model="gpt-4.1-nano-2025-04-14",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7
        )
        
        import json
        ai_content = json.loads(response.choices[0].message.content)
        
        # Fusionner avec le contenu par défaut pour garantir toutes les clés
        result = default_content.copy()
        result.update(ai_content)
        
        option_names = {
            1: "Métadonnées SEO",
            2: "Description courte", 
            3: "Description longue",
            4: "Balise alt",
            5: "Mots-clés",
            6: "Vente croisée"
        }
        selected_names = [option_names[opt] for opt in ai_options]
        print(f"  🤖 IA générée ({', '.join(selected_names)}) : {name}")
        
        return result
        
    except Exception as e:
        print(f"  ⚠️ Erreur IA pour {name} : {e}")
        return default_content

def load_stock_from_teds(export_file):
    """Charge les stocks depuis l'export Ted's CMS"""
    try:
        # Essayer avec séparateur point-virgule d'abord (format Ted's CMS)
        try:
            df_teds = pd.read_csv(export_file, sep=';')
            print(f"✅ Export Ted's chargé pour stocks : {len(df_teds)} produits (format point-virgule)")
        except:
            # Fallback avec virgule standard
            df_teds = pd.read_csv(export_file)
            print(f"✅ Export Ted's chargé pour stocks : {len(df_teds)} produits (format virgule)")
        
        # Créer un dictionnaire de mapping nom -> stock
        stock_mapping = {}
        
        # Colonnes possibles pour le nom du produit
        name_columns = ['Nom du produit', 'nom', 'name', 'title', 'titre']
        name_col = None
        for col in name_columns:
            if col in df_teds.columns:
                name_col = col
                break
        
        # Colonnes possibles pour le stock
        stock_columns = ['stock', 'Stock', 'quantity', 'quantité', 'Quantité', 'Qty']
        stock_col = None
        for col in stock_columns:
            if col in df_teds.columns:
                stock_col = col
                break
        
        if not name_col or not stock_col:
            print(f"❌ Colonnes stock non trouvées dans l'export Ted's")
            print(f"   Colonnes disponibles : {list(df_teds.columns)}")
            print(f"   Nom trouvé : {name_col}, Stock trouvé : {stock_col}")
            return {}
        
        print(f"✅ Colonnes détectées - Nom: '{name_col}', Stock: '{stock_col}'")
        
        for _, row in df_teds.iterrows():
            name = safe_get(row, name_col)
            stock_value = safe_get(row, stock_col)
            
            if name and stock_value:
                try:
                    # Nettoyer la valeur stock (convertir en int)
                    stock_clean = str(stock_value).replace(',', '.').strip()
                    stock_qty = int(float(stock_clean))
                    
                    # Normaliser le nom pour la recherche
                    name_normalized = name.lower().strip()
                    stock_mapping[name_normalized] = max(0, stock_qty)  # Stock minimum 0
                    
                except ValueError:
                    print(f"⚠️ Stock invalide pour '{name}': '{stock_value}'")
                    continue
        
        print(f"✅ {len(stock_mapping)} stocks chargés depuis Ted's")
        return stock_mapping
        
    except Exception as e:
        print(f"❌ Erreur lecture stocks Ted's : {e}")
        return {}

def get_stock_from_teds(product_name, stock_mapping, default_stock=100):
    """Récupère le stock depuis le mapping Ted's"""
    if not stock_mapping:
        return default_stock
    
    # Normaliser le nom pour la recherche
    name_normalized = product_name.lower().strip()
    
    # Recherche exacte
    if name_normalized in stock_mapping:
        stock = stock_mapping[name_normalized]
        print(f"  📦 Stock {stock} trouvé dans Ted's pour: {product_name}")
        return stock
    
    # Recherche approximative (contient)
    for teds_name, stock in stock_mapping.items():
        if teds_name in name_normalized or name_normalized in teds_name:
            print(f"  📦 Stock {stock} trouvé (approx) dans Ted's pour: {product_name}")
            return stock
    
    # Pas trouvé
    print(f"  📦 Stock {default_stock} par défaut (non trouvé dans Ted's) pour: {product_name}")
    return default_stock

def process_csv_to_wizi(csv_file, access_token, store_id, limit=None, global_brand=None, ai_config=None, tva_config=None, stock_config=None):
    """Traite un CSV et l'importe dans WiziShop"""
    print(f"\n🔄 Traitement du fichier : {os.path.basename(csv_file)}")
    
    # Initialisation API, IA, TVA, marque et stocks
    wizi_api = WiziShopAPI(access_token, store_id)
    category_mapper = CategoryMapper(wizi_api)
    filter_manager = FilterManager(wizi_api)
    filter_manager.load_existing_filters()
    ai_config = ai_config or {'options': [], 'openai_key': None}
    tva_config = tva_config or {'mode': 'auto', 'default': 20.0}
    stock_config = stock_config or {'sync_enabled': False}
    
    # Chargement des stocks depuis Ted's si activé
    stock_mapping = {}
    if stock_config.get('sync_enabled') and tva_config.get('export_file'):
        stock_mapping = load_stock_from_teds(tva_config['export_file'])
    elif stock_config.get('sync_enabled'):
        # Chercher un fichier d'export Ted's dans le dossier
        export_files = detect_teds_export_files()
        if export_files:
            print(f"📁 Utilisation de l'export pour stocks : {os.path.basename(export_files[0])}")
            stock_mapping = load_stock_from_teds(export_files[0])
        else:
            print("⚠️ Synchronisation stocks demandée mais aucun export Ted's trouvé")
    
    # Lecture CSV
    try:
        df = pd.read_csv(csv_file)
        print(f"✅ {len(df)} produits chargés depuis le CSV")
    except Exception as e:
        print(f"❌ Erreur lecture CSV : {e}")
        return
    
    if limit:
        df = df.head(limit)
        print(f"ℹ️ Limitation à {limit} produits pour test")
    
    # Logs séparés
    products_log = []
    categories_log = []
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    products_log_filename = f"wizi_products_log_{timestamp}.json"
    categories_log_filename = f"wizi_categories_log_{timestamp}.json"
    products_log_path = os.path.join(OUTPUT_DIR, products_log_filename)
    categories_log_path = os.path.join(OUTPUT_DIR, categories_log_filename)
    
    # Traitement des produits
    success_count = 0
    error_count = 0
    
    for i, row in df.iterrows():
        nom = safe_get(row, "Nom du produit")
        if not nom:
            print(f"❌ Ligne {i+2} : Nom du produit manquant")
            error_count += 1
            continue
        
        try:
            print(f"\n--- Produit {i+1}/{len(df)} : {nom} ---")
            
            # Mapping des catégories
            main_cat = safe_get(row, "Catégorie principale") or safe_get(row, "Catégorie")
            sub_cat = safe_get(row, "Catégorie secondaire") or safe_get(row, "Sous catégorie") or safe_get(row, "Sous-catégorie")
            
            if not main_cat:
                print(f"⚠️ Aucune catégorie trouvée pour '{nom}', produit ignoré")
                error_count += 1
                continue
            
            category_id = category_mapper.get_category_id(main_cat, sub_cat)
            if not category_id:
                print(f"❌ Impossible de mapper les catégories pour : {nom}")
                error_count += 1
                continue
            
            # Prix et TVA intelligente
            prix_ttc = safe_get(row, "Prix TTC") or safe_get(row, "Prix")
            if not prix_ttc:
                print(f"❌ Prix manquant pour : {nom}")
                error_count += 1
                continue
            
            # Détection du taux de TVA
            tva = detect_tva_rate(nom, safe_get(row, "Description"), main_cat, tva_config)
            prix_ht = clean_price_ttc_to_ht(prix_ttc, tva)
            
            # Description et métadonnées avec IA
            description_brute = safe_get(row, "Description")
            meta_title_csv = safe_get(row, "Meta title")
            meta_desc_csv = safe_get(row, "Meta description")
            
            ai_content = generate_ai_content(description_brute, nom, ai_config)
            
            # Gestion des stocks avec Ted's si activé
            if stock_mapping:
                product_stock = get_stock_from_teds(nom, stock_mapping, default_stock=100)
            else:
                product_stock = 100  # Stock par défaut
            
            # Images (format API Wizi : juste l'URL string)
            images = []
            for j in range(1, 6):
                img_url = safe_get(row, f"Image {j}")
                if img_url and img_url.startswith('http'):
                    images.append(img_url)  # API Wizi attend juste l'URL
            
            # SKU
            sku_base = generate_sku(nom[:5].upper().replace(" ", "-"))
            
            # Construction du payload produit selon la doc WiziShop (simplifié)
            product_payload = {
                "category_id": category_id,
                "sku": sku_base,
                "name": nom,
                "description": ai_content["description_html"],
                "short_description": ai_content["short_description"],
                "brand": global_brand,  # Marque globale configurée
                "tax": tva,
                "weight": 0.02,
                "quantity": product_stock,  # Stock synchronisé avec Ted's
                "price_tax_excluded": round(prix_ht, 2),
                "wholesale_price_tax_excluded": round(prix_ht * 0.4, 2),
                "reduction": 0,
                "reduction_type": "percentage",
                "images": images,
                "visible": True,
                "url": slugify(nom),
                "meta": {
                    "title": meta_title_csv or ai_content["meta_title"],
                    "description": meta_desc_csv or ai_content["meta_description"]
                },
                "type": "standard"
            }
            
            # Ajouter les champs optionnels seulement si nécessaire
            if ai_content.get("keywords"):
                product_payload["tags"] = ai_content["keywords"]
            
            # Gestion des attributs (déclinaisons)
            attributes = []
            for attr_index in range(1, 3):  # 1 et 2 selon les colonnes CSV
                attr_name = safe_get(row, f"Attribut {attr_index} Nom")
                if not attr_name:
                    continue
                
                options = []
                # Nombre de valeurs variable selon l'attribut (jusqu'à 4 pour attr1, 7 pour attr2)
                max_values = 4 if attr_index == 1 else 7
                for j in range(1, max_values + 1):
                    val_raw = safe_get(row, f"Attribut {attr_index} Valeur {j}")
                    if not val_raw:
                        continue
                    
                    val_clean = clean_value_label(val_raw)
                    if not val_clean:
                        continue
                    
                    # Prix de la déclinaison
                    prix_var_csv = safe_get(row, f"Attribut {attr_index} Prix {j}")
                    if prix_var_csv:  # Si prix spécifié pour cette déclinaison
                        prix_var_ht = clean_price_ttc_to_ht(prix_var_csv, tva)
                    else:  # Si colonne vide = 0€ pour cette déclinaison
                        prix_var_ht = 0.0
                    
                    # Image de la déclinaison
                    image_var = safe_get(row, f"Attribut {attr_index} Photo {j}")
                    
                    # Structure selon l'API Wizi : price_tax_excluded (prix absolu)
                    options.append({
                        "value": val_clean,
                        "sku": f"{sku_base}-A{attr_index}-{j}",
                        "ean13": "",
                        "weight": 0.02,
                        "quantity": product_stock,
                        "price_tax_excluded": round(prix_var_ht, 2),  # Prix absolu comme dans l'API
                        "reduction": 0,
                        "reduction_type": "pourc",
                        "image": image_var if image_var and image_var.startswith('http') else None,
                        "active": True,
                        "default": (j == 1)
                    })
                
                if options:
                    attributes.append({
                        "name": attr_name,
                        "options": options
                    })
            
            if attributes:
                product_payload["attributes"] = attributes
                product_payload["type"] = "declinations"
                product_payload["quantity"] = None  # Les déclinaisons gèrent leurs propres quantités
            
            # Envoi à l'API
            print(f"📡 Envoi du produit : {nom} (Catégorie ID: {category_id})")
            response = wizi_api.create_product(product_payload)
            
            # Plus besoin de ce debug, c'est dans create_product maintenant
            
            if response and response.status_code < 400:
                print(f"✅ Produit importé avec succès : {nom}")
                success_count += 1

                try:
                    response_data = response.json()
                    # L'API retourne l'id directement à la racine
                    if "id" in response_data:
                        product_id = response_data['id']
                        print(f"   ID WiziShop : {product_id}")

                        # Association des filtres (notes olfactives)
                        filters_data = {}

                        # Tête : fusion wizi + export sans doublons
                        tete_notes = set()
                        for note in safe_get(row, "tete_wizi").split(","):
                            if note.strip():
                                tete_notes.add(note.strip())
                        for note in safe_get(row, "tete_export").split(","):
                            if note.strip():
                                tete_notes.add(note.strip())
                        if tete_notes:
                            filters_data["Tête"] = list(tete_notes)

                        # Cœur : fusion wizi + export sans doublons
                        coeur_notes = set()
                        for note in safe_get(row, "coeur_wizi").split(","):
                            if note.strip():
                                coeur_notes.add(note.strip())
                        for note in safe_get(row, "coeur_export").split(","):
                            if note.strip():
                                coeur_notes.add(note.strip())
                        if coeur_notes:
                            filters_data["Cœur"] = list(coeur_notes)

                        # Fond : fusion wizi + export sans doublons
                        fond_notes = set()
                        for note in safe_get(row, "fond_wizi").split(","):
                            if note.strip():
                                fond_notes.add(note.strip())
                        for note in safe_get(row, "fond_export").split(","):
                            if note.strip():
                                fond_notes.add(note.strip())
                        if fond_notes:
                            filters_data["Fond"] = list(fond_notes)

                        # Associer les filtres au produit
                        if filters_data:
                            print(f"   🏷️ Association filtres : {sum(len(v) for v in filters_data.values())} notes")
                            filter_manager.associate_filters_to_product(product_id, filters_data)
                except Exception as e:
                    print(f"   ⚠️ Erreur association filtres: {e}")
            else:
                print(f"❌ Erreur import produit : {nom}")
                if response:
                    print(f"   Code : {response.status_code}")
                    print(f"   Réponse : {response.text}")
                error_count += 1
            
            # Log produits pour debug
            log_entry = product_payload.copy()
            log_entry["_csv_line"] = i+2
            log_entry["_product_name"] = nom
            if response:
                log_entry["_api_status_code"] = response.status_code
                try:
                    log_entry["_api_response"] = response.json()
                except:
                    log_entry["_api_response"] = response.text
            
            products_log.append(log_entry)
            
            # Pause pour éviter de surcharger l'API
            time.sleep(1.2)
            
        except Exception as e:
            print(f"❌ Erreur traitement produit '{nom}' : {e}")
            import traceback
            traceback.print_exc()
            error_count += 1
            
            products_log.append({
                "csv_line": i+2,
                "product_name": nom,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
    
    # Log des catégories créées
    categories_log.extend(category_mapper.get_creation_log())
    
    # Sauvegarde des logs
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(products_log_path, "w", encoding="utf-8") as f:
        json.dump(products_log, f, indent=2, ensure_ascii=False)
    
    with open(categories_log_path, "w", encoding="utf-8") as f:
        json.dump(categories_log, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Résumé de l'import :")
    print(f"   ✅ Succès : {success_count}")
    print(f"   ❌ Erreurs : {error_count}")
    print(f"   📄 Log produits : {products_log_path}")
    print(f"   📄 Log catégories : {categories_log_path}")
    if global_brand:
        print(f"   🏷️ Marque appliquée : {global_brand}")
    if ai_config.get('options'):
        option_names = {1: "SEO", 2: "Desc. courte", 3: "Desc. longue", 4: "Alt images", 5: "Mots-clés", 6: "Vente croisée"}
        selected = [option_names[opt] for opt in ai_config['options'] if opt in option_names]
        print(f"   🤖 IA utilisée : {', '.join(selected)}")
    if stock_config.get('sync_enabled'):
        print(f"   📦 Stocks synchronisés avec Ted's CMS")

def main():
    """Point d'entrée principal"""
    # Configurer l'encodage de sortie pour Windows
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(description="Import de produits vers WiziShop depuis CSV Teds")
    parser.add_argument("--csv", help="Fichier CSV spécifique à traiter")
    parser.add_argument("--limit", type=int, help="Nombre de produits à traiter (pour test)")
    parser.add_argument("--list", action="store_true", help="Lister les fichiers CSV disponibles")
    parser.add_argument("--token", help="Access token WiziShop")
    parser.add_argument("--store", help="Store ID WiziShop")
    args = parser.parse_args()
    
    # Créer les dossiers
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(EXPORT_TEDS_DIR, exist_ok=True)
    
    if args.list:
        csv_files = detect_csv_files()
        if csv_files:
            print("📁 Fichiers CSV disponibles dans input :")
            for i, file in enumerate(csv_files, 1):
                print(f"   {i}. {os.path.basename(file)}")
        else:
            print("❌ Aucun fichier CSV trouvé dans input/")
            print("💡 Placez vos CSV traités par convert_img dans le dossier input/")
        return
    
    # Récupération des identifiants
    if args.token and args.store:
        access_token, store_id = args.token, args.store
        limit = args.limit  # Utilise la limite des arguments
        global_brand = None  # Pas de marque en mode arguments
        ai_config = {'options': [], 'openai_key': None}  # Pas d'IA en mode arguments
        tva_config = {'mode': 'auto', 'default': 20.0}  # Configuration par défaut
        stock_config = {'sync_enabled': False}  # Pas de sync stock en mode arguments
    else:
        access_token, store_id, limit, global_brand, ai_config, tva_config, stock_config = get_shop_credentials()
        if not access_token or not store_id:
            return
        # Si une limite est passée en argument ET saisie interactivement, 
        # on prend celle des arguments (plus spécifique)
        if args.limit is not None:
            limit = args.limit
    
    # Sélection du fichier CSV
    if args.csv:
        csv_path = os.path.join(INPUT_DIR, args.csv) if not os.path.isabs(args.csv) else args.csv
        if not os.path.exists(csv_path):
            print(f"❌ Fichier CSV introuvable : {csv_path}")
            return
    else:
        csv_files = detect_csv_files()
        if not csv_files:
            print("❌ Aucun fichier CSV trouvé dans input/")
            print("💡 Placez vos CSV traités par convert_img dans le dossier input/")
            return
        
        if len(csv_files) == 1:
            csv_path = csv_files[0]
            print(f"📁 Fichier unique détecté : {os.path.basename(csv_path)}")
        else:
            print("📁 Plusieurs fichiers CSV trouvés :")
            for i, file in enumerate(csv_files, 1):
                print(f"   {i}. {os.path.basename(file)}")
            
            try:
                choice = int(input("Choisissez le numéro du fichier à traiter : ")) - 1
                if 0 <= choice < len(csv_files):
                    csv_path = csv_files[choice]
                else:
                    print("❌ Choix invalide")
                    return
            except ValueError:
                print("❌ Veuillez entrer un numéro valide")
                return
    
    # Traitement
    process_csv_to_wizi(csv_path, access_token, store_id, limit=limit, global_brand=global_brand, ai_config=ai_config, tva_config=tva_config, stock_config=stock_config)

if __name__ == "__main__":
    main()