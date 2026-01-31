"""
Extract and geocode place names from transcript files.
Run with: uv run 01_find_placenames.py [recording_path]

Processes all recording folders in public/recordings/ (including nested folders),
or a specific one if path is provided (e.g., "memoirs/Norm_red").

All places are saved to a single public/places.json file, with mentions
including the transcript path and timestamp for each occurrence.

Options:
  --interactive: Prompt for user input on uncertain matches
  --revalidate: Re-run LLM validation on previously found places
  --timeout N: Stop after N seconds (for testing)

Outputs:
  - public/places.json: Global places file with all recordings' mentions

Global outputs (in scripts/places/output/):
  - ignored_words.json: Words marked as non-places
  - review_queue.json: Words that need manual review

Requires: pip install ollama tqdm
Or with uv: uv pip install ollama tqdm

Prerequisites:
  1. Run 00_import_geonames.py first to create the places database
  2. Make sure Ollama is running with gemma3:12b model
"""

import sqlite3
import json
import re
import sys
import time
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Set
from dataclasses import dataclass, asdict
from math import radians, cos, sin, asin, sqrt
from collections import defaultdict

# Check for required packages
try:
    import ollama
    from tqdm import tqdm
except ImportError as e:
    print(f"\nMissing required package: {e}")
    print("\nInstall with:")
    print("  uv pip install ollama tqdm")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
GEONAMES_DIR = SCRIPT_DIR / "geonames"
OUTPUT_DIR = SCRIPT_DIR / "output"
DB_PATH = GEONAMES_DIR / "places.db"
RECORDINGS_DIR = PROJECT_ROOT / "public" / "recordings"

# Add scripts directory to path for imports
sys.path.insert(0, str(SCRIPT_DIR.parent))
from transcript_utils import load_transcript, get_transcript_path

# Regina, Saskatchewan coordinates (reference point)
REGINA_LAT = 50.4452
REGINA_LON = -104.6189

# LLM Model
PREFERRED_MODEL = "gemma3:12b"

# Global output files (for shared data across recordings)
IGNORED_WORDS_FILE = OUTPUT_DIR / "ignored_words.json"
REVIEW_QUEUE_FILE = OUTPUT_DIR / "review_queue.json"
GLOBAL_PLACES_FILE = PROJECT_ROOT / "public" / "places.json"

# State/Province names to skip (don't try to geocode these)
STATE_PROVINCE_NAMES = {
    # US States
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
    'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina',
    'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania',
    'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas',
    'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia',
    'Wisconsin', 'Wyoming',
    # Canadian Provinces
    'Alberta', 'British Columbia', 'Manitoba', 'New Brunswick',
    'Newfoundland', 'Newfoundland and Labrador', 'Nova Scotia',
    'Northwest Territories', 'Nunavut', 'Ontario', 'Prince Edward Island',
    'Quebec', 'Saskatchewan', 'Yukon',
    # Countries
    'Canada', 'United States', 'States', 'USA', 'America',
}

# Known false positives to always skip
KNOWN_FALSE_POSITIVES = {
    'Hardware', 'Summertime', 'Six', 'Mass', 'Light', 'Street', 'School',
    'Lakes', 'Construction', 'Electric', 'United', 'Airport',
}


