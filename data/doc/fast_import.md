# Plan d'Optimisation Import WiziShop

## Problème actuel

**Performance mesurée** : 350 produits importés en 35 minutes = **10 produits/minute** (6 secondes par produit)

Pour un CSV de ~9000 produits → **~15 heures d'import** 😱

---

## Analyse des Bottlenecks

### 1. Délai artificiel de 1.2 seconde par produit ⚠️

**Localisation** : `wizi_import/wizi_import.py` ligne 1067

```python
time.sleep(1.2)  # Entre chaque produit
```

**Impact** :
- 350 produits × 1.2s = 420 secondes = **7 minutes de pure attente**
- Représente **20% du temps total**
- Rate-limiting trop agressif (probablement inutile)

---

### 2. Import 100% séquentiel (aucune parallélisation)

**Localisation** : `wizi_import/wizi_import.py` lignes 857-1080

```python
for i, row in df.iterrows():
    # ... process product ...
    response = wizi_api.create_product(product_payload)  # Bloquant
    # ... filter association ...
    filter_manager.associate_filters_to_product(product_id, filters_data)  # Bloquant
    time.sleep(1.2)
```

**Impact** :
- Chaque produit = 5-20 requêtes API exécutées séquentiellement
- Temps de latence réseau × nombre de requêtes
- Aucune requête en parallèle
- Représente **70% du temps total**

---

### 3. Multiples requêtes API par produit

**Décomposition pour 1 produit avec filtres complets** :

#### A. Opérations sur les catégories (3-5 requêtes)
```
GET  /categories                    (récupérer toutes les catégories)
GET  /categories                    (chercher catégorie principale)
POST /categories                    (créer si inexistante)
GET  /categories                    (chercher sous-catégorie)
POST /categories                    (créer si inexistante)
```

#### B. Création du produit (1 requête)
```
POST /products                       (créer le produit)
```

#### C. Association des filtres (10-18 requêtes)
```
Pour chaque type de filtre (Marques, Modèles, Cylindrées, Années) :
   GET  /product-filters/label       (lister tous les filtres)
   POST /product-filters/label       (créer si inexistant)

   Pour chaque valeur du filtre :
      GET  /product-filters/label/{id}         (lister les facets)
      POST /product-filters/label/{id}/facets  (créer facet si inexistante)

PUT /products/{product_id}/filters   (associer tous les filtres au produit)
```

**Total moyen : 14-24 requêtes API par produit** 🔥

---

### 4. Cache des catégories inefficace

**Localisation** : `wizi_import/wizi_import.py` lignes 95-129, 200-202

```python
def get_categories(self):
    if self.categories_cache is not None:
        return self.categories_cache

    response = requests.get(f"{self.base_url}/categories", headers=self.headers)
    # ... build cache ...
    return self.categories_cache

def create_category(self, name, parent_id=None):
    # ... create category ...
    self.categories_cache = None  # ⚠️ Invalide tout le cache !
```

**Problème** :
- Cache invalidé après chaque création de catégorie
- Force un nouveau `GET /categories` au produit suivant
- Recherche linéaire O(n) dans toutes les catégories

**Impact** :
- Requêtes inutiles répétées
- ~10% de temps perdu

---

### 5. Recherche de catégories inefficace

**Localisation** : `wizi_import/wizi_import.py` lignes 131-153

```python
def find_category_by_name(self, name, parent_id=None):
    categories = self.get_categories()
    name_lower = name.lower().strip()

    matches = []
    for cat in categories:  # ⚠️ Recherche linéaire O(n)
        if cat.get('name', '').lower().strip() == name_lower:
            matches.append(cat)
```

**Problème** :
- Recherche linéaire dans toutes les catégories (peut-être 100-500)
- Aucun index/dictionnaire

**Impact** :
- ~5% de temps perdu

---

## Solutions Proposées

### 🚀 Phase 1 : Quick Wins (15 minutes de dev)

#### Optimisation 1.1 : Réduire le délai artificiel

**Fichier** : `wizi_import/wizi_import.py` ligne 1067

