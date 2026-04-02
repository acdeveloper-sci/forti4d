# html_report.py

## Purpose

Generates a self-contained HTML report from `report_prioritization.csv`.
The output is a single `.html` file with inline CSS and JavaScript — no
external dependencies, no internet connection required to view it.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `PRIORITY_CSV` | `RESULTS_PATH / "report_prioritization.csv"` | Input |
| `HTML_OUTPUT` | `RESULTS_PATH / "report.html"` | Output |

---

## Inputs

- `<FORT_OUT>/report_prioritization.csv` (required)

---

## Output: `<FORT_OUT>/report.html`

Single self-contained HTML file. Sections:

1. **Header** — project title, generation date and time, total unit count
2. **Priority summary** — one card per tier (CRITICAL / HIGH / MEDIUM / LOW /
   DEAD_CODE / TOTAL) showing count and percentage
3. **Main table** — all units from `report_prioritization.csv`, with:
   - Color-coded `Priority` badge per row
   - Filter buttons to show only one priority tier
   - Click-to-sort on every column header (numeric-aware)

### Visible columns

| Column header | Source field |
| :--- | :--- |
| Priority | `Priority` |
| Score | `Score` |
| File | `File` |
| Unit | `Unit` |
| Type | `Type` |
| CC | `CC` |
| Fan-In | `Fan_In` |
| Pct_Legacy | `Pct_Legacy` |
| Reachability | `Reachability_Status` |
| Strategy | `Strategy` |
| Impl.None | `Implicit_None` |
| Equiv | `Has_Equiv` |

---

## Notes

- No third-party Python packages required — standard library only.
- No external CSS frameworks or JavaScript libraries — the HTML file
  is fully standalone.
- Priority tier colors: CRITICAL=red, HIGH=orange, MEDIUM=yellow,
  LOW=green, DEAD_CODE=grey.
- The sort is stable within equal values; numeric columns sort
  numerically, text columns sort lexicographically.