@dataclass
class Place:
    """Represents a geocoded place mention."""
    name: str
    geonameid: int
    latitude: float
    longitude: float
    country_code: str
    admin1_name: Optional[str]
    population: int
    feature_code: str
    distance_from_regina_km: float
    confidence: str  # 'high', 'medium', 'low'
    needs_review: bool  # Flag for manual review
    mentions: List[Dict]  # List of {transcript: str, context: str, timestamp: float}
    
    def to_dict(self):
        return asdict(self)
    
    def add_mention(self, transcript: str, context: str, timestamp: float):
        """Add a mention, avoiding duplicates by transcript+timestamp key."""
        # Check if this exact mention already exists (by transcript and timestamp)
        for m in self.mentions:
            if m.get('transcript') == transcript and m.get('timestamp') == timestamp:
                return  # Already exists
        self.mentions.append({
            'transcript': transcript,
            'context': context,
            'timestamp': timestamp,
        })


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
    print(f"[OK] Using database: {DB_PATH}")


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
    
    # Check if this is "City, State" format
    if ', ' in name:
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
                    return _process_candidates(conn, results)
    
    # Regular search
    candidates = []
    
    # Exact match on main name
    cursor.execute("""
        SELECT p.geonameid, p.name, p.asciiname, p.latitude, p.longitude,
               p.country_code, p.admin1_code, p.population, p.feature_code
        FROM places p
        WHERE p.name = ? COLLATE NOCASE OR p.asciiname = ? COLLATE NOCASE
        ORDER BY CASE WHEN p.name = ? COLLATE NOCASE THEN 0 ELSE 1 END
        LIMIT ?
    """, (name, name, name, limit))
    candidates.extend(cursor.fetchall())
    
    # Exact match on alternate names
    if len(candidates) < limit:
        cursor.execute("""
            SELECT DISTINCT p.geonameid, p.name, p.asciiname, p.latitude, p.longitude,
                   p.country_code, p.admin1_code, p.population, p.feature_code
            FROM places p
            JOIN alternate_names a ON p.geonameid = a.geonameid
            WHERE a.alternate_name = ? COLLATE NOCASE
            LIMIT ?
        """, (name, limit - len(candidates)))
        candidates.extend(cursor.fetchall())
    
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
        })
    
    # Sort by priority (lower is better)
    results.sort(key=lambda x: x['priority'])
    return results[:20]


# Known multi-word place names that should be detected as units
KNOWN_MULTI_WORD_PLACES = {
    # Saskatchewan
    'Moose Jaw', 'Swift Current', 'Prince Albert', 'North Battleford', 
    'Maple Creek', 'Fort Qu\'Appelle', 'Qu\'Appelle', 'Indian Head',
    'White City', 'Pilot Butte', 'Belle Plaine', 'Fife Lake',
    # US Cities
    'Sioux Falls', 'Sioux City', 'Grand Forks', 'Devils Lake',
    'Rapid City', 'Kansas City', 'Salt Lake City', 'New York',
    'Los Angeles', 'San Francisco', 'Las Vegas', 'Des Moines',
    # Alberta/Manitoba
    'Red Deer', 'Grande Prairie', 'Fort McMurray', 'Medicine Hat',
    'Portage la Prairie', 'The Pas', 'Flin Flon',
    # States/Provinces (to be detected as units, not parts)
    'South Dakota', 'North Dakota', 'British Columbia', 'New Brunswick',
    'Nova Scotia', 'Prince Edward Island', 'Northwest Territories',
}


