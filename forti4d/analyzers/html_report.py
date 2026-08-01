"""
html_report.py
Generates a self-contained HTML report from report_prioritization.csv.

Output: report.html — single file, inline CSS and JS, no external dependencies.

Sections:
  1. Header — project name, generation date, global totals
  2. Priority summary — count and % per tier
  3. Main table — all units, filterable by priority, sortable by column
"""

import csv
import html
from datetime import datetime
from pathlib import Path

from forti4d import config

# Visible columns in the main table: (CSV_field, display_label)
TABLE_COLUMNS = [
    ("Priority", "Priority"),
    ("Score", "Score"),
    ("File", "File"),
    ("Unit", "Unit"),
    ("Type", "Type"),
    ("CC", "CC"),
    ("Fan_In", "Fan-In"),
    ("Pct_Legacy", "Pct_Legacy"),
    ("Reachability_Status", "Reachability"),
    ("Strategy", "Strategy"),
    ("Implicit_None", "Impl.None"),
    ("Has_Equiv", "Equiv"),
]

PRIORITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "DEAD_CODE"]

TIER_COLORS = {
    "CRITICAL": "#c0392b",
    "HIGH": "#e67e22",
    "MEDIUM": "#f1c40f",
    "LOW": "#27ae60",
    "DEAD_CODE": "#95a5a6",
}

TIER_TEXT_COLORS = {
    "CRITICAL": "#ffffff",
    "HIGH": "#ffffff",
    "MEDIUM": "#333333",
    "LOW": "#ffffff",
    "DEAD_CODE": "#ffffff",
}


