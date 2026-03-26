import csv
import sys
import os
from collections import Counter, defaultdict

try:
    from inventario import cargar_inventario
except ImportError:

    def cargar_inventario():
        return []


# =============================================================================
# DEFINICIONES MAESTRAS (GRAMÁTICA DE ESTRUCTURAS)
# =============================================================================

CONSTRUCTORES_INICIO = {
    "IF_CONSTRUCT",
    "DO_CONSTRUCT",
    "DO_WHILE_CONSTRUCT",
    "SELECT_CONSTRUCT",
    "SELECT_TYPE_CONSTRUCT",
    "BLOCK_CONSTRUCT",
    "INTERFACE_BLOCK",
    "TYPE_DEFINITION",
    "ASSOCIATE_CONSTRUCT",
    "FORALL_CONSTRUCT",
    "WHERE_CONSTRUCT",
    "CRITICAL_CONSTRUCT",
}

# LISTA EXHAUSTIVA DE CIERRES PARA EVITAR DESBORDE DE PILA
CONSTRUCTORES_FIN = {
    "END_IF_STMT",
    "END_DO_STMT",
    "END_SELECT_STMT",
    "END_BLOCK_STMT",
    "END_ASSOCIATE_STMT",
    "END_FORALL_STMT",
    "END_WHERE_STMT",
    "END_CRITICAL_STMT",
    "END_INTERFACE_STMT",
    "END_TYPE_STMT",
    "END_FUNCTION_STMT",
    "END_SUBROUTINE_STMT",
    "END_MODULE_STMT",
    "END_PROGRAM_STMT",
}

KINDS_ESPECIFICACION = {
    "VAR_DECLARATION",
    "PARAMETER_STMT",
    "USE_STMT",
    "IMPLICIT_STMT",
    "IMPORT_STMT",
    "NAMELIST_STMT",
    "DATA_STMT",
    "COMMON_STMT",
    "EQUIVALENCE_STMT",
    "INCLUDE_STMT",
    "EXTERNAL_STMT",
    "INTRINSIC_STMT",
}


def clasificar_intencion(kind, contenido):
    kind = kind.strip()

    # 1. Estructura Mayor
    if kind == "CONTAINS_STMT":
        return "ESTRUCTURA_CONTAINS"

    # 2. Especificación (Declaraciones)
    if kind in KINDS_ESPECIFICACION:
        return "ESPECIFICACION"

    # 3. Control de Flujo (Jerarquía)
    if kind in CONSTRUCTORES_INICIO:
        return "INICIO_ESTRUCTURA"
    if kind in CONSTRUCTORES_FIN:
        return "FIN_ESTRUCTURA"

    # 4. Acciones Ejecutables
    if kind in ("ALLOCATION_STMT", "DEALLOCATE_STMT", "NULLIFY_STMT"):
        return "GESTION_MEMORIA"
    if kind == "IO_STMT":
        return "ENTRADA_SALIDA"
    if kind == "ASSIGNMENT_STMT":
        return "CALCULO"
    if kind == "CONTROL_STMT":
        return "CONTROL_FLUJO"  # GOTO, CYCLE, EXIT, STOP

    # 5. Divisores de estructura (no cambian profundidad pero son visibles)
    if kind in ("ELSE_STMT", "CASE_STMT"):
        return "DIVISOR_BLOQUE"

    # 6. Ruido Visual
    # COMMENT: perfilador produce "COMMENT", no "COMMENT_LINE"
    # Headers de unidad (SUBROUTINE, FUNCTION, etc.): son fronteras estructurales, no lógica
    if kind in ("BLANK_LINE", "COMMENT",
                "SUBROUTINE_UNIT", "FUNCTION_UNIT", "MODULE_UNIT",
                "PROGRAM_UNIT", "BLOCK_DATA_UNIT"):
        return "ESPACIO"

    return "OTRO"


# =============================================================================
# MOTOR DE ANÁLISIS TOPOLÓGICO (STACK TRACKING)
# =============================================================================