def extract_capitalized_words(text: str) -> Set[str]:
    """Extract all capitalized words that could be place names.
    
    Priority order:
    1. Known multi-word place names (Moose Jaw, Sioux Falls, etc.)
    2. "City, State" format pairs
    3. Two consecutive capitalized words (potential multi-word places)
    4. Single capitalized words
    """
    place_names = set()
    words_used_in_multi = set()  # Track words used in multi-word matches
    
    # Phase 1: Find known multi-word place names first
    for multi_place in KNOWN_MULTI_WORD_PLACES:
        # Case-insensitive search
        pattern = r'\b' + re.escape(multi_place).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            place_names.add(multi_place)
            # Mark component words as used
            for word in multi_place.split():
                words_used_in_multi.add(word)
    
    # Phase 2: "City, State/Province" format
    city_state_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
    for match in re.finditer(city_state_pattern, text):
        city = match.group(1).strip()
        state = match.group(2).strip()
        combined = f"{city}, {state}"
        place_names.add(combined)
        # Mark words as used
        for word in city.split() + state.split():
            words_used_in_multi.add(word)
    
    # Phase 3: Find two consecutive capitalized words (potential multi-word places)
    two_word_pattern = r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'
    for match in re.finditer(two_word_pattern, text):
        word1 = match.group(1)
        word2 = match.group(2)
        # Skip if either word is a common stop word
        common_prefixes = {'The', 'New', 'Old', 'North', 'South', 'East', 'West', 'Upper', 'Lower', 'Great', 'Little', 'Big', 'Grand', 'Fort', 'Lake', 'Mount', 'Saint', 'St'}
        common_suffixes = {'City', 'Falls', 'Creek', 'Lake', 'River', 'Bay', 'Hill', 'Hills', 'Valley', 'Park', 'Beach', 'Springs', 'Junction', 'Crossing'}
        
        # If first word is a geographic prefix and second is capitalized, treat as potential place
        if word1 in common_prefixes or word2 in common_suffixes:
            combined = f"{word1} {word2}"
            if combined not in KNOWN_MULTI_WORD_PLACES:  # Don't duplicate known ones
                place_names.add(combined)
                words_used_in_multi.add(word1)
                words_used_in_multi.add(word2)
    
    # Phase 4: Individual capitalized words (but not if used in multi-word matches)
    words = re.findall(r'\b[A-Z][a-z]+(?:-[A-Z][a-z]+)*\b', text)
    
    # Extensive stop words list
    stop_words = {
        # Articles, prepositions, conjunctions
        'The', 'A', 'An', 'And', 'Or', 'But', 'In', 'On', 'At', 'To', 'For',
        'Of', 'With', 'By', 'From', 'Up', 'About', 'Into', 'Through', 'During',
        'Before', 'After', 'Above', 'Below', 'Between', 'Under', 'Again',
        'Further', 'Then', 'Once', 'Here', 'There', 'When', 'Where', 'Why',
        'How', 'All', 'Both', 'Each', 'Few', 'More', 'Most', 'Other', 'Some',
        'Such', 'No', 'Nor', 'Not', 'Only', 'Own', 'Same', 'So', 'Than',
        'Too', 'Very', 'Can', 'Will', 'Just', 'Should', 'Now', 'Well', 'Oh',
        # Pronouns
        'I', 'He', 'She', 'It', 'They', 'We', 'You',
        'My', 'His', 'Her', 'Its', 'Their', 'Our', 'Your',
        # Questions and interjections
        'What', 'Which', 'Who', 'Whom', 'Whose', 'Uh', 'Um', 'Ah', 'Er', 'Hm',
        'Yes', 'Yeah', 'Yep', 'Nope', 'Okay', 'Alright',
        # Months
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December',
        # Days
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
        # Religious/holiday terms
        'God', 'Lord', 'Jesus', 'Christ', 'Christmas', 'Easter', 'Thanksgiving',
        # Directional/descriptive words (often part of compound names) - kept but will be used in multi-word detection
        'Canadian', 'Grey', 'Cup', 'New', 'Old', 'North', 'South', 'East', 'West',
        'Central', 'Upper', 'Lower', 'Great', 'Little', 'Big', 'Grand',
        # Common first names
        'George', 'John', 'Mary', 'William', 'James', 'Robert', 'Michael',
        'David', 'Richard', 'Joseph', 'Thomas', 'Charles', 'Christopher',
        'Daniel', 'Matthew', 'Donald', 'Mark', 'Paul', 'Steven', 'Andrew',
        'Kenneth', 'Joshua', 'Kevin', 'Brian', 'Edward', 'Ronald', 'Timothy',
        'Jason', 'Jeffrey', 'Ryan', 'Jacob', 'Gary', 'Nicholas', 'Eric',
        'Stephen', 'Jonathan', 'Larry', 'Justin', 'Scott', 'Brandon', 'Frank',
        'Benjamin', 'Gregory', 'Raymond', 'Samuel', 'Patrick', 'Alexander',
        'Jack', 'Dennis', 'Jerry', 'Tyler', 'Aaron', 'Henry', 'Douglas',
        'Peter', 'Walter', 'Nathan', 'Harold', 'Kyle', 'Carl', 'Arthur',
        'Gerald', 'Roger', 'Keith', 'Jeremy', 'Terry', 'Lawrence', 'Sean',
        'Albert', 'Joe', 'Christian', 'Austin', 'Willie', 'Jesse', 'Ethan',
        'Billy', 'Bruce', 'Bryan', 'Ralph', 'Roy', 'Eugene', 'Louis',
        'Russell', 'Harry', 'Wayne', 'Howard', 'Fred', 'Ernest', 'Alan',
        # Common female names
        'Patricia', 'Jennifer', 'Linda', 'Barbara', 'Elizabeth', 'Susan',
        'Jessica', 'Sarah', 'Karen', 'Nancy', 'Lisa', 'Margaret', 'Betty',
        'Sandra', 'Ashley', 'Dorothy', 'Kimberly', 'Emily', 'Donna', 'Michelle',
        'Carol', 'Amanda', 'Melissa', 'Deborah', 'Stephanie', 'Rebecca',
        'Laura', 'Sharon', 'Cynthia', 'Kathleen', 'Amy', 'Shirley', 'Angela',
        'Helen', 'Anna', 'Brenda', 'Pamela', 'Nicole', 'Ruth', 'Katherine',
        'Samantha', 'Christine', 'Catherine', 'Virginia', 'Debra', 'Rachel',
        'Janet', 'Emma', 'Carolyn', 'Maria', 'Heather', 'Diane', 'Julie',
        'Joyce', 'Evelyn', 'Joan', 'Victoria', 'Kelly', 'Christina', 'Lauren',
        'Frances', 'Martha', 'Judith', 'Cheryl', 'Megan', 'Andrea', 'Olivia',
        'Ann', 'Jean', 'Alice', 'Jacqueline', 'Hannah', 'Doris', 'Gloria',
        'Teresa', 'Kathryn', 'Sara', 'Janice', 'Marie', 'Julia', 'Grace',
        'Judy', 'Theresa', 'Madison', 'Beverly', 'Denise', 'Marilyn', 'Amber',
        'Danielle', 'Rose', 'Brittany', 'Diana', 'Abigail', 'Natalie',
        'Jane', 'Lori', 'Alexis', 'Tiffany', 'Kayla',
        # Common last names
        'Smith', 'Johnson', 'Brown', 'Jones', 'Miller', 'Davis', 'Wilson',
        'Anderson', 'Taylor', 'Thomas', 'Moore', 'Martin', 'Thompson', 'White',
        'Harris', 'Clark', 'Lewis', 'Walker', 'Hall', 'Allen', 'Young',
        'King', 'Wright', 'Hill', 'Green', 'Adams', 'Baker', 'Nelson',
        'Carter', 'Mitchell', 'Roberts', 'Turner', 'Phillips', 'Campbell',
        'Parker', 'Evans', 'Edwards', 'Collins', 'Stewart', 'Morris',
        'Rogers', 'Reed', 'Cook', 'Bell', 'Cooper', 'Richardson', 'Cox',
        'Ward', 'Peterson', 'Gray', 'James', 'Watson', 'Brooks', 'Kelly',
        'Sanders', 'Price', 'Bennett', 'Wood', 'Barnes', 'Ross', 'Henderson',
        'Coleman', 'Jenkins', 'Perry', 'Powell', 'Long', 'Patterson', 'Hughes',
        'Flores', 'Washington', 'Butler', 'Simmons', 'Foster', 'Gonzales',
        'Bryant', 'Alexander', 'Russell', 'Griffin', 'Diaz', 'Hayes',
    }
    
    for word in words:
        # Skip if word is in stop words
        if word in stop_words:
            continue
        # Skip if word was used in a multi-word place name
        if word in words_used_in_multi:
            continue
        # Skip if word is part of a "City, State" pattern
        is_in_pattern = any(word in pname for pname in place_names if ', ' in pname)
        if is_in_pattern:
            continue
        place_names.add(word)
    
    return place_names


