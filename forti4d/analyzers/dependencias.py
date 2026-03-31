import sys
import os
import csv
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Set, Tuple

# --- IMPORTACIÓN DE HERRAMIENTAS BASE ---
try:
    from forti4d.lib.reader_logical import read_logical_lines
    from forti4d.lib.patterns_v1 import (
        RE_PROGRAM,
        RE_MODULE,
        RE_SUBROUTINE,
        RE_FUNCTION,
        RE_INTERFACE,
    )
except ImportError as e:
    print(f"ERROR: Faltan archivos base (reader.py o patterns.py).\n{e}")
    sys.exit(1)

# =============================================================================
# CONFIGURACIÓN Y CONSTANTES
# =============================================================================
from forti4d.config import CARPETA_CODIGO, RUTA_RESULTADOS

ARCHIVO_INVENTARIO = RUTA_RESULTADOS / "inventory_report.csv"

# Archivos de Salida
OUT_AMBIGUOS  = RUTA_RESULTADOS / "dep_00_ambiguities.csv"
OUT_MAESTRO   = RUTA_RESULTADOS / "dep_01_master_data.csv"
OUT_GRAFO     = RUTA_RESULTADOS / "dep_02_unit_graph.csv"
OUT_IMPACTO   = RUTA_RESULTADOS / "dep_03_impact_matrix.csv"
OUT_HUERFANOS = RUTA_RESULTADOS / "dep_04_external_orphans.csv"
OUT_ARCHIVOS  = RUTA_RESULTADOS / "dep_05_file_dependencies.csv"
OUT_INCLUDES  = RUTA_RESULTADOS / "dep_06_include_files.csv"

# Jerarquía de Naturaleza (Menor índice = Más fuerte)
RANKING_NATURALEZA = {
    "ARQUITECTONICA": 1,  # USE
    "FISICA": 2,  # INCLUDE
    "OPERATIVA": 3,  # CALL, FUNCTION
    "UNKNOWN": 99,
}

# Listas de referencia
INTRINSECAS = {
    "ABS",
    "ACOS",
    "AIMAG",
    "AINT",
    "ALOG",
    "ALOG10",
    "AMAX0",
    "AMAX1",
    "AMIN0",
    "AMIN1",
    "AMOD",
    "ANINT",
    "ASIN",
    "ATAN",
    "ATAN2",
    "CABS",
    "CCOS",
    "CEXP",
    "CHAR",
    "CLOG",
    "CMPLX",
    "CONJG",
    "COS",
    "COSH",
    "CSIN",
    "CSQRT",
    "DABS",
    "DACOS",
    "DASIN",
    "DATAN",
    "DATAN2",
    "DBLE",
    "DCOS",
    "DCOSH",
    "DDIM",
    "DEXP",
    "DIM",
    "DINT",
    "DLOG",
    "DLOG10",
    "DMAX1",
    "DMIN1",
    "DMOD",
    "DNINT",
    "DPROD",
    "DSIGN",
    "DSIN",
    "DSINH",
    "DSQRT",
    "DTAN",
    "DTANH",
    "EXP",
    "FLOAT",
    "IABS",
    "ICHAR",
    "IDIM",
    "IDINT",
    "IDNINT",
    "IFIX",
    "INDEX",
    "INT",
    "ISIGN",
    "LEN",
    "LGE",
    "LGT",
    "LLE",
    "LLT",
    "LOG",
    "LOG10",
    "MAX",
    "MAX0",
    "MAX1",
    "MIN",
    "MIN0",
    "MIN1",
    "MOD",
    "NINT",
    "REAL",
    "SIGN",
    "SIN",
    "SINH",
    "SNGL",
    "SQRT",
    "TAN",
    "TANH",
    "TRIM",
    "ADJUSTL",
    "ADJUSTR",
    "ALLOCATED",
    "ASSOCIATED",
    "PRESENT",
    "KIND",
    "SIZE",
    "SHAPE",
    "LBOUND",
    "UBOUND",
    "SUM",
    "PRODUCT",
    "MATMUL",
    "DOT_PRODUCT",
    "TRANSPOSE",
    "COUNT",
    "ANY",
    "ALL",
    "MAXVAL",
    "MINVAL",
    "MAXLOC",
    "MINLOC",
    "LSHIFT",
    "RSHIFT",
    "AND",
    "OR",
    "XOR",
    "NOT",
    "IAND",
    "IOR",
    "IEOR",
}