```python
# AVANT
time.sleep(1.2)

# APRÈS
time.sleep(0.3)  # Ou 0.2s, à tester
```

**Gain estimé** : **+3x plus rapide** (7 minutes économisées sur 35)

**Risque** : Vérifier les limites de rate-limiting WiziShop
- Tester sur boutique TEST avec 20-50 produits
- Si erreur 429 (Too Many Requests) → augmenter légèrement
- Sinon, peut même descendre à 0.2s ou 0.1s

---

#### Optimisation 1.2 : Améliorer le cache des catégories

**Fichier** : `wizi_import/wizi_import.py` lignes 95-129, 200-202

```python
# AVANT
def create_category(self, name, parent_id=None):
    # ...
    self.categories_cache = None  # ⚠️ Invalide tout

# APRÈS
def create_category(self, name, parent_id=None):
    # ...
    # Ne PAS invalider le cache, juste ajouter la nouvelle catégorie
    new_category = response_data.get('data', response_data)
    if self.categories_cache:
        self.categories_cache.append(new_category)
        # Mettre à jour l'index si présent
        if hasattr(self, 'category_index'):
            self.category_index['by_id'][new_category['id']] = new_category
            self.category_index['by_name'][new_category['name'].lower()] = new_category
```

**Pré-charger les catégories au démarrage** :

```python
# Dans __init__ ou au début de import_products()
print("Pré-chargement des catégories...")
self.get_categories()  # Force le chargement initial
print(f"✓ {len(self.categories_cache)} catégories en cache")
```

**Gain estimé** : **+10%** (30-70 secondes économisées)

---

#### Optimisation 1.3 : Indexer la recherche de catégories

**Fichier** : `wizi_import/wizi_import.py` lignes 95-129, 131-153

```python
# APRÈS get_categories() :
def get_categories(self):
    if self.categories_cache is not None:
        return self.categories_cache

    # ... existing code to fetch categories ...

    # Créer des index pour recherche rapide
    self.category_index = {
        'by_id': {cat['id']: cat for cat in self.categories_cache},
        'by_name': {cat['name'].lower(): cat for cat in self.categories_cache}
    }

    return self.categories_cache

# MODIFIER find_category_by_name :
def find_category_by_name(self, name, parent_id=None):
    if not hasattr(self, 'category_index'):
        self.get_categories()

    name_lower = name.lower().strip()

    # Recherche rapide O(1) au lieu de O(n)
    cat = self.category_index['by_name'].get(name_lower)

    if cat and parent_id is not None:
        if cat.get('parent_id') == parent_id:
            return cat
        return None

    return cat
```

**Gain estimé** : **+5%** (10-30 secondes économisées)

---

### 📊 Résultat Phase 1

**Temps actuel** : 350 produits = 35 minutes

**Temps après Phase 1** : 350 produits = **8-12 minutes** 🎉

**Gain total** : **3-4x plus rapide**

**Effort** : 15 minutes de modifications simples

---

### 🚀 Phase 1.5 : Optimisation des Filtres (IMPLÉMENTÉ ✅)

**Problème identifié** : La gestion des filtres est le plus gros bottleneck après le sleep

Pour chaque produit avec filtres, le code faisait :
- 1 GET pour lister les filtres existants
- 1 POST par filtre si inexistant (×4 filtres potentiels)
- 1 GET par filtre pour lister les facets
- 1 POST par facet si inexistante (×3-5 valeurs en moyenne)
- 1 PUT pour associer tous les filtres au produit

**Total : ~15-20 requêtes API rien que pour les filtres par produit !**

Avec 9000 produits → **135,000-180,000 requêtes API** 😱

---

#### Optimisation 1.5.1 : Pré-chargement des filtres

**Fichier** : `wizi_import/wizi_import fast_try.py` lignes 437-497