def validate_place_with_llm(name: str, contexts: List[str], candidates: List[Dict], model_name: str) -> Optional[Dict]:
    """Use LLM to validate if a word is actually a place name in context.
    
    Improved prompt to reduce false positives like 'Moon', 'Warren', etc.
    Now takes multiple contexts to give the LLM better information.
    """
    
    if not candidates:
        candidate_text = "No matching places found in database."
    else:
        candidate_list = []
        for i, cand in enumerate(candidates[:5], 1):
            admin = cand['admin1_name'] or cand['admin1_code']
            candidate_list.append(
                f"{i}. {cand['name']}, {admin}, {cand['country_code']} "
                f"(pop: {cand['population']:,}, {cand['distance_km']:.0f}km from Regina)"
            )
        candidate_text = "\n".join(candidate_list)
    
    # Format contexts - show up to 5 different contexts
    unique_contexts = list(dict.fromkeys(contexts))[:5]  # Remove duplicates, keep order
    if len(unique_contexts) == 1:
        context_text = f'Context: "{unique_contexts[0]}"'
    else:
        context_lines = [f'{i}. "{ctx}"' for i, ctx in enumerate(unique_contexts, 1)]
        context_text = "Contexts (multiple mentions):\n" + "\n".join(context_lines)
    
    # Improved prompt with stricter criteria
    prompt = f"""You are analyzing transcripts of voice memoirs from the 1980s recorded by Lindy Achen from Regina, Saskatchewan, Canada.

Determine if "{name}" is being used as a GEOGRAPHIC PLACE NAME (city, town, village, region) in ANY of these contexts:

{context_text}

Database matches for "{name}":
{candidate_text}

IMPORTANT: Look at ALL contexts. If "{name}" is used as a place in ANY context (even if also used as a person name elsewhere), answer YES.

PLACE INDICATORS - Answer YES (is_place=true) if ANY context shows:
1. Locational prepositions: "at {name}", "in {name}", "to {name}", "from {name}", "near {name}", "around {name}"
   - "lived at Frederick" = Frederick is a PLACE
   - "the farm near Weyburn" = Weyburn is a PLACE
   - "out of Aberdeen" = Aberdeen is a PLACE
2. Travel indicators: "went to", "moved to", "drove to", "came from", "road to", "back to"
   - "go back to Frederick" = Frederick is a PLACE
3. Geographic references: "town of", "city of", state/province names nearby
   - "Frederick, out of Aberdeen, South Dakota" = Frederick AND Aberdeen are PLACES

PERSON INDICATORS - Answer NO (is_place=false) ONLY if ALL contexts show:
1. Personal prepositions: "with {name}", "and {name} said", "told {name}", "{name} was a"
   - "acquainted with Frederick" = likely a PERSON (but check other contexts!)
2. Family/title references: "Uncle {name}", "Aunt {name}", "Mr. {name}"
3. Personal actions: "{name} said", "{name} told me", "{name} worked"

STRICT RULE: If even ONE context shows place usage, answer YES.
- "at Frederick" in any context = Frederick IS a place, even if also used as person name elsewhere

MATCH SELECTION: The database matches are sorted by relevance (most relevant first).
- Usually choose match_index=1 (the first/best match)
- Only choose a different match if the context explicitly mentions that specific location

Respond with ONLY this JSON (no other text):
{{"is_place": true/false, "match_index": 1 or 2 or 3 or 4 or 5 or null, "confidence": "high/medium/low", "reasoning": "one sentence"}}
"""
    
    response_text = ""
    try:
        response = ollama.generate(
            model=model_name,
            prompt=prompt,
            stream=False,
            options={"temperature": 0.1, "num_ctx": 2048},
            keep_alive="15m"
        )
        
        response_text = response.get("response", "") if isinstance(response, dict) else response.response
        
        if not response_text or not response_text.strip():
            print(f"  ⚠️  Empty response from LLM for '{name}'")
            return None
        
        # Strip markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # Fix common LLM JSON errors: "match_index": 1-5 -> "match_index": 1
        import re
        response_text = re.sub(r'"match_index":\s*(\d+)-\d+', r'"match_index": \1', response_text)
        
        result = json.loads(response_text)
        
        if not result.get('is_place', False):
            return None
        
        match_idx = result.get('match_index')
        if match_idx and 1 <= match_idx <= len(candidates):
            match = candidates[match_idx - 1].copy()
            match['llm_confidence'] = result.get('confidence', 'medium')
            match['llm_reasoning'] = result.get('reasoning', '')
            
            # Geographic filtering for manual review
            country = match['country_code']
            admin1 = match.get('admin1_name') or ''
            
            needs_review = False
            if country == 'CA':
                if admin1 not in ['Saskatchewan', 'Alberta', 'Manitoba', 'British Columbia', 'Ontario']:
                    needs_review = True
            elif country == 'US':
                if admin1 not in ['Iowa', 'North Dakota', 'South Dakota', 'Minnesota', 'Montana', 'Nebraska', 'Kansas']:
                    needs_review = True
            else:
                needs_review = True
            
            match['needs_review'] = needs_review
            if needs_review:
                match['review_reason'] = f"Outside expected region: {admin1}, {country}"
            
            return match
        
        # LLM says it's a place but no match in database
        return {
            'is_place_but_no_match': True,
            'confidence': result.get('confidence', 'low'),
            'reasoning': result.get('reasoning', ''),
        }
        
    except Exception as e:
        print(f"  ⚠️  LLM validation error for '{name}': {e}")
        if response_text:
            print(f"      Response was: {response_text[:200]}")
        return None


