# Eliseus Sorter — Installation (Mac)

No coding experience needed. Two double-clicks.

## What you need

- A Mac running macOS 12 or newer (recommended)
- An internet connection (first install only)
- About 10–15 minutes the first time (downloads libraries)

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
| “Python 3 was not found” | Install Python from [python.org/downloads](https://www.python.org/downloads/macos/) (3.10+), then run **Install** again. |
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
