import json, re, os, math, textwrap, pathlib

base="/mnt/data"
paths = {
    "scene_cards": f"{base}/all_scene_cards.json",
    "chapters": f"{base}/chapters.json",
    "transcript": f"{base}/transcript.json",
}
for k,p in paths.items():
    assert os.path.exists(p), (k,p)

scene_cards = json.load(open(paths["scene_cards"],"r",encoding="utf-8"))
chapters = json.load(open(paths["chapters"],"r",encoding="utf-8"))
transcript = json.load(open(paths["transcript"],"r",encoding="utf-8"))

# --- Helpers to find chapters by keyword ---
def chapter_items(ch):
    # chapters.json structure may vary; normalize into list of {title,startTime,endTime?}
    if isinstance(ch, dict):
        if "chapters" in ch and isinstance(ch["chapters"], list):
            return ch["chapters"]
        # sometimes list under "items"
        for key in ("items","data","results"):
            if key in ch and isinstance(ch[key], list):
                return ch[key]
    if isinstance(ch, list):
        return ch
    return []

chap_list = chapter_items(chapters)

def norm(s): 
    return re.sub(r"\s+"," ",str(s or "")).strip()

def find_chapter_by_keywords(keywords):
    kw = [k.lower() for k in keywords]
    candidates=[]
    for i,c in enumerate(chap_list):
        title = norm(c.get("title") or c.get("name") or c.get("label"))
        t = title.lower()
        if all(k in t for k in kw):
            candidates.append((i,c,title))
    return candidates

# --- Build an index of scenes by video file and activity ---
videos_by_name = {v["video_file"]: v for v in scene_cards}

def pick_scenes(video_file, predicate, limit=5):
    v = videos_by_name.get(video_file)
    if not v: 
        return []
    out=[]
    for s in v.get("scenes",[]):
        if predicate(s):
            out.append(s)
        if len(out)>=limit:
            break
    return out

def scene_ref(video_file, scene):
    return {
        "video_file": video_file,
        "scene_index": scene.get("scene_index"),
        "start_seconds": scene.get("start_seconds"),
        "end_seconds": scene.get("end_seconds"),
        "title": scene.get("title"),
        "summary": scene.get("summary"),
        "tags": scene.get("tags",[]),
        "activity_type": scene.get("activity_type"),
    }

# Heuristic selections:
# - Power-2: choose a mix of surveying, pole_setting, cross_arms, stringing, planning
power2 = videos_by_name.get("Power-2.mp4", {})
power7 = videos_by_name.get("Power-7.mp4", {})
frisco = videos_by_name.get("Climbing poles in bush (Frisco-5).mp4", {})
family = videos_by_name.get("Grama and Grampa by flowers (LA).mp4", {})

def has_tag(scene, substr):
    return any(substr.lower() in (t or "").lower() for t in scene.get("tags",[]))

def activity_is(scene, *types):
    return (scene.get("activity_type") in set(types))

# pick representative scenes by activity buckets for Power-2
power2_scenes = power2.get("scenes",[])
# bucketed pick
def first_scene_where(pred):
    for s in power2_scenes:
        if pred(s):
            return s
    return None

p2_survey = first_scene_where(lambda s: "survey" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))
p2_poleset = first_scene_where(lambda s: activity_is(s,"pole_setting"))
p2_cross = first_scene_where(lambda s: activity_is(s,"cross_arms"))
p2_string = first_scene_where(lambda s: activity_is(s,"stringing"))
p2_plans = first_scene_where(lambda s: "plans" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))
# fallback: any early wide landscape scene
p2_wide = first_scene_where(lambda s: "landscape" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))

# pick representative scenes for Power-7 (boom truck / auger / line)
power7_scenes = power7.get("scenes",[])
def first_p7(pred):
    for s in power7_scenes:
        if pred(s): return s
    return None
p7_boom = first_p7(lambda s: "boom" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))
p7_auger = first_p7(lambda s: "auger" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))
p7_string = first_p7(lambda s: activity_is(s,"stringing") or "string" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))
p7_poleset = first_p7(lambda s: activity_is(s,"pole_setting"))
p7_truck = first_p7(lambda s: "truck" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))

# Frisco-5 picks: stringing, boat, river, damage assessment
frisco_scenes = frisco.get("scenes",[])
def first_f(pred):
    for s in frisco_scenes:
        if pred(s): return s
    return None
f_string = first_f(lambda s: activity_is(s,"stringing"))
f_boat = first_f(lambda s: "boat" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))
f_river = first_f(lambda s: "river" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))
f_damage = first_f(lambda s: "damage" in (s.get("title","").lower()+ " " + s.get("summary","").lower()))