def analizar_topologia(lineas):
    """
    Recorre las líneas manteniendo una pila de profundidad y generando
    bloques consolidados por (Nivel, Tipo).
    """
    if not lineas:
        return []

    bloques = []
    stack = []

    # Estado del bloque actual
    # Iniciamos con un bloque ficticio para facilitar la lógica del bucle
    bloque_act = {"inicio": lineas[0]["n"], "fin": lineas[0]["n"], "dp": 0, "tipo": "INICIO", "detalle": Counter()}

    for l in lineas:
        tipo = clasificar_intencion(l["kind"], l["contenido"])

        # --- Lógica de Profundidad (Visualización Alineada) ---
        # Queremos:
        # IF (...)      -> Nivel 0
        #   CALCULO     -> Nivel 1
        # END IF        -> Nivel 0

        dp_visual = len(stack)

        if tipo == "INICIO_ESTRUCTURA":
            # El inicio se imprime al nivel actual, luego subimos
            stack.append(l["kind"])
            # dp_visual se queda en len(stack)-1 (el nivel antes de entrar)
            # Pero como acabamos de hacer append, len es N+1. Restamos 1.
            dp_visual = len(stack) - 1

        elif tipo == "FIN_ESTRUCTURA":
            # Bajamos primero, luego imprimimos al nivel destino
            if stack:
                stack.pop()
            dp_visual = len(stack)

        else:
            # Contenido normal: está al nivel actual de la pila
            dp_visual = len(stack)

        # --- Lógica de Corte de Bloque ---
        # Cortamos si:
        # 1. Cambia la profundidad visual (entramos/salimos de estructura)
        # 2. Cambia la intención (ej. de MEMORIA a CALCULO)
        # 3. Es un delimitador de estructura (para aislarlos visualmente)

        cambio_dp = dp_visual != bloque_act["dp"]
        cambio_tipo = tipo != bloque_act["tipo"] and tipo != "ESPACIO" and bloque_act["tipo"] != "ESPACIO"
        es_hito = tipo in ("INICIO_ESTRUCTURA", "FIN_ESTRUCTURA", "ESTRUCTURA_CONTAINS")

        if cambio_dp or cambio_tipo or es_hito:
            # Guardar el anterior (si no es basura inicial)
            if bloque_act["tipo"] != "INICIO":
                bloques.append(bloque_act)

            # Crear nuevo bloque
            tipo_nuevo = tipo if tipo != "ESPACIO" else bloque_act["tipo"]

            # Renombrar para claridad en reporte
            if tipo == "INICIO_ESTRUCTURA":
                tipo_nuevo = f"APERTURA ({l['kind'].replace('_CONSTRUCT','').replace('_BLOCK','')})"
            if tipo == "FIN_ESTRUCTURA":
                tipo_nuevo = "CIERRE_ESTRUCTURA"

            bloque_act = {"inicio": l["n"], "fin": l["n"], "dp": dp_visual, "tipo": tipo_nuevo, "detalle": Counter()}

        # Acumular
        bloque_act["fin"] = l["n"]
        if tipo not in ("ESPACIO", "INICIO_ESTRUCTURA", "FIN_ESTRUCTURA"):
            bloque_act["detalle"][tipo] += 1

    # Guardar el último
    if bloque_act["tipo"] != "INICIO":
        bloques.append(bloque_act)

    # --- Fase de Consolidación Visual ---
    # Unir bloques consecutivos que sean idénticos en tipo y profundidad
    # (Ej. 3 líneas de CALCULO seguidas de 1 comentario seguido de 2 de CALCULO)
    bloques_finales = []
    if not bloques:
        return []

    curr = bloques[0]
    for b in bloques[1:]:
        ignorable = b["tipo"] == "ESPACIO"
        mismo_tipo = b["tipo"] == curr["tipo"] and b["dp"] == curr["dp"]

        if mismo_tipo:
            curr["fin"] = b["fin"]
            curr["detalle"] += b["detalle"]
        elif not ignorable:
            bloques_finales.append(curr)
            curr = b

    bloques_finales.append(curr)

    return [b for b in bloques_finales if b["tipo"] not in ("ESPACIO", "INICIO")]


