import json

with open('public/recordings/memoirs/Norm_red/transcript.json') as f:
    data = json.load(f)
    segments = data['segments']
    
    # Key sections to analyze:
    # 1. Around 1596s (Father's Death chapter start)
    # 2. Around 2052s (claimed Lineman Career start)
    # 3. Around 2184s (Harvesting & Nebraska start)
    # 4. Around 2340s (actual lineman work start)
    
    ranges = [
        (1580, 1620, "Father's Death chapter start (1596s)"),
        (2040, 2070, "Lineman Career claimed start (2052s)"),
        (2170, 2210, "Harvesting & Nebraska start (2184s)"),
        (2330, 2400, "Actual lineman work start area"),
        (2510, 2560, "Lineman career explicit mention"),
    ]
    
    for start, end, label in ranges:
        print(f"\n{'='*60}")
        print(f"{label}")
        print(f"{'='*60}")
        for seg in segments:
            if start <= seg['start'] <= end:
                print(f"[{seg['start']:.1f}s] {seg['text']}")
