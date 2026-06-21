# Eliseus Sorter

Desktop photo organizer for macOS. Detects faces with **InsightFace** (RetinaFace + ArcFace CNN), groups identities through **unsupervised clustering**, and optionally assigns human-readable labels via **reference matching** — entirely on your machine.

**Requires macOS 12 or later.**

---

## How it works

| Stage | Method |
|-------|--------|
| **Detection & embedding** | InsightFace `buffalo_l` — RetinaFace bounding boxes, ArcFace 512-D embeddings (cosine similarity) |
| **Roster groups** | Large multi-face photos seed per-group identity clusters; overlapping rosters merge automatically |
| **Assignment** | Remaining faces matched to the nearest cluster centroid above a similarity threshold |
| **Naming** *(optional)* | Reference library of labeled portraits; cluster centroids matched to reference embeddings |
| **Output** | Files copied or moved into `class_*/Person_*` folders (or flat `Person_*` mode) |

No cloud API. Models run locally via ONNX Runtime (CPU or Apple CoreML GPU when available).

---

## Install

```bash
git clone https://github.com/mabreumac/eliseus_sorter.git
cd eliseus_sorter
bash installer.command
```

Or double-click **`installer.command`** in Finder.

One step installs Homebrew and Python if needed, Python dependencies, and builds **`~/Applications/Eliseus Sorter.app`** (~10–15 minutes, internet required).

Open from **Applications** or Spotlight — no extra setup on first launch.

If macOS blocks the app: **right-click → Open → Open**.

### Installer prompts

| Prompt | Action |
|--------|--------|
| **Install Eliseus Sorter now?** | Click **Install** |
| **Mac password** | Required once for Homebrew (if missing) |
| **Xcode Command Line Tools** | Install, then re-run `installer.command` |

Logs: **`logs/install.log`**

### Requirements

| Requirement | Notes |
|-------------|--------|
| macOS 12+ | Apple Silicon or Intel |
| Internet | First install and model download |
| ~2 GB disk | Packages + InsightFace weights |

---

## Use the app

1. **Input** — photos to sort  
2. **Output** — destination folder  
3. **Naming ref** *(optional)* — labeled reference portraits (see below)  
4. **Ref folder skip** — folder levels **up** from each reference photo to the identity label  
5. **Group if faces >** — photos with more faces than this define a roster group (default: 5)  
6. **Duplicate group photos** — also copy multi-face images into each matched person folder  
7. **Scan workers** — parallel inference (`1` = safest; up to `8` or custom; more RAM per worker)  
8. **Background faces** — slider to ignore distant/bokeh detections (strict ← → permissive)  
9. **Move files** — relocate instead of copy (unchecked = copy)  
10. **Acceleration** — `Auto` prefers CoreML on Apple Silicon  
11. **Sort photos**

Progress shows scan, cluster, naming, and copy phases plus memory, CPU, and elapsed time.

### Input / output behavior

- **Copy** (default) — originals stay in the input folder; sorted photos go to output.  
- **Move** — matched photos are relocated; source folders may be left empty. Extra copies still apply when one file must appear in multiple destinations (e.g. group photos).  
- **Nested input** — all images under every subfolder are treated as **one pool**. When input contains subfolders, output is written to `YYYYMMDD_HHMMSS_eliseus_sorter/` under your chosen output folder.  
- Use the **Move files** checkbox in the app (or `--move` in the CLI) instead of inferring behavior from paths.

---

## Optional: reference matching

Provide a **Naming ref** folder of labeled portraits. The app discovers every image underneath, extracts a face embedding, and walks **up** N folder levels to read the identity label.

| Ref folder skip | Label folder is… |
|-----------------|------------------|
| **0** | Parent folder of the image |
| **1** | One level above that |
| **2** | Two levels above that |

Example (`skip = 1` → label `person_a`):

```
reference_library/
  batch_2024/
    set_01/
      person_a/
        images/
          portrait.jpg
```

Each label needs at least one clear **single-face** image. Clusters rename from `Person_001` to the matched label when similarity exceeds the configured threshold.

---

## Output layout

```
output/
  class_001/
    _class_photos/      ← roster seed images (large groups)
    _group_photos/      ← smaller multi-face images
    person_a/           ← matched identity (or Person_001 without reference)
  _no_class/            ← faces outside any roster (still clustered)
    Person_001/
  _unmatched/           ← no face or unreadable file
```

- Duplicate roster photos with ≥ 50% face overlap merge into one `class_*` folder.  
- Low-confidence or very small detections are filtered to reduce false multi-face classification.  
- CLI **`--flat`** skips roster groups and writes `Person_*` at the output root ([DEVELOPING.md](DEVELOPING.md)).

---

## Performance

| Setting | Recommendation |
|---------|----------------|
| **Acceleration → Auto** | Best on Apple Silicon (CoreML) |
| **Scan workers → 1** | Safest with GPU acceleration |
| **Scan workers → 2–8** | Good on 16 GB+ systems; custom for higher counts |

Tune defaults in `code/config.py`, then rebuild with **`installer.command`** or **`bash code/build_mac_app.sh`**.

| Constant | Default | Effect |
|----------|---------|--------|
| `MIN_FACE_AREA_RATIO` | `0.12` | Ignore tiny background detections (or use GUI slider) |
| `MIN_FACE_DET_SCORE` | `0.45` | Minimum detector confidence (linked to slider) |
| `MAX_IMAGE_WIDTH` | `1024` | Pre-scale before inference |
| `MATCH_TOLERANCE` | `0.4` | Minimum cosine similarity to merge identities |

---

## Help

| Issue | Fix |
|-------|-----|
| App won't open | Right-click → **Open**; check **`logs/app.log`** |
| Setup failed | **`logs/install.log`** → re-run **`installer.command`** |
| Slow first run | InsightFace models download once (~100 MB) |
| Wrong labels | Verify reference layout and **Ref folder skip** |
| False group detection | Raise `MIN_FACE_AREA_RATIO` in `config.py` |
| No roster in batch | Lower **Group if faces** or use **`--flat`** |

Settings: `~/Library/Application Support/Eliseus Sorter/settings.json`  
Logs: **`logs/`** in the project folder

---

## Privacy

All inference and file operations run locally. Images are not transmitted to external services.

---

Development, CLI, and benchmarks: [DEVELOPING.md](DEVELOPING.md).

---

Built with assistance from [Cursor](https://cursor.com).