def find_all_recordings(base_dir: Path) -> List[Path]:
    """Recursively find all folders containing transcripts."""
    recordings = []
    
    def scan_folder(folder: Path):
        if get_transcript_path(folder) is not None:
            recordings.append(folder)
        for item in sorted(folder.iterdir()):
            if item.is_dir():
                scan_folder(item)
    
    if base_dir.exists():
        scan_folder(base_dir)
    return recordings


def load_ignored_words() -> Set[str]:
    """Load the list of words the user has marked as non-places."""
    if not IGNORED_WORDS_FILE.exists():
        return set()
    with open(IGNORED_WORDS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return set(data.get('ignored', []))


def save_ignored_words(ignored: Set[str]):
    """Save the list of ignored words."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(IGNORED_WORDS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'ignored': sorted(ignored)}, f, indent=2)


def load_review_queue() -> Dict:
    """Load words that need manual review."""
    if not REVIEW_QUEUE_FILE.exists():
        return {}
    with open(REVIEW_QUEUE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_review_queue(queue: Dict):
    """Save words that need manual review."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(queue, f, indent=2)


def load_global_places() -> Dict[int, Place]:
    """Load existing places from the global places.json."""
    if not GLOBAL_PLACES_FILE.exists():
        return {}
    try:
        with open(GLOBAL_PLACES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        places_dict = {}
        for place_data in data.get('places', []):
            geonameid = place_data['geonameid']
            places_dict[geonameid] = Place(
                name=place_data['name'],
                geonameid=geonameid,
                latitude=place_data['latitude'],
                longitude=place_data['longitude'],
                country_code=place_data['country_code'],
                admin1_name=place_data.get('admin1_name'),
                population=place_data['population'],
                feature_code=place_data['feature_code'],
                distance_from_regina_km=place_data['distance_from_regina_km'],
                confidence=place_data['confidence'],
                needs_review=place_data.get('needs_review', False),
                mentions=place_data.get('mentions', []),
            )
        return places_dict
    except Exception as e:
        print(f"  Warning: Could not load existing places: {e}")
        return {}


def save_global_places(places: Dict[int, Place]):
    """Save places to the global places.json."""
    places_list = [p.to_dict() for p in places.values()]
    places_list.sort(key=lambda p: len(p['mentions']), reverse=True)
    
    json_output = {
        'metadata': {
            'total_places': len(places),
            'last_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            'reference_point': {
                'name': 'Regina, Saskatchewan',
                'latitude': REGINA_LAT,
                'longitude': REGINA_LON,
            },
        },
        'places': places_list,
    }
    
    with open(GLOBAL_PLACES_FILE, 'w', encoding='utf-8') as f:
        json.dump(json_output, f, indent=2)
    
    print(f"   [SAVED] {GLOBAL_PLACES_FILE}")


def process_single_recording(
    conn: sqlite3.Connection, 
    model_name: str, 
    recording_folder: Path,
    global_places: Dict[int, Place],
    ignored_words: Set[str],
    review_queue: Dict,
    timeout_seconds: Optional[int] = None,
    startsecs: Optional[float] = None,
    endsecs: Optional[float] = None
) -> int:
    """Process a single recording and extract place names.
    
    Returns the number of new places found in this recording.
    Updates global_places dict in place.
    """
    
    start_time = time.time()
    relative_path = str(recording_folder.relative_to(RECORDINGS_DIR)).replace("\\", "/")
    
    print(f"\n{'='*60}")
    print(f"[Recording] {relative_path}")
    if startsecs or endsecs:
        print(f"   Time range: {startsecs or 0}s - {endsecs or 'end'}s")
    print(f"{'='*60}")
    
    # Load transcript
    transcript_data = load_transcript(recording_folder)
    segments = transcript_data.get("segments", [])
    
    if not segments:
        print("   No segments found in transcript")
        return 0
    
    # Filter segments by time range if specified
    if startsecs is not None or endsecs is not None:
        filtered_segments = []
        for seg in segments:
            seg_start = seg.get("start", 0)
            if startsecs is not None and seg_start < startsecs:
                continue
            if endsecs is not None and seg_start > endsecs:
                continue
            filtered_segments.append(seg)
        segments = filtered_segments
        print(f"   Filtered to {len(segments)} segments in time range")
    
    # Extract all capitalized words
    all_words = set()
    word_contexts = defaultdict(list)
    
    for seg in segments:
        text = seg.get("text", "")
        timestamp = seg.get("start", 0)
        cap_words = extract_capitalized_words(text)
        all_words.update(cap_words)
        for word in cap_words:
            word_contexts[word].append((text, timestamp))
    
    # Filter out ignored words
    all_words = all_words - ignored_words
    
    # Filter out state/province names (we don't geocode these)
    all_words = all_words - STATE_PROVINCE_NAMES
    
    # Filter out known false positives
    all_words = all_words - KNOWN_FALSE_POSITIVES
    
    # Filter out words that are already in global places (we already have them)
    existing_place_names = {p.name for p in global_places.values()}
    all_words = all_words - existing_place_names
    
    print(f"   Found {len(all_words)} unique capitalized words to check")
    
    new_places_count = 0
    words_processed = 0
    for word in sorted(all_words):
        # Check timeout
        if timeout_seconds and (time.time() - start_time) > timeout_seconds:
            print(f"\n   ⏱️  Timeout reached ({timeout_seconds}s), stopping...")
            break
        
        # Skip state/province names that might appear in "City, State" format
        if word in STATE_PROVINCE_NAMES:
            continue
        
        # Get all contexts for this word
        contexts = word_contexts[word]
        all_context_texts = [ctx[0] for ctx in contexts]  # Extract just the text, not timestamps
        timestamp = contexts[0][1]  # Use first timestamp for the mention
        
        # Find candidates in database
        candidates = find_place_candidates(conn, word, limit=10)
        
        # Validate with LLM - pass all contexts
        match = validate_place_with_llm(word, all_context_texts, candidates, model_name)
        
        words_processed += 1
        
        # LLM says NOT a place
        if match is None:
            print(f"   [SKIP] '{word}' - NOT a place")
            ignored_words.add(word)
            save_ignored_words(ignored_words)
            continue
        
        # LLM confirmed place with database match
        if match and not match.get('is_place_but_no_match'):
            geonameid = match['geonameid']
            admin = match.get('admin1_name') or match.get('admin1_code')
            needs_review = match.get('needs_review', False)
            
            review_flag = " [REVIEW]" if needs_review else ""
            print(f"   [PLACE]{review_flag} '{word}' -> {match['name']}, {admin}, {match['country_code']}")
            
            # Create Place if not exists in global places
            if geonameid not in global_places:
                distance = haversine_distance(REGINA_LAT, REGINA_LON, match['latitude'], match['longitude'])
                
                if distance < 200:
                    confidence = 'high'
                elif distance < 800:
                    confidence = 'medium'
                else:
                    confidence = 'low'
                
                global_places[geonameid] = Place(
                    name=match['name'],
                    geonameid=geonameid,
                    latitude=match['latitude'],
                    longitude=match['longitude'],
                    country_code=match['country_code'],
                    admin1_name=match.get('admin1_name'),
                    population=match['population'],
                    feature_code=match['feature_code'],
                    distance_from_regina_km=distance,
                    confidence=confidence,
                    needs_review=needs_review,
                    mentions=[],
                )
                new_places_count += 1
            
            # Add mention with transcript path (upsert by transcript+timestamp)
            global_places[geonameid].add_mention(
                transcript=relative_path,
                context=all_context_texts[0],
                timestamp=timestamp
            )
            
            # Save global places immediately
            save_global_places(global_places)
            
        # LLM says place but not in database
        elif match and match.get('is_place_but_no_match'):
            print(f"   [REVIEW] '{word}' - Place not in database")
            if word not in review_queue:
                review_queue[word] = {
                    'recording': relative_path,
                    'context': all_context_texts[0],
                    'timestamp': timestamp,
                    'llm_reasoning': match.get('reasoning', ''),
                }
            save_review_queue(review_queue)
    
    elapsed = time.time() - start_time
    print(f"\n   Processed {words_processed} words in {elapsed:.1f}s")
    print(f"   Found {new_places_count} new places in this recording")
    
    return new_places_count


def check_ollama_connection():
    """Check if Ollama is running and has the required model."""
    try:
        models = ollama.list()
        print("[OK] Connected to Ollama")
        
        model_list = models.get('models', []) if isinstance(models, dict) else models.models if hasattr(models, 'models') else []
        available = [m.get('name', m.model) if isinstance(m, dict) else m.model for m in model_list]
        
        for avail in available:
            if avail.startswith(PREFERRED_MODEL.split(':')[0]):
                print(f"   Using model: {avail}")
                return avail
        
        print(f"\n⚠️  Preferred model {PREFERRED_MODEL} not found")
        print("   Available models:", available)
        
        if available:
            print(f"   Using: {available[0]}")
            return available[0]
        
        return None
        
    except Exception as e:
        print(f"\n❌ Cannot connect to Ollama: {e}")
        print("\nMake sure Ollama is running:")
        print("  ollama serve")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and geocode place names from transcript files."
    )
    parser.add_argument(
        'recording_path',
        nargs='?',
        help='Path to specific recording (e.g., "memoirs/Norm_red"). If omitted, processes all.'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Prompt for user input on uncertain matches'
    )
    parser.add_argument(
        '--revalidate',
        action='store_true',
        help='Re-run LLM validation on previously found places'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=None,
        help='Stop processing after N seconds (for testing)'
    )
    parser.add_argument(
        '--startsecs',
        type=float,
        default=None,
        help='Only process segments starting after this timestamp (for debugging)'
    )
    parser.add_argument(
        '--endsecs',
        type=float,
        default=None,
        help='Only process segments ending before this timestamp (for debugging)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("PLACE NAME EXTRACTION")
    print("=" * 60)
    
    # Check prerequisites
    check_database()
    model_name = check_ollama_connection()
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    
    # Load global data
    ignored_words = load_ignored_words()
    print(f"Loaded {len(ignored_words)} ignored words")
    
    review_queue = load_review_queue()
    print(f"Loaded {len(review_queue)} items in review queue")
    
    # Load global places
    global_places = load_global_places()
    print(f"Loaded {len(global_places)} existing places")
    
    # Determine which recordings to process
    if args.recording_path:
        # Specific recording
        recording_folder = RECORDINGS_DIR / args.recording_path.replace("\\", "/")
        if not recording_folder.exists():
            print(f"\n❌ Recording not found: {recording_folder}")
            sys.exit(1)
        if get_transcript_path(recording_folder) is None:
            print(f"\n❌ No transcript found in: {recording_folder}")
            sys.exit(1)
        recordings = [recording_folder]
    else:
        # All recordings
        recordings = find_all_recordings(RECORDINGS_DIR)
    
    print(f"\nProcessing {len(recordings)} recording(s)")
    
    # Process each recording
    new_places_total = 0
    for recording_folder in recordings:
        new_count = process_single_recording(
            conn, 
            model_name, 
            recording_folder, 
            global_places,
            ignored_words, 
            review_queue,
            timeout_seconds=args.timeout,
            startsecs=args.startsecs,
            endsecs=args.endsecs
        )
        new_places_total += new_count
    
    # Final save
    save_ignored_words(ignored_words)
    save_review_queue(review_queue)
    save_global_places(global_places)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"New places found: {new_places_total}")
    print(f"Total places in database: {len(global_places)}")
    print(f"Ignored words: {len(ignored_words)}")
    print(f"Review queue: {len(review_queue)} items")
    
    conn.close()


if __name__ == "__main__":
    main()
