import csv
from collections import defaultdict
from pathlib import Path

import reader_logical
from inventario import cargar_inventario
from config import CARPETA_CODIGO, RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
SALIDA_CSV = RUTA_RESULTADOS / "reporte_sloc.csv"


# =============================================================================
# CLASIFICACIÓN DE LÍNEAS FÍSICAS
# =============================================================================

# Categorías
BLANK        = "BLANK"
COMMENT      = "COMMENT"
CONTINUATION = "CONTINUATION"
CODE         = "CODE"


def clasificar_fisicas(sentencias: list) -> dict:
    """
    A partir de la lista de LogicalLines devuelta por reader_logical,
    construye un dict  linea_fisica (int) -> categoría (str).

    Reglas:
      - LogicalLine.is_comment=True           → COMMENT
      - LogicalLine con texto vacío/blanco     → BLANK
      - LogicalLine con código, 1 raw_line     → CODE  (sentencia de una línea)
      - LogicalLine con código, varias raw_lines:
          · primera raw_line                  → CODE
          · las demás                         → CONTINUATION
    """
    result = {}
    for s in sentencias:
        if s.is_comment:
            for lineno, _ in s.raw_lines:
                result[lineno] = COMMENT
        elif not s.text.strip():
            for lineno, _ in s.raw_lines:
                result[lineno] = BLANK
        else:
            for i, (lineno, _) in enumerate(s.raw_lines):
                result[lineno] = CODE if i == 0 else CONTINUATION
    return result


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def analizar_sloc():
    print("--- Contador SLOC Preciso ---")

    # 1. Cargar inventario
    try:
        inventario_lista = cargar_inventario()
    except Exception as e:
        print(f"ERROR cargando inventario: {e}")
        return

    if not inventario_lista:
        print("El inventario está vacío.")
        return

    # Convertir tipos numéricos y agrupar por archivo
    mapa_unidades = defaultdict(list)
    for u in inventario_lista:
        archivo = u.get("Archivo", "").strip()
        if not archivo:
            continue
        try:
            u["Linea_Inicio"] = int(u["Linea_Inicio"])
            u["Linea_Fin"]    = int(u["Linea_Fin"])
        except (ValueError, KeyError):
            u["Linea_Inicio"] = 0
            u["Linea_Fin"]    = 0
        mapa_unidades[archivo].append(u)

    ruta_codigo       = CARPETA_CODIGO
    archivos_ordenados = sorted(mapa_unidades.keys(), key=str.lower)
    datos_salida       = []

    for idx, nombre_archivo in enumerate(archivos_ordenados):
        ruta_fisica = ruta_codigo / nombre_archivo
        print(f"  [{idx+1}/{len(archivos_ordenados)}] {nombre_archivo}")

        try:
            sentencias = reader_logical.read_logical_lines(ruta_fisica)
        except Exception as e:
            print(f"    -> Error leyendo: {e}")
            continue

        # Clasificar líneas físicas
        clasif = clasificar_fisicas(sentencias)

        if not clasif:
            continue

        # Ordenar unidades por Linea_Inicio para scope resolution
        unidades = sorted(mapa_unidades[nombre_archivo], key=lambda u: u["Linea_Inicio"])

        # Acumuladores por unidad: { nombre_unidad -> { cat -> count } }
        contadores = defaultdict(lambda: defaultdict(int))

        for lineno, cat in clasif.items():
            # Scope: unidad más interna que contenga lineno
            candidatos = [
                u for u in unidades
                if u["Linea_Inicio"] <= lineno <= u["Linea_Fin"]
            ]
            if candidatos:
                scope = max(candidatos, key=lambda u: u["Linea_Inicio"])["Nombre"]
            else:
                scope = "GLOBAL"
            contadores[scope][cat] += 1

        # Construir filas de salida
        for u in unidades:
            nombre = u["Nombre"]
            c      = contadores[nombre]

            loc          = c[BLANK] + c[COMMENT] + c[CODE] + c[CONTINUATION]
            n_blank      = c[BLANK]
            n_comment    = c[COMMENT]
            n_cont       = c[CONTINUATION]
            sloc_fisico  = loc - n_blank - n_comment          # incluye continuaciones
            sloc_neto    = sloc_fisico - n_cont               # = sentencias lógicas de código
            pct_comment  = round(n_comment / loc * 100, 1) if loc > 0 else 0.0

            datos_salida.append({
                "Archivo":       nombre_archivo,
                "Unidad":        nombre,
                "Tipo":          u.get("Tipo", "UNKNOWN"),
                "LOC":           loc,
                "N_Blancos":     n_blank,
                "N_Comentarios": n_comment,
                "N_Continuacion":n_cont,
                "SLOC_fisico":   sloc_fisico,
                "SLOC_neto":     sloc_neto,
                "Pct_Comentario":pct_comment,
            })

    if not datos_salida:
        print("Sin datos para exportar.")
        return

    # Ordenar por SLOC_neto descendente
    datos_salida.sort(key=lambda x: -x["SLOC_neto"])

    # Exportar
    columnas = [
        "Archivo", "Unidad", "Tipo",
        "LOC", "N_Blancos", "N_Comentarios", "N_Continuacion",
        "SLOC_fisico", "SLOC_neto", "Pct_Comentario",
    ]
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(datos_salida)

    # Resumen en consola
    total_loc         = sum(r["LOC"]           for r in datos_salida)
    total_blank       = sum(r["N_Blancos"]      for r in datos_salida)
    total_comment     = sum(r["N_Comentarios"]  for r in datos_salida)
    total_cont        = sum(r["N_Continuacion"] for r in datos_salida)
    total_sloc_fisico = sum(r["SLOC_fisico"]    for r in datos_salida)
    total_sloc_neto   = sum(r["SLOC_neto"]      for r in datos_salida)

    # Totales por archivo (solo unidades raíz para no doblar conteo)
    # Nota: sumamos todos porque la mayoría son no-solapables (distintos rangos)
    # Para un total de archivo real usamos el mayor LOC por archivo
    archivos_loc = defaultdict(int)
    for r in datos_salida:
        # Acumulamos el LOC raíz (Padre==GLOBAL) por archivo
        archivos_loc[r["Archivo"]] = max(archivos_loc[r["Archivo"]], r["LOC"])

    print(f"\nResumen global:")
    print(f"  LOC total (físico, corpus)   : {sum(archivos_loc.values()):>8,}")
    print(f"  Líneas en blanco             : {total_blank:>8,}")
    print(f"  Líneas comentario            : {total_comment:>8,}")
    print(f"  Líneas continuación          : {total_cont:>8,}")
    print(f"  SLOC físico                  : {total_sloc_fisico:>8,}  (código sin blancos/comentarios)")
    print(f"  SLOC neto                    : {total_sloc_neto:>8,}  (sentencias lógicas)")

    loc_corpus = sum(archivos_loc.values())
    if loc_corpus > 0:
        print(f"  Densidad comentario (corpus) : {total_comment/loc_corpus*100:>7.1f}%")

    print(f"\nTop 10 unidades más grandes (SLOC neto):")
    for r in datos_salida[:10]:
        pct = f"{r['Pct_Comentario']:4.1f}%"
        print(f"  {r['SLOC_neto']:5}  sloc  {r['Pct_Comentario']:4.1f}% coment  "
              f"{r['Archivo']:25} {r['Unidad']}")

    # Unidades sin ningún comentario
    sin_comentarios = [
        r for r in datos_salida
        if r["N_Comentarios"] == 0 and r["SLOC_neto"] > 10
    ]
    if sin_comentarios:
        print(f"\nUnidades con >10 sentencias y 0 comentarios ({len(sin_comentarios)}):")
        for r in sorted(sin_comentarios, key=lambda x: -x["SLOC_neto"])[:15]:
            print(f"  {r['SLOC_neto']:5}  sloc  {r['Archivo']:25} {r['Unidad']}")

    print(f"\nGenerado: {SALIDA_CSV}")


if __name__ == "__main__":
    analizar_sloc()
