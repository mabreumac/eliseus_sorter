# Eliseus Sorter

Sort school photos by face into class and student folders. Everything runs on your Mac — nothing is uploaded.

**Requires macOS 12 or later.**

---

## Install

### From git

```bash
git clone https://github.com/mabreumac/eliseus_sorter.git
cd eliseus_sorter
bash installer.command
```

Or double-click **`installer.command`** in Finder.

This **one step** installs Homebrew and Python if needed, all libraries (numpy, InsightFace, GUI, etc.), and copies the app to **`~/Applications/Eliseus Sorter.app`**. Takes about 10–15 minutes (internet required).

Open the app from **Applications** or Spotlight — **no second setup** on first launch.

If macOS blocks the app: **right-click → Open → Open**.

### What the installer may ask

| Prompt | Action |
|--------|--------|
| **Install Eliseus Sorter now?** | Click **Install** (default) |
| **Mac password** | Required once for Homebrew (if not already installed) |
| **Xcode Command Line Tools** | Click **Install** in the Apple dialog; then run `installer.command` again |

Logs: **`logs/install.log`** in the project folder.

### Requirements

| Requirement | Notes |
|-------------|--------|
| macOS 12+ | Apple Silicon or Intel |
| Internet | Required for the installer |
| ~2 GB free disk | Python packages and face models |

---

## Use the app

1. **Input** — folder with your photos  
2. **Output** — where sorted photos should go  
3. **Naming ref** *(optional)* — reference portraits to name students (see below)  
4. **Ref folder skip** — how many folder levels to walk **up** from each reference photo to the student name (see below)  
5. **Class if faces >** — photos with more faces than this count define a class (default: 5)  
6. **Duplicate group photos** — when checked, group photos are also copied into each matched person folder  
7. **Scan workers** — parallel face scanning (`1` = safest; `2–4` = faster, more RAM)  
8. **Acceleration** — `Auto` uses Apple GPU (CoreML) on M-series Macs when available; `CPU only` to disable  
9. Click **Sort photos**

While sorting, the app shows **phase progress** (scan, cluster, naming, copy), **elapsed time**, **memory**, and **CPU** usage.

### Input and output

- **Different folders** — photos are **copied** into the output structure; originals stay in the input folder.  
- **Same folder** — photos are **moved** into sorted subfolders. Extra copies are only created when a file must appear in more than one place (e.g. a group photo duplicated into person folders).

If your **Input** folder has immediate subfolders, each one is sorted separately into `run_<folder_name>/` under **Output**.

---

## Optional: name students automatically

Point **Naming ref** at a folder of reference portraits. The app finds **every photo** under that folder, then derives each student name by walking **up** from the photo’s folder (depth-agnostic — JPGs can be in any subfolder).

**Ref folder skip** = levels **up** from the folder that holds the JPG:

| Skip | Student name is… |
|------|------------------|
| **0** | The folder that directly contains the photo |
| **1** | One folder above that |
| **2** | Two folders above that |

**Example** — same student, photo nested deep (`skip = 1` → `Maria`):

```
naming_reference/
  2024/
    ClassA/
      Maria/
        pics/
          portrait.jpg
```

**Example** — photo directly in the student folder (`skip = 0`):

```
naming_reference/
  Maria/
    portrait.jpg
```

Each student needs at least one clear **single-face** photo. Matched output folders are renamed from `Person_001` to that student name.

---

## What you get

```
output/
  class_001/
    _class_photos/      ← large class group shots (6+ faces by default)
    _group_photos/      ← smaller group photos for this class
    Maria_Silva/        ← matched student (or Person_001 without naming ref)
  class_002/
    ...
  _no_class/            ← faces that did not match any class roster (still clustered)
    Person_001/
    _group_photos/
  _unmatched/           ← no face detected or unreadable image
```

- **Multiple class photos of the same class** merge into one `class_001` folder when ≥ 50% of faces match.  
- With **Duplicate group photos** unchecked (default), multi-face photos go only to `_group_photos` / `_class_photos`, not into individual student folders.  
- Portraits with **blurred faces in the background** are less likely to count as group photos (small/low-confidence detections are filtered).

---

## Performance (GUI & defaults)

| Setting | Recommendation |
|---------|----------------|
| **Acceleration → Auto** | Best on Apple Silicon (uses CoreML GPU) |
| **Scan workers → 1** | Safest RAM use; use with GPU |
| **Scan workers → 2** | Good balance on 16 GB Macs |
| **Scan workers → 3–4** | Faster scan; ~200 MB RAM per extra worker |

After changing defaults in `code/config.py`, rebuild with **`installer.command`** or **`bash code/build_mac_app.sh`**.

Useful `config.py` knobs:

| Constant | Default | Effect |
|----------|---------|--------|
| `MIN_FACE_AREA_RATIO` | `0.12` | Ignore background faces much smaller than the main subject; `0` = off |
| `MIN_FACE_DET_SCORE` | `0.45` | Drop low-confidence face detections |
| `MAX_IMAGE_WIDTH` | `1024` | Lower = faster scan, less accurate on tiny faces |
| `SCAN_WORKERS` | `0` (→ 1 in app) | Default parallel scan processes in bundled config |

---

## Help

| Issue | Fix |
|-------|-----|
| App won’t open | Right-click → **Open** → **Open**; see **`logs/app.log`** in the project folder |
| Setup failed | See **`logs/install.log`** — then re-run **`installer.command`** |
| Missing numpy / packages | Re-run **`installer.command`** (reinstalls the full environment) |
| Slow first sort | Normal — face models download once (~100 MB) |
| Wrong student names | Check naming ref layout and **Ref folder skip** (walk-up from each photo) |
| Portraits treated as group photos | Raise `MIN_FACE_AREA_RATIO` in `config.py` (e.g. `0.18`) and rebuild |
| Real group rows missing faces | Lower `MIN_FACE_AREA_RATIO` slightly (e.g. `0.08`) |
| No class photos in batch | Need at least one photo with more than **Class if faces** count, or use CLI **`--flat`** (see [DEVELOPING.md](DEVELOPING.md)) |
| GPU + high RAM use | Use **Scan workers = 1** with **Acceleration = Auto** |

Settings: `~/Library/Application Support/Eliseus Sorter/settings.json`  
Logs: **`logs/`** in the project folder (same folder as `installer.command`)

---

## Privacy

All face detection and sorting happens on your computer. Photos are not uploaded anywhere.

---

For development, CLI usage, and benchmarks, see [DEVELOPING.md](DEVELOPING.md).