def imprimir_bloques(bloques, indent_base=""):
    print(f"{indent_base}{'LÍNEAS':>11} | DP | {'ÁRBOL':<28} {'ESTRUCTURA / INTENCIÓN':<22} | DETALLE")
    print(f"{indent_base}{'-'*95}")

    for b in bloques:
        # Visualización de árbol con caracteres ASCII
        # Nivel 0: ""
        # Nivel 1: "|_"
        # Nivel 2: "| |_"

        arbol = ""
        if b["dp"] > 0:
            arbol = "| " * (b["dp"] - 1) + "|_"

        # Formato de detalle limpio
        det = ", ".join([f"{k}:{v}" for k, v in b["detalle"].most_common(3)])

        print(f"{indent_base}{b['inicio']:>5}-{b['fin']:<5} | {b['dp']:>2} | {arbol:<28} {b['tipo']:<22} | {det}")


# =============================================================================
# MAIN (Integración con Inventario)
# =============================================================================


def main(archivo_debug):
    if not os.path.exists(archivo_debug):
        return
    nombre_fuente = os.path.basename(archivo_debug).replace("_DEBUG.csv", "")

    # 1. Cargar metadatos
    inv = cargar_inventario()
    unidades_map = {u["Nombre"]: u for u in inv if u["Archivo"].lower() == nombre_fuente.lower()}

    # 2. Cargar líneas crudas
    lineas_por_unidad = defaultdict(list)
    lineas_raw = []
    with open(archivo_debug, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lineas_raw.append({"n": int(row["Linea"]), "kind": row["Kind"], "contenido": row.get("Contenido", "")})

    # Asignar líneas a unidades
    for nombre, u in unidades_map.items():
        ini, fin = int(u["Linea_Inicio"]), int(u["Linea_Fin"])
        mis_lineas = [l for l in lineas_raw if ini <= l["n"] <= fin]
        mis_lineas.sort(key=lambda x: x["n"])
        lineas_por_unidad[nombre] = mis_lineas

    # 3. Reporte Jerárquico Recursivo
    visitados = set()

    def reportar(nombre_u, nivel=0):
        if nombre_u in visitados:
            return
        visitados.add(nombre_u)

        u = unidades_map.get(nombre_u)
        if not u:
            return

        lineas = lineas_por_unidad[nombre_u]
        hijos = [h["Nombre"] for h in inv if h["Padre"] == nombre_u]
        hijos_objs = [unidades_map[h] for h in hijos if h in unidades_map]
        hijos_objs.sort(key=lambda x: int(x["Linea_Inicio"]))

        indent = "    " * nivel
        print(f"\n{indent}>> UNIDAD: {nombre_u} ({u['Tipo']})")

        # Procesar segmentos entre hijos (Huecos)
        cursor = 0
        total = len(lineas)

        for h in hijos_objs:
            h_ini = int(h["Linea_Inicio"])
            h_fin = int(h["Linea_Fin"])

            # Segmento antes del hijo
            seg = []
            while cursor < total and lineas[cursor]["n"] < h_ini:
                seg.append(lineas[cursor])
                cursor += 1

            if seg:
                bloques = analizar_topologia(seg)
                imprimir_bloques(bloques, indent + "  ")

            # Recurrir al hijo
            reportar(h["Nombre"], nivel + 1)

            # Saltar líneas del hijo en el padre
            while cursor < total and lineas[cursor]["n"] <= h_fin:
                cursor += 1

        # Segmento final
        seg_final = []
        while cursor < total:
            seg_final.append(lineas[cursor])
            cursor += 1

        if seg_final:
            bloques = analizar_topologia(seg_final)
            imprimir_bloques(bloques, indent + "  ")

    print(f"ANÁLISIS ESTRUCTURAL V10: {nombre_fuente}")
    print("=" * 80)

    raices = [u for u in unidades_map.values() if u["Padre"] == "GLOBAL"]
    raices.sort(key=lambda x: int(x["Linea_Inicio"]))

    for r in raices:
        reportar(r["Nombre"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python analisis_bloques.py <archivo_DEBUG.csv>")
    else:
        main(sys.argv[1])
