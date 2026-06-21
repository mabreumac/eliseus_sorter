# Eliseus Sorter — Installation (Mac)

## Option A — Install as a Mac app (recommended)

1. Double-click **`Install to Applications.command`**
2. Enter your Mac password when asked (copies the app to `/Applications`)
3. Open **Eliseus Sorter** from Launchpad or the Applications folder
4. On **first launch**, click **Install** in the dialog (one-time setup, ~10–15 min)

**Where things live:**

| Item | Location |
|------|----------|
| App | `/Applications/Eliseus Sorter.app` |
| Your photos & database | `~/Library/Application Support/Eliseus Sorter/data/` |
| Python environment | `~/Library/Application Support/Eliseus Sorter/venv/` |
| Logs | `~/Library/Application Support/Eliseus Sorter/logs/` |

No Terminal windows. No `.command` files needed after this.

---

## Option B — Run from the project folder

No coding experience needed. Two double-clicks.

## What you need

- A Mac running macOS 12 or newer (recommended)
- **Python 3.10 or newer** (macOS often ships with 3.9 — the installer will help)
- An internet connection (first install only)
- About 10–15 minutes the first time (downloads libraries)

---

## Python 3.9 on your Mac?

macOS includes **Python 3.9**, which is too old. The installer will try to fix this automatically:

1. Look for Python 3.10+ already installed (`python3.12`, Homebrew, etc.)
2. If Homebrew is installed → download **Python 3.12** for you
3. If not → show a link to [python.org/downloads](https://www.python.org/downloads/macos/)

**Recommended (easiest):** install [Homebrew](https://brew.sh), then double-click **`install.command`** again.

**Manual alternative:**
1. Download **Python 3.12** from [python.org/downloads/macos](https://www.python.org/downloads/macos/)
2. Run the installer (click through, keep defaults)
3. Double-click **`install.command`** again

---

## Step 1 — Install (one time)

1. Open this project folder in **Finder**.
2. Double-click **`install.command`**.

   **First time only:** macOS may say the file is from an unidentified developer.
   - Right-click **`install.command`** → **Open** → **Open** again.

3. If a dialog asks to install **Command Line Tools**, click **Install** and wait.
4. When you see **Installation complete!**, press **Enter** to close the window.

You only need to do this once per Mac (or again after moving the folder).

---

## Step 2 — Open the app

Double-click **`Eliseus Sorter.command`**.

The desktop window opens. Use **Browse…** to pick your photo folders, or use the default `data/` folders inside this project.

---

## Where to put photos

```
data/
  ground_truth/
    Maria_Silva/     ← one folder per student
      photo1.jpg
    Joao_Santos/
      photo1.jpg
  test_subset/       ← loose photos to identify
    IMG_001.jpg
    IMG_002.jpg
```

Then in the app: **Build reference** → **Match photos** (or **Run all**).

Reports are saved in `data/output/` as CSV and JSON. Original files are never moved.

---

## Troubleshooting

| Problem | What to do |
|--------|------------|
| “Python 3.10 or newer is required” (you have 3.9) | Install [Homebrew](https://brew.sh), then run **Install** again — it will fetch Python 3.12. Or install Python 3.12 from [python.org/downloads](https://www.python.org/downloads/macos/). |
| **`No module named '_tkinter'`** | Run **Install.command** again — it installs `python-tk` via Homebrew automatically. Or manually: `brew install python-tk@3.11` then re-run Install. |
| “Python 3 was not found” | Install Python from [python.org/downloads](https://www.python.org/downloads/macos/) (3.12+), then run **Install** again. |
| Install stops on **dlib** | Install [Homebrew](https://brew.sh), then run **Install** again. |
| App says “not installed yet” | Run **`install.command`** first. |
| Nothing happens when double-clicking | Right-click → **Open**, or open **Terminal**, drag the `.command` file in, press Enter. |
| Very slow first run | Normal — face libraries are large; later runs are faster. |

---

## For technical users (optional)

```bash
bash scripts/install.sh
bash scripts/launch.sh

# CLI instead of GUI:
cd code && ../.venv/bin/python main.py all
```

---

## Privacy note

Everything runs **on your Mac**. Photos and the database (`data/school_photos.db`) stay on your machine unless you copy them elsewhere.

Face matching uses **pre-trained model files** from the official
[`face_recognition_models`](https://github.com/ageitgey/face_recognition_models)
package (same author as `face_recognition`). They are downloaded once during
install and stored inside your `.venv` folder. **No photos or face data are sent
to the cloud** — all detection and matching happens locally offline.
