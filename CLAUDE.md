# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ETL pipeline for migrating product catalogs from WooCommerce (RoelParis.com) to WiziShop e-commerce platform. Handles 329+ products with variations, categories, images, and olfactory note filters.

## Project Structure (ETL)

```
woo_migration/
├── 1-extract/                      # Stage 1: Extraction from WooCommerce
│   └── woocommerce_to_wizi.py      # Main converter
│
├── 2-transform/                    # Stage 2: Data transformation
│   ├── add_notes_filters.py        # Add olfactory notes columns
│   └── convert_img/                # Image conversion (with input/output)
│       ├── convert_img.py          # Convert images from processed CSV
│       └── convert_woocommerce_webp.py  # WebP to PNG via FTP
│
├── 3-load/                         # Stage 3: Load to WiziShop API
│   ├── wizi_import.py              # Main import (with filters)
│   ├── wizi_import_fasttry.py      # Parallel import (Phase 2)
│   ├── filter_manager.py           # Filter/facet API management
│   ├── feature_manager.py          # Product features API
│   ├── input/                      # CSV files for import
│   │   ├── woocommerce_converted_with_filters.csv
│   │   └── filtres_wizishop.csv
│   └── output/                     # Import logs (JSON)
│
├── data/
│   ├── api/                        # WiziShop API examples
│   └── doc/                        # Documentation
│
├── tests/                          # Test scripts
├── legacy/                         # Old versions and archived files
├── export_webtoffe_woocommerce.csv # Source CSV (WooCommerce export)
└── .env                            # Configuration
```

## ETL Pipeline

```
1-Extract: woocommerce_to_wizi.py
├─ Input:  export_webtoffe_woocommerce.csv (root)
├─ Process: Parse → Flatten variations → Normalize categories
└─ Output: 3-load/input/woocommerce_converted_*.csv

2-Transform: add_notes_filters.py
├─ Input:  3-load/input/woocommerce_converted_*.csv
├─ Process: Classify olfactory notes (Tête/Cœur/Fond)
└─ Output: 3-load/input/woocommerce_converted_with_filters.csv

3-Load: wizi_import.py
├─ Input:  3-load/input/woocommerce_converted_with_filters.csv
├─ Process: API calls → Categories → Products → Filters
└─ Output: Products in WiziShop + 3-load/output/*.json logs
```

## Common Development Commands

### Stage 1: Extract

```bash
cd 1-extract
python woocommerce_to_wizi.py
# Output: 3-load/input/woocommerce_converted_*.csv
```

### Stage 2: Transform

```bash
cd 2-transform
python add_notes_filters.py
# Adds 6 columns: tete_wizi, tete_export, coeur_wizi, coeur_export, fond_wizi, fond_export
# Output: 3-load/input/woocommerce_converted_with_filters.csv
```

### Stage 3: Load

```bash
cd 3-load

# Test import (10 products)
python wizi_import.py --csv woocommerce_converted_with_filters.csv --limit 10

# Full import
python wizi_import.py --csv woocommerce_converted_with_filters.csv

# With CLI credentials (non-interactive)
python wizi_import.py --token YOUR_TOKEN --store YOUR_STORE_ID --csv woocommerce_converted_with_filters.csv
```

## Critical WiziShop API Constraints

1. **2-Level Category Hierarchy Only**
   - WooCommerce: `Parfums > Familles Olfactives > Ambré` (3 levels)
   - WiziShop: `Familles Olfactives > Ambré` (2 levels max)

2. **No Products in Parent Categories**
   - Products MUST be assigned to leaf categories only

3. **Variations Format**
   - Single row with attributes: `Attribut 1 Valeur 1`, `Attribut 1 Prix 1`, etc.
   - Max 7 variations per attribute

## Olfactory Notes Filters

The pipeline handles olfactory notes (Tête/Cœur/Fond) as WiziShop product filters:

1. **add_notes_filters.py** classifies notes from `Notes olfactives` column
2. Creates 6 columns:
   - `tete_wizi`, `coeur_wizi`, `fond_wizi` (existing on WiziShop)
   - `tete_export`, `coeur_export`, `fond_export` (to create)
3. **wizi_import.py** associates filters via FilterManager after product creation

## Environment Configuration

Create `.env` at project root:
```env
WIZI_ACCESS_TOKEN=eyJ0eXAiOiJKV1Q...
WIZI_STORE_ID=411081
OPENAI_API_KEY=sk-proj-...  # Optional for AI features
```

## Debugging Import Errors

Logs in `3-load/output/wizi_products_log_*.json`:

```json
{
  "_csv_line": 42,
  "_product_name": "UDEN",
  "_api_status_code": 400,
  "_api_response": {"message": "Error details"}
}
```

## Key Files

| File | Purpose |
|------|---------|
| `1-extract/woocommerce_to_wizi.py` | WooCommerce → WiziShop CSV conversion |
| `2-transform/add_notes_filters.py` | Add olfactory note columns |
| `2-transform/convert_img/convert_woocommerce_webp.py` | WebP to PNG conversion via FTP |
| `3-load/wizi_import_fasttry.py` | Parallel import (private, on request) |
| `3-load/filter_manager.py` | Filter/facet API management |
| `3-load/input/filtres_wizishop.csv` | Reference of existing WiziShop filters |
