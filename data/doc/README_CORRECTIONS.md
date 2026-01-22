# Corrections apportées - Migration WooCommerce vers WiziShop

## Problèmes corrigés

### 1. Catégories à 3+ niveaux de profondeur ❌ → ✅

**Problème** : WiziShop ne supporte que 2 niveaux de catégories (parent > enfant)
**Erreur** : `"Can't add category to a child category #70"`

**Exemple** :
```
WooCommerce: Parfums > Familles Olfactives > Ambré (3 niveaux)
WiziShop:    Familles Olfactives > Ambré (2 niveaux) ✅
```

**Solution** : Aplatissement automatique en prenant les 2 derniers niveaux.

### 2. Produits sans sous-catégorie ❌ → ✅

**Problème** : WiziShop refuse d'assigner un produit à une catégorie parente qui a des enfants
**Erreur** : `"Category is parent with id -> 62. Error #2"`

**Exemple** :
```
Avant:
- Catégorie principale: "Parfums"
- Catégorie secondaire: (vide)
❌ Erreur si "Parfums" a des sous-catégories

Après:
- Catégorie principale: "Parfums"
- Catégorie secondaire: "Parfums"
✅ Toujours une sous-catégorie
```

**Solution** : Duplication automatique du nom de catégorie si pas de sous-catégorie.

### 3. Catégories multiples avec hiérarchie ❌ → ✅

**Problème** : WooCommerce permet plusieurs catégories par produit avec hiérarchie
**Format WooCommerce** : `"Parfums > Familles Olfactives > Épicé|Parfums > Marques > Xerjoff"`

**Exemple - UDEN** :
```
Avant:
- Parfums > Familles Olfactives > Épicé (3 niveaux)
- Parfums > Marques > Xerjoff (3 niveaux)
❌ Impossible dans WiziShop

Après:
- Catégorie principale: "Familles Olfactives"
- Catégorie secondaire: "Épicé"
✅ Prend la première catégorie et aplatit à 2 niveaux
```

**Solution** : Sélection de la première catégorie + aplatissement à 2 niveaux.

## Modifications du script

### `woocommerce_to_wizi.py`

#### Fonction `parse_category_hierarchy()` améliorée

```python
def parse_category_hierarchy(category_string):
    """
    Gère 3 formats WooCommerce :
    1. "Cat1|Cat2" : plusieurs catégories
    2. "Cat1 > Cat2 > Cat3" : hiérarchie
    3. "Cat1 > Cat2|Cat3 > Cat4" : mixte

    Applique les règles WiziShop :
    - Max 2 niveaux
    - Toujours une sous-catégorie
    """
```

**Logique appliquée** :
1. Si plusieurs catégories séparées par `|` + hiérarchie `>` → Prendre la première
2. Si 3+ niveaux → Aplatir en prenant les 2 derniers
3. Si 1 seul niveau → Dupliquer pour créer une sous-catégorie

#### Gestion de l'encodage UTF-8

```python
# Lecture avec détection automatique
try:
    df_woo = pd.read_csv(woo_csv_path, dtype=str, encoding='utf-8')
except UnicodeDecodeError:
    df_woo = pd.read_csv(woo_csv_path, dtype=str, encoding='latin1')

# Écriture avec BOM pour Excel
df_wizi.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
```

## Résultats

### Statistiques de conversion

```
✅ 329 produits traités
✅ 265 produits simples
🔀 64 produits variables
📦 131 variations
❌ 0 erreur
```

### Exemples de conversions réussies

| Produit | WooCommerce | WiziShop |
|---------|-------------|----------|
| **UDEN** | `Parfums > Familles Olfactives > Épicé\|Parfums > Marques > Xerjoff` | `Familles Olfactives` > `Épicé` |
| **PERDIZIONE** | `Parfums > Familles Olfactives > Fleuri\|...\|Parfums > Marques > NOBILE 1942` | `Familles Olfactives` > `Fleuri` |
| **Translucent Setting Powder** | `Parfums > Familles Olfactives > Ambré` | `Familles Olfactives` > `Ambré` |

## Test d'import

Pour tester le nouveau CSV corrigé :

```bash
cd wizi_import
python wizi_import.py
```

Sélectionnez le fichier : `woocommerce_converted_fixed.csv`

### Vérifications à faire

- [ ] Les catégories se créent sans erreur
- [ ] Aucune erreur "Can't add category to a child category"
- [ ] Aucune erreur "Category is parent with id"
- [ ] Les produits sont bien assignés à leurs catégories
- [ ] Les variations sont correctement importées

## Fichiers générés

- `wizi_import/input/woocommerce_converted_fixed.csv` - CSV corrigé prêt pour import
- `wizi_import/output/wizi_products_log_*.json` - Log détaillé des produits
- `wizi_import/output/wizi_categories_log_*.json` - Log des catégories créées

## Notes

- Les accents (é, è, à) sont préservés grâce à l'encodage UTF-8 avec BOM
- Les noms de catégories sont nettoyés (espaces, caractères spéciaux)
- L'ordre des catégories est préservé (première = plus pertinente)
