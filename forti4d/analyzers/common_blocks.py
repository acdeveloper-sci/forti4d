import os
import csv
import re
from collections import defaultdict
from pathlib import Path

from forti4d.analyzers.inventario import cargar_inventario
from forti4d.config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
RUTA_AUDIT          = RUTA_RESULTADOS / "audit"
SALIDA_USO          = RUTA_RESULTADOS / "common_uso.csv"
SALIDA_ACOPLAMIENTO = RUTA_RESULTADOS / "common_acoplamiento.csv"

NOMBRE_BLANK = "(BLANK)"   # Etiqueta para COMMON sin nombre


# =============================================================================
# PARSEO DE SENTENCIAS COMMON
# =============================================================================

def extraer_bloques(contenido: str) -> list:
    """
    Extrae los nombres de bloque de una sentencia COMMON.

    Retorna una lista de nombres únicos de bloques referenciados en esa línea.
    El blank COMMON (sin nombre o con //) se representa como NOMBRE_BLANK.

    Ejemplos:
      "COMMON /A/ x, y"          → ["A"]
      "COMMON x, y"              → ["(BLANK)"]
      "COMMON //x"               → ["(BLANK)"]
      "COMMON /A/ x /B/ y"       → ["A", "B"]
      "COMMON x /A/ y"           → ["(BLANK)", "A"]
    """
    # Quitar la keyword COMMON del inicio
    resto = re.sub(r"^\s*common\s*", "", contenido.strip(), flags=re.IGNORECASE)

    if not resto:
        return []

    bloques = []

    if resto.lstrip().startswith("/"):
        # Comienza con bloque nombrado (o // para blank)
        for m in re.finditer(r"/(\w*)/", resto):
            nombre = m.group(1).strip()
            bloques.append(nombre if nombre else NOMBRE_BLANK)
    else:
        # Comienza con blank COMMON (variables antes de cualquier /)
        bloques.append(NOMBRE_BLANK)
        # Puede haber bloques nombrados después: COMMON x /A/ y
        for m in re.finditer(r"/(\w*)/", resto):
            nombre = m.group(1).strip()
            bloques.append(nombre if nombre else NOMBRE_BLANK)

    # Deduplicar manteniendo orden (una línea no debería repetir el mismo bloque,
    # pero si lo hace, lo contamos una sola vez por línea)
    vistos = []
    seen = set()
    for b in bloques:
        if b not in seen:
            vistos.append(b)
            seen.add(b)
    return vistos


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def analizar_common():
    print("--- Análisis de COMMON Blocks ---")

    # 1. Cargar inventario
    try:
        inventario_lista = cargar_inventario()
    except Exception as e:
        print(f"ERROR cargando inventario: {e}")
        return

    if not inventario_lista:
        print("El inventario está vacío.")
        return

    # Conversión de tipos y agrupación por archivo
    mapa_unidades = defaultdict(list)
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
        mapa_unidades[archivo].append(u)

    # Estructura de resultados:
    # uso[(archivo, unidad)] = Counter(bloque -> n_apariciones)
    uso = defaultdict(lambda: defaultdict(int))
    # metadatos de unidad para el reporte
    meta = {}   # (archivo, unidad) -> dict con Tipo

    for u in inventario_lista:
        k = (u["Archivo"], u["Name"])
        meta[k] = {"Type": u.get("Type", "UNKNOWN")}

    ruta_audit = RUTA_AUDIT
    archivos_ordenados = sorted(mapa_unidades.keys(), key=str.lower)

    common_total = 0

    for nombre_archivo in archivos_ordenados:
        debug_file = ruta_audit / f"{nombre_archivo}_DEBUG.csv"
        if not debug_file.exists():
            continue

        unidades_en_archivo = sorted(
            mapa_unidades[nombre_archivo], key=lambda u: u["Start_Line"]
        )

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("Kind") != "COMMON_STMT":
                    continue

                try:
                    n_linea = int(row["Linea"])
                except ValueError:
                    continue

                contenido = row.get("Contenido", "")
                bloques   = extraer_bloques(contenido)

                if not bloques:
                    continue

                # Scope resolution
                candidatos = [
                    u for u in unidades_en_archivo
                    if u["Start_Line"] <= n_linea <= u["End_Line"]
                ]
                if not candidatos:
                    scope = "GLOBAL"
                    tipo  = "FILE_SCOPE"
                else:
                    u_scope = max(candidatos, key=lambda u: u["Start_Line"])
                    scope   = u_scope["Name"]
                    tipo    = u_scope.get("Type", "UNKNOWN")
                    meta[(nombre_archivo, scope)] = {"Type": tipo}

                for bloque in bloques:
                    uso[(nombre_archivo, scope)][bloque] += 1
                    common_total += 1

    if common_total == 0:
        print("No se encontraron sentencias COMMON en el corpus.")
        print("(El código utiliza módulos F90 en lugar de COMMON blocks)")
        # Generar CSVs vacíos con cabecera para mantener consistencia del pipeline
        _escribir_csv_vacio(SALIDA_USO,
            ["Archivo", "Unidad", "Type", "Bloque", "Apariciones"])
        _escribir_csv_vacio(SALIDA_ACOPLAMIENTO,
            ["Bloque", "N_Unidades", "N_Archivos", "Riesgo", "Unidades", "Archivos"])
        return

    # 2. Construir reporte de uso (una fila por (unidad, bloque))
    filas_uso = []
    for (archivo, unidad), bloques_cnt in sorted(uso.items()):
        tipo = meta.get((archivo, unidad), {}).get("Type", "UNKNOWN")
        for bloque, apariciones in sorted(bloques_cnt.items()):
            filas_uso.append({
                "Archivo":     archivo,
                "Unidad":      unidad,
                "Type":        tipo,
                "Bloque":      bloque,
                "Apariciones": apariciones,
            })

    # 3. Construir reporte de acoplamiento (una fila por bloque)
    # bloque -> set de (archivo, unidad)
    bloque_unidades = defaultdict(set)
    for (archivo, unidad), bloques_cnt in uso.items():
        for bloque in bloques_cnt:
            bloque_unidades[bloque].add((archivo, unidad))

    filas_acoplamiento = []
    for bloque, pares in sorted(bloque_unidades.items()):
        n_unidades = len(pares)
        archivos_unicos = sorted(set(a for a, _ in pares))
        unidades_sorted = sorted(u for _, u in pares)

        if n_unidades >= 5:
            riesgo = "ALTO"
        elif n_unidades >= 2:
            riesgo = "MEDIO"
        else:
            riesgo = "BAJO"

        filas_acoplamiento.append({
            "Bloque":     bloque,
            "N_Unidades": n_unidades,
            "N_Archivos": len(archivos_unicos),
            "Riesgo":     riesgo,
            "Unidades":   "; ".join(unidades_sorted),
            "Archivos":   "; ".join(archivos_unicos),
        })

    filas_acoplamiento.sort(key=lambda x: -x["N_Unidades"])

    # 4. Exportar
    _escribir_csv(SALIDA_USO, filas_uso,
        ["Archivo", "Unidad", "Type", "Bloque", "Apariciones"])

    _escribir_csv(SALIDA_ACOPLAMIENTO, filas_acoplamiento,
        ["Bloque", "N_Unidades", "N_Archivos", "Riesgo", "Unidades", "Archivos"])

    # 5. Resumen en consola
    n_bloques = len(bloque_unidades)
    n_unidades_afectadas = len(uso)

    print(f"Sentencias COMMON encontradas : {common_total}")
    print(f"Bloques únicos                : {n_bloques}")
    print(f"Unidades con COMMON           : {n_unidades_afectadas}")
    print()

    from collections import Counter
    riesgos = Counter(r["Riesgo"] for r in filas_acoplamiento)
    print("Distribución de acoplamiento por bloque:")
    for nivel in ("ALTO", "MEDIO", "BAJO"):
        n = riesgos.get(nivel, 0)
        if n:
            print(f"  {nivel:6}: {n} bloque(s)")

    print()
    print("Bloques con mayor acoplamiento (más unidades comparten el bloque):")
    for r in filas_acoplamiento[:10]:
        print(f"  {r['Bloque']:20}  {r['N_Unidades']:3} unidades  "
              f"[{r['Riesgo']}]  → {r['Unidades'][:60]}")

    print(f"\nGenerados: {SALIDA_USO}, {SALIDA_ACOPLAMIENTO}")


# =============================================================================
# HELPERS DE ESCRITURA
# =============================================================================

def _escribir_csv(ruta, filas, columnas):
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def _escribir_csv_vacio(ruta, columnas):
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=columnas).writeheader()
    print(f"  {ruta} generado (vacío — sin COMMON en corpus)")


if __name__ == "__main__":
    analizar_common()