KEYWORDS_IGNORE = {
    "IF",
    "WHILE",
    "READ",
    "WRITE",
    "PRINT",
    "OPEN",
    "CLOSE",
    "INQUIRE",
    "BACKSPACE",
    "REWIND",
    "FORMAT",
    "ALLOCATE",
    "DEALLOCATE",
    "NULLIFY",
    "DATA",
    "COMMON",
    "DIMENSION",
    "IMPLICIT",
    "PARAMETER",
    "INTENT",
    "PUBLIC",
    "PRIVATE",
    "OPTIONAL",
    "TARGET",
    "POINTER",
    "SAVE",
    "CASE",
    "SELECT",
    "TYPE",
    "CLASS",
    "FORALL",
    "WHERE",
    "ELSE",
    "ELSEIF",
    "THEN",
    "STOP",
    "PAUSE",
    "RETURN",
    "CYCLE",
    "EXIT",
    "CONTINUE",
    "ENTRY",
    "NAMELIST",
}

# Regex Blindados
RE_USE = re.compile(r"^\s*use\b\s+(\w+)", re.IGNORECASE)
RE_CALL = re.compile(r"^\s*call\b\s+(\w+)", re.IGNORECASE)
# INCLUDE busca comillas. Ignora <...> de C.
RE_INCLUDE = re.compile(r"^\s*include\b\s+['\"]([^'\"]+)['\"]", re.IGNORECASE)
RE_FUNC_CALL = re.compile(r"\b([a-zA-Z]\w*)\s*\(", re.IGNORECASE)

RE_END_MODULE = re.compile(r"^\s*end\s*module\b", re.IGNORECASE)

RE_END_INTERFACE = re.compile(r"^\s*END\s*INTERFACE\b", re.IGNORECASE)

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================


def mask_strings(text: str) -> str:
    """Reemplaza contenido de strings por '' para evitar falsos positivos."""
    text = re.sub(r"'[^']*'", "''", text)
    text = re.sub(r'"[^"]*"', '""', text)
    return text


def get_strongest_nature(nature_set: Set[str]) -> str:
    """Devuelve la naturaleza más fuerte de un conjunto."""
    if not nature_set:
        return ""
    # Ordenar por ranking
    sorted_natures = sorted(nature_set, key=lambda x: RANKING_NATURALEZA.get(x, 99))
    return sorted_natures[0]


# =============================================================================
# LÓGICA PRINCIPAL
# =============================================================================