# Build playlists keyed to your earlier chapter plan, but store chapter selection as "match_rules"
playlists = [
    {
        "id": "restubbing_early_linework",
        "chapter_match": {"keywords_any": ["Power", "Restubbing"], "fallback_time_seconds": 2344.27},
        "ui_label": "Early line work (restubbing / first crew jobs)",
        "clips": [x for x in [
            ("Power-2.mp4", p2_survey, "Surveying and route setup (sets the scene)"),
            ("Power-2.mp4", p2_poleset, "Pole setting — manpower + truck assistance"),
            ("Power-2.mp4", p2_cross, "Crossarm framing / hardware"),
            ("Climbing poles in bush (Frisco-5).mp4", f_string, "Crew stringing wire between poles"),
        ] if x[1] is not None],
    },
    {
        "id": "power_gang_transition",
        "chapter_match": {"keywords_any": ["Power Gang"], "fallback_time_seconds": 3260.15},
        "ui_label": "Joining the power gang (crew mobilizes)",
        "clips": [x for x in [
            ("Power-2.mp4", p2_wide, "Wide prairie + line work context"),
            ("Power-7.mp4", p7_truck, "Line truck / staging"),
            ("Power-7.mp4", p7_boom, "Boom truck in action"),
        ] if x[1] is not None],
    },
    {
        "id": "line_construction_centerpiece",
        "chapter_match": {"keywords_any": ["Line Construction"], "fallback_time_seconds": 3426.14},
        "ui_label": "Line construction (core build-out montage)",
        "clips": [x for x in [
            ("Power-7.mp4", p7_poleset, "Pole setting (mechanized + crew)"),
            ("Power-7.mp4", p7_auger, "Auger digging / pole hole work"),
            ("Climbing poles in bush (Frisco-5).mp4", f_river, "Stringing across a river (special setup)"),
            ("Climbing poles in bush (Frisco-5).mp4", f_boat, "Boat inspection / line work over water"),
        ] if x[1] is not None],
    },
    {
        "id": "dominion_electric_maintenance",
        "chapter_match": {"keywords_any": ["Dominion Electric"], "fallback_time_seconds": 5159.88},
        "ui_label": "Dominion Electric era (maintenance / upgrades vibe)",
        "clips": [x for x in [
            ("Power-2.mp4", p2_plans, "Reviewing plans in the field"),
            ("Power-2.mp4", p2_cross, "Hardware / crossarm work"),
            ("Power-7.mp4", p7_boom, "Boom truck assisting installs"),
        ] if x[1] is not None],
    },
    {
        "id": "bidding_and_expansion_montage",
        "chapter_match": {"keywords_any": ["Bidding"], "fallback_time_seconds": 5740.93},
        "ui_label": "Bidding & expansion (scale montage, not literal)",
        "clips": [x for x in [
            ("Power-2.mp4", p2_wide, "Finished line in landscape (scale)"),
            ("Power-7.mp4", p7_boom, "Equipment scale / pace of work"),
            ("Power-2.mp4", p2_string, "Stringing / conductors"),
        ] if x[1] is not None],
    },
    {
        "id": "storm_response_1954",
        "chapter_match": {"keywords_any": ["Sleet", "Storm"], "fallback_time_seconds": 11293.44},
        "ui_label": "Storm response / damage assessment (1954 sleet storm)",
        "clips": [x for x in [
            ("Climbing poles in bush (Frisco-5).mp4", f_damage, "Surveying damage / cleared landscape"),
            ("Climbing poles in bush (Frisco-5).mp4", f_boat, "Inspection / repair context"),
        ] if x[1] is not None],
    },
]

# resolve chapter references for each playlist
def find_chapter_match(match):
    kws = [k.lower() for k in match.get("keywords_any",[])]
    best=None
    for c in chap_list:
        title = norm(c.get("title") or c.get("name") or c.get("label"))
        t = title.lower()
        if any(k in t for k in kws):
            best=c
            break
    return best

out_playlists = []
for pl in playlists:
    ch = find_chapter_match(pl["chapter_match"])
    ch_ref = None
    if ch:
        ch_ref = {
            "title": norm(ch.get("title") or ch.get("name") or ch.get("label")),
            "startTime": ch.get("startTime") or ch.get("start_seconds") or ch.get("start"),
            "endTime": ch.get("endTime") or ch.get("end_seconds") or ch.get("end"),
            "id": ch.get("id") or ch.get("chapterId") or ch.get("uuid"),
        }
    else:
        ch_ref = {
            "title": None,
            "startTime": pl["chapter_match"].get("fallback_time_seconds"),
            "endTime": None,
            "id": None,
            "note": "No exact title match found in chapters.json; using fallback_time_seconds"
        }
    clips=[]
    for (vf, scene, caption) in pl["clips"]:
        clip = scene_ref(vf, scene)
        clip["caption"] = caption
        clips.append(clip)
    out_playlists.append({
        "id": pl["id"],
        "ui_label": pl["ui_label"],
        "chapter": ch_ref,
        "clips": clips,
    })

chapter_playlist_path = f"{base}/chapter_video_playlists.json"
with open(chapter_playlist_path,"w",encoding="utf-8") as f:
    json.dump({"generated_from": paths, "playlists": out_playlists}, f, ensure_ascii=False, indent=2)

