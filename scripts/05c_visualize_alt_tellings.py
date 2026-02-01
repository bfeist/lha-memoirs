import json, math, os
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# Get the script's directory
script_dir = Path(__file__).parent
json_path = script_dir.parent / "public" / "recordings" / "memoirs" / "alternate_tellings.json"  # or wherever alternate_tellings.json is
if not json_path.exists():
    json_path = Path("/mnt/data/alternate_tellings.json")
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Durations provided by user (seconds)
dur_norm = 13315.66
dur_tdk = 10880.07

alts = data.get("alt_tellings", [])
if not alts:
    print("No alternate tellings found in the JSON file.")
    exit(1)

# Prepare plot dimensions
max_dur = max(dur_norm, dur_tdk)
height_units = 12  # inches
width_units = 10   # inches
fig, ax = plt.subplots(figsize=(width_units, height_units))

# Coordinate system: y in seconds, x arbitrary
# We'll map y directly in seconds for accuracy, then set limits.
x_left = 1.0
box_width = 2.0
gap = 3.0
x_right = x_left + box_width + gap

# Boxes from y=0 to y=duration
rect_norm = Rectangle((x_left, 0), box_width, dur_norm, fill=False, linewidth=2)
rect_tdk  = Rectangle((x_right, 0), box_width, dur_tdk, fill=False, linewidth=2)
ax.add_patch(rect_norm)
ax.add_patch(rect_tdk)

# Labels
ax.text(x_left + box_width/2, dur_norm + max_dur*0.02, f"Memoirs\n{dur_norm:.2f}s", ha="center", va="bottom", fontsize=12)
ax.text(x_right + box_width/2, dur_tdk + max_dur*0.02, f"Memoirs Earlier\n{dur_tdk:.2f}s", ha="center", va="bottom", fontsize=12)

# Lines for alt_tellings using start time from norm_window and tdk_window
for i, item in enumerate(alts):
    a = item.get("norm_window", {})
    b = item.get("tdk_window", {})
    y1 = float(a.get("start", 0.0))
    y2 = float(b.get("start", 0.0))
    # draw line from center of left box to center of right box
    ax.plot([x_left + box_width, x_right], [y1, y2], linewidth=1, alpha=0.8)
    # small tick marks at connection points
    ax.plot([x_left + box_width*0.95, x_left + box_width], [y1, y1], linewidth=1)
    ax.plot([x_right, x_right + box_width*0.05], [y2, y2], linewidth=1)
    # Add label with topic from norm_window
    mid_x = (x_left + box_width + x_right) / 2
    mid_y = (y1 + y2) / 2
    topic = a.get("topics", "")
    # Truncate topic if too long
    if len(topic) > 50:
        topic = topic[:47] + "..."
    ax.text(mid_x, mid_y, topic, ha="center", va="center", fontsize=6, rotation=0, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

# Aesthetic settings
ax.set_xlim(0, x_right + box_width + 1.0)
ax.set_ylim(-max_dur*0.02, max_dur*1.05)
ax.invert_yaxis()  # so time 0 at top? Actually typical is top start; invert to show 0 at top.
# But then boxes need to start at 0 at top; rectangles drawn from 0 downward; invert makes correct orientation.
ax.set_xticks([])
ax.set_ylabel("Time (seconds from start)")
ax.set_title("Alternate tellings connections (startTime → startTime)")
ax.grid(False)
for spine in ["top", "right", "bottom"]:
    ax.spines[spine].set_visible(False)

out_png = script_dir / "alternate_tellings_connections.png"
plt.tight_layout()
fig.savefig(out_png, dpi=200)
plt.close(fig)

print(f"Visualization saved to: {out_png}")
print(f"Number of alternate tellings: {len(alts)}")

