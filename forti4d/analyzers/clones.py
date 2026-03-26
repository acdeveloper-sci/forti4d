"""
clones.py
Compares same-named units across files to detect whether they are identical,
similar, or diverged copies.

Reads the duplicate-unit list from dep_00_ambiguedades.csv, extracts and
normalizes the source of each unit, and performs pairwise comparison.

Output: reporte_clones.csv  — one row per (unit, file_A, file_B) pair.
"""

import csv
import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from forti4d.analyzers.inventario import cargar_inventario
from forti4d.lib.reader_logical import read_logical_lines
from forti4d.config import CARPETA_CODIGO, RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
AMBIGUEDADES = RUTA_RESULTADOS / "dep_00_ambiguedades.csv"
SALIDA_CSV   = RUTA_RESULTADOS / "reporte_clones.csv"

# Umbral de similitud: >= este valor → SIMILAR; == 1.0 → IDENTICO
UMBRAL_SIMILAR = 0.80


# =============================================================================
# EXTRACCIÓN Y NORMALIZACIÓN
# =============================================================================

def construir_indice_archivos(carpeta: Path) -> dict:
    """Returns dict: basename → full Path for all Fortran source files."""
    index = {}
    for f in carpeta.rglob("*"):
        if f.suffix.lower() in (".f90", ".f", ".for", ".f77", ".f95", ".f03"):
            index[f.name] = f
    return index


def extraer_lineas_unidad(ruta: Path, inicio: int, fin: int) -> list:
    """
    Reads a Fortran source file and returns the normalized logical lines
    belonging to the unit at [inicio, fin].

    Normalization: comments and blank lines removed, whitespace collapsed,
    text uppercased.
    """
    try:
        logical_lines = read_logical_lines(str(ruta))
    except Exception:
        return []

    resultado = []
    for ll in logical_lines:
        if ll.start_line < inicio:
            continue
        if ll.start_line > fin:
            break
        if ll.is_comment or not ll.text.strip():
            continue
        normalizado = " ".join(ll.text.upper().split())
        resultado.append(normalizado)
    return resultado


def similitud(lineas_a: list, lineas_b: list) -> float:
    if not lineas_a and not lineas_b:
        return 1.0
    if not lineas_a or not lineas_b:
        return 0.0
    return SequenceMatcher(None, lineas_a, lineas_b).ratio()


def clasificar(ratio: float) -> str:
    if ratio >= 1.0:
        return "IDENTICO"
    if ratio >= UMBRAL_SIMILAR:
        return "SIMILAR"
    return "DIVERGIDO"


# =============================================================================
# MAIN
# =============================================================================

def main():
    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)

    # Load inventory
    inventario = cargar_inventario()
    if not inventario:
        print("ERROR: inventario vacío. Ejecuta inventario.py primero.")
        return

    # Index: (archivo_basename, nombre_upper) → {tipo, inicio, fin}
    inv_idx = {}
    for row in inventario:
        key = (row["Archivo"], row["Nombre"].upper())
        inv_idx[key] = {
            "tipo":   row["Tipo"],
            "inicio": int(row["Linea_Inicio"]),
            "fin":    int(row["Linea_Fin"]),
        }

    # Load ambiguedades
    if not AMBIGUEDADES.exists():
        print(f"ERROR: {AMBIGUEDADES} no encontrado. Ejecuta dependencias.py primero.")
        return

    grupos = []  # [(nombre, tipo, [archivo1, archivo2, ...])]
    with open(AMBIGUEDADES, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nombre  = row["Nombre_Unidad"].strip().upper()
            tipo    = row["Tipo"].strip()
            archivos = [a.strip() for a in row["Lista_Archivos"].split(";") if a.strip()]
            if len(archivos) >= 2:
                grupos.append((nombre, tipo, archivos))

    if not grupos:
        print("No hay unidades duplicadas.")
        _escribir_vacio()
        return

    # Build file path index
    arch_idx = construir_indice_archivos(CARPETA_CODIGO)

    # Pairwise comparisons
    filas = []
    for nombre, tipo, archivos in grupos:
        for i in range(len(archivos)):
            for j in range(i + 1, len(archivos)):
                arch_a = archivos[i]
                arch_b = archivos[j]

                info_a = inv_idx.get((arch_a, nombre))
                info_b = inv_idx.get((arch_b, nombre))
                if not info_a or not info_b:
                    continue

                ruta_a = arch_idx.get(arch_a)
                ruta_b = arch_idx.get(arch_b)
                if not ruta_a or not ruta_b:
                    continue

                lineas_a = extraer_lineas_unidad(ruta_a, info_a["inicio"], info_a["fin"])
                lineas_b = extraer_lineas_unidad(ruta_b, info_b["inicio"], info_b["fin"])

                ratio  = similitud(lineas_a, lineas_b)
                estado = clasificar(ratio)

                filas.append({
                    "Nombre":        nombre,
                    "Tipo":          tipo,
                    "Archivo_A":     arch_a,
                    "Archivo_B":     arch_b,
                    "SLOC_A":        len(lineas_a),
                    "SLOC_B":        len(lineas_b),
                    "Similitud_Pct": round(ratio * 100, 1),
                    "Estado":        estado,
                })

    # Sort: diverged first, then similar, then identical; then by name
    _orden = {"DIVERGIDO": 0, "SIMILAR": 1, "IDENTICO": 2}
    filas.sort(key=lambda r: (_orden[r["Estado"]], r["Nombre"]))

    campos = ["Nombre", "Tipo", "Archivo_A", "Archivo_B",
              "SLOC_A", "SLOC_B", "Similitud_Pct", "Estado"]
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    n_id  = sum(1 for r in filas if r["Estado"] == "IDENTICO")
    n_sim = sum(1 for r in filas if r["Estado"] == "SIMILAR")
    n_div = sum(1 for r in filas if r["Estado"] == "DIVERGIDO")

    print(f"\n{len(filas)} pares comparados  ({len(grupos)} unidades con duplicados)")
    print(f"  IDENTICO  : {n_id}")
    print(f"  SIMILAR   : {n_sim}")
    print(f"  DIVERGIDO : {n_div}")
    print(f"\nGenerado: {SALIDA_CSV}")


def _escribir_vacio():
    campos = ["Nombre", "Tipo", "Archivo_A", "Archivo_B",
              "SLOC_A", "SLOC_B", "Similitud_Pct", "Estado"]
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=campos).writeheader()


if __name__ == "__main__":
    main()
