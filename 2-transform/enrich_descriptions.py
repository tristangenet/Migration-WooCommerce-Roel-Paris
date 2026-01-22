import pandas as pd
import re
from pathlib import Path

def clean_text(text):
    """Remove HTML tags and extra whitespace from text."""
    if not isinstance(text, str):
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_notes_type(notes_str):
    """Extract the type of notes (Tête, Coeur, Fond) if available."""
    if not isinstance(notes_str, str) or not notes_str.strip():
        return "olfactives"
    return "olfactives"

def generate_description(row):
    """Generate a synthetic description for a product."""
    product_name = str(row.get('Nom du produit', '')).strip()
    brand = str(row.get('Marque', '')).strip()
    olfactory_notes = str(row.get('Notes olfactives', '')).strip()
    category = str(row.get('Catégorie secondaire', '')).strip()

    # If category is "Uncategorized", try to use primary category
    if category in ['', 'Uncategorized', 'nan', None]:
        category = str(row.get('Catégorie principale', '')).strip()
    if category in ['', 'Uncategorized', 'nan', None]:
        category = "parfum"

    # Build the description
    description_parts = []

    # First sentence: Product name and category/brand
    if brand and brand.lower() not in ['nan', '', 'none']:
        first_sentence = f"Parfum {category.lower()} de la maison {brand}."
    else:
        first_sentence = f"Parfum {category.lower()}."
    description_parts.append(first_sentence)

    # Second sentence: Olfactory notes if available
    if olfactory_notes and olfactory_notes.lower() not in ['nan', '', 'none']:
        # Clean up the notes
        notes = olfactory_notes.split(',')
        notes_list = [note.strip() for note in notes if note.strip()]

        if notes_list:
            if len(notes_list) == 1:
                notes_text = notes_list[0]
                second_sentence = f"Accord {category.lower()} caractérisé par des notes de {notes_text}."
            else:
                # Create a more natural description
                if len(notes_list) == 2:
                    notes_formatted = f"{notes_list[0]} et {notes_list[1]}"
                else:
                    notes_formatted = ", ".join(notes_list[:-1]) + f" et {notes_list[-1]}"
                second_sentence = f"Accord {category.lower()} subtil associant des notes de {notes_formatted}."
            description_parts.append(second_sentence)

    # Third sentence: Catchy ending (adaptable based on category)
    if category.lower() in ['ambré', 'ambre']:
        third_sentence = "Une fragrance enveloppante et sophistiquée."
    elif category.lower() in ['fleuri', 'floral']:
        third_sentence = "Une fragrance florale et élégante."
    elif category.lower() in ['gourmand']:
        third_sentence = "Une fragrance gourmande et irrésistible."
    elif category.lower() in ['frais', 'frais citronné']:
        third_sentence = "Une fragrance fraîche et vivifiante."
    else:
        third_sentence = "Une fragrance unique et captivante."

    description_parts.append(third_sentence)

    return " ".join(description_parts)

def is_description_empty_or_short(description):
    """Check if description is empty or shorter than 50 characters."""
    if not isinstance(description, str):
        return True
    cleaned = clean_text(description)
    return len(cleaned) < 50

def enrich_csv(input_file, output_file=None):
    """Enrich CSV with synthetic descriptions."""
    # Default output file if not specified
    if output_file is None:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_enrichi{input_path.suffix}"

    print(f"Lecture du fichier: {input_file}")

    # Read CSV
    df = pd.read_csv(input_file, encoding='utf-8-sig')

    print(f"Total de produits: {len(df)}")

    # Track statistics
    empty_descriptions = 0
    short_descriptions = 0
    enriched_count = 0

    # Process each row
    for idx, row in df.iterrows():
        description = df.at[idx, 'Description']

        if is_description_empty_or_short(description):
            if not isinstance(description, str) or len(str(description).strip()) == 0:
                empty_descriptions += 1
            else:
                short_descriptions += 1

            # Generate new description
            new_description = generate_description(row)
            df.at[idx, 'Description'] = new_description
            enriched_count += 1

            # Print progress for enriched products
            product_name = row.get('Nom du produit', 'Unknown')
            print(f"  [{idx+1}] Enrichi: {product_name}")

    print(f"\nStatistiques d'enrichissement:")
    print(f"  - Descriptions vides: {empty_descriptions}")
    print(f"  - Descriptions courtes (<50 car): {short_descriptions}")
    print(f"  - Total enrichi: {enriched_count}")
    print(f"  - Descriptions conservées: {len(df) - enriched_count}")

    # Save the enriched CSV
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\nFichier sauvegardé: {output_file}")

    return output_file

if __name__ == "__main__":
    input_csv = r"c:\Users\Loic Blanc\Documents\dev\woo_migration\3-load\input\woocommerce_converted_with_filters.csv"
    output_csv = r"c:\Users\Loic Blanc\Documents\dev\woo_migration\3-load\input\woocommerce_converted_with_filters_enrichi.csv"

    enrich_csv(input_csv, output_csv)
