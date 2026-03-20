"""
grafo_visual.py
Genera archivos DOT (Graphviz) del grafo de llamadas del corpus Fortran.

Salidas:
  grafo_completo.dot   — todos los nodos y aristas
  grafo_simple.dot     — solo unidades alcanzables, solo CALL y FUNC_CALL

Renderizado (requiere Graphviz instalado):
  dot -Tpng grafo_simple.dot   -o grafo_simple.png
  dot -Tsvg grafo_completo.dot -o grafo_completo.svg
  dot -Tpdf grafo_simple.dot   -o grafo_simple.pdf
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
GRAFO_CSV    = "dep_02_grafo_unidades.csv"
CONSOLIDADO  = "reporte_consolidado.csv"

SALIDA_FULL   = "grafo_completo.dot"
SALIDA_SIMPLE = "grafo_simple.dot"

# Colores por estado de alcanzabilidad
COLOR_ENTRADA       = "#4472C4"   # azul
COLOR_ALCANZABLE    = "#70AD47"   # verde
COLOR_NO_ALCANZABLE = "#A6A6A6"   # gris
COLOR_DESCONOCIDO   = "#FFE699"   # amarillo (sin dato)

COLOR_FONT_DARK  = "#FFFFFF"      # texto blanco sobre fondos oscuros
COLOR_FONT_LIGHT = "#000000"      # texto negro sobre fondos claros

# Estilos de arista por tipo de dependencia
EDGE_STYLE = {
    "CALL":      'style=solid color="#222222"',
    "FUNC_CALL": 'style=solid color="#1F7A1F"',
    "USE":       'style=dashed color="#2E74B5" penwidth=0.8',
}

# Formas de nodo por tipo de unidad
SHAPE = {
    "PROGRAM":       "doubleoctagon",
    "IMPLICIT-MAIN": "doubleoctagon",
    "MODULE":        "hexagon",
    "SUBROUTINE":    "box",
    "FUNCTION":      "ellipse",
    "BLOCK_DATA":    "diamond",
}
SHAPE_DEFAULT = "box"


# =============================================================================
# CARGA DE DATOS
# =============================================================================

def cargar_consolidado() -> dict:
    """
    Devuelve dict: nombre_upper -> fila del consolidado.
    La clave en mayúsculas permite búsqueda case-insensitive.
    """
    p = Path(CONSOLIDADO)
    if not p.exists():
        return {}
    meta = {}
    with open(CONSOLIDADO, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nombre = row.get("Unidad", "").strip()
            if nombre:
                meta[nombre.upper()] = row
    return meta


def cargar_grafo() -> list:
    """Devuelve lista de filas del grafo de dependencias."""
    with open(GRAFO_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def nombre_amigable(nodo_grafo: str, meta: dict) -> str:
    """
    Convierte el nombre interno del grafo al nombre del inventario.
    MAIN__chcump.f90  →  chcump
    GEOLEC            →  GEOLEC  (ya está bien)
    """
    if nodo_grafo.startswith("MAIN__"):
        archivo = nodo_grafo[6:]          # quita "MAIN__"
        # El nombre en inventario es el archivo sin extensión... pero puede
        # tener espacios (ej: "mcdes - Copie.f90").  Buscamos en meta.
        sin_ext = re.sub(r"\.\w+$", "", archivo)
        if sin_ext.upper() in meta:
            return meta[sin_ext.upper()]["Unidad"]
        # Fallback: usar el nombre de archivo sin extensión
        return sin_ext
    return nodo_grafo


# =============================================================================
# CONSTRUCCIÓN DEL DOT
# =============================================================================

def dot_id(nombre: str) -> str:
    """Identificador DOT seguro: entre comillas dobles escapadas."""
    return '"' + nombre.replace('"', '\\"') + '"'


def atributos_nodo(nombre_inv: str, meta: dict) -> str:
    """
    Devuelve la cadena de atributos DOT para un nodo dado su nombre inventario.
    """
    row = meta.get(nombre_inv.upper(), {})

    tipo   = row.get("Tipo",   "")
    estado = row.get("Estado", "")
    cc     = row.get("CC",     "")
    fan_in = row.get("Fan_In", "")
    archivo= row.get("Archivo","")

    # Color de fondo
    if estado == "ENTRADA":
        fillcolor = COLOR_ENTRADA
        fontcolor = COLOR_FONT_DARK
    elif estado == "ALCANZABLE":
        fillcolor = COLOR_ALCANZABLE
        fontcolor = COLOR_FONT_LIGHT
    elif estado == "NO_ALCANZABLE":
        fillcolor = COLOR_NO_ALCANZABLE
        fontcolor = COLOR_FONT_LIGHT
    else:
        fillcolor = COLOR_DESCONOCIDO
        fontcolor = COLOR_FONT_LIGHT

    shape = SHAPE.get(tipo, SHAPE_DEFAULT)

    # Etiqueta: nombre + métricas clave (si existen)
    partes = [nombre_inv]
    if cc:
        partes.append(f"CC={cc}")
    if fan_in:
        partes.append(f"Fi={fan_in}")
    label = r"\n".join(partes)

    tooltip = f"{tipo} | {archivo}" if tipo else archivo

    return (f'shape={shape} style=filled fillcolor="{fillcolor}" '
            f'fontcolor="{fontcolor}" fontsize=9 '
            f'label="{label}" tooltip="{tooltip}"')


def generar_dot(edges: list, meta: dict, solo_alcanzables: bool, incluir_use: bool) -> str:
    """
    Construye el texto DOT completo.

    solo_alcanzables : excluye nodos NO_ALCANZABLE
    incluir_use      : incluye aristas de tipo USE
    """
    # Filtrar aristas
    tipos_arista = {"CALL", "FUNC_CALL"}
    if incluir_use:
        tipos_arista.add("USE")

    aristas_filtradas = [
        e for e in edges
        if e["Tipo_Dep"] in tipos_arista
    ]

    # Resolver nombres amigables en las aristas
    aristas_resueltas = []
    for e in aristas_filtradas:
        origen  = nombre_amigable(e["Unidad_Origen"],  meta)
        destino = nombre_amigable(e["Unidad_Destino"], meta)
        aristas_resueltas.append((origen, destino, e["Tipo_Dep"]))

    # Filtrar nodos si solo_alcanzables
    nodos_usados = set()
    for orig, dest, _ in aristas_resueltas:
        nodos_usados.add(orig)
        nodos_usados.add(dest)

    if solo_alcanzables:
        # Mantener solo nodos con Estado != NO_ALCANZABLE
        nodos_ok = set()
        for n in nodos_usados:
            row = meta.get(n.upper(), {})
            estado = row.get("Estado", "")
            if estado != "NO_ALCANZABLE":
                nodos_ok.add(n)
        # Filtrar aristas donde ambos extremos estén en nodos_ok
        aristas_resueltas = [
            (o, d, t) for o, d, t in aristas_resueltas
            if o in nodos_ok and d in nodos_ok
        ]
        nodos_usados = nodos_ok

    # Agrupar nodos por archivo para clusters
    archivo_nodos = defaultdict(list)
    for n in sorted(nodos_usados):
        row    = meta.get(n.upper(), {})
        archivo = row.get("Archivo", "SIN_ARCHIVO")
        archivo_nodos[archivo].append(n)

    # --- Construir DOT ---
    lines = []
    titulo = "CallGraph_Simple" if solo_alcanzables else "CallGraph_Completo"
    lines.append(f'digraph {titulo} {{')
    lines.append('  rankdir=LR;')
    lines.append('  compound=true;')
    lines.append('  graph [fontname="Helvetica" fontsize=10 bgcolor="#F8F8F8"];')
    lines.append('  node  [fontname="Helvetica"];')
    lines.append('  edge  [fontname="Helvetica" fontsize=8 arrowsize=0.7];')
    lines.append('')

    # Leyenda
    lines.append('  // --- Leyenda ---')
    lines.append('  subgraph cluster_leyenda {')
    lines.append('    label="Leyenda" fontsize=9 style=dotted;')
    lines.append(f'    _ep   [label="Entry Point" shape=doubleoctagon style=filled fillcolor="{COLOR_ENTRADA}"     fontcolor=white  fontsize=8];')
    lines.append(f'    _alc  [label="Alcanzable"  shape=box          style=filled fillcolor="{COLOR_ALCANZABLE}"  fontcolor=black  fontsize=8];')
    lines.append(f'    _dead [label="Dead code"   shape=box          style=filled fillcolor="{COLOR_NO_ALCANZABLE}" fontcolor=black fontsize=8];')
    lines.append('    _ep -> _alc  [style=solid  label="CALL"      fontsize=7];')
    lines.append('    _ep -> _dead [style=dashed label="USE"       fontsize=7];')
    lines.append('    _alc -> _dead [style=solid color="#1F7A1F" label="FUNC_CALL" fontsize=7];')
    lines.append('  }')
    lines.append('')

    # Clusters por archivo
    cluster_id = 0
    for archivo in sorted(archivo_nodos.keys()):
        nodos = sorted(archivo_nodos[archivo])
        label_arch = archivo.replace('"', '\\"')
        lines.append(f'  subgraph cluster_{cluster_id} {{')
        lines.append(f'    label="{label_arch}" fontsize=8 style=rounded color="#CCCCCC";')
        for n in nodos:
            attrs = atributos_nodo(n, meta)
            lines.append(f'    {dot_id(n)} [{attrs}];')
        lines.append('  }')
        cluster_id += 1

    lines.append('')

    # Aristas
    lines.append('  // --- Aristas ---')
    for orig, dest, tipo_dep in sorted(set(aristas_resueltas)):
        style = EDGE_STYLE.get(tipo_dep, "")
        lines.append(f'  {dot_id(orig)} -> {dot_id(dest)} [{style}];')

    lines.append('}')
    return "\n".join(lines)


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def main():
    print("--- Generador de Grafo Visual (DOT) ---")

    if not Path(GRAFO_CSV).exists():
        print(f"ERROR: No se encuentra {GRAFO_CSV}")
        return

    meta   = cargar_consolidado()
    edges  = cargar_grafo()

    n_call     = sum(1 for e in edges if e["Tipo_Dep"] == "CALL")
    n_func     = sum(1 for e in edges if e["Tipo_Dep"] == "FUNC_CALL")
    n_use      = sum(1 for e in edges if e["Tipo_Dep"] == "USE")
    n_nodos    = len(meta)

    print(f"Grafo: {n_nodos} nodos  |  {n_call} CALL  {n_func} FUNC_CALL  {n_use} USE")

    # Grafo completo (todos los nodos, todas las aristas)
    dot_full = generar_dot(edges, meta, solo_alcanzables=False, incluir_use=True)
    Path(SALIDA_FULL).write_text(dot_full, encoding="utf-8")
    print(f"Generado: {SALIDA_FULL}")

    # Grafo simplificado (solo alcanzables, solo CALL + FUNC_CALL)
    dot_simple = generar_dot(edges, meta, solo_alcanzables=True, incluir_use=False)
    Path(SALIDA_SIMPLE).write_text(dot_simple, encoding="utf-8")
    print(f"Generado: {SALIDA_SIMPLE}")

    print()
    print("Para renderizar (requiere Graphviz):")
    print(f"  dot -Tpng  {SALIDA_SIMPLE}  -o grafo_simple.png")
    print(f"  dot -Tsvg  {SALIDA_FULL}    -o grafo_completo.svg")
    print(f"  dot -Tpdf  {SALIDA_SIMPLE}  -o grafo_simple.pdf")


if __name__ == "__main__":
    main()