```python
def preload_all_filters(self):
    """
    Phase 1.5 optimisation: Pré-charge tous les filtres et facets existants en mémoire
    """
    # Récupérer tous les filtres (1 requête)
    response = requests.get(f"{self.wizi_api.base_url}/product-filters/label", ...)

    # Pour chaque filtre, charger ses facets
    for filter_obj in existing_filters:
        filter_id = filter_obj.get('id')
        filter_label = filter_obj.get('label')

        # Ajouter au cache
        self.filters_cache[filter_label] = filter_id

        # Charger les facets de ce filtre
        facets_response = requests.get(
            f"{self.wizi_api.base_url}/product-filters/label/{filter_id}", ...
        )

        # Mettre en cache toutes les facets
        for facet in facets:
            cache_key = (filter_id, facet_value)
            self.facets_cache[cache_key] = facet_id
```

**Gain** : Cache complet en mémoire, aucune requête de vérification pendant l'import

---

#### Optimisation 1.5.2 : Scanner le CSV et créer en batch

**Fichier** : `wizi_import/wizi_import fast_try.py` lignes 1057-1133

```python
def prepare_filters_batch(csv_file, filter_manager):
    """
    Pré-charge et pré-crée tous les filtres/facets AVANT l'import des produits
    """
    # 1. Pré-charger les filtres existants
    filter_manager.preload_all_filters()

    # 2. Scanner le CSV pour identifier tous les filtres nécessaires
    df = pd.read_csv(csv_file)

    filter_columns = {
        "Marques compatibles": "Marque compatible",
        "Modèles compatibles": "Modèle compatible",
        "Cylindrées compatibles": "Cylindrée compatible",
        "Années compatibles": "Année compatible"
    }

    needed_filters = {}
    for col_name, filter_label in filter_columns.items():
        unique_values = set()
        for val in df[col_name].dropna():
            values = [v.strip() for v in str(val).split('|') if v.strip()]
            unique_values.update(values)
        needed_filters[filter_label] = sorted(unique_values)

    # 3. Créer les filtres/facets manquants
    filter_manager.create_missing_filters_batch(needed_filters)
```

**Gain** : Tous les filtres/facets créés une seule fois au début

---

#### Optimisation 1.5.3 : Association rapide (cache uniquement)

**Fichier** : `wizi_import/wizi_import fast_try.py` lignes 723-801

```python
def associate_filters_to_product_fast(self, product_id, filters_data):
    """
    Version rapide qui utilise UNIQUEMENT le cache pré-chargé
    AUCUNE requête de vérification/création - 1 seul PUT pour l'association
    """
    product_filters = []

    for col_name, filter_label in filter_columns.items():
        values = [v.strip() for v in str(values_str).split('|') if v.strip()]

        # Récupérer depuis le cache (PAS de création)
        filter_id = self.filters_cache.get(filter_label)

        # Récupérer les facet_ids depuis le cache (PAS de création)
        facet_values = []
        for value in values:
            cache_key = (filter_id, value)
            facet_id = self.facets_cache.get(cache_key)
            if facet_id:
                facet_values.append({"id": facet_id, "value": value, "position": 0})

        product_filters.append({"id": filter_id, "label": filter_label, "values": facet_values})

    # Association finale - SEULE requête API
    requests.put(f"{self.wizi_api.base_url}/products/{product_id}/filters", ...)
```

**Gain** : 1 seule requête PUT au lieu de 15-20 requêtes par produit

---

### 📊 Résultat Phase 1.5

**Avant** :
- 9000 produits × 15 requêtes filtres = **135,000 requêtes**
- Temps filtres : **plusieurs heures**

**Après** :
- Phase pré-import : ~500-1000 requêtes (création unique)
- Phase import : 9000 requêtes (1 PUT par produit)
- **Total : ~10,000 requêtes au lieu de 135,000**

**Gain estimé** : **~13x plus rapide sur la partie filtres**

**Combiné avec Phase 1** :
- 9000 produits : **2-3 heures** au lieu de 15+ heures
- 350 produits : **~5 minutes** au lieu de 35 minutes

**Effort** : 30 minutes de développement

**Statut** : ✅ **IMPLÉMENTÉ** dans `wizi_import fast_try.py`

---

### 🔥 Phase 2 : Async/Parallel (optionnel, 1-2h de dev)

