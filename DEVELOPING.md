# Developing Eliseus Sorter

## Setup

Run **`installer.command`** once from the project folder (installs everything).

For development without rebuilding the app:

```bash
bash code/install.sh          # Python env only
pip install -r requirements-dev.txt   # adds matplotlib for benchmarks
bash code/launch.sh --local
```

## Benchmark (optional)

```bash
python code/build_test_subset.py
cd code && python benchmark.py all
```

Reports go to `results/`. Test data lives in `data/benchmark/` (not shipped with the app).

## Build & install the Mac app

```bash
bash code/install.sh           # dependencies only (if already run via installer.command)
bash code/build_mac_app.sh     # installs to ~/Applications
```

Or double-click **`installer.command`** to do both in one step.

The app bundle excludes benchmark and dev-only scripts.

## Local dev (run code from this folder)

```bash
bash code/launch.sh --local
```

## CLI

```bash
python code/main.py --input /path/to/photos --output /path/to/sorted
python code/main.py -i /path/in -o /path/out --naming-reference /path/to/names
```
