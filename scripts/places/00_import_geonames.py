"""
Import GeoNames data into SQLite database for fast place name lookups.
Run with: uv run 00_import_geonames.py

This imports:
- CA.txt (Canada)
- US.txt (United States)
- alternateNamesV2.txt (alternate spellings and historical names)

Creates a SQLite database at: places/geonames/places.db

The database enables fast proximity-based searches for geocoding place names.
"""

import sqlite3
import csv
from pathlib import Path
from typing import Iterator
import sys

SCRIPT_DIR = Path(__file__).parent
GEONAMES_DIR = SCRIPT_DIR / "geonames"
DB_PATH = GEONAMES_DIR / "places.db"

# Regina, Saskatchewan coordinates for distance calculations
REGINA_LAT = 50.4452
REGINA_LON = -104.6189

# Feature codes we care about (populated places)
PLACE_FEATURES = {
    'PPL',    # populated place
    'PPLA',   # seat of a first-order administrative division
    'PPLA2',  # seat of a second-order administrative division
    'PPLA3',  # seat of a third-order administrative division
    'PPLA4',  # seat of a fourth-order administrative division
    'PPLC',   # capital of a political entity
    'PPLG',   # seat of government
    'PPLL',   # populated locality
    'PPLQ',   # abandoned populated place
    'PPLS',   # populated places
    'PPLX',   # section of populated place
}


