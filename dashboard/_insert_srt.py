"""One-shot script: insert Task 11b into the plan markdown, then delete itself."""
import os
from pathlib import Path

plan_path = Path(__file__).parent.parent / "docs/superpowers/plans/2026-04-26-drone-mapping-mvp.md"

SRT_TASK = r"""---

## Task 11b: SRT Video Telemetry → Frame Geotagging

**Files:** `backend/services/srt_sync.py`, `backend/routers/srt.py`, modify `backend/main.py`, modify `frontend/src/tabs/SyncTab.jsx`, `tests/test_srt_sync.py`

**Goal:** Geotag JPEG frames extracted from DJI flight videos using the per-second GPS telemetry embedded in the video's `.SRT` subtitle file, combined with the takeoff altitude from the FlightRecord `.TXT`. Covers the workflow where a user shoots video and extracts frames with ffmpeg.

**Data sources used:**
- SRT: `GPS (lon, lat, _) H X.XXm` per-second entries → lat, lon, relative height
- FlightRecord: `Takeoff altitude: X m` header → absolute altitude base
- Altitude math: `GPSAltitude = takeoff_alt_m + SRT_H_m` (e.g. 236.94 + 115.90 = 352.84 m)
- Frame timing: `offset_sec = frame_number / fps` (frame number parsed from filename e.g. `frame_0042.jpg`)

- [ ] **Step 1: Write failing tests (tests/test_srt_sync.py)**

```python
from backend.services.srt_sync import parse_srt, parse_flightrecord_header, match_frames_to_srt

SAMPLE_SRT = """1
00:00:00,000 --> 00:00:01,000
GPS (-81.3382, 41.1509, 24) H 115.90m D 25.00m

