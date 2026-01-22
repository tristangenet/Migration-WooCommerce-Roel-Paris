#!/usr/bin/env python3
"""Test rapide de connexion à l'API WiziShop"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('WIZI_ACCESS_TOKEN')
STORE_ID = os.getenv('WIZI_STORE_ID')

print("="*60)
print("TEST DE CONNEXION API WIZISHOP")
print("="*60)

if not TOKEN or not STORE_ID:
    print("❌ Variables d'environnement manquantes dans .env")
    exit(1)

print(f"✅ Token trouvé: {TOKEN[:20]}...")
print(f"✅ Store ID: {STORE_ID}")

url = f"https://api.wizishop.com/v3/shops/{STORE_ID}/categories"
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

print(f"\n🌐 Test GET {url}")
print("⏳ Requête en cours (timeout 10s)...\n")

try:
    response = requests.get(url, headers=headers, timeout=10)

    print(f"✅ Réponse reçue!")
    print(f"   Status: {response.status_code}")
    print(f"   Temps: {response.elapsed.total_seconds():.2f}s")

    if response.status_code == 200:
        data = response.json()
        results = data.get('results', [])
        print(f"   Catégories: {len(results)} trouvées")
        print("\n✅ API FONCTIONNE CORRECTEMENT")
    elif response.status_code == 401:
        print("\n❌ ERREUR 401: Token expiré ou invalide")
        print("   → Régénère un nouveau token dans WiziShop")
    elif response.status_code == 403:
        print("\n❌ ERREUR 403: Accès refusé")
        print("   → Vérifie les permissions du token")
    elif response.status_code == 404:
        print("\n❌ ERREUR 404: Store ID incorrect")
        print("   → Vérifie WIZI_STORE_ID dans .env")
    else:
        print(f"\n❌ ERREUR {response.status_code}")
        print(f"   Réponse: {response.text[:200]}")

except requests.exceptions.Timeout:
    print("\n❌ TIMEOUT après 10 secondes")
    print("   → L'API WiziShop ne répond pas")
    print("   → Vérifie ta connexion internet")
    print("   → Ou l'API est peut-être down")

except requests.exceptions.ConnectionError as e:
    print(f"\n❌ ERREUR DE CONNEXION")
    print(f"   {e}")
    print("   → Vérifie ta connexion internet")
    print("   → Vérifie que tu peux accéder à api.wizishop.com")

except Exception as e:
    print(f"\n❌ ERREUR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