Si Phase 1 n'est pas suffisante et que vous voulez aller encore plus vite...

#### Optimisation 2.1 : Connection Pooling

**Utiliser `requests.Session()`** pour réutiliser les connexions HTTP :

```python
class WiziShopAPI:
    def __init__(self, access_token, store_id, base_url=None):
        self.session = requests.Session()  # ← Réutilise les connexions
        self.session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        # ...

    def create_product(self, product_data):
        # AVANT : requests.post(url, headers=self.headers, json=product_data)
        # APRÈS : self.session.post(url, json=product_data)
        response = self.session.post(f"{self.base_url}/products", json=product_data)
        # ...
```

**Gain estimé** : **+50%** (connexions réutilisées)

---

#### Optimisation 2.2 : Import parallèle (ThreadPoolExecutor)

**Traiter 3-5 produits simultanément** :

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def import_products_parallel(df, wizi_api, category_mapper, filter_manager, max_workers=5):
    """Import products in parallel with ThreadPoolExecutor"""

    def import_single_product(row_data):
        """Function to import one product (thread-safe)"""
        i, row = row_data
        # ... existing product import logic from lines 857-1080 ...
        # Sans le time.sleep(1.2) global, juste un petit délai si besoin
        return i, success

    # Préparer les données
    rows = list(df.iterrows())

    # Import parallèle
    success_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Soumettre tous les produits
        futures = {executor.submit(import_single_product, row): row for row in rows}

        # Traiter les résultats au fur et à mesure
        for future in as_completed(futures):
            i, success = future.result()
            if success:
                success_count += 1
            print(f"Progress: {success_count}/{len(rows)}")

    return success_count
```

**Gain estimé** : **+3-5x** (3-5 produits en parallèle)

**Attention** :
- Nécessite des locks pour les opérations sur les caches partagés
- Tester d'abord avec `max_workers=3`, puis augmenter progressivement
- Surveiller les erreurs de rate-limiting

---

#### Optimisation 2.3 : Async avec httpx (avancé)

**Alternative encore plus performante** avec vraies coroutines async :

```python
import asyncio
import httpx

class WiziShopAPIAsync:
    def __init__(self, access_token, store_id):
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        self.base_url = f"https://api.wizishop.com/v3/shops/{store_id}"

    async def create_product(self, client, product_data):
        response = await client.post(
            f"{self.base_url}/products",
            headers=self.headers,
            json=product_data
        )
        return response

    async def import_products_batch(self, products, max_concurrent=5):
        async with httpx.AsyncClient(timeout=30.0) as client:
            semaphore = asyncio.Semaphore(max_concurrent)

            async def import_one(product_data):
                async with semaphore:  # Limite à 5 requêtes simultanées
                    return await self.create_product(client, product_data)

            tasks = [import_one(p) for p in products]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

# Utilisation :
async def main():
    api = WiziShopAPIAsync(token, store_id)
    results = await api.import_products_batch(products, max_concurrent=5)

