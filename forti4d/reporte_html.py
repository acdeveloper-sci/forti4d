"""
reporte_html.py
Generates a self-contained HTML report from reporte_priorizacion.csv.

Output: reporte.html — single file, inline CSS and JS, no external dependencies.

Sections:
  1. Header — project name, generation date, global totals
  2. Priority summary — count and % per tier
  3. Main table — all units, filterable by priority, sortable by column
"""

import csv
import html
from datetime import datetime
from pathlib import Path

from config import RUTA_RESULTADOS

PRIORIDAD_CSV = RUTA_RESULTADOS / "reporte_priorizacion.csv"
SALIDA_HTML   = RUTA_RESULTADOS / "reporte.html"

# Visible columns in the main table: (CSV_field, display_label)
COLUMNAS_TABLA = [
    ("Prioridad",     "Prioridad"),
    ("Score",         "Score"),
    ("Archivo",       "Archivo"),
    ("Unidad",        "Unidad"),
    ("Tipo",          "Tipo"),
    ("CC",            "CC"),
    ("Fan_In",        "Fan-In"),
    ("Pct_Legacy",    "Pct_Legacy"),
    ("Estado_Alcanz", "Alcanzabilidad"),
    ("Estrategia",    "Estrategia"),
    ("Implicit_None", "Impl.None"),
    ("Tiene_Equiv",   "Equiv"),
]

PRIORITY_ORDER = ["CRITICA", "ALTA", "MEDIA", "BAJA", "DEAD_CODE"]

TIER_COLORS = {
    "CRITICA":   "#c0392b",
    "ALTA":      "#e67e22",
    "MEDIA":     "#f1c40f",
    "BAJA":      "#27ae60",
    "DEAD_CODE": "#95a5a6",
}

TIER_TEXT_COLORS = {
    "CRITICA":   "#ffffff",
    "ALTA":      "#ffffff",
    "MEDIA":     "#333333",
    "BAJA":      "#ffffff",
    "DEAD_CODE": "#ffffff",
}


def cargar_datos():
    if not PRIORIDAD_CSV.exists():
        print(f"ERROR: {PRIORIDAD_CSV} no encontrado. Ejecuta priorizacion.py primero.")
        return []
    with open(PRIORIDAD_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _badge(prioridad):
    bg  = TIER_COLORS.get(prioridad, "#cccccc")
    fg  = TIER_TEXT_COLORS.get(prioridad, "#000000")
    txt = html.escape(prioridad)
    return (f'<span class="badge" '
            f'style="background:{bg};color:{fg}">{txt}</span>')


def _td(value, field):
    v = html.escape(str(value)) if value is not None else ""
    if field == "Prioridad":
        return f"<td>{_badge(value)}</td>"
    return f"<td>{v}</td>"


def generar_html(filas):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(filas)

    # Count per tier
    conteo = {t: 0 for t in PRIORITY_ORDER}
    for r in filas:
        p = r.get("Prioridad", "")
        if p in conteo:
            conteo[p] += 1

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
        n   = conteo[tier]
        pct = f"{n/total*100:.1f}%" if total else "0%"
        bg  = TIER_COLORS[tier]
        fg  = TIER_TEXT_COLORS[tier]
        cards_html.append(
            f'<div class="card" style="background:{bg};color:{fg}">'
            f'<div class="tier">{tier}</div>'
            f'<div class="count">{n}</div>'
            f'<div class="pct">{pct}</div>'
            f'</div>'
        )
    cards_html.append(
        f'<div class="card" style="background:#2c3e50;color:#fff">'
        f'<div class="tier">TOTAL</div>'
        f'<div class="count">{total}</div>'
        f'<div class="pct">100%</div>'
        f'</div>'
    )

    # ---- Filter buttons ------------------------------------------------------
    filter_buttons = ['<span>Filtrar:</span>',
                      '<button class="btn btn-all active" onclick="filterBy(\'ALL\')">Todas</button>']
    for tier in PRIORITY_ORDER:
        bg = TIER_COLORS[tier]
        fg = TIER_TEXT_COLORS[tier]
        filter_buttons.append(
            f'<button class="btn" style="background:{bg};color:{fg}" '
            f'onclick="filterBy(\'{tier}\')">{tier}</button>'
        )

    # ---- Table headers -------------------------------------------------------
    th_list = []
    for i, (_, label) in enumerate(COLUMNAS_TABLA):
        th_list.append(f'<th onclick="sortTable({i})">{html.escape(label)}</th>')

    # ---- Table rows ----------------------------------------------------------
    rows_html = []
    for r in filas:
        prioridad = r.get("Prioridad", "")
        cells = "".join(_td(r.get(field, ""), field) for field, _ in COLUMNAS_TABLA)
        rows_html.append(
            f'<tr data-priority="{html.escape(prioridad)}">{cells}</tr>'
        )

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
  <p>Generated: {fecha} &nbsp;|&nbsp; {total} program units</p>
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


def main():
    filas = cargar_datos()
    if not filas:
        return

    doc = generar_html(filas)

    with open(SALIDA_HTML, "w", encoding="utf-8") as f:
        f.write(doc)

    print(f"Generado: {SALIDA_HTML} ({len(filas)} unidades)")


if __name__ == "__main__":
    main()
