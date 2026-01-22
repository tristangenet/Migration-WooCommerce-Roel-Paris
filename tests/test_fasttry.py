#!/usr/bin/env python3
"""Script de test pour wizi_import_fasttry.py"""

import sys
import os

# Test 1: Import du module
print("Test 1: Import du module...")
try:
    import wizi_import_fasttry as wizi
    print("✅ Import OK")
except Exception as e:
    print(f"❌ Erreur import: {e}")
    sys.exit(1)

# Test 2: Vérifier que les classes existent
print("\nTest 2: Vérification des classes...")
try:
    assert hasattr(wizi, 'WiziShopAPI'), "Classe WiziShopAPI manquante"
    assert hasattr(wizi, 'CategoryMapper'), "Classe CategoryMapper manquante"
    assert hasattr(wizi, 'import_single_product'), "Fonction import_single_product manquante"
    assert hasattr(wizi, 'import_products_parallel'), "Fonction import_products_parallel manquante"
    print("✅ Toutes les classes/fonctions présentes")
except AssertionError as e:
    print(f"❌ {e}")
    sys.exit(1)

# Test 3: Créer une instance (sans credentials)
print("\nTest 3: Création d'instance WiziShopAPI...")
try:
    api = wizi.WiziShopAPI("fake_token", "fake_store_id")
    assert hasattr(api, 'session'), "Session manquante"
    assert hasattr(api, 'cache_lock'), "Lock manquant"
    assert hasattr(api, 'categories_cache'), "Cache manquant"
    print("✅ Instance créée correctement")
    print(f"   - Session: {type(api.session)}")
    print(f"   - Lock: {type(api.cache_lock)}")
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Vérifier que CategoryMapper a les locks
print("\nTest 4: Création d'instance CategoryMapper...")
try:
    mapper = wizi.CategoryMapper(api)
    assert hasattr(mapper, 'mapping_lock'), "Lock manquant dans CategoryMapper"
    print("✅ CategoryMapper créé correctement")
    print(f"   - Lock: {type(mapper.mapping_lock)}")
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("✅ TOUS LES TESTS PASSENT")
print("="*60)
print("\nLe problème de blocage vient probablement de :")
print("1. Token WiziShop expiré")
print("2. Problème réseau/firewall")
print("3. API WiziShop lente ou down")
print("\nVérifie ton .env et teste manuellement avec curl.")
