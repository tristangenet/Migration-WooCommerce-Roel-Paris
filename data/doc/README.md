# Migration WooCommerce vers WiziShop

Outils de migration du catalogue produit de WooCommerce (RoelParis.com) vers WiziShop.

## 📋 Vue d'ensemble

Ce projet contient deux scripts complémentaires :

1. **`woocommerce_to_wizi.py`** : Convertit l'export WooCommerce vers un format compatible
2. **`wizi_import/wizi_import.py`** : Importe les produits dans WiziShop via API

## 🔄 Workflow complet

```
Export WooCommerce (Webtoffee)
         ↓
   woocommerce_to_wizi.py
         ↓
   CSV format WiziShop
         ↓
   wizi_import.py
         ↓
   Boutique WiziShop
```

## 🚀 Utilisation rapide

### Étape 1 : Conversion de l'export WooCommerce

```bash
python woocommerce_to_wizi.py
```

Le script :
- ✅ Détecte automatiquement `export_webtoffe_woocommerce.csv`
- ✅ Regroupe les variations sur une ligne
- ✅ Extrait et nettoie les images
- ✅ Parse les catégories hiérarchiques
- ✅ Génère un CSV dans `wizi_import/input/`

### Étape 2 : Import vers WiziShop

```bash
cd wizi_import
python wizi_import.py
```

Le script vous demandera :
- 🔑 Identifiants WiziShop (ou utilise `.env`)
- 📊 Nombre de produits à importer (ou tous)
- 🏷️ Marque globale (optionnel)
- 🤖 Options IA (OpenAI pour SEO/descriptions)
- 💰 Configuration TVA

## 📁 Structure du projet

```
woo_migration/
├── woocommerce_to_wizi.py          # Script de conversion
├── export_webtoffe_woocommerce.csv # Export WooCommerce (source)
├── wizi_import/
│   ├── wizi_import.py              # Script d'import WiziShop
│   ├── .env                        # Identifiants (à créer)
│   ├── input/                      # CSV convertis (générés)
│   ├── output/                     # Logs d'import
│   └── export_teds/                # Exports Ted's CMS (TVA/stocks)
├── API WIZI/                       # Documentation API
└── README.md                       # Ce fichier
```

## ⚙️ Configuration

### Variables d'environnement (optionnel)

Créez `wizi_import/.env` :

```env
WIZI_ACCESS_TOKEN=votre_token_wizishop
WIZI_STORE_ID=votre_store_id
OPENAI_API_KEY=votre_cle_openai  # Optionnel pour IA
```

## 📊 Détails de conversion

### Champs mappés

| WooCommerce | → | Format WiziShop |
|-------------|---|-----------------|
| `post_title` | → | `Nom du produit` |
| `post_content` | → | `Description` (HTML nettoyé) |
| `regular_price` | → | `Prix TTC` |
| `product_page_url` | → | `URL produit` |
| `tax:product_cat` | → | `Catégorie principale` + `Catégorie secondaire` |
| `images` | → | `Image 1` à `Image 5` |
| Variations enfants | → | `Attribut 1 Valeur X` + `Prix` + `Photo` |

### Gestion des variations

**WooCommerce** (plusieurs lignes) :
```
- Produit parent : "T-shirt"
  - Variation : "T-shirt - Rouge" (290€)
  - Variation : "T-shirt - Bleu" (320€)
```

**Format WiziShop** (une ligne) :
```csv
Nom du produit,Attribut 1 Nom,Attribut 1 Valeur 1,Attribut 1 Prix 1,Attribut 1 Valeur 2,Attribut 1 Prix 2
T-shirt,Color,Rouge,290,Bleu,320
```

### Nettoyage HTML

Le script :
- ✅ Supprime les styles CSS inline
- ✅ Garde uniquement les balises essentielles (p, h1-h6, ul, li, strong)
- ✅ Nettoie les espaces multiples
- ✅ Décode les entités HTML