2
00:00:01,000 --> 00:00:02,000
GPS (-81.3381, 41.1510, 24) H 116.20m D 25.00m
"""

SAMPLE_FR = """Takeoff altitude: 236.937890625 m
Aircraft Model: DJI Mini 4K
Flight Start Time: 2025-08-06 18:28:47 UTC
"""

def test_parse_srt_count():
    pts = parse_srt(SAMPLE_SRT)
    assert len(pts) == 2

def test_parse_srt_values():
    pts = parse_srt(SAMPLE_SRT)
    assert pts[0]['offset_sec'] == 0
    assert abs(pts[0]['lat'] - 41.1509) < 0.0001
    assert abs(pts[0]['lon'] - (-81.3382)) < 0.0001
    assert abs(pts[0]['alt_rel_m'] - 115.90) < 0.01

def test_parse_flightrecord():
    info = parse_flightrecord_header(SAMPLE_FR)
    assert abs(info['takeoff_alt_m'] - 236.937890625) < 0.001

def test_match_frames_matched():
    pts = parse_srt(SAMPLE_SRT)
    images = [
        {'id': 1, 'filename': 'frame_0000.jpg'},
        {'id': 2, 'filename': 'frame_0030.jpg'},  # 30/30fps = 1.0s
    ]
    matches = match_frames_to_srt(images, pts, fps=30, takeoff_alt_m=236.94, tolerance_sec=2.0)
    assert matches[0]['matched'] is True
    assert matches[0]['offset_sec'] == 0.0
    assert abs(matches[0]['abs_alt_m'] - (236.94 + 115.90)) < 0.1

def test_match_frames_tolerance():
    pts = parse_srt(SAMPLE_SRT)
    images = [{'id': 1, 'filename': 'frame_0300.jpg'}]  # 10s, no SRT point within 2s
    matches = match_frames_to_srt(images, pts, fps=30, takeoff_alt_m=236.94, tolerance_sec=2.0)
    assert matches[0]['matched'] is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_srt_sync.py -v
```

- [ ] **Step 3: Implement backend/services/srt_sync.py**

```python
import re

_GPS_RE  = re.compile(r'GPS\s*\(([\-\d.]+),\s*([\-\d.]+),\s*[\-\d.]+\)')
_H_RE    = re.compile(r'H\s+([\d.]+)m')
_TIME_RE = re.compile(r'(\d{2}):(\d{2}):(\d{2})')
_FRAME_NUM_RE = re.compile(r'_(\d+)\.')

def parse_srt(text: str) -> list:
    """Return [{offset_sec, lat, lon, alt_rel_m}] from a DJI SRT string."""
    points = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].strip() or lines[i].strip().isdigit():
            i += 1; continue
        if '-->' in lines[i]:
            start_str = lines[i].split('-->')[0].strip()
            m = _TIME_RE.match(start_str)
            if m:
                offset = int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
                j = i + 1
                lat = lon = alt = None
                while j < len(lines) and lines[j].strip() and '-->' not in lines[j]:
                    gm = _GPS_RE.search(lines[j])
                    hm = _H_RE.search(lines[j])
                    if gm: lon, lat = float(gm.group(1)), float(gm.group(2))
                    if hm: alt = float(hm.group(1))
                    j += 1
                if lat is not None and alt is not None:
                    points.append({'offset_sec': offset, 'lat': lat, 'lon': lon, 'alt_rel_m': alt})
                i = j; continue
        i += 1
    return points

def parse_flightrecord_header(text: str) -> dict:
    """Extract takeoff altitude from FlightRecord TXT header."""
    result = {'takeoff_alt_m': 0.0, 'flight_start_utc': None}
    for line in text.splitlines():
        m = re.search(r'[Tt]akeoff\s+[Aa]ltitude[\s:]+([0-9.]+)', line)
        if m: result['takeoff_alt_m'] = float(m.group(1))
        m2 = re.search(r'[Ff]light\s+[Ss]tart\s+[Tt]ime[\s:]+(.+UTC)', line)
        if m2: result['flight_start_utc'] = m2.group(1).strip()
    return result

def match_frames_to_srt(images, srt_points, fps=30.0, takeoff_alt_m=0.0, tolerance_sec=2.0):
    """Match extracted video frames to SRT GPS points by video timestamp."""
    results = []
    for img in images:
        nm = _FRAME_NUM_RE.search(img['filename'])
        frame_num  = int(nm.group(1)) if nm else 0
        offset_sec = frame_num / fps
        if not srt_points:
            results.append({'image_id': img['id'], 'filename': img['filename'],
                            'offset_sec': offset_sec, 'matched': False})
            continue
        nearest = min(srt_points, key=lambda p: abs(p['offset_sec'] - offset_sec))
        delta   = abs(nearest['offset_sec'] - offset_sec)
        matched = delta <= tolerance_sec
        results.append({
            'image_id':   img['id'],
            'filename':   img['filename'],
            'offset_sec': offset_sec,
            'lat':        nearest['lat']       if matched else None,
            'lon':        nearest['lon']       if matched else None,
            'alt_rel_m':  nearest['alt_rel_m'] if matched else None,
            'abs_alt_m':  (takeoff_alt_m + nearest['alt_rel_m']) if matched else None,
            'delta_sec':  delta,
            'matched':    matched,
        })
    return results

def apply_srt_geotag(image_paths: dict, matches: list) -> dict:
    """Write GPS EXIF to matched frames. image_paths: {image_id: abs_path}"""
    import piexif
    from PIL import Image as PILImage

    def _to_rational(val):
        frac = int(abs(val) * 1_000_000)
        return (frac, 1_000_000)

    results = {}
    for m in matches:
        iid = m['image_id']
        path = image_paths.get(iid)
        if not path or not m['matched']:
            results[iid] = 'skipped'; continue
        try:
            img = PILImage.open(path)
            exif = piexif.load(img.info.get('exif', b'')) if img.info.get('exif') else {'GPS': {}}
            lat, lon, alt = m['lat'], m['lon'], m['abs_alt_m'] or 0.0
            exif['GPS'] = {
                piexif.GPSIFD.GPSLatitudeRef:  b'N' if lat >= 0 else b'S',
                piexif.GPSIFD.GPSLatitude:     (_to_rational(int(abs(lat))),
                                                _to_rational(int((abs(lat) % 1)*60)),
                                                (int((abs(lat)*3600) % 60 * 1000), 1000)),
                piexif.GPSIFD.GPSLongitudeRef: b'E' if lon >= 0 else b'W',
                piexif.GPSIFD.GPSLongitude:    (_to_rational(int(abs(lon))),
                                                _to_rational(int((abs(lon) % 1)*60)),
                                                (int((abs(lon)*3600) % 60 * 1000), 1000)),
                piexif.GPSIFD.GPSAltitudeRef:  0,
                piexif.GPSIFD.GPSAltitude:     (int(alt * 100), 100),
            }
            img.save(path, exif=piexif.dump(exif))
            results[iid] = 'ok'
        except Exception as e:
            results[iid] = str(e)
    return results
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_srt_sync.py -v
```

- [ ] **Step 5: Write backend/routers/srt.py**

FastAPI router with three endpoints:
- `POST /api/sessions/{id}/srt-sync/upload` — multipart: `srt_file` + optional `flightrecord_file`; parses both, stores in memory dict keyed by session_id
- `GET  /api/sessions/{id}/srt-sync/preview?fps=30&tolerance_sec=1.0` — returns `{matches, matched, total}`
- `POST /api/sessions/{id}/srt-sync/apply?fps=30&tolerance_sec=1.0` — writes EXIF + updates DB lat/lon/alt, returns `{applied, total}`

Register in `backend/main.py`:
```python
from backend.routers import srt as srt_router
app.include_router(srt_router.router)
```

- [ ] **Step 6: Extend frontend GPS Sync tab with Video SRT mode 🤖**

> **Codex prompt:**
> Extend `frontend/src/tabs/SyncTab.jsx` to add a **mode toggle** at the top:
> two buttons `[ Flight Log CSV/TXT ]` and `[ Video SRT ]` (one highlighted at a time).
>
> When **Video SRT** is selected, show a new panel:
> - File input for `.srt` file (required)
> - File input for FlightRecord `.txt` (optional — labeled "FlightRecord .txt (optional — for absolute altitude)")
> - Number input: FPS (default 30, step 1, label "Frame rate (fps)")
> - Number input: Tolerance (default 1.0s, step 0.5)
> - "Upload & Preview" button → POST multipart to `/api/sessions/{id}/srt-sync/upload`, then GET `/api/sessions/{id}/srt-sync/preview?fps=&tolerance_sec=`
> - Preview table: Filename | Offset (s) | Lat | Lon | Altitude (m) | Δt | Status (✅/❌)
> - Match stats badge: "X / Y matched" in emerald (>90%), amber (>50%), or red (<50%)
> - "Apply Geotag" button → POST `/api/sessions/{id}/srt-sync/apply?fps=&tolerance_sec=`; show success or error
> - Amber info box: "Altitude = FlightRecord takeoff alt + SRT relative height H. Frame number parsed from filename (frame_0042.jpg = frame 42 at 30fps = 1.4s offset)."
>
> Keep the existing Flight Log CSV/TXT mode fully working. All Tailwind dark styling. No new dependencies.

- [ ] **Step 7: Commit**

```bash
git add backend/services/srt_sync.py backend/routers/srt.py backend/main.py frontend/src/tabs/SyncTab.jsx tests/test_srt_sync.py
git commit -m "feat: SRT video telemetry geotagging — parse DJI SRT + FlightRecord, match extracted frames by timestamp"
```

---

"""

content = plan_path.read_text(encoding='utf-8')

insert_before = '## Task 12:'
idx = content.find(insert_before)
if idx == -1:
    print('ERROR: Could not find Task 12')
else:
    new_content = content[:idx] + SRT_TASK + content[idx:]
    plan_path.write_text(new_content, encoding='utf-8')
    print(f'Task 11b inserted. New line count: {len(new_content.splitlines())}')

# Self-delete
os.remove(__file__)
print('Script self-deleted.')
