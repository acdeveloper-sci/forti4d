import os
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

# --- IMPORTACIONES DEL PROYECTO ---
import forti4d.lib.reader_logical as reader_logical
import forti4d.lib.patterns_v2 as patterns
import forti4d.lib.kinds as kinds

# Usamos la nueva función maestra que acabamos de definir
from forti4d.analyzers.inventario import cargar_inventario

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
from forti4d.config import CARPETA_CODIGO, RUTA_RESULTADOS

SALIDA_CSV = RUTA_RESULTADOS / "reporte_densidad.csv"
RUTA_AUDIT = RUTA_RESULTADOS / "audit"

# =============================================================================
# GRUPOS DE DENSIDAD
# =============================================================================
GROUP_CALCULO = kinds.CALCULATION_ACTIONS | {kinds.StatementKind.ASSIGNMENT_STMT}
GROUP_CONTROL = kinds.EXECUTABLE_CONSTRUCTS | {
    kinds.StatementKind.CONTROL_STMT,
    kinds.StatementKind.ELSE_STMT,
    kinds.StatementKind.CASE_STMT,
}
GROUP_IO = kinds.IO_ACTIONS
GROUP_LEGACY = kinds.LEGACY_DATA
GROUP_DECLAR = {
    kinds.StatementKind.VAR_DECLARATION,
    kinds.StatementKind.PARAMETER_STMT,
    kinds.StatementKind.IMPLICIT_STMT,
    kinds.StatementKind.USE_STMT,
    kinds.StatementKind.IMPORT_STMT,
    kinds.StatementKind.TYPE_DEFINITION,
    kinds.StatementKind.ENUM_DEF,
    kinds.StatementKind.INTERFACE_BLOCK,
    kinds.StatementKind.CONTAINS_STMT,
    kinds.StatementKind.END_BLOCK_STMT,
}

