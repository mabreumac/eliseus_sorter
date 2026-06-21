# Eliseus Sorter

Sorts school photos by face into folders — no names required upfront.

Give it a folder of unsorted photos and an output folder. It detects faces, groups similar ones together, and copies files into `Person_001`, `Person_002`, … Multi-face photos go to `Grupo`. Originals are never moved.

Everything runs locally on your Mac (InsightFace). No cloud upload.

---

## Mac app

1. Double-click **`Install to Applications.command`**
2. Open **Eliseus Sorter** from Applications (or Spotlight)
3. On first launch, click **Install** in the dialog (~10–15 min, one time)
4. Choose **Input** and **Output**, then click **Sort photos**

If macOS blocks the app: right-click → **Open** → **Open**.

---

## CLI

One-time setup:

```bash
bash code/install.sh
```

Sort photos:

```bash
python code/main.py --input /path/to/photos --output /path/to/sorted
```

Or launch the GUI from the project folder:

```bash
bash code/launch.sh
```

---

## Output

| Folder | Contents |
|--------|----------|
| `Person_001/`, `Person_002/`, … | One person per folder |
| `Grupo/` | Photos with multiple faces |
| `_unmatched/` | No face detected |
| `_sort_log.csv` | Copy log |

Requires **Python 3.10+** and **macOS 12+**. First run downloads face models (~100 MB).