asyncio.run(main())
```

**Gain estimé** : **+5-10x** (async non-bloquant)

**Effort** : 2-3h (refactoring complet)

---

### 📊 Résultat Phase 2

**Temps actuel** : 350 produits = 35 minutes

**Temps après Phase 1+2** : 350 produits = **3-6 minutes** 🚀

**Gain total** : **6-10x plus rapide**

**Effort** : 1-2h de développement

---

## Stratégie Recommandée

### Approche Progressive

1. **Commencer par Phase 1 (quick wins)** ✅
   - Effort : 15 minutes
   - Gain : 3-4x
   - Risque : Très faible
   - Tester sur boutique TEST

2. **Si besoin de plus de vitesse → Phase 2** 🔥
   - Effort : 1-2h
   - Gain : 6-10x total
   - Risque : Moyen (nécessite tests)
   - Commencer par ThreadPoolExecutor avant async complet

---

## Métriques de Référence

| Scénario | 350 produits | 9000 produits |
|---|---|---|
| **Actuel** | 35 min | ~15h |
| **Phase 1** | 10 min | ~4h |
| **Phase 1+1.5** ✅ | 5 min | **2-3h** |
| **Phase 1+1.5+2** | 3 min | ~1h |

---

## Emplacements de Code à Modifier

### Phase 1

| Fichier | Lignes | Modification |
|---|---|---|
| `wizi_import/wizi_import.py` | 1067 | Réduire sleep 1.2s → 0.3s |
| `wizi_import/wizi_import.py` | 95-129 | Ajouter index catégories |
| `wizi_import/wizi_import.py` | 131-153 | Utiliser index au lieu de loop |
| `wizi_import/wizi_import.py` | 200-202 | Ne pas invalider cache |
| `wizi_import/wizi_import.py` | Début de main | Pré-charger catégories |

### Phase 2

| Fichier | Lignes | Modification |
|---|---|---|
| `wizi_import/wizi_import.py` | 50-89 | Ajouter requests.Session() |
| `wizi_import/wizi_import.py` | 857-1080 | Refactor pour ThreadPoolExecutor |
| `wizi_import/wizi_import.py` | Nouveau | Créer import_products_parallel() |

---

## Notes Importantes

### Rate Limiting WiziShop

- **Limite inconnue** : tester progressivement
- Commencer avec sleep(0.3) sur TEST
- Surveiller les erreurs HTTP 429
- Si erreur 429 → ajouter exponential backoff :

```python
import time
from functools import wraps

