# 3-Load - Import WiziShop

Cette etape charge les produits transformes vers l'API WiziShop.

## Script principal

Le script `wizi_import_fasttry.py` n'est pas inclus dans ce repo public.

**Disponible sur demande** : contactez le proprietaire du repo.

## Fonctionnalites du script

- Import parallele (1-5 threads configurable)
- Pre-creation des categories (evite les race conditions)
- Gestion des variations/declinaisons avec prix et stocks
- Association automatique des filtres (notes olfactives)
- Retry automatique avec backoff exponentiel
- Logs JSON detailles

## Utilisation

```bash
# Placer votre script dans ce dossier puis :
python wizi_import_fasttry.py --csv fichier.csv --limit 10
```

## Fichiers

- `input/` : CSV a importer
- `output/` : Logs JSON de l'import
- `filter_manager.py` : Gestion des filtres WiziShop (inclus)