def read_geonames_file(filepath: Path) -> Iterator[dict]:
    """Read a GeoNames .txt file and yield rows as dictionaries."""
    print(f"Reading {filepath.name}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if len(row) < 19:
                continue
            
            try:
                yield {
                    'geonameid': int(row[0]),
                    'name': row[1],
                    'asciiname': row[2],
                    'alternatenames': row[3],
                    'latitude': float(row[4]),
                    'longitude': float(row[5]),
                    'feature_class': row[6],
                    'feature_code': row[7],
                    'country_code': row[8],
                    'cc2': row[9],
                    'admin1_code': row[10],
                    'admin2_code': row[11],
                    'admin3_code': row[12],
                    'admin4_code': row[13],
                    'population': int(row[14]) if row[14] else 0,
                    'elevation': int(row[15]) if row[15] else None,
                    'dem': int(row[16]) if row[16] else None,
                    'timezone': row[17],
                    'modification_date': row[18],
                }
            except (ValueError, IndexError) as e:
                print(f"  Warning: Skipping invalid row: {e}")
                continue


def read_alternate_names(filepath: Path) -> Iterator[dict]:
    """Read alternateNamesV2.txt and yield alternate name records."""
    print(f"Reading {filepath.name}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if len(row) < 4:
                continue
            
            try:
                yield {
                    'alternateNameId': int(row[0]),
                    'geonameid': int(row[1]),
                    'isolanguage': row[2],
                    'alternate_name': row[3],
                    'isPreferredName': row[4] == '1' if len(row) > 4 else False,
                    'isShortName': row[5] == '1' if len(row) > 5 else False,
                    'isColloquial': row[6] == '1' if len(row) > 6 else False,
                    'isHistoric': row[7] == '1' if len(row) > 7 else False,
                }
            except (ValueError, IndexError):
                continue


def create_database():
    """Create SQLite database with optimized schema."""
    print(f"\nCreating database: {DB_PATH}")
    
    # Remove existing database
    if DB_PATH.exists():
        DB_PATH.unlink()
        print("  Removed existing database")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Main places table
    cursor.execute("""
        CREATE TABLE places (
            geonameid INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            asciiname TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            feature_class TEXT,
            feature_code TEXT,
            country_code TEXT,
            admin1_code TEXT,
            admin2_code TEXT,
            population INTEGER,
            elevation INTEGER,
            timezone TEXT
        )
    """)
    
    # Alternate names table
    cursor.execute("""
        CREATE TABLE alternate_names (
            alternateNameId INTEGER PRIMARY KEY,
            geonameid INTEGER NOT NULL,
            isolanguage TEXT,
            alternate_name TEXT NOT NULL,
            isPreferredName INTEGER,
            isHistoric INTEGER,
            FOREIGN KEY (geonameid) REFERENCES places(geonameid)
        )
    """)
    
    # Create indexes for fast lookups
    cursor.execute("CREATE INDEX idx_places_name ON places(name COLLATE NOCASE)")
    cursor.execute("CREATE INDEX idx_places_asciiname ON places(asciiname COLLATE NOCASE)")
    cursor.execute("CREATE INDEX idx_places_country ON places(country_code)")
    cursor.execute("CREATE INDEX idx_places_feature ON places(feature_code)")
    cursor.execute("CREATE INDEX idx_places_population ON places(population DESC)")
    cursor.execute("CREATE INDEX idx_alternate_name ON alternate_names(alternate_name COLLATE NOCASE)")
    cursor.execute("CREATE INDEX idx_alternate_geonameid ON alternate_names(geonameid)")
    
    conn.commit()
    print("  Database schema created")
    
    return conn


def import_places(conn: sqlite3.Connection):
    """Import places from CA.txt and US.txt."""
    cursor = conn.cursor()
    
    # Process Canada and US files
    for filename in ['CA.txt', 'US.txt']:
        filepath = GEONAMES_DIR / filename
        if not filepath.exists():
            print(f"  Warning: {filename} not found, skipping")
            continue
        
        count = 0
        batch = []
        
        for place in read_geonames_file(filepath):
            # Only import populated places
            if place['feature_code'] not in PLACE_FEATURES:
                continue
            
            batch.append((
                place['geonameid'],
                place['name'],
                place['asciiname'],
                place['latitude'],
                place['longitude'],
                place['feature_class'],
                place['feature_code'],
                place['country_code'],
                place['admin1_code'],
                place['admin2_code'],
                place['population'],
                place['elevation'],
                place['timezone'],
            ))
            
            count += 1
            
            # Insert in batches of 1000
            if len(batch) >= 1000:
                cursor.executemany("""
                    INSERT INTO places VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                conn.commit()
                batch = []
                print(f"  {filename}: Imported {count} places...", end='\r')
        
        # Insert remaining
        if batch:
            cursor.executemany("""
                INSERT INTO places VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
        
        print(f"  {filename}: Imported {count} places     ")


def import_alternate_names(conn: sqlite3.Connection):
    """Import alternate names for places in our database."""
    cursor = conn.cursor()
    
    # Get all geoname IDs we have in our places table
    cursor.execute("SELECT geonameid FROM places")
    valid_geonameids = set(row[0] for row in cursor.fetchall())
    print(f"\nFiltering alternate names for {len(valid_geonameids)} places...")
    
    filepath = GEONAMES_DIR / "alternateNamesV2.txt"
    if not filepath.exists():
        print(f"  Warning: alternateNamesV2.txt not found, skipping")
        return
    
    count = 0
    batch = []
    
    for alt_name in read_alternate_names(filepath):
        # Only import alternate names for places we have
        if alt_name['geonameid'] not in valid_geonameids:
            continue
        
        # Skip postal codes and airport codes
        lang = alt_name['isolanguage']
        if lang in ('post', 'iata', 'icao', 'faac', 'link', 'wkdt'):
            continue
        
        batch.append((
            alt_name['alternateNameId'],
            alt_name['geonameid'],
            alt_name['isolanguage'],
            alt_name['alternate_name'],
            1 if alt_name['isPreferredName'] else 0,
            1 if alt_name['isHistoric'] else 0,
        ))
        
        count += 1
        
        # Insert in batches of 5000
        if len(batch) >= 5000:
            cursor.executemany("""
                INSERT INTO alternate_names VALUES (?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            batch = []
            print(f"  Imported {count} alternate names...", end='\r')
    
    # Insert remaining
    if batch:
        cursor.executemany("""
            INSERT INTO alternate_names VALUES (?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
    
    print(f"  Imported {count} alternate names     ")


def create_admin_name_cache(conn: sqlite3.Connection):
    """Create a cache table for admin division names (provinces/states)."""
    cursor = conn.cursor()
    
    # Admin1 codes file
    admin1_file = GEONAMES_DIR / "admin1CodesASCII.txt"
    if not admin1_file.exists():
        print("  ⚠️  admin1CodesASCII.txt not found")
        print("  Province/state names will not be available")
        print("  Download from: https://download.geonames.org/export/dump/")
        # Still create empty table so queries don't fail
        cursor.execute("""
            CREATE TABLE admin1_names (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asciiname TEXT NOT NULL,
                geonameid INTEGER
            )
        """)
        conn.commit()
        return
    
    cursor.execute("""
        CREATE TABLE admin1_names (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            asciiname TEXT NOT NULL,
            geonameid INTEGER
        )
    """)
    
    print("\nImporting admin division names...")
    count = 0
    
    with open(admin1_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if len(row) < 4:
                continue
            
            cursor.execute("""
                INSERT INTO admin1_names VALUES (?, ?, ?, ?)
            """, (row[0], row[1], row[2], int(row[3]) if row[3] else None))
            count += 1
    
    conn.commit()
    print(f"  Imported {count} admin division names")


def main():
    print("=" * 60)
    print("GEONAMES DATABASE IMPORT")
    print("=" * 60)
    
    # Check for required files
    required_files = ['CA.txt', 'US.txt']
    missing = [f for f in required_files if not (GEONAMES_DIR / f).exists()]
    
    if missing:
        print("\n❌ Missing required files:")
        for f in missing:
            print(f"   - {f}")
        print("\nDownload from: https://download.geonames.org/export/dump/")
        print("Place in: scripts/places/geonames/")
        sys.exit(1)
    
    # Create database
    conn = create_database()
    
    # Import data
    print("\nImporting places...")
    import_places(conn)
    
    print("\nImporting alternate names...")
    import_alternate_names(conn)
    
    print("\nImporting admin division names...")
    create_admin_name_cache(conn)
    
    # Show statistics
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM places")
    place_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM alternate_names")
    alt_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM places WHERE country_code = 'CA'")
    ca_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM places WHERE country_code = 'US'")
    us_count = cursor.fetchone()[0]
    
    print("\n" + "=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Total places: {place_count:,}")
    print(f"  Canada: {ca_count:,}")
    print(f"  United States: {us_count:,}")
    print(f"Alternate names: {alt_count:,}")
    print(f"\nDatabase: {DB_PATH}")
    print(f"Size: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    
    conn.close()


if __name__ == "__main__":
    main()
