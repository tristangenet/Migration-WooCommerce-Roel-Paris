# Migration WooCommerce - Roel Paris

Pipeline ETL pour migrer le catalogue produits de WooCommerce (RoelParis.com) vers la plateforme e-commerce WiziShop.

## Aperçu

- **329+ produits** migrés (265 simples, 64 avec variations)
- **Gestion des variations** (jusqu'à 7 par attribut)
- **Classification des notes olfactives** (Tête/Cœur/Fond)
- **Import parallèle** optimisé avec cache

## Structure du Projet

```
woo_migration/
├── 1-extract/                      # Extraction depuis WooCommerce
│   └── woocommerce_to_wizi.py      # Convertisseur principal
│
├── 2-transform/                    # Transformation des données
│   ├── add_notes_filters.py        # Classification notes olfactives
│   ├── enrich_descriptions.py      # Enrichissement descriptions
│   ├── feature_manager.py          # Gestion features produits
│   ├── filter_manager.py           # Gestion filtres/facettes
│   ├── wizi_update_brands.py       # Mise à jour marques
│   └── convert_img/                # Conversion d'images
│       ├── convert_img.py          # Conversion depuis CSV traité
│       └── convert_woocommerce_webp.py  # WebP → PNG via FTP
│
├── 3-load/                         # Chargement vers WiziShop
│   ├── wizi_import_fasttry.py      # Import parallèle (principal)
│   ├── filter_manager.py           # Association filtres produits
│   ├── input/                      # CSV d'entrée
│   └── output/                     # Logs JSON
│
├── data/
│   ├── api/                        # Exemples API WiziShop
│   └── doc/                        # Documentation détaillée
│
├── tests/                          # Scripts de test
└── legacy/                         # Anciennes versions archivées
```

## Pipeline ETL

```
┌─────────────────────────────────────────────────────────────────┐
│  1. EXTRACT                                                     │
│  export_webtoffe_woocommerce.csv                                │
│       ↓                                                         │
│  woocommerce_to_wizi.py                                         │
│  • Parse format WooCommerce                                     │
│  • Aplatit les variations (max 7)                               │
│  • Extrait les images (jusqu'à 5)                               │
│  • Adapte les catégories (3 → 2 niveaux)                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. TRANSFORM                                                   │
│  add_notes_filters.py                                           │
│  • Classifie les notes olfactives                               │
│  • Ajoute 6 colonnes (tete/coeur/fond × wizi/export)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. LOAD                                                        │
│  wizi_import_fasttry.py                                         │
│  • Phase 1: Pré-création catégories (séquentiel)                │
│  • Phase 2: Import produits (parallèle, 1-5 threads)            │
│  • Phase 3: Association des filtres                             │
└─────────────────────────────────────────────────────────────────┘
```

## Utilisation

### Prérequis

```bash
pip install requests python-dotenv openai Pillow
```

### Configuration

Créer un fichier `.env` à la racine :

```env
WIZI_ACCESS_TOKEN=votre_token_jwt
WIZI_STORE_ID=votre_store_id
OPENAI_API_KEY=votre_cle_openai  # Optionnel

# FTP pour conversion images WebP
FTP_HOST=votre_host_ftp
FTP_USER=votre_user_ftp
FTP_PASS=votre_password_ftp
FTP_REMOTE_DIR=/chemin/distant
FTP_URL_BASE=https://votre-domaine.com/
```

### Exécution

```bash
# 1. Extraction
cd 1-extract
python woocommerce_to_wizi.py

# 2. Transformation
cd ../2-transform
python add_notes_filters.py

# 3. Chargement
cd ../3-load
python wizi_import_fasttry.py
```


### Interface web (sans CLI)

```bash
python web/app.py
```

(Serveur web Python standard library, sans dépendance externe.)

Puis ouvrez `http://localhost:5000` pour :
- uploader un CSV WooCommerce,
- lancer **Extract + Transform** automatiquement,
- récupérer les fichiers générés dans `3-load/input/`.

### Déploiement Vercel

Le repo est maintenant compatible Vercel via `api/index.py` + `vercel.json`.

- Route principale servie par la fonction serverless Python
- Upload CSV via formulaire web
- Exécution Extract + Transform côté fonction

> ⚠️ Limites Vercel : stockage éphémère (`/tmp`) et timeout de fonction. Pour des gros imports, privilégiez l'exécution locale.

### Options d'import

```bash
# Test avec 10 produits
python wizi_import_fasttry.py --limit 10

# Mode non-interactif
python wizi_import_fasttry.py --token TOKEN --store STORE_ID --csv fichier.csv
```

## Contraintes WiziShop Gérées

| Contrainte | Solution |
|------------|----------|
| 2 niveaux de catégories max | Aplatissement automatique (Parfums > Famille > Type → Famille > Type) |
| Pas de produits dans catégories parentes | Attribution aux catégories feuilles uniquement |
| Format variations spécifique | Conversion en colonnes Attribut X Valeur/Prix/Stock |
| Filtres notes olfactives | Classification automatique Tête/Cœur/Fond |

## Fonctionnalités

- **Import parallèle** : ThreadPoolExecutor configurable (1-5 threads)
- **Cache intelligent** : Catégories et filtres en mémoire
- **Retry automatique** : 3 tentatives avec backoff exponentiel
- **Logs détaillés** : JSON avec ligne CSV, réponse API, statut
- **IA optionnelle** : Enrichissement SEO via OpenAI (meta, descriptions, alt)

## Logs et Debugging

Les logs sont générés dans `3-load/output/` :

```
wizi_products_log_2024-01-15_14-30-00.json
wizi_categories_log_2024-01-15_14-30-00.json
```

Exemple de log produit :
```json
{
  "_csv_line": 42,
  "_product_name": "UDEN",
  "_api_status_code": 201,
  "_wizi_product_id": 12345
}
```


## Visuel du pipeline

Pour une vue graphique rapide du projet (sans parcourir tout le code), consultez :

- [Visuel du projet](data/doc/VISUEL_PROJET.md)

## Documentation

- [Documentation détaillée](data/doc/README.md)
- [Corrections WiziShop](data/doc/README_CORRECTIONS.md)
- [Import rapide](data/doc/fast_import.md)
- [Enrichissement descriptions](data/doc/ENRICHISSEMENT_DESCRIPTIONS.md)

## Licence

Projet privé - Roel Paris