# =============================================================================
# MAPA DE PATRONES (Mismo de antes, verificado)
# =============================================================================
PATTERN_MAP = [
    (patterns.RE_END_BLOCK, kinds.StatementKind.END_BLOCK_STMT),       # Cierres primero: evita que cualquier opener capture un END
    (patterns.RE_PROGRAM, kinds.StatementKind.PROGRAM_UNIT),
    (patterns.RE_MODULE, kinds.StatementKind.MODULE_UNIT),
    (patterns.RE_SUBROUTINE, kinds.StatementKind.SUBROUTINE_UNIT),
    (patterns.RE_FUNCTION, kinds.StatementKind.FUNCTION_UNIT),
    (patterns.RE_BLOCK_DATA, kinds.StatementKind.BLOCK_DATA_UNIT),
    (patterns.RE_INTERFACE, kinds.StatementKind.INTERFACE_BLOCK),
    (patterns.RE_MODULE_PROCEDURE, kinds.StatementKind.INTERFACE_BLOCK),
    (patterns.RE_TYPE_DEF, kinds.StatementKind.TYPE_DEFINITION),
    (patterns.RE_ENUM_DEF, kinds.StatementKind.ENUM_DEF),
    (patterns.RE_CONTAINS, kinds.StatementKind.CONTAINS_STMT),
    (patterns.RE_COMMON, kinds.StatementKind.COMMON_STMT),
    (patterns.RE_EQUIVALENCE, kinds.StatementKind.EQUIVALENCE_STMT),
    (patterns.RE_DATA, kinds.StatementKind.DATA_STMT),
    (patterns.RE_NAMELIST, kinds.StatementKind.NAMELIST_STMT),
    (patterns.RE_IF_BLOCK, kinds.StatementKind.IF_CONSTRUCT),
    (patterns.RE_DO_LOOP, kinds.StatementKind.DO_CONSTRUCT),
    (patterns.RE_SELECT_CASE, kinds.StatementKind.SELECT_CONSTRUCT),
    (patterns.RE_ASSOCIATE, kinds.StatementKind.ASSOCIATE_CONSTRUCT),
    (patterns.RE_BLOCK_CONST, kinds.StatementKind.BLOCK_CONSTRUCT),
    (patterns.RE_CRITICAL, kinds.StatementKind.CRITICAL_CONSTRUCT),
    (patterns.RE_WHERE_BLOCK, kinds.StatementKind.WHERE_CONSTRUCT),
    (patterns.RE_FORALL_BLOCK, kinds.StatementKind.FORALL_CONSTRUCT),
    (patterns.RE_ELSE, kinds.StatementKind.ELSE_STMT),
    (patterns.RE_CASE, kinds.StatementKind.CASE_STMT),
    (patterns.RE_USE, kinds.StatementKind.USE_STMT),
    (patterns.RE_IMPORT, kinds.StatementKind.IMPORT_STMT),
    (patterns.RE_IMPLICIT, kinds.StatementKind.IMPLICIT_STMT),
    (patterns.RE_VAR_DECL, kinds.StatementKind.VAR_DECLARATION),
    (patterns.RE_PARAMETER, kinds.StatementKind.PARAMETER_STMT),
    (patterns.RE_ATTR_SPEC, kinds.StatementKind.VAR_DECLARATION),
    (patterns.RE_ALLOCATE, kinds.StatementKind.ALLOCATION_STMT),
    (patterns.RE_DEALLOCATE, kinds.StatementKind.ALLOCATION_STMT),
    (patterns.RE_POINTER_OP, kinds.StatementKind.POINTER_ACTION),
    (patterns.RE_IO, kinds.StatementKind.IO_STMT),
    (patterns.RE_CONTROL, kinds.StatementKind.CONTROL_STMT),
    (patterns.RE_INCLUDE, kinds.StatementKind.INCLUDE_STMT),
    (patterns.RE_ARITHMETIC_IF, kinds.StatementKind.CONTROL_STMT),
    (patterns.RE_IF_SINGLE, kinds.StatementKind.IF_CONSTRUCT),
    (patterns.RE_WHERE_SINGLE, kinds.StatementKind.WHERE_CONSTRUCT),
    (patterns.RE_FORALL_SINGLE, kinds.StatementKind.FORALL_CONSTRUCT),
]


def mask_strings(linea: str) -> str:
    """Evita falsos positivos en strings."""
    pattern = r"('([^']*)'|\"([^\"]*)\")"

    def replacer(match):
        full = match.group(0)
        return full[0] + "_" * (len(full) - 2) + full[-1]

    return re.sub(pattern, replacer, linea)


def clasificar_linea(linea_logica: str):
    linea_limpia = mask_strings(linea_logica)
    for pattern, kind in PATTERN_MAP:
        if pattern.match(linea_limpia):
            return kind

    if "=" in linea_limpia:
        temp = linea_limpia.replace("==", "").replace("=>", "").replace(">=", "").replace("<=", "")
        if "=" in temp:
            return kinds.StatementKind.ASSIGNMENT_STMT

    return kinds.StatementKind.UNKNOWN


