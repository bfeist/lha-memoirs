"""
Add an individual place to places.json using the same distance from Regina logic.

Usage:
  uv run 01a_add_individual_place.py <place_name> [--dry-run]

Examples:
  uv run 01a_add_individual_place.py Dinsmore
  uv run 01a_add_individual_place.py "Moose Jaw"
  uv run 01a_add_individual_place.py "Dinsmore" --dry-run
"""

import sqlite3
import json
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Dict
from math import radians, cos, sin, asin, sqrt
from dataclasses import dataclass, asdict
from datetime import datetime

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
GEONAMES_DIR = SCRIPT_DIR / "geonames"
DB_PATH = GEONAMES_DIR / "places.db"
GLOBAL_PLACES_FILE = PROJECT_ROOT / "public" / "places.json"

# Regina, Saskatchewan coordinates (reference point)
REGINA_LAT = 50.4452
REGINA_LON = -104.6189


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points on Earth in kilometers."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Earth radius in kilometers
    return c * r


def check_database():
    """Check if the GeoNames database exists."""
    if not DB_PATH.exists():
        print(f"\n❌ Database not found: {DB_PATH}")
        print("\nPlease run: uv run 00_import_geonames.py")
        sys.exit(1)
    print(f"[OK] Database found: {DB_PATH}")


def get_admin1_name(conn: sqlite3.Connection, country_code: str, admin1_code: str) -> Optional[str]:
    """Get the name of an admin1 division (province/state)."""
    cursor = conn.cursor()
    code = f"{country_code}.{admin1_code}"
    try:
        cursor.execute("SELECT name FROM admin1_names WHERE code = ?", (code,))
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def find_place_candidates(conn: sqlite3.Connection, name: str, limit: int = 20) -> List[Dict]:
    """Find potential place matches from the database."""
    cursor = conn.cursor()
    
    print(f"\n[SEARCH] Looking up: '{name}'")
    
    # Check if this is "City, State" format
    if ', ' in name:
        print(f"  → Detected 'City, State' format")
        parts = name.split(', ')
        if len(parts) == 2:
            city_name, state_name = parts
            # Use 2-letter codes for US states and numeric codes for Canadian provinces
            us_state_codes = {
                'Iowa': 'IA', 'North Dakota': 'ND', 'South Dakota': 'SD', 
                'Minnesota': 'MN', 'Montana': 'MT', 'Nebraska': 'NE', 
                'Kansas': 'KS', 'California': 'CA', 'Texas': 'TX',
                'Washington': 'WA', 'Oregon': 'OR', 'Arizona': 'AZ',
            }
            ca_province_codes = {
                'Saskatchewan': '11', 'Alberta': '01', 'Manitoba': '03',
                'Ontario': '08', 'British Columbia': '02',
            }
            
            admin1_code = us_state_codes.get(state_name) or ca_province_codes.get(state_name)
            if admin1_code:
                country = 'US' if state_name in us_state_codes else 'CA'
                print(f"  → City: '{city_name}', State: '{state_name}' ({country}/{admin1_code})")
                cursor.execute("""
                    SELECT p.geonameid, p.name, p.asciiname, p.latitude, p.longitude,
                           p.country_code, p.admin1_code, p.population, p.feature_code
                    FROM places p
                    WHERE (p.name = ? COLLATE NOCASE OR p.asciiname = ? COLLATE NOCASE)
                      AND p.country_code = ?
                      AND p.admin1_code = ?
                    ORDER BY CASE WHEN p.name = ? COLLATE NOCASE THEN 0 ELSE 1 END, p.population DESC
                    LIMIT ?
                """, (city_name, city_name, country, admin1_code, city_name, limit))
                results = cursor.fetchall()
                if results:
                    print(f"  → Found {len(results)} exact match(es)")
                    return _process_candidates(conn, results)
    
    # Regular search
    candidates = []
    
    # Exact match on main name
    print(f"  → Searching main place names...")
    cursor.execute("""
        SELECT p.geonameid, p.name, p.asciiname, p.latitude, p.longitude,
               p.country_code, p.admin1_code, p.population, p.feature_code
        FROM places p
        WHERE p.name = ? COLLATE NOCASE OR p.asciiname = ? COLLATE NOCASE
        ORDER BY CASE WHEN p.name = ? COLLATE NOCASE THEN 0 ELSE 1 END
        LIMIT ?
    """, (name, name, name, limit))
    candidates.extend(cursor.fetchall())
    print(f"  → Main name search: {len(candidates)} match(es)")
    
    # Exact match on alternate names
    if len(candidates) < limit:
        print(f"  → Searching alternate names...")
        cursor.execute("""
            SELECT DISTINCT p.geonameid, p.name, p.asciiname, p.latitude, p.longitude,
                   p.country_code, p.admin1_code, p.population, p.feature_code
            FROM places p
            JOIN alternate_names a ON p.geonameid = a.geonameid
            WHERE a.alternate_name = ? COLLATE NOCASE
            LIMIT ?
        """, (name, limit - len(candidates)))
        alt_results = cursor.fetchall()
        candidates.extend(alt_results)
        print(f"  → Alternate name search: {len(alt_results)} match(es)")
    
    return _process_candidates(conn, candidates)