## ✨ Corrections des limitations WiziShop

Le script gère automatiquement les limitations de l'API WiziShop :

### Catégories à 2 niveaux maximum

WiziShop ne supporte que 2 niveaux de catégories. Le script aplatit automatiquement :
```
WooCommerce: Parfums > Familles Olfactives > Ambré (3 niveaux)
WiziShop:    Familles Olfactives > Ambré (2 niveaux) ✅
```

### Pas de produits dans catégorie parente

WiziShop refuse d'assigner un produit à une catégorie qui a des enfants. Le script :
- Crée automatiquement une sous-catégorie si nécessaire
- Assigne toujours les produits à une sous-catégorie

### Catégories multiples

WooCommerce permet plusieurs catégories par produit. Le script :
- Prend la première catégorie (généralement la plus pertinente)
- Aplatit à 2 niveaux si nécessaire

Voir [README_CORRECTIONS.md](README_CORRECTIONS.md) pour plus de détails.

## 🔧 Options avancées

### Conversion personnalisée

```bash
# Spécifier un fichier
python woocommerce_to_wizi.py export_custom.csv

# Spécifier le fichier de sortie
python woocommerce_to_wizi.py -o output_custom.csv
```

### Import avec limite

```bash
# Tester avec 10 produits
python wizi_import.py --limit 10
```

### Gestion TVA intelligente

Le script `wizi_import.py` propose plusieurs modes :

1. **Ted's CMS** (recommandé) : Utilise les taux exacts depuis un export
2. **Auto-détection** : Détecte alimentaire (5.5%), alcool (20%), etc.
3. **Profils prédéfinis** : Librairie, Mode, Pharmacie, High-tech
4. **TVA fixe** : 20% ou 5.5% pour tous

### Options IA (OpenAI)

Génération automatique de :
- 🎯 Métadonnées SEO (title, description)
- 📝 Descriptions courtes et longues
- 🖼️ Balises alt des images
- 🏷️ Mots-clés produit
- 🔗 Suggestions de vente croisée

## 📈 Statistiques du dernier test

Conversion réussie :
- ✅ **329 produits** traités
- ✅ **265 produits simples**
- 🔀 **64 produits variables**
- 📦 **131 variations** regroupées
- ❌ **0 erreur**

## 🛠️ Dépendances

```bash
pip install pandas python-dotenv requests
```

## 📝 Logs

Les logs d'import sont sauvegardés dans `wizi_import/output/` :
- `wizi_products_log_YYYY-MM-DD_HH-MM-SS.json` : Détails des produits
- `wizi_categories_log_YYYY-MM-DD_HH-MM-SS.json` : Catégories créées

## 🐛 Dépannage

### Problème d'encodage Windows

Le script gère automatiquement l'encodage UTF-8 sur Windows.

### Images manquantes

Vérifiez que les URLs commencent par `http://` ou `https://`.

### Variations non détectées

Le script extrait le nom de l'attribut depuis `post_excerpt` (format : `"attribute: value"`).

### Catégories dupliquées

Le script vérifie les catégories existantes avant création et gère la hiérarchie parent/enfant.

## 📚 Documentation API

Consultez `API WIZI/` pour la documentation complète de l'API WiziShop.

## 🎯 Prochaines étapes

Après conversion et import :
1. ✅ Vérifier les catégories créées dans WiziShop
2. ✅ Contrôler quelques produits variables
3. ✅ Ajuster les prix si nécessaire (TTC vs HT)
4. ✅ Vérifier les images
5. ✅ Tester les variations

## 📧 Support

Pour toute question sur :
- Le script de conversion : vérifier les logs de conversion
- L'import WiziShop : consulter `wizi_import/output/`
- L'API WiziShop : voir documentation dans `API WIZI/`

---

**Projet créé pour la migration de RoelParis.com vers WiziShop**