def analizar_densidad():
    print("INICIO PERFILADO DE DENSIDAD (V3 Auditada)")

    ruta_archivos = CARPETA_CODIGO
    if not ruta_archivos.exists():
        print(f"ERROR: No existe la carpeta {CARPETA_CODIGO}")
        return

    # 1. Cargar Inventario usando la función en inventario.py
    # Esto devuelve una lista de dicts con claves 'Archivo', 'Linea_Inicio', etc.
    try:
        inventario_lista = cargar_inventario()
        print(f"Inventario cargado: {len(inventario_lista)} registros totales.")
    except ImportError:
        print("ERROR: No se encontró la función 'cargar_inventario' en inventario.py.")
        return
    except Exception as e:
        print(f"Error cargando inventario: {e}")
        return

    if not inventario_lista:
        print("El inventario está vacío o no se pudo leer.")
        return

    # 2. Agrupar unidades por Archivo para evitar iteraciones ineficientes
    # Clave: Nombre del archivo (str) -> Valor: Lista de diccionarios de unidades
    mapa_unidades_archivo = defaultdict(list)
    for u in inventario_lista:
        archivo = u.get("Archivo")
        if archivo:
            mapa_unidades_archivo[archivo].append(u)

    datos_salida = []

    ruta_audit = RUTA_AUDIT
    ruta_audit.mkdir(parents=True, exist_ok=True)

    # Ordenamos los archivos alfabéticamente para el reporte
    # archivos_ordenados = mapa_unidades_archivo.keys()
    archivos_ordenados = sorted(mapa_unidades_archivo.keys(), key=lambda x: x.lower())

    for idx, nombre_archivo in enumerate(archivos_ordenados):
        print(f"[{idx+1}/{len(archivos_ordenados)}] Procesando: {nombre_archivo}")

        # Obtener las unidades que pertenecen a este archivo
        unidades_en_archivo = mapa_unidades_archivo[nombre_archivo]

        # Ordenamos por Linea_Inicio para la resolución de scope
        # NOTA: Usamos la clave correcta 'Linea_Inicio'
        unidades_en_archivo.sort(key=lambda x: x["Linea_Inicio"])

        # Construir ruta física
        ruta_fisica = ruta_archivos / nombre_archivo

        # Leer Líneas Lógicas
        try:
            sentencias = reader_logical.read_logical_lines(ruta_fisica)
        except Exception as e:
            print(f"  -> Error lectura/No existe: {e}")
            continue

        contadores = defaultdict(Counter)
        filas_debug = []

        # 3. Clasificación y Asignación
        for sentencia in sentencias:
            if sentencia.is_comment:
                filas_debug.append(
                    {
                        "Linea": sentencia.start_line,
                        "Kind": str(kinds.StatementKind.COMMENT).split(".")[1],  # Convertimos el Enum a string legible
                        "Contenido": sentencia.text[:120],  # Primeros 120 chars para no saturar
                    }
                )
                continue

            contenido = sentencia.text.strip()

            if sentencia.label:
                # Usamos regex para quitar la etiqueta al inicio del string de forma segura
                # Buscamos: inicio + etiqueta + espacios
                contenido = re.sub(r"^\s*" + re.escape(sentencia.label) + r"\s+", "", contenido, count=1)

            if not contenido:
                filas_debug.append(
                    {
                        "Linea": sentencia.start_line,
                        "Kind": str(kinds.StatementKind.BLANK_LINE).split(".")[
                            1
                        ],  # Convertimos el Enum a string legible
                        "Contenido": "",
                    }
                )
                continue

            # Usamos start_line tal como definimos que existe en LogicalLine
            n_linea = sentencia.start_line

            # Scope Resolution: ¿A quién pertenece esta línea?
            nombre_unidad = "GLOBAL"

            # Buscamos la unidad más interna que contenga n_linea (Inicio <= n <= Fin)
            candidatos = [u for u in unidades_en_archivo
                          if u["Linea_Inicio"] <= n_linea <= u["Linea_Fin"]]

            if candidatos:
                # El más interno es el que empezó más tarde (mayor Linea_Inicio)
                nombre_unidad = max(candidatos, key=lambda u: u["Linea_Inicio"])["Nombre"]

            kind = clasificar_linea(contenido)
            contadores[nombre_unidad][kind] += 1

            if kind == kinds.StatementKind.IO_STMT:
                lower = mask_strings(contenido.lower())
                if re.match(r"^\s*print\b", lower):
                    contadores[nombre_unidad]["_IO_PRINT"] += 1
                elif re.match(r"^\s*write\b", lower):
                    contadores[nombre_unidad]["_IO_WRITE"] += 1
                # Nota: Si quisieras contar READ, OPEN, etc., los agregarías aquí.

            # --- AUDITORÍA: Guardar dato ---
            # Guardamos: Linea, Clasificación, Contenido (truncado para limpieza)
            filas_debug.append(
                {
                    "Linea": n_linea,
                    "Kind": str(kind).split(".")[1],  # Convertimos el Enum a string legible
                    "Contenido": sentencia.text[:120],  # Primeros 120 chars para no saturar
                }
            )

        # AUDITORIA
        # --- AL FINAL DEL PROCESAMIENTO DEL ARCHIVO ---
        # Generar nombre del CSV de debug: "nombrearchivo_f90_DEBUG.csv"
        nombre_debug = f"{nombre_archivo}_DEBUG.csv"
        ruta_debug = ruta_audit / nombre_debug

        # Escribir a disco (puedes poner una ruta específica si prefieres)
        try:
            with open(ruta_debug, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["Linea", "Kind", "Contenido"])
                writer.writeheader()
                writer.writerows(filas_debug)
            print(f"  -> Auditoría guardada en: {ruta_debug}")
        except Exception as e:
            print(f"  -> Error guardando debug: {e}")

        # 4. Consolidación

        # Agregar GLOBAL si se detectó código fuera de unidades
        if "GLOBAL" in contadores:
            if not any(u["Nombre"] == "GLOBAL" for u in unidades_en_archivo):
                # Creamos una unidad ficticia para el reporte
                unidades_en_archivo.insert(0, {"Nombre": "GLOBAL", "Tipo": "FILE_SCOPE", "Linea_Inicio": 0})

        for u in unidades_en_archivo:
            nombre = u["Nombre"]  # Clave correcta
            tipo = u.get("Tipo", "UNKNOWN")  # Clave correcta

            c = contadores[nombre]
            total_sentencias = sum(c.values())

            # Sumas
            n_calculo = sum(c[k] for k in GROUP_CALCULO if k in c)
            n_control = sum(c[k] for k in GROUP_CONTROL if k in c)
            n_io = sum(c[k] for k in GROUP_IO if k in c)
            n_legacy = sum(c[k] for k in GROUP_LEGACY if k in c)
            n_declar = sum(c[k] for k in GROUP_DECLAR if k in c)

            # Porcentajes
            pct = lambda x: round((x / total_sentencias) * 100, 1) if total_sentencias > 0 else 0.0

            fila = {
                "Archivo": nombre_archivo,
                "Unidad": nombre,
                "Tipo": tipo,
                "Total_Sentencias": total_sentencias,
                "Total_Calculo": n_calculo,
                "Total_Control": n_control,
                "Total_IO": n_io,
                "Total_Legacy": n_legacy,
                "Total_Declar": n_declar,
                "Pct_Calculo": pct(n_calculo),
                "Pct_Control": pct(n_control),
                "Pct_IO": pct(n_io),
                "Pct_Legacy": pct(n_legacy),
                "Pct_Declar": pct(n_declar),
                "N_Common": c[kinds.StatementKind.COMMON_STMT],
                "N_Equiv": c[kinds.StatementKind.EQUIVALENCE_STMT],
                "N_Print": c["_IO_PRINT"],
                "N_Write": c["_IO_WRITE"],
            }
            datos_salida.append(fila)

    # 5. Exportar
    headers = [
        "Archivo",
        "Unidad",
        "Tipo",
        "Total_Sentencias",
        "Total_Calculo",
        "Total_Control",
        "Total_IO",
        "Total_Legacy",
        "Total_Declar",
        "Pct_Calculo",
        "Pct_Control",
        "Pct_IO",
        "Pct_Legacy",
        "Pct_Declar",
        "N_Common",
        "N_Equiv",
        "N_Print",
        "N_Write",
    ]

    try:
        with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerows(datos_salida)
        print(f"\nREPORTE GENERADO: {SALIDA_CSV}")
    except Exception as e:
        print(f"Error escribiendo CSV: {e}")


if __name__ == "__main__":
    analizar_densidad()
