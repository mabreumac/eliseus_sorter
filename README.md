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
4. **Ref folder skip** — wrapper folders between the naming ref root and student names (default: 0)  
5. **Class if faces >** — photos with more faces than this count define a class (default: 5)  
6. **Duplicate group photos** — when checked, group photos are also copied into each matched person folder  
7. Click **Sort photos**

### Input and output

- **Different folders** — photos are **copied** into the output structure; originals stay in the input folder.  
- **Same folder** — photos are **moved** into sorted subfolders. Extra copies are only created when a file must appear in more than one place (e.g. a group photo duplicated into person folders).

If your **Input** folder has immediate subfolders, each one is sorted separately into `run_<folder_name>/` under **Output**.

---

## Optional: name students automatically

Point **Naming ref** at a folder of reference portraits — one subfolder per student, at least one clear single-face photo each (photos can be in subfolders under the student folder).

**Default layout** (`Ref folder skip = 0`):

```
naming_reference/
  Maria_Silva/
    portrait.jpg
  Joao_Santos/
    photos/
      photo.jpg
```

**With wrapper folders** (`Ref folder skip = 1`):

```
naming_reference/
  export_2024/          ← skipped
    Maria_Silva/
      portrait.jpg
    Joao_Santos/
      photo.jpg
```

Matched output folders are renamed from `Person_001` to the student folder name.

---

## What you get

```
output/
  class_001/
    _class_photos/      ← large class group shot
    _group_photos/      ← smaller group photos
    Maria_Silva/        ← one student (or Person_001 without naming ref)
  _unmatched/           ← no face detected
```

With **Duplicate group photos** unchecked (default), multi-face photos go only to `_group_photos` (or `_class_photos` for class shots), not into individual student folders.

---

## Help

| Issue | Fix |
|-------|-----|
| App won’t open | Right-click → **Open** → **Open**; see **`logs/app.log`** in the project folder |
| Setup failed | See **`logs/install.log`** — then re-run **`installer.command`** |
| Missing numpy / packages | Re-run **`installer.command`** (reinstalls the full environment) |
| Slow first sort | Normal — face models download once (~100 MB) |
| Wrong student names | Check naming ref layout and **Ref folder skip** |

Settings: `~/Library/Application Support/Eliseus Sorter/`  
Logs: **`logs/`** in the project folder (same folder as `installer.command`)

---

## Privacy

All face detection and sorting happens on your computer. Photos are not uploaded anywhere.

---

For development, CLI usage, and benchmarks, see [DEVELOPING.md](DEVELOPING.md).
