# Place Name Extraction

This folder contains scripts for extracting and geocoding place names from the LHA Memoirs transcripts.

## Overview

The scripts scan through all transcript files, identify place names, geocode them using GeoNames data, and validate them using an LLM for context awareness. The output includes GeoJSON and JSON files suitable for mapping and analysis.

## Prerequisites

1. **GeoNames Data Files**: Download the following files from [GeoNames](https://download.geonames.org/export/dump/) and place them in `geonames/`:
   - `CA.txt` - All Canadian places
   - `US.txt` - All US places
   - `alternateNamesV2.txt` - Alternate spellings and historical names
   - `admin1CodesASCII.txt` - Province/state names

2. **Python Packages**:

   ```bash
   uv pip install ollama tqdm
   ```

3. **Ollama**: Running locally with `gemma3:12b` model:
   ```bash
   ollama serve
   ollama pull gemma3:12b
   ```

## Usage

### Step 1: Import GeoNames Data

First, import the GeoNames data into a SQLite database for fast queries:

```bash
uv run 00_import_geonames.py
```

This creates `geonames/places.db` (~100-200 MB) with indexed place data for Canada and the US.

**Expected time**: 2-5 minutes depending on disk speed

### Step 2: Extract Place Names

Scan all transcripts and extract place names:

```bash
# Standard mode (automatic)
uv run 01_find_placenames.py

# Interactive mode (prompt for uncertain matches)
uv run 01_find_placenames.py --interactive

# Re-validate previously found places
uv run 01_find_placenames.py --revalidate
```

**Expected time**: 20-45 minutes for ~80,000 words (depends on GPU speed for LLM)

## How It Works

### 1. Capitalized Word Extraction

The script scans transcripts for capitalized words, filtering out:

- Common English words (articles, pronouns, etc.)
- Months and days of the week
- Common proper nouns (God, Christmas, etc.)

### 2. Database Matching

For each capitalized word:

1. Search for exact matches in place names and alternate names
2. Search for partial matches (starts with)
3. Rank candidates by:
   - Distance from Regina, Saskatchewan (reference point)
   - Population (larger cities ranked higher)
   - Match quality (exact > starts with > contains)

### 3. LLM Validation

Each potential match is validated by an LLM that:

- Analyzes the context (full sentence)
- Determines if the word is actually a place name
- Selects the most appropriate candidate
- Assigns confidence level (high/medium/low)

Example prompts:

- ✅ "moved to Moose Jaw" → Place name
- ✅ "lived in Regina" → Place name
- ❌ "his name was Frank" → Not a place
- ❌ "Uncle Bob" → Not a place

### 4. Confidence Scoring

Places are assigned confidence levels:

- **High**: Within 100km of Regina AND population > 1,000
- **Medium**: Within 500km OR population > 5,000
- **Low**: Other cases

## Output Files

All output is saved to `output/`:

### `places.json`

Detailed JSON with all place information:

```json
{
  "metadata": {
    "total_places": 145,
    "reference_point": {
      "name": "Regina, Saskatchewan",
      "latitude": 50.4452,
      "longitude": -104.6189
    }
  },
  "places": [
    {
      "name": "Moose Jaw",
      "geonameid": 6076211,
      "latitude": 50.39339,
      "longitude": -105.53445,
      "country_code": "CA",
      "admin1_name": "Saskatchewan",
      "population": 33274,
      "feature_code": "PPL",
      "distance_from_regina_km": 71.2,
      "confidence": "high",
      "mentions": [
        {
          "recording": "memoirs/HF_60",
          "context": "We moved to Moose Jaw in 1924...",
          "timestamp": 1234.5
        }
      ]
    }
  ]
}
```

### `places.geojson`

GeoJSON FeatureCollection for mapping:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [-105.53445, 50.39339]
      },
      "properties": {
        "name": "Moose Jaw",
        "geonameid": 6076211,
        "country": "CA",
        "admin1": "Saskatchewan",
        "population": 33274,
        "confidence": "high",
        "mention_count": 5,
        "distance_from_regina_km": 71.2
      }
    }
  ]
}
```

### `ignored_words.json`

Words marked as non-places (either by LLM or user):

```json
{
  "ignored": ["Frank", "Bob", "Alice", "Brown"]
}
```

### `review_queue.json`

Capitalized words that need manual review:

```json
{
  "Mistatim": {
    "occurrences": [
      {
        "recording": "memoirs/HF_60",
        "context": "near the Mistatim creek",
        "timestamp": 2345.6
      }
    ],
    "status": "needs_review"
  }
}
```

## Interactive Mode

In interactive mode (`--interactive`), the script will prompt you when it's uncertain:

```
🤔 Uncertain about: Brownlee
   Context: We lived near Brownlee for a few years
   Candidates: 3
     1. Brownlee, Saskatchewan, CA
     2. Brownlee, Texas, US
     3. Brownlee, Nebraska, US
   Is this a place? (y/n/s=skip): y
```

- `y` - Yes, use the first candidate
- `n` - No, add to ignored words
- `s` - Skip, add to review queue

## Review Process

1. Run the script in standard mode
2. Check `review_queue.json` for unmatched capitalized words
3. For misspellings:
   - Correct the transcript using the LLM context
   - Re-run the script
4. For valid place names not in database:
   - Manually add coordinates to output files
   - Or add to the database directly

## Performance

- **Database queries**: <1ms per lookup (SQLite with indexes)
- **LLM validation**: ~1-2 seconds per word (GPU-dependent)
- **Total time**: ~30 minutes for 80,000 words with ~500 unique capitalized words

## Tips

- The LLM is conservative - it will reject ambiguous cases
- Places closer to Regina are favored for disambiguation
- US places are often stated with state (e.g., "Minot, North Dakota")
- Canadian places often lack province/state context
- Run in standard mode first, then review the queue interactively

## Example Output

For a corpus of 80,000 words, you might find:

- ~150-250 unique places
- ~500-1000 total mentions
- 60-70% in Saskatchewan
- 15-20% in other Canadian provinces
- 10-15% in US states (primarily North Dakota, Iowa)

## Troubleshooting

**"Database not found"**

- Run `00_import_geonames.py` first

**"Cannot connect to Ollama"**

- Start Ollama: `ollama serve`
- Pull model: `ollama pull gemma3:12b`

**"Missing required files"**

- Download GeoNames .txt files to `geonames/` folder

**Too many false positives**

- Increase temperature in LLM calls (line ~300)
- Add more stop words to `extract_capitalized_words()`

**Too many false negatives**

- Decrease temperature in LLM calls
- Lower confidence threshold requirements