def cargar_inventario(report_ambiguos=False) -> Tuple[Dict, Dict]:
    """
    Carga inventario y detecta duplicados.
    Retorna:
      - inventory: {NOMBRE_UPPER: [ {archivo, tipo, padre, ...}, ... ]}
      - file_map: {ARCHIVO: set(NOMBRES_UNIDADES_DEFINIDAS)}
    Genera reporte de ambigüedades GLOBAL.
    """
    inventory = defaultdict(list)
    file_map = defaultdict(set)  # Para saber qué define cada archivo rápido

    if not os.path.exists(ARCHIVO_INVENTARIO):
        print(f"ERROR: No existe '{ARCHIVO_INVENTARIO}'. Ejecuta inventario.py primero.")
        sys.exit(1)

    print("Cargando inventario...")
    with open(ARCHIVO_INVENTARIO, "r", encoding="utf-8") as f:
        reader_csv = csv.DictReader(f)
        for row in reader_csv:
            nombre = row.get("Name", "").strip().upper()
            archivo = row.get("Archivo", "").strip()
            tipo = row.get("Type", "").strip().upper()
            # LEER EL PADRE (Si no existe columna, asume GLOBAL por compatibilidad)
            padre = row.get("Parent", "GLOBAL").strip().upper()

            # Ajuste de nombre para Implicit Main en el Inventario (si aplica)
            # Pero normalmente el inventario ya trae "IMPLICIT-MAIN".
            # Aquí lo trataremos al resolver, o podemos pre-procesarlo.

            if nombre:
                # Guardamos TODA la info necesaria para decidir luego
                inventory[nombre].append(
                    {
                        "archivo": archivo,
                        "tipo": tipo,
                        "padre": padre,
                    }
                )
                file_map[archivo].add(nombre)

    # Detección de Ambigüedades (Solo Informativo Global)
    ambiguos_rows = []

    for nombre, occurrences in inventory.items():
        if len(occurrences) > 1:
            # Recopilamos todos los tipos distintos involucrados en la colisión
            tipos_detectados = sorted(list(set(d["tipo"] for d in occurrences)))
            tipo_reporte = "/".join(tipos_detectados)  # Ej: "SUBROUTINE/FUNCTION" o solo "SUBROUTINE"

            # if len(tipos_detectados) == 1:
            #     # Caso A: Duplicados físicos, pero coincidencia lógica (Ej: 2 Subrutinas iguales)
            #     tipo_final = tipos_detectados[0]
            # else:
            #     # Caso B: Conflicto real (Ej: Subrutina vs Módulo)
            #     # tipo_final = "AMBIGUOUS_TYPE (" + "/".join(tipos_detectados) + ")"
            #     tipo_final = "AMBIGUOUS_TYPE"

            # Guardar en reporte de ambigüedades con detalle
            archivos_list = [d["archivo"] for d in occurrences]
            ambiguos_rows.append(
                {
                    "Unit_Name": nombre,
                    "Type": tipo_reporte,
                    "Count": len(occurrences),
                    "File_List": "; ".join(sorted(set(archivos_list))),
                }
            )

    # Guardar reporte de ambigüedades
    if ambiguos_rows and report_ambiguos:
        with open(OUT_AMBIGUOS, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Unit_Name", "Type", "Count", "File_List"])
            w.writeheader()
            w.writerows(ambiguos_rows)
        print(f"  -> Detectadas {len(ambiguos_rows)} unidades ambiguas (ver {OUT_AMBIGUOS})")

    # Retornamos 'inventory' tal cual (lista de candidatos) para que la resolución decida
    return inventory, file_map


def scan_file(ruta_archivo: Path) -> List[Dict]:
    """
    Escanea un archivo y retorna lista de dependencias crudas.
    Escanea dependencias rastreando el Scope (Padre) del llamador.
    """
    raw_deps = []

    try:
        logical_lines = read_logical_lines(str(ruta_archivo))
    except Exception as e:
        print(f"Error leyendo {ruta_archivo.name}: {e}")
        return []

    # Nombre base para unidades implícitas
    # REGLA: IMPLICIT-MAIN se convierte en "MAIN__nombrearchivo.f"
    file_main_name = f"MAIN__{ruta_archivo.name}"

    # Estado inicial
    current_unit_name = file_main_name
    current_unit_type = "IMPLICIT-MAIN"

    # RASTREO DE SCOPE (PADRE)
    # Si entramos a un MODULE, current_scope se vuelve el nombre del módulo.
    # Las subrutinas dentro heredarán ese scope.
    current_scope = "GLOBAL"

    # Estados de Control
    inside_interface = False
    current_is_recursive = False

    for lline in logical_lines:
        if lline.is_comment:
            continue

        text_raw = lline.text.strip()
        line_num = lline.start_line
        text_safe = mask_strings(text_raw)

        # --- LÓGICA DE INTERFACE (CRÍTICO PARA EVITAR FALSOS POSITIVOS) ---

        # ¿Empieza una interfaz?
        if RE_INTERFACE.match(text_safe):
            inside_interface = True
            continue  # Saltamos, no queremos analizar lo de adentro

        # ¿Termina una interfaz?
        if RE_END_INTERFACE.match(text_safe):
            inside_interface = False
            continue

        # Si estamos dentro, IGNORAR TODO (Para no cambiar current_unit_name falsamente)
        if inside_interface:
            continue

        # ------------------------------------------------------------------

        # 0. DETECTAR CIERRE DE MÓDULO (Para resetear scope)
        if RE_END_MODULE.match(text_safe):
            current_scope = "GLOBAL"
            # (Opcional: Podríamos resetear current_unit_name, pero el siguiente header lo hará)
            continue

        # 1. DETECTAR CAMBIO DE UNIDAD
        m_prog = RE_PROGRAM.match(text_safe)
        m_mod = RE_MODULE.match(text_safe)
        m_sub = RE_SUBROUTINE.match(text_safe)
        m_func = RE_FUNCTION.match(text_safe)

        is_header = False
        if m_prog:
            current_unit_name = m_prog.group(1).upper()
            current_unit_type = "PROGRAM"
            current_scope = "GLOBAL"  # Program siempre es global
            is_header = True
        elif m_mod:
            current_unit_name = m_mod.group(1).upper()
            current_unit_type = "MODULE"
            current_scope = current_unit_name  # ¡El módulo se convierte en el Scope!
            is_header = True
        elif m_sub:
            current_unit_name = m_sub.group(1).upper()
            current_unit_type = "SUBROUTINE"
            # Si estamos dentro de un módulo (current_scope != GLOBAL), esta subrutina pertenece a él.
            # Si current_scope es GLOBAL, es una subrutina externa normal.
            # Chequeamos si la palabra RECURSIVE está en la definición
            current_is_recursive = "RECURSIVE" in text_safe.upper()
            is_header = True
        elif m_func:
            current_unit_name = m_func.group(1).upper()
            current_unit_type = "FUNCTION"
            # Chequeamos si la palabra RECURSIVE está en la definición
            current_is_recursive = "RECURSIVE" in text_safe.upper()
            is_header = True

        if is_header:
            continue

        # 2. CAPTURAR DEPENDENCIAS (Pasamos source_parent = current_scope)

        # INCLUDE (Física) - Usa text_raw
        m_inc = RE_INCLUDE.match(text_raw)
        if m_inc:
            target = m_inc.group(1)
            raw_deps.append(
                {
                    "source_file": ruta_archivo.name,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "INCLUDE",
                    "target_raw": target,
                    "line": line_num,
                    "nature": "FISICA",
                }
            )
            continue

        # USE (Arquitectónica) - Usa text_safe
        m_use = RE_USE.match(text_safe)
        if m_use:
            target = m_use.group(1).upper()
            raw_deps.append(
                {
                    "source_file": ruta_archivo.name,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "USE",
                    "target_raw": target,
                    "line": line_num,
                    "nature": "ARQUITECTONICA",
                }
            )
            continue

        # CALL (Operativa) - Usa text_safe
        m_call = RE_CALL.match(text_safe)
        if m_call:
            target = m_call.group(1).upper()

            # Filtro de Recursividad para CALL (raro en subrutinas, pero posible)
            if target == current_unit_name and not current_is_recursive:
                continue

            raw_deps.append(
                {
                    "source_file": ruta_archivo.name,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "CALL",
                    "target_raw": target,
                    "line": line_num,
                    "nature": "OPERATIVA",
                }
            )
            # No continue

        # FUNCTION CALL (Operativa) - Usa text_safe
        candidates = RE_FUNC_CALL.findall(text_safe)
        for cand in candidates:
            cand_upper = cand.upper()
            if cand_upper in KEYWORDS_IGNORE:
                continue
            if cand_upper in INTRINSECAS:
                continue
            if m_call and m_call.group(1).upper() == cand_upper:  # verifica si es un CALL <nombre>
                continue

            # RECURSIVIDAD
            if cand_upper == current_unit_name:
                if not current_is_recursive:
                    # Es acceso a array de retorno, no llamada recursiva
                    continue

            # Lo agregamos como candidato. La resolución determinará si es array o función.
            raw_deps.append(
                {
                    "source_file": ruta_archivo.name,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "FUNC_CALL",
                    "target_raw": cand_upper,
                    "line": line_num,
                    "nature": "OPERATIVA",
                }
            )

    return raw_deps


def main():
    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)

    # 1. Cargar datos base
    inventory, _ = cargar_inventario(report_ambiguos=True)
    path_fuente = CARPETA_CODIGO

    # 2. Escanear Archivos
    archivos = sorted([f for f in path_fuente.rglob("*") if f.suffix.lower() in (".f90", ".f", ".for", ".f95")])
    print(f"Analizando {len(archivos)} archivos...")

    all_raw_deps = []
    for f in archivos:
        # print(f"  Scanning: {f.name}")
        all_raw_deps.extend(scan_file(f))

    # 3. Resolución y Cruzamiento
    master_rows = []
    huerfanos_set = set()

    # Estructuras para reportes agregados
    dest_file_map = defaultdict(list)
    graph_edges = set()  # (UnitA, TypeA, UnitB, TypeB, DepType)
    edges_counter = Counter()
    impact_fan_out = Counter()
    impact_fan_in = Counter()

    # Estructura para reporte de archivos
    # {(FileSrc, FileDest): set(Nature)}
    file_deps_map = defaultdict(set)
    file_deps_details = defaultdict(set)  # Para listar tipos de dep (USE, CALL...)

    print("Resolviendo dependencias con Scope...")

    for item in all_raw_deps:
        target = item["target_raw"]
        dtype = item["dep_type"]

        # Contexto del Llamador
        source_parent = item.get("source_parent", "GLOBAL")

        # Resolución del Destino
        dest_file = None
        dest_type = "UNKNOWN"
        dest_unit = target  # Por defecto el nombre raw

        if dtype == "INCLUDE":
            # Include es especial, el target es un archivo
            dest_file = target
            dest_type = "FILE"
            # Verificar existencia
            if not (CARPETA_CODIGO / target).exists():
                dest_file = "MISSING_FILE"

        else:
            # Buscar candidatos en inventario
            candidates = inventory.get(target)

            if not candidates:
                # NO ENCONTRADO
                dest_file = None
                if dtype == "FUNC_CALL":
                    continue  # Ignorar arrays/funciones no inventariadas
            else:
                # ESTRATEGIA DE RESOLUCIÓN DE SCOPE
                match = None

                # 1. Prioridad: Scope Hermano/Interno (Mismo Padre)
                # Si area_square llama a area, y ambos son hijos de mod_calc.
                internal_matches = [c for c in candidates if c["padre"] == source_parent and source_parent != "GLOBAL"]

                if internal_matches:
                    match = internal_matches[0]  # ¡Encontrado internamente!
                else:
                    # 2. Scope Global
                    global_matches = [c for c in candidates if c["padre"] == "GLOBAL"]
                    if global_matches:
                        match = global_matches[0]
                    else:
                        # 3. Scope Externo (Otro Módulo)
                        # Aquí hay ambigüedad si hay varios módulos con el mismo nombre (raro en código válido)
                        # Si solo hay uno, asumimos que se importó vía USE (aunque no validemos el USE explícito aun)
                        if len(candidates) == 1:
                            match = candidates[0]
                        else:
                            # Conflicto Real: Existe en mod_A y mod_B, y no sé cuál usas.
                            dest_file = "MULTIPLE_CANDIDATES"

                            # Recuperamos los tipos para reportar algo útil (ej: SUBROUTINE)
                            tipos = sorted(list(set(c["tipo"] for c in candidates)))
                            if len(tipos) == 1:
                                dest_type = tipos[0]
                            else:
                                dest_type = "AMBIGUOUS_TYPE"

                if match:
                    dest_file = match["archivo"]
                    dest_type = match["tipo"]

        # Si llegamos aquí, es una dependencia relevante (o un huerfano confirmado USE/CALL)

        # Registrar Huérfano real
        if dest_file is None:
            dest_file = "EXTERNAL_OR_MISSING"
            dest_type = "EXTERNAL"
            huerfanos_set.add((target, dtype))

        # --- Agregar a Maestro ---
        master_rows.append(
            {
                "Archivo_Origen": item["source_file"],
                "Unidad_Origen": item["source_unit"],
                "Tipo_Unidad_Origen": item["source_type"],
                "Tipo_Dep": dtype,
                "Unidad_Destino": dest_unit,
                "Tipo_Unidad_Destino": dest_type,
                "Archivo_Destino": dest_file,
                "Linea_Origen": item["line"],
            }
        )

        # --- Agregar a Grafo y Matriz Impacto (Solo internas resueltas) ---
        if dest_file and dest_file not in ("MULTIPLE_CANDIDATES", "EXTERNAL_OR_MISSING", "MISSING_FILE"):
            # Grafo
            dest_files = "; ".join(sorted(set(inv["archivo"] for inv in inventory.get(dest_unit, []))))
            graph_edges.add((item["source_unit"], item["source_type"], dest_unit, dest_type, dtype, dest_files))
            key = (item["source_unit"], dest_unit, item["source_type"], dest_type)
            edges_counter[key] += 1

            # Impacto
            impact_fan_out[item["source_unit"]] += 1
            impact_fan_in[dest_unit] += 1

            # Dependencia de Archivos (Solo si son distintos)
            if item["source_file"] != dest_file:
                pair = (item["source_file"], dest_file)
                file_deps_map[pair].add(item["nature"])
                file_deps_details[pair].add(dtype)

    # 4. Generación de Archivos CSV

    # A. Maestro
    if master_rows:
        keys = [
            "Archivo_Origen",
            "Unidad_Origen",
            "Tipo_Unidad_Origen",
            "Tipo_Dep",
            "Unidad_Destino",
            "Tipo_Unidad_Destino",
            "Archivo_Destino",
            "Linea_Origen",
        ]
        with open(OUT_MAESTRO, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(master_rows)
        print(f"Generado: {OUT_MAESTRO}")

    # B. Grafo Unidades
    if graph_edges:
        with open(OUT_GRAFO, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "Source_Unit",
                    "Source_Type",
                    "Target_Unit",
                    "Target_Type",
                    "Dep_Type",
                    "Target_File",
                    "Weight",
                ]
            )
            for row in sorted(list(graph_edges)):
                # (source_unit, dest_unit, source_type, dest_type)
                key = (row[0], row[2], row[1], row[3])
                peso = edges_counter[key]
                rowt = row + (peso,)
                w.writerow(rowt)
        print(f"Generado: {OUT_GRAFO}")

    # C. Matriz Impacto
    all_units = set(impact_fan_out.keys()) | set(impact_fan_in.keys())
    if all_units:
        # Recuperar tipos para la matriz (buscando en inventory o inferido)
        rows_impact = []
        for u in sorted(all_units):
            # Tipo? Buscamos en inventario. Si no, quizas es Implicit Main
            tipo = "UNKNOWN"
            archivo = "N/A"

            if u.startswith("MAIN__"):
                tipo_reporte = "IMPLICIT-MAIN"
                # Opcional: intentar recuperar el nombre del archivo del string MAIN__
                archivos_reporte = u.replace("MAIN__", "")
            else:
                candidates = inventory.get(u)  # Esto devuelve una LISTA o None
                if candidates:
                    # Tomamos el primero para sacar el Tipo
                    # first = candidates[0]
                    # tipo = first["tipo"]

                    # Determinamos el archivo
                    # if len(candidates) > 1:
                    #     archivo = "MULTIPLE_CANDIDATES"
                    # else:
                    #     archivo = first["archivo"]

                    tipos_detectados = sorted(list(set(d["tipo"] for d in candidates)))
                    tipo_reporte = "/".join(tipos_detectados)

                    archivos_list = [d["archivo"] for d in candidates]
                    archivos_reporte = "; ".join(sorted(set(archivos_list)))
                    # if len(candidates) > 1:
                    #     archivos_reporte = "MULTIPLE_CANDIDATES"
                    # else:
                    #     archivos_reporte = archivos_list[0]

            rows_impact.append(
                {
                    "Unit": u,
                    "Type": tipo_reporte,
                    "Archivo": archivos_reporte,
                    "Fan_Out": impact_fan_out.get(u, 0),
                    "Fan_In": impact_fan_in.get(u, 0),
                }
            )

        with open(OUT_IMPACTO, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Unit", "Type", "Archivo", "Fan_Out", "Fan_In"])
            w.writeheader()
            w.writerows(rows_impact)
        print(f"Generado: {OUT_IMPACTO}")

    # D. Huérfanos
    if huerfanos_set:
        with open(OUT_HUERFANOS, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Target_Unit", "Dep_Type", "Status"])
            for u, t in sorted(list(huerfanos_set)):
                w.writerow([u, t, "EXTERNAL_OR_LIBRARY"])
        print(f"Generado: {OUT_HUERFANOS}")

    # E. Dependencia de Archivos
    if file_deps_map:
        file_rows = []
        for (src, dst), natures in file_deps_map.items():
            strongest = get_strongest_nature(natures)
            details = "; ".join(sorted(file_deps_details[(src, dst)]))
            all_nats = "; ".join(sorted(natures))

            file_rows.append(
                {
                    "Archivo_Origen": src,
                    "Archivo_Destino": dst,
                    "Naturaleza_Fuerte": strongest,
                    "Lista_Naturalezas": all_nats,
                    "Detalle_Tipos": details,
                }
            )

        with open(OUT_ARCHIVOS, "w", newline="", encoding="utf-8") as f:
            keys = ["Archivo_Origen", "Archivo_Destino", "Naturaleza_Fuerte", "Lista_Naturalezas", "Detalle_Tipos"]
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(file_rows)
        print(f"Generado: {OUT_ARCHIVOS}")

        # dep_06: INCLUDE file references — one row per INCLUDE statement
        include_rows = []
        seen_includes = set()
        for item in all_raw_deps:
            if item.get("dep_type") != "INCLUDE":
                continue
            target = item["target_raw"]
            key = (item["source_file"], item["source_unit"], target)
            if key in seen_includes:
                continue
            seen_includes.add(key)
            estado = "PRESENT" if (CARPETA_CODIGO / target).exists() else "MISSING"
            include_rows.append({
                "Source_File":    item["source_file"],
                "Source_Unit":    item["source_unit"],
                "Included_File":  target,
                "Status":         estado,
            })
        include_rows.sort(key=lambda r: (r["Source_File"], r["Source_Unit"]))

        with open(OUT_INCLUDES, "w", newline="", encoding="utf-8") as f:
            keys = ["Source_File", "Source_Unit", "Included_File", "Status"]
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(include_rows)
        print(f"Generado: {OUT_INCLUDES} ({len(include_rows)} referencias INCLUDE)")


if __name__ == "__main__":
    main()