def _process_candidates(conn: sqlite3.Connection, candidates: List) -> List[Dict]:
    """Process raw database results into candidate dicts."""
    results = []
    seen_ids = set()
    
    # Expected regions - places here should be prioritized
    expected_us_states = {'IA', 'ND', 'SD', 'MN', 'MT', 'NE', 'KS'}
    expected_ca_provinces = {'11', '01', '03', '02', '08'}  # SK, AB, MB, BC, ON
    
    for row in candidates:
        if row[0] in seen_ids:
            continue
        seen_ids.add(row[0])
        
        distance = haversine_distance(REGINA_LAT, REGINA_LON, row[3], row[4])
        admin1_name = get_admin1_name(conn, row[5], row[6])
        
        # Calculate a priority score - lower is better
        # Places in expected regions get priority bonus
        country = row[5]
        admin1_code = row[6]
        in_expected_region = (
            (country == 'US' and admin1_code in expected_us_states) or
            (country == 'CA' and admin1_code in expected_ca_provinces)
        )
        
        # Priority: expected region + close distance + population
        priority = distance
        if in_expected_region:
            priority = priority * 0.3  # Heavily favor expected regions
        if row[7] > 1000:  # Population
            priority = priority * 0.8  # Favor larger places
        
        results.append({
            'geonameid': row[0],
            'name': row[1],
            'asciiname': row[2],
            'latitude': row[3],
            'longitude': row[4],
            'country_code': row[5],
            'admin1_code': row[6],
            'admin1_name': admin1_name,
            'population': row[7],
            'feature_code': row[8],
            'distance_km': distance,
            'priority': priority,
            'in_expected_region': in_expected_region,
        })
    
    # Sort by priority (lower is better)
    results.sort(key=lambda x: x['priority'])
    return results[:20]


def select_best_candidate(candidates: List[Dict]) -> Optional[Dict]:
    """Select the best candidate from the list, preferring nearby places in expected regions."""
    if not candidates:
        return None
    
    print(f"\n[CANDIDATES] Found {len(candidates)} potential match(es):")
    for i, cand in enumerate(candidates[:5], 1):  # Show top 5
        region = f"{cand['admin1_name']}, {cand['country_code']}" if cand['admin1_name'] else cand['country_code']
        distance = cand['distance_km']
        pop = f" (pop: {cand['population']})" if cand['population'] > 0 else ""
        expected = " ✓ EXPECTED" if cand['in_expected_region'] else ""
        print(f"  {i}. {cand['name']:30s} - {region:20s} {distance:8.1f} km away{pop}{expected}")
    
    if len(candidates) > 5:
        print(f"  ... and {len(candidates) - 5} more")
    
    # Automatically select the top candidate
    best = candidates[0]
    print(f"\n[SELECTED] Using top candidate: {best['name']}")
    return best