def retry_on_rate_limit(max_retries=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                response = func(*args, **kwargs)
                if response.status_code == 429:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    print(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                return response
            return response
        return wrapper
    return decorator
```

### Thread Safety

Si vous implémentez Phase 2 (parallèle), protéger les caches partagés :

```python
from threading import Lock

class CategoryMapper:
    def __init__(self, ...):
        self.cache_lock = Lock()
        # ...

    def get_category_id(self, ...):
        with self.cache_lock:
            # ... accès au cache ...
```

### Monitoring

Ajouter des métriques pour suivre les performances :

```python
import time
from collections import defaultdict

class PerformanceMonitor:
    def __init__(self):
        self.timings = defaultdict(list)

    def measure(self, label):
        class Timer:
            def __enter__(timer_self):
                timer_self.start = time.time()
                return timer_self

            def __exit__(timer_self, *args):
                duration = time.time() - timer_self.start
                self.timings[label].append(duration)

        return Timer()

    def report(self):
        for label, times in self.timings.items():
            avg = sum(times) / len(times)
            total = sum(times)
            print(f"{label}: {avg:.2f}s avg, {total:.1f}s total ({len(times)} calls)")

# Usage:
monitor = PerformanceMonitor()

with monitor.measure("create_product"):
    response = wizi_api.create_product(payload)

with monitor.measure("associate_filters"):
    filter_manager.associate_filters(...)

# À la fin :
monitor.report()
```

---

## Checklist d'Implémentation

### Phase 1

- [ ] Réduire `time.sleep(1.2)` → `time.sleep(0.3)`
- [ ] Ajouter index des catégories dans `get_categories()`
- [ ] Modifier `find_category_by_name()` pour utiliser l'index
- [ ] Pré-charger les catégories au démarrage
- [ ] Ne plus invalider le cache après création de catégorie
- [ ] Tester sur boutique TEST avec 50 produits
- [ ] Mesurer le temps d'import (avant/après)
- [ ] Si pas d'erreur 429 → réduire encore le sleep

### Phase 2 (optionnel)

- [ ] Ajouter `requests.Session()` dans WiziShopAPI
- [ ] Refactorer import loop pour extraction de fonction
- [ ] Implémenter `import_products_parallel()` avec ThreadPoolExecutor
- [ ] Ajouter locks pour thread safety
- [ ] Tester avec `max_workers=3` puis augmenter
- [ ] Ajouter exponential backoff sur 429
- [ ] Mesurer le temps d'import
- [ ] Surveiller les erreurs

---

## Exemple Complet Phase 1

Voici les modifications exactes à faire pour Phase 1 :

### 1. Réduire le sleep

```python
# Ligne 1067
# AVANT
time.sleep(1.2)

# APRÈS
time.sleep(0.3)  # Ajuster selon les résultats de test
```

### 2. Améliorer le cache

```python
# Lignes 95-129
def get_categories(self):
    """Récupère la liste des catégories avec cache et index"""
    if self.categories_cache is not None:
        return self.categories_cache

    print("Chargement des catégories...")
    response = requests.get(f"{self.base_url}/categories", headers=self.headers)

    if response.status_code != 200:
        print(f"Erreur GET /categories: {response.status_code}")
        return []

    data = response.json()

    if isinstance(data, dict) and 'data' in data:
        self.categories_cache = data['data']
    elif isinstance(data, list):
        self.categories_cache = data
    else:
        self.categories_cache = []

    # NOUVEAU : Créer des index pour recherche rapide
    self.category_index = {
        'by_id': {},
        'by_name': {},
        'by_name_and_parent': {}
    }

    for cat in self.categories_cache:
        cat_id = cat.get('id')
        cat_name = cat.get('name', '').lower()
        parent_id = cat.get('parent_id')

        self.category_index['by_id'][cat_id] = cat
        self.category_index['by_name'][cat_name] = cat

        # Index par nom + parent pour sous-catégories
        key = (cat_name, parent_id)
        self.category_index['by_name_and_parent'][key] = cat

    print(f"✓ {len(self.categories_cache)} catégories chargées et indexées")

    return self.categories_cache
```

### 3. Recherche indexée

```python
# Lignes 131-153
def find_category_by_name(self, name, parent_id=None):
    """Cherche une catégorie par nom (avec index O(1) au lieu de O(n))"""
    if not hasattr(self, 'category_index'):
        self.get_categories()

    name_lower = name.lower().strip()

    # Recherche avec parent_id si fourni
    if parent_id is not None:
        key = (name_lower, parent_id)
        return self.category_index['by_name_and_parent'].get(key)

    # Recherche simple par nom
    return self.category_index['by_name'].get(name_lower)
```

### 4. Ne plus invalider le cache

```python
# Lignes 200-227
def create_category(self, name, parent_id=None):
    """Crée une nouvelle catégorie"""
    payload = {"name": name}
    if parent_id:
        payload["parent_id"] = parent_id

    print(f"Création catégorie : {name}" + (f" (parent: {parent_id})" if parent_id else ""))

    response = requests.post(
        f"{self.base_url}/categories",
        headers=self.headers,
        json=payload
    )

    if response.status_code in [200, 201]:
        response_data = response.json()
        new_category = response_data.get('data', response_data)

        # NOUVEAU : Ajouter au cache au lieu de l'invalider
        if self.categories_cache is not None:
            self.categories_cache.append(new_category)

            # Mettre à jour les index
            cat_id = new_category.get('id')
            cat_name = new_category.get('name', '').lower()
            parent = new_category.get('parent_id')

            self.category_index['by_id'][cat_id] = new_category
            self.category_index['by_name'][cat_name] = new_category
            self.category_index['by_name_and_parent'][(cat_name, parent)] = new_category

        print(f"✓ Catégorie créée (ID: {new_category.get('id')})")
        return new_category
    else:
        print(f"✗ Erreur création catégorie: {response.status_code}")
        print(response.text)
        return None
```

### 5. Pré-chargement au démarrage

```python
# Dans import_products(), après création de category_mapper
# Autour de la ligne 870
def import_products(csv_file, global_brand=None, env="test", limit=None, use_ai=False, ...):
    # ... existing code ...

    category_mapper = CategoryMapper(wizi_api, mapping_file=mapping_file)

    # NOUVEAU : Pré-charger les catégories
    print("\n" + "="*70)
    print("PRÉ-CHARGEMENT DES DONNÉES")
    print("="*70)
    category_mapper.get_categories()  # Force le chargement initial

    # ... rest of code ...
```

---

C'est tout pour Phase 1 ! Testez d'abord ces modifications avant de passer à Phase 2.