def data_load(rows=None, results_dir=None):
    """Uses in-memory `rows` if given, otherwise reads
    report_prioritization.csv from results_dir."""
    if rows is not None:
        return rows
    priority_csv = Path(results_dir) / "report_prioritization.csv"
    if not priority_csv.exists():
        print(f"ERROR: {priority_csv} not found. Run prioritization.py first.")
        return []
    with open(priority_csv, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _badge(priority):
    bg = TIER_COLORS.get(priority, "#cccccc")
    fg = TIER_TEXT_COLORS.get(priority, "#000000")
    txt = html.escape(priority)
    return f'<span class="badge" ' f'style="background:{bg};color:{fg}">{txt}</span>'


def _td(value, field):
    v = html.escape(str(value)) if value is not None else ""
    if field == "Priority":
        return f"<td>{_badge(value)}</td>"
    return f"<td>{v}</td>"


def generate_html(rows):
    date_ = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(rows)

    # Count per tier
    count = {t: 0 for t in PRIORITY_ORDER}
    for r in rows:
        p = r.get("Priority", "")
        if p in count:
            count[p] += 1

    # ---- CSS ----------------------------------------------------------------
    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       font-size: 13px; color: #222; background: #f4f6f8; }
header { background: #2c3e50; color: #fff; padding: 18px 24px; }
header h1 { font-size: 1.4em; font-weight: 600; }
header p  { font-size: 0.85em; opacity: 0.75; margin-top: 4px; }
.container { padding: 20px 24px; }

/* Summary cards */
.summary { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.card { border-radius: 6px; padding: 12px 20px; min-width: 110px; text-align: center; }
.card .tier  { font-size: 0.75em; font-weight: 700; letter-spacing: 0.05em; }
.card .count { font-size: 2em; font-weight: 700; line-height: 1.1; }
.card .pct   { font-size: 0.8em; opacity: 0.85; }

/* Filter buttons */
.filters { margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filters span { font-size: 0.8em; color: #666; }
.btn { border: none; border-radius: 4px; padding: 5px 14px; cursor: pointer;
       font-size: 0.8em; font-weight: 600; transition: opacity 0.15s; }
.btn.active { outline: 2px solid #2c3e50; outline-offset: 2px; }
.btn:hover { opacity: 0.85; }
.btn-all { background: #2c3e50; color: #fff; }

/* Table */
.table-wrap { overflow-x: auto; border-radius: 6px;
              box-shadow: 0 1px 4px rgba(0,0,0,0.10); }
table { border-collapse: collapse; width: 100%; background: #fff; }
thead th { background: #2c3e50; color: #fff; padding: 9px 12px;
           text-align: left; font-size: 0.78em; letter-spacing: 0.04em;
           white-space: nowrap; cursor: pointer; user-select: none; }
thead th:hover { background: #34495e; }
thead th.sorted-asc::after  { content: " ▲"; }
thead th.sorted-desc::after { content: " ▼"; }
tbody tr:nth-child(even) { background: #f9fafb; }
tbody tr:hover { background: #eaf2ff; }
tbody td { padding: 7px 12px; border-bottom: 1px solid #eee;
           white-space: nowrap; max-width: 220px;
           overflow: hidden; text-overflow: ellipsis; }
.badge { display: inline-block; border-radius: 3px; padding: 2px 8px;
         font-size: 0.75em; font-weight: 700; letter-spacing: 0.04em; }
.hidden { display: none; }
footer { text-align: center; padding: 16px; color: #999; font-size: 0.78em; }
"""

    # ---- Summary cards -------------------------------------------------------
    cards_html = []
    for tier in PRIORITY_ORDER:
        n = count[tier]
        pct = f"{n/total*100:.1f}%" if total else "0%"
        bg = TIER_COLORS[tier]
        fg = TIER_TEXT_COLORS[tier]
        cards_html.append(
            f'<div class="card" style="background:{bg};color:{fg}">'
            f'<div class="tier">{tier}</div>'
            f'<div class="count">{n}</div>'
            f'<div class="pct">{pct}</div>'
            f"</div>"
        )
    cards_html.append(
        f'<div class="card" style="background:#2c3e50;color:#fff">'
        f'<div class="tier">TOTAL</div>'
        f'<div class="count">{total}</div>'
        f'<div class="pct">100%</div>'
        f"</div>"
    )

    # ---- Filter buttons ------------------------------------------------------
    filter_buttons = [
        "<span>Filter:</span>",
        '<button class="btn btn-all active" onclick="filterBy(\'ALL\')">All</button>',
    ]
    for tier in PRIORITY_ORDER:
        bg = TIER_COLORS[tier]
        fg = TIER_TEXT_COLORS[tier]
        filter_buttons.append(
            f'<button class="btn" style="background:{bg};color:{fg}" ' f"onclick=\"filterBy('{tier}')\">{tier}</button>"
        )

    # ---- Table headers -------------------------------------------------------
    th_list = []
    for i, (_, label) in enumerate(TABLE_COLUMNS):
        th_list.append(f'<th onclick="sortTable({i})">{html.escape(label)}</th>')

    # ---- Table rows ----------------------------------------------------------
    rows_html = []
    for r in rows:
        priority = r.get("Priority", "")
        cells = "".join(_td(r.get(field, ""), field) for field, _ in TABLE_COLUMNS)
        rows_html.append(f'<tr data-priority="{html.escape(priority)}">{cells}</tr>')

    # ---- JS ------------------------------------------------------------------
    js = """
var currentFilter = 'ALL';
var sortCol = -1;
var sortAsc = true;

function filterBy(tier) {
    currentFilter = tier;
    var rows = document.querySelectorAll('#mainTable tbody tr');
    rows.forEach(function(row) {
        var p = row.getAttribute('data-priority');
        row.classList.toggle('hidden', tier !== 'ALL' && p !== tier);
    });
    document.querySelectorAll('.btn').forEach(function(b) {
        b.classList.remove('active');
    });
    event.target.classList.add('active');
}

function sortTable(col) {
    var table = document.getElementById('mainTable');
    var tbody = table.querySelector('tbody');
    var rows  = Array.from(tbody.querySelectorAll('tr'));
    var headers = table.querySelectorAll('thead th');

    if (sortCol === col) { sortAsc = !sortAsc; }
    else { sortCol = col; sortAsc = true; }

    headers.forEach(function(h, i) {
        h.classList.remove('sorted-asc', 'sorted-desc');
        if (i === col) h.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
    });

    rows.sort(function(a, b) {
        var va = a.cells[col].textContent.trim();
        var vb = b.cells[col].textContent.trim();
        var na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) {
            return sortAsc ? na - nb : nb - na;
        }
        return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
}
"""

    # ---- Assemble HTML -------------------------------------------------------
    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fortran Static Analysis Report</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>Fortran Static Analysis — Migration Priority Report</h1>
  <p>Generated: {date_} &nbsp;|&nbsp; {total} program units</p>
</header>
<div class="container">

  <div class="summary">
    {"".join(cards_html)}
  </div>

  <div class="filters">
    {"".join(filter_buttons)}
  </div>

  <div class="table-wrap">
    <table id="mainTable">
      <thead><tr>{"".join(th_list)}</tr></thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>

</div>
<footer>Fortran Static Analysis Toolkit &nbsp;|&nbsp; stdlib only, no external dependencies</footer>
<script>{js}</script>
</body>
</html>"""

    return doc


def analyze_html_report(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes. Returns None for report_html when
    there's nothing to process (same as the original — no file is written)."""
    inputs = inputs or {}
    rows = data_load(rows=inputs.get("report_prioritization"), results_dir=results_dir)
    if not rows:
        return {"report_html": None}

    doc = generate_html(rows)
    return {"report_html": doc, "n_units": len(rows)}


def write_html_report(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    doc = data["report_html"]
    if doc is None:
        return  # nothing to process — nothing written at all, same as before

    output_file = Path(results_dir) / "report.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(doc)

    print(f"Generated: {output_file} ({data['n_units']} units)")


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = analyze_html_report(source_dir, results_dir, inputs=inputs)
    write_html_report(results_dir, data)
    return data


if __name__ == "__main__":
    main()
