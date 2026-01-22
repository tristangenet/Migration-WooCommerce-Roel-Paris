# Instructions de test - Migration WooCommerce → WiziShop

## ✅ Ce qui a été corrigé

Les erreurs d'import ont été corrigées dans le script de conversion :

### Erreur 1 : "Can't add category to a child category"
- ❌ **Avant** : `Parfums > Familles Olfactives > Épicé` (3 niveaux)
- ✅ **Après** : `Familles Olfactives > Épicé` (2 niveaux)

### Erreur 2 : "Category is parent with id"
- ❌ **Avant** : Produit dans catégorie parente qui a des enfants
- ✅ **Après** : Toujours une sous-catégorie créée automatiquement

## 🚀 Test de la correction

### Étape 1 : Le CSV corrigé est prêt

Le fichier `wizi_import/input/woocommerce_converted_fixed.csv` contient :
- ✅ 329 produits convertis
- ✅ Catégories aplaties à 2 niveaux max
- ✅ Sous-catégories automatiques
- ✅ 0 erreur de conversion

### Étape 2 : Lancer l'import de test

```bash
cd wizi_import
python wizi_import.py --csv woocommerce_converted_fixed.csv --limit 10
```

**Le script va vous demander** :
1. Configuration TVA → Choisir "1" (Ted's CMS) ou "7" (20% fixe pour test)
2. Marque globale → Laisser vide pour test
3. Options IA → Laisser vide pour test
4. Sync stocks → "N" pour test

### Étape 3 : Vérifier les résultats

Après l'import de test, vérifiez :

```bash
# Voir les logs détaillés
cd output
# Ouvrir le dernier fichier wizi_products_log_*.json
```

**Attendu** :
- ✅ 10 produits importés
- ✅ 0 erreur "Can't add category to a child category"
- ✅ 0 erreur "Category is parent with id"
- ✅ Statut HTTP 201 (créé) pour tous les produits

### Étape 4 : Import complet (si test OK)

```bash
python wizi_import.py --csv woocommerce_converted_fixed.csv
```

Configuration recommandée :
1. **TVA** : Option "1" (Ted's CMS) si vous avez un export
2. **Marque** : "Roel Paris" (ou laisser vide)
3. **IA** : Laisser vide pour le premier import (peut être ajouté après)
4. **Stocks** : "N" pour le premier import

## 📊 Produits critiques à vérifier

Ces produits avaient des erreurs et sont maintenant corrigés :

| Produit | Avant | Après | Statut |
|---------|-------|-------|--------|
| **UDEN** | 3 niveaux + catégories multiples | `Familles Olfactives > Épicé` | ✅ Corrigé |
| **PERDIZIONE** | 3 niveaux + catégories multiples | `Familles Olfactives > Fleuri` | ✅ Corrigé |
| **Translucent Setting Powder** | 3 niveaux | `Familles Olfactives > Ambré` | ✅ Corrigé |

## 🔍 Vérification dans WiziShop

Après l'import, vérifiez dans votre back-office WiziShop :

### Catégories
1. Aller dans **Catalogue > Catégories**
2. Vérifier que les catégories suivantes existent :
   - `Familles Olfactives` (parent)
     - `Épicé` (enfant)
     - `Fleuri` (enfant)
     - `Ambré` (enfant)
     - etc.

### Produits
1. Aller dans **Catalogue > Produits**
2. Filtrer par catégorie
3. Vérifier que :
   - Les produits sont bien dans les bonnes catégories
   - Les variations sont correctement importées
   - Les prix sont corrects (HT calculé automatiquement)
   - Les images sont bien affichées

## 🐛 Si vous rencontrez des erreurs

### Erreur "Category already exists"
C'est normal ! Le script détecte les catégories existantes et ne les recrée pas.

### Erreur "Product already exists"
Si vous relancez l'import, des produits peuvent déjà exister. Options :
1. Supprimer les produits existants dans WiziShop
2. Utiliser `--limit` pour ne pas réimporter tous les produits

### Erreur d'encodage (accents)
Les accents sont préservés dans le CSV UTF-8. Si vous voyez des `�` dans le terminal Windows, c'est normal - les données dans le fichier sont correctes.

### Erreur de TVA
Si les prix semblent incorrects :
1. Vérifier le taux de TVA choisi (20% par défaut)
2. Les prix dans WooCommerce sont TTC
3. Le script calcule automatiquement le HT selon la TVA

## 📋 Checklist finale

Avant l'import complet :
- [ ] Test avec 10 produits réussi
- [ ] Vérification catégories dans WiziShop
- [ ] Vérification produits de test
- [ ] Configuration TVA validée
- [ ] Backup WiziShop effectué (si applicable)

Après l'import complet :
- [ ] 329 produits importés sans erreur
- [ ] Catégories hiérarchiques correctes
- [ ] Produits avec variations fonctionnels
- [ ] Prix cohérents (TTC → HT)
- [ ] Images chargées correctement

## 💾 Logs et sauvegarde

Tous les logs sont dans `wizi_import/output/` :
- `wizi_products_log_*.json` : Détails de chaque produit
- `wizi_categories_log_*.json` : Catégories créées

Conservez ces fichiers pour référence !

## 🆘 Support

En cas de problème :
1. Vérifiez les logs dans `wizi_import/output/`
2. Consultez [README_CORRECTIONS.md](README_CORRECTIONS.md)
3. Vérifiez votre configuration dans `.env`

---

**Prêt pour l'import ?** Suivez les étapes ci-dessus ! 🚀