def load_places_json() -> Dict:
    """Load the existing places.json file."""
    if GLOBAL_PLACES_FILE.exists():
        print(f"[LOAD] Loading existing places.json...")
        with open(GLOBAL_PLACES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        print(f"[NEW] Creating new places.json...")
        return {
            "metadata": {
                "total_places": 0,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "reference_point": {
                    "name": "Regina, Saskatchewan",
                    "latitude": REGINA_LAT,
                    "longitude": REGINA_LON
                }
            },
            "places": []
        }


def place_exists(places_data: Dict, geonameid: int) -> bool:
    """Check if a place with this geonameid already exists in places.json."""
    for place in places_data['places']:
        if place['geonameid'] == geonameid:
            return True
    return False


def add_place_to_json(places_data: Dict, candidate: Dict) -> Dict:
    """Create a new place entry to add to places.json."""
    new_place = {
        "name": candidate['name'],
        "geonameid": candidate['geonameid'],
        "latitude": candidate['latitude'],
        "longitude": candidate['longitude'],
        "country_code": candidate['country_code'],
        "admin1_name": candidate['admin1_name'],
        "population": candidate['population'],
        "feature_code": candidate['feature_code'],
        "distance_from_regina_km": candidate['distance_km'],
        "confidence": "user_added",
        "needs_review": False,
        "mentions": []  # No mentions for manually added places
    }
    return new_place


def save_places_json(places_data: Dict, dry_run: bool = False):
    """Save places.json, updating metadata."""
    places_data['metadata']['total_places'] = len(places_data['places'])
    places_data['metadata']['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if dry_run:
        print(f"\n[DRY-RUN] Would save {len(places_data['places'])} total places to {GLOBAL_PLACES_FILE}")
        print(f"[DRY-RUN] New metadata: {json.dumps(places_data['metadata'], indent=2)}")
    else:
        with open(GLOBAL_PLACES_FILE, 'w', encoding='utf-8') as f:
            json.dump(places_data, f, indent=2, ensure_ascii=False)
        print(f"\n[SAVED] Updated {GLOBAL_PLACES_FILE}")
        print(f"  → Total places: {places_data['metadata']['total_places']}")
        print(f"  → Last updated: {places_data['metadata']['last_updated']}")


def main():
    parser = argparse.ArgumentParser(
        description="Add an individual place to places.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run 01a_add_individual_place.py Dinsmore
  uv run 01a_add_individual_place.py "Moose Jaw"
  uv run 01a_add_individual_place.py "Dinsmore" --dry-run
        """
    )
    parser.add_argument('place_name', help='Name of the place to add')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ADD INDIVIDUAL PLACE")
    print("=" * 80)
    
    if args.dry_run:
        print("[MODE] DRY-RUN (no changes will be made)")
    
    # Check database exists
    check_database()
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Search for place
        candidates = find_place_candidates(conn, args.place_name)
        
        if not candidates:
            print(f"\n❌ No places found matching '{args.place_name}'")
            print("   Try a different name or check the geonames database.")
            return 1
        
        # Select best candidate
        best = select_best_candidate(candidates)
        if not best:
            return 1
        
        # Load existing places
        places_data = load_places_json()
        
        # Check if already exists
        if place_exists(places_data, best['geonameid']):
            print(f"\n⚠️  Place already exists in places.json (geonameid: {best['geonameid']})")
            return 0
        
        # Create new place entry
        new_place = add_place_to_json(places_data, best)
        
        print(f"\n[NEW PLACE]")
        print(f"  Name: {new_place['name']}")
        print(f"  Location: {new_place['admin1_name']}, {new_place['country_code']}")
        print(f"  Coordinates: {new_place['latitude']:.4f}, {new_place['longitude']:.4f}")
        print(f"  Distance from Regina: {new_place['distance_from_regina_km']:.1f} km")
        print(f"  Population: {new_place['population']}")
        print(f"  Feature code: {new_place['feature_code']}")
        
        # Add to places list
        places_data['places'].append(new_place)
        
        # Sort places by name for consistency
        places_data['places'].sort(key=lambda x: x['name'].lower())
        
        print(f"\n[TOTAL] Will have {len(places_data['places'])} places after this addition")
        
        # Save
        save_places_json(places_data, dry_run=args.dry_run)
        
        if args.dry_run:
            print("\n[✓] Dry-run complete. Run without --dry-run to save changes.")
        else:
            print("\n[✓] Place successfully added!")
        
        return 0
        
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
