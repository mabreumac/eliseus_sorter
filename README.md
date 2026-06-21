# Eliseus Sorter

Sort school photos by face into class and student folders. Everything runs on your Mac — nothing is uploaded.

**Requires macOS 12 or later.**

---

## Install

Double-click **`installer.command`**, or run in Terminal:

```bash
bash installer.command
```

Open **Eliseus Sorter** from Applications (or Spotlight).

The first time you open the app, click **Install** when asked. This downloads libraries once (~10–15 minutes, internet required).

If macOS says the app is from an unidentified developer: **right-click the app → Open → Open**.

---

## Use the app

1. **Input** — folder with your photos  
2. **Output** — where sorted copies should go  
3. **Naming ref** *(optional)* — reference portraits (see below)  
4. **Class if faces >** — photos with more faces than this count define a class (default: 5)  
5. Click **Sort photos**

Original photos are never moved or deleted.

---

## Optional: name students automatically

Point **Naming ref** at a folder like this — one subfolder per student, one clear portrait each:

```
naming_reference/
  Maria_Silva/
    portrait.jpg
  Joao_Santos/
    photo.jpg
```

Matched folders are renamed from `Person_001` to the subfolder name.

---

## What you get

```
output/
  class_001/
    _class_photos/      ← large class group shot
    _group_photos/      ← smaller group photos
    Maria_Silva/        ← one student (or Person_001)
  _unmatched/           ← no face detected
```

If your **Input** folder has subfolders, each is sorted separately into `run_folder_name/` under **Output**.

---

## Help

| Issue | Fix |
|-------|-----|
| App won’t open | Right-click → **Open** → **Open**; check `~/Library/Application Support/Eliseus Sorter/logs/app.log` |
| Two copies of the app | Use **Applications** only; remove any old copy from the Dock or project folder |
| Setup failed | See `~/Library/Application Support/Eliseus Sorter/logs/install.log` |
| Slow first sort | Normal — face models download once (~100 MB) |

Settings and logs: `~/Library/Application Support/Eliseus Sorter/`

---

## Privacy

All face detection and sorting happens on your computer. Photos stay where you put them unless you copy them elsewhere.

For development and benchmarking, see [DEVELOPING.md](DEVELOPING.md).
