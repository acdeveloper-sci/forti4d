import os
import csv
from collections import defaultdict
from pathlib import Path

from forti4d.analyzers.inventario import cargar_inventario
from forti4d.config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
RUTA_AUDIT = RUTA_RESULTADOS / "audit"
SALIDA_CSV = RUTA_RESULTADOS / "report_complexity.csv"


# =============================================================================
# LÓGICA DE COMPLEJIDAD CICLOMÁTICA
# =============================================================================

def contar_punto_decision(kind: str, contenido: str) -> int:
    """
    Retorna 1 si la sentencia es un punto de decisión, 0 en caso contrario.

    Reglas (McCabe simplificado):
      IF_CONSTRUCT     → +1  (bloque IF y IF de una línea)
      ELSE_STMT        → +1  solo si es ELSE IF / ELSEIF (ELSE puro = 0)
      DO_CONSTRUCT     → +1  (DO, DO WHILE, DO etiquetado)
      SELECT_CONSTRUCT → +0  (las ramas CASE ya contabilizan los caminos)
      CASE_STMT        → +1  salvo CASE DEFAULT / CLASS DEFAULT
      WHERE_CONSTRUCT  → +1
      FORALL_CONSTRUCT → +1
    """
    lower = contenido.strip().lower()

    if kind == "IF_CONSTRUCT":
        return 1

    if kind == "ELSE_STMT":
        # "else if ..." y "elseif..." son puntos de decisión; "else" y
        # "elsewhere" no lo son.
        return 1 if (lower.startswith("else if") or lower.startswith("elseif")) else 0

    if kind == "DO_CONSTRUCT":
        return 1

    if kind == "SELECT_CONSTRUCT":
        return 0

    if kind == "CASE_STMT":
        # CASE DEFAULT y CLASS DEFAULT son el camino implícito (≡ ELSE).
        if lower.startswith("case default") or lower.startswith("class default"):
            return 0
        return 1

    if kind == "WHERE_CONSTRUCT":
        return 1

    if kind == "FORALL_CONSTRUCT":
        return 1

    return 0


def interpretar_cc(cc: int) -> str:
    if cc <= 10:
        return "LOW"
    if cc <= 20:
        return "MEDIUM"
    if cc <= 50:
        return "HIGH"
    return "CRITICAL"


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def analizar_complejidad():
    print("--- Complejidad Ciclomática de McCabe ---")

    # 1. Cargar inventario
    try:
        inventario_lista = cargar_inventario()
    except Exception as e:
        print(f"ERROR cargando inventario: {e}")
        return

    if not inventario_lista:
        print("El inventario está vacío.")
        return

    print(f"Inventario cargado: {len(inventario_lista)} unidades.")

    # Convertir tipos numéricos y agrupar por archivo
    mapa_unidades_archivo = defaultdict(list)
    for u in inventario_lista:
        archivo = u.get("Archivo", "").strip()
        if not archivo:
            continue
        try:
            u["Start_Line"] = int(u["Start_Line"])
            u["End_Line"]   = int(u["End_Line"])
        except (ValueError, KeyError):
            u["Start_Line"] = 0
            u["End_Line"]   = 0
        mapa_unidades_archivo[archivo].append(u)

    datos_salida = []
    ruta_audit   = RUTA_AUDIT

    archivos_ordenados = sorted(mapa_unidades_archivo.keys(), key=str.lower)

    for idx, nombre_archivo in enumerate(archivos_ordenados):
        debug_file = ruta_audit / f"{nombre_archivo}_DEBUG.csv"

        if not debug_file.exists():
            print(f"  [{idx+1}] Sin DEBUG: {nombre_archivo} — omitido")
            continue

        unidades_en_archivo = mapa_unidades_archivo[nombre_archivo]
        unidades_en_archivo.sort(key=lambda u: u["Start_Line"])

        # Acumuladores: cada unidad parte con CC base = 1
        puntos = defaultdict(int)

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    n_linea = int(row["Linea"])
                except ValueError:
                    continue

                kind      = row.get("Kind", "")
                contenido = row.get("Contenido", "")

                delta = contar_punto_decision(kind, contenido)
                if not delta:
                    continue

                # Scope resolution: unidad más interna que contenga n_linea
                candidatos = [
                    u for u in unidades_en_archivo
                    if u["Start_Line"] <= n_linea <= u["End_Line"]
                ]
                if not candidatos:
                    continue
                scope = max(candidatos, key=lambda u: u["Start_Line"])["Name"]

                puntos[scope] += delta

        # Construir filas de salida para cada unidad del archivo
        for u in unidades_en_archivo:
            nombre = u["Name"]
            cc     = 1 + puntos[nombre]
            datos_salida.append({
                "Archivo":      nombre_archivo,
                "Unidad":       nombre,
                "Type":         u.get("Type", "UNKNOWN"),
                "CC":           cc,
                "Level": interpretar_cc(cc),
                "Start_Line":   u["Start_Line"],
                "End_Line":     u["End_Line"],
                "Total_Lines":  u.get("Total_Lines", 0),
            })

    # 3. Ordenar por CC descendente
    datos_salida.sort(key=lambda x: -x["CC"])

    # 4. Exportar
    columnas = [
        "Archivo", "Unidad", "Type", "CC", "Level",
        "Start_Line", "End_Line", "Total_Lines",
    ]
    try:
        with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(datos_salida)
        print(f"\nReporte generado: {SALIDA_CSV}")
    except IOError as e:
        print(f"Error escribiendo CSV: {e}")
        return

    # 5. Resumen en consola
    from collections import Counter
    conteo   = Counter(r["Level"] for r in datos_salida)
    cc_vals  = [r["CC"] for r in datos_salida]

    print(f"\nDistribution ({len(datos_salida)} units):")
    for nivel in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        n = conteo.get(nivel, 0)
        if n:
            print(f"  {nivel:8}: {n:4}")

    print(f"\nTop 10 unidades más complejas:")
    for r in datos_salida[:10]:
        print(f"  CC={r['CC']:5}  {r['Level']:8}  "
              f"{r['Archivo']:25} {r['Unidad']}")


if __name__ == "__main__":
    analizar_complejidad()
