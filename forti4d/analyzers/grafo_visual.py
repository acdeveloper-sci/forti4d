"""
grafo_visual.py
Genera archivos DOT (Graphviz) del grafo de llamadas del corpus Fortran.

Uso:
  python grafo_visual.py                        # grafo completo + simplificado (todos los EPs)
  python grafo_visual.py --entry mcdes          # solo el subgrafo de mcdes
  python grafo_visual.py --entry util0 util1    # subgrafo de dos ejecutables
  python grafo_visual.py --list                 # lista los entry points disponibles
  python grafo_visual.py --use                  # incluir aristas USE (módulos)

Renderizado (requiere Graphviz):
  dot -Tpng grafo_mcdes.dot        -o grafo_mcdes.png
  dot -Tsvg grafo_completo.dot     -o grafo_completo.svg
  dot -Tpdf grafo_simple.dot       -o grafo_simple.pdf
"""

import argparse
import csv
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
from forti4d.config import RUTA_RESULTADOS

GRAFO_CSV   = RUTA_RESULTADOS / "dep_02_grafo_unidades.csv"
CONSOLIDADO = RUTA_RESULTADOS / "reporte_consolidado.csv"

# Colores base
COLOR_ENTRADA       = "#4472C4"   # azul  — entry point seleccionado
COLOR_ALCANZABLE    = "#70AD47"   # verde — alcanzable
COLOR_NO_ALCANZABLE = "#A6A6A6"   # gris  — dead code
COLOR_COMPARTIDO    = "#FFD966"   # amarillo — alcanzable desde varios EPs
COLOR_DESCONOCIDO   = "#F2F2F2"   # gris claro — sin dato en consolidado

# Paleta para múltiples entry points (hasta 8)
PALETA_EP = [
    "#4472C4",  # azul
    "#ED7D31",  # naranja
    "#C00000",  # rojo
    "#7030A0",  # púrpura
    "#00B050",  # verde oscuro
    "#00B0F0",  # celeste
    "#9E480E",  # marrón
    "#FF69B4",  # rosa
]

# Estilos de arista
EDGE_STYLE = {
    "CALL":      'style=solid color="#333333"',
    "FUNC_CALL": 'style=solid color="#1F7A1F"',
    "USE":       'style=dashed color="#2E74B5" penwidth=0.8',
}

# Formas por tipo de unidad
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
    """dict: nombre.upper() -> fila del consolidado."""
    if not CONSOLIDADO.exists():
        return {}
    meta = {}
    with open(CONSOLIDADO, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            n = row.get("Unidad", "").strip()
            if n:
                meta[n.upper()] = row
    return meta


def cargar_grafo_raw() -> list:
    """Lista de filas de dep_02_grafo_unidades.csv."""
    with open(GRAFO_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def nombre_amigable(nodo: str, meta: dict) -> str:
    """
    MAIN__chcump.f90 → chcump   (IMPLICIT-MAIN)
    GEOLEC           → GEOLEC   (sin cambio)
    """
    if nodo.startswith("MAIN__"):
        archivo  = nodo[6:]
        sin_ext  = re.sub(r"\.\w+$", "", archivo)
        if sin_ext.upper() in meta:
            return meta[sin_ext.upper()]["Unidad"]
        return sin_ext
    return nodo


def construir_grafo_amigable(raw_edges: list, meta: dict) -> list:
    """
    Resuelve nombres MAIN__ y devuelve lista de
    (origen_inv, destino_inv, tipo_dep).
    """
    resultado = []
    for e in raw_edges:
        orig = nombre_amigable(e["Unidad_Origen"],  meta)
        dest = nombre_amigable(e["Unidad_Destino"], meta)
        resultado.append((orig, dest, e["Tipo_Dep"]))
    return resultado


# =============================================================================
# BFS DESDE ENTRY POINTS SELECCIONADOS
# =============================================================================

def entry_points_disponibles(meta: dict) -> list:
    """Lista de nombres de entry points (Estado=ENTRADA)."""
    return sorted(
        row["Unidad"]
        for row in meta.values()
        if row.get("Estado") == "ENTRADA"
    )


def bfs_desde(semilla: str, adyacencia: dict) -> set:
    """BFS en el grafo amigable. Devuelve set de nodos alcanzados."""
    visitados = {semilla}
    cola = deque([semilla])
    while cola:
        actual = cola.popleft()
        for vecino in adyacencia.get(actual.upper(), []):
            if vecino.upper() not in {v.upper() for v in visitados}:
                visitados.add(vecino)
                cola.append(vecino)
    return visitados


def calcular_alcance(entry_names: list, edges_amigables: list) -> dict:
    """
    Para cada entry point en entry_names, calcula el conjunto de nodos
    alcanzados por BFS.

    Devuelve dict: nombre_nodo_inv -> set de entry points que lo alcanzan.
    """
    # Construir adyacencia: origen.upper() -> [destino, ...]
    adyacencia = defaultdict(list)
    for orig, dest, _ in edges_amigables:
        adyacencia[orig.upper()].append(dest)

    alcance_por_ep = {}    # ep -> set de nodos
    for ep in entry_names:
        alcance_por_ep[ep] = bfs_desde(ep, adyacencia)

    # Invertir: nodo -> set de EPs que lo alcanzan
    nodo_eps = defaultdict(set)
    for ep, nodos in alcance_por_ep.items():
        for n in nodos:
            nodo_eps[n].add(ep)

    return dict(nodo_eps)


# =============================================================================
# COLORES
# =============================================================================

def asignar_colores_ep(entry_names: list) -> dict:
    """dict: ep_name -> color_hex (para la paleta de múltiples EPs)."""
    return {ep: PALETA_EP[i % len(PALETA_EP)] for i, ep in enumerate(entry_names)}


def color_nodo(nombre_inv: str, meta: dict,
               nodo_eps: dict, colores_ep: dict,
               entry_names_sel: list) -> tuple:
    """
    Devuelve (fillcolor, fontcolor) para el nodo.

    Lógica:
      - Si es uno de los entry points seleccionados → color del EP
      - Si alcanzado por un solo EP → color de ese EP (más claro)
      - Si alcanzado por varios EPs → COLOR_COMPARTIDO
      - Si no alcanzado (dead code en contexto filtrado) → COLOR_NO_ALCANZABLE
      - Sin datos → COLOR_DESCONOCIDO
    """
    eps_que_alcanzan = nodo_eps.get(nombre_inv, set()) & set(entry_names_sel)
    row   = meta.get(nombre_inv.upper(), {})
    tipo  = row.get("Tipo", "")
    es_ep = nombre_inv in entry_names_sel

    if es_ep:
        color = colores_ep.get(nombre_inv, COLOR_ENTRADA)
        return color, "#FFFFFF"

    if not eps_que_alcanzan:
        return COLOR_NO_ALCANZABLE, "#000000"

    if len(eps_que_alcanzan) == 1:
        # Mismo color del EP pero más claro: usamos el verde estándar
        # si hay un solo EP seleccionado, o el color del EP en multi
        if len(entry_names_sel) == 1:
            return COLOR_ALCANZABLE, "#000000"
        else:
            return COLOR_ALCANZABLE, "#000000"

    # Alcanzado por varios EPs
    return COLOR_COMPARTIDO, "#000000"


# =============================================================================
# GENERACIÓN DOT
# =============================================================================

def dot_id(nombre: str) -> str:
    return '"' + nombre.replace('"', '\\"') + '"'


def generar_dot(edges_amigables: list, meta: dict,
                nodos_permitidos: set,
                nodo_eps: dict,
                colores_ep: dict,
                entry_names_sel: list,
                incluir_use: bool,
                titulo: str) -> str:

    tipos_ok = {"CALL", "FUNC_CALL"}
    if incluir_use:
        tipos_ok.add("USE")

    # Filtrar aristas
    aristas = [
        (o, d, t) for o, d, t in edges_amigables
        if t in tipos_ok
        and o in nodos_permitidos
        and d in nodos_permitidos
    ]

    # Nodos que aparecen en alguna arista + entry points seleccionados
    nodos_usados = set(entry_names_sel)
    for o, d, _ in aristas:
        nodos_usados.add(o)
        nodos_usados.add(d)
    nodos_usados &= nodos_permitidos

    # Agrupar por archivo
    archivo_nodos = defaultdict(list)
    for n in sorted(nodos_usados):
        row     = meta.get(n.upper(), {})
        archivo = row.get("Archivo", "SIN_ARCHIVO")
        archivo_nodos[archivo].append(n)

    lines = []
    lines.append(f'digraph {titulo} {{')
    lines.append('  rankdir=LR;')
    lines.append('  compound=true;')
    lines.append('  graph [fontname="Helvetica" fontsize=10 bgcolor="#F8F8F8"];')
    lines.append('  node  [fontname="Helvetica"];')
    lines.append('  edge  [fontname="Helvetica" fontsize=8 arrowsize=0.7];')
    lines.append('')

    # Leyenda dinámica
    lines.append('  subgraph cluster_leyenda {')
    lines.append('    label="Leyenda" fontsize=9 style=dotted rank=sink;')
    if len(entry_names_sel) == 1:
        ep = entry_names_sel[0]
        c  = colores_ep[ep]
        lines.append(f'    _ep  [label="{ep}" shape=doubleoctagon style=filled fillcolor="{c}" fontcolor=white fontsize=8];')
        lines.append(f'    _alc [label="Alcanzable"  shape=box style=filled fillcolor="{COLOR_ALCANZABLE}"    fontcolor=black fontsize=8];')
        lines.append(f'    _ep -> _alc [style=solid label="CALL" fontsize=7];')
    else:
        for ep, c in colores_ep.items():
            safe = ep.replace('"', '\\"').replace('-', '_').replace(' ', '_')
            lines.append(f'    _ep_{safe} [label="{ep}" shape=doubleoctagon style=filled fillcolor="{c}" fontcolor=white fontsize=8];')
        lines.append(f'    _comp [label="Compartido" shape=box style=filled fillcolor="{COLOR_COMPARTIDO}" fontcolor=black fontsize=8];')
        lines.append(f'    _alc  [label="Alcanzable" shape=box style=filled fillcolor="{COLOR_ALCANZABLE}"  fontcolor=black fontsize=8];')
    lines.append('  }')
    lines.append('')

    # Clusters por archivo
    for cid, archivo in enumerate(sorted(archivo_nodos.keys())):
        nodos = sorted(archivo_nodos[archivo])
        label_arch = archivo.replace('"', '\\"')
        lines.append(f'  subgraph cluster_{cid} {{')
        lines.append(f'    label="{label_arch}" fontsize=8 style=rounded color="#CCCCCC";')
        for n in nodos:
            row    = meta.get(n.upper(), {})
            tipo   = row.get("Tipo", "")
            cc     = row.get("CC", "")
            fan_in = row.get("Fan_In", "")
            shape  = SHAPE.get(tipo, SHAPE_DEFAULT)

            fillcolor, fontcolor = color_nodo(
                n, meta, nodo_eps, colores_ep, entry_names_sel
            )

            partes = [n]
            if cc:     partes.append(f"CC={cc}")
            if fan_in: partes.append(f"Fi={fan_in}")
            label   = r"\n".join(partes)
            tooltip = f"{tipo} | {archivo}" if tipo else archivo

            lines.append(
                f'    {dot_id(n)} [shape={shape} style=filled '
                f'fillcolor="{fillcolor}" fontcolor="{fontcolor}" '
                f'fontsize=9 label="{label}" tooltip="{tooltip}"];'
            )
        lines.append('  }')

    lines.append('')
    lines.append('  // --- Aristas ---')
    for orig, dest, tipo_dep in sorted(set(aristas)):
        style = EDGE_STYLE.get(tipo_dep, "")
        lines.append(f'  {dot_id(orig)} -> {dot_id(dest)} [{style}];')

    lines.append('}')
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Genera grafos DOT del call graph Fortran."
    )
    parser.add_argument(
        "--entry", nargs="+", metavar="NOMBRE",
        help="Entry point(s) a graficar. Sin este flag genera el grafo completo."
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Lista los entry points disponibles y termina."
    )
    parser.add_argument(
        "--use", action="store_true",
        help="Incluir aristas USE (dependencias de módulo). Por defecto solo CALL/FUNC_CALL."
    )
    args = parser.parse_args()

    if not GRAFO_CSV.exists():
        print(f"ERROR: No se encuentra {GRAFO_CSV}")
        sys.exit(1)

    meta        = cargar_consolidado()
    raw_edges   = cargar_grafo_raw()
    edges_am    = construir_grafo_amigable(raw_edges, meta)
    eps_disponibles = entry_points_disponibles(meta)

    # --list
    if args.list:
        print("Entry points disponibles:")
        for ep in eps_disponibles:
            row = meta.get(ep.upper(), {})
            tipo = row.get("Tipo", "")
            arch = row.get("Archivo", "")
            print(f"  {ep:25}  [{tipo}]  {arch}")
        return

    incluir_use = args.use

    # -------------------------------------------------------------------------
    # Modo filtrado: --entry especificado
    # -------------------------------------------------------------------------
    if args.entry:
        # Resolver nombres (case-insensitive)
        ep_upper = {ep.upper(): ep for ep in eps_disponibles}
        entry_sel = []
        for nombre in args.entry:
            if nombre.upper() in ep_upper:
                entry_sel.append(ep_upper[nombre.upper()])
            else:
                print(f"AVISO: '{nombre}' no es un entry point conocido. Ignorado.")

        if not entry_sel:
            print("ERROR: Ninguno de los entry points indicados existe.")
            print("Usa --list para ver los disponibles.")
            sys.exit(1)

        print(f"Entry points seleccionados: {', '.join(entry_sel)}")

        # BFS desde los seleccionados
        nodo_eps   = calcular_alcance(entry_sel, edges_am)
        colores_ep = asignar_colores_ep(entry_sel)

        # Nodos permitidos = todos los alcanzados desde alguno de los EPs
        nodos_perm = set(nodo_eps.keys())

        # Nombre del archivo de salida
        safe_names = "_".join(
            re.sub(r"[^a-zA-Z0-9]", "", ep) for ep in entry_sel
        )
        salida = RUTA_RESULTADOS / f"grafo_{safe_names}.dot"

        titulo = "CallGraph_" + safe_names
        dot = generar_dot(
            edges_am, meta,
            nodos_permitidos=nodos_perm,
            nodo_eps=nodo_eps,
            colores_ep=colores_ep,
            entry_names_sel=entry_sel,
            incluir_use=incluir_use,
            titulo=titulo,
        )
        RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
        salida.write_text(dot, encoding="utf-8")
        print(f"Generado: {salida}  ({len(nodos_perm)} nodos)")
        print(f"\nPara renderizar:")
        stem = salida.stem
        print(f"  dot -Tpng {salida} -o {RUTA_RESULTADOS / (stem + '.png')}")
        print(f"  dot -Tsvg {salida} -o {RUTA_RESULTADOS / (stem + '.svg')}")

    # -------------------------------------------------------------------------
    # Modo completo: sin --entry
    # -------------------------------------------------------------------------
    else:
        n_call = sum(1 for e in raw_edges if e["Tipo_Dep"] == "CALL")
        n_func = sum(1 for e in raw_edges if e["Tipo_Dep"] == "FUNC_CALL")
        n_use  = sum(1 for e in raw_edges if e["Tipo_Dep"] == "USE")
        print(f"Grafo: {len(meta)} nodos  |  {n_call} CALL  {n_func} FUNC_CALL  {n_use} USE")

        nodo_eps   = calcular_alcance(eps_disponibles, edges_am)
        colores_ep = asignar_colores_ep(eps_disponibles)

        # Grafo completo: todos los nodos del consolidado
        todos = set(row["Unidad"] for row in meta.values())

        dot_full = generar_dot(
            edges_am, meta,
            nodos_permitidos=todos,
            nodo_eps=nodo_eps,
            colores_ep=colores_ep,
            entry_names_sel=eps_disponibles,
            incluir_use=True,
            titulo="CallGraph_Completo",
        )
        RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
        (RUTA_RESULTADOS / "grafo_completo.dot").write_text(dot_full, encoding="utf-8")
        print(f"Generado: {RUTA_RESULTADOS / 'grafo_completo.dot'}")

        # Grafo simple: solo alcanzables, sin USE
        alcanzables = {
            n for n, eps in nodo_eps.items() if eps
        } | set(eps_disponibles)

        dot_simple = generar_dot(
            edges_am, meta,
            nodos_permitidos=alcanzables,
            nodo_eps=nodo_eps,
            colores_ep=colores_ep,
            entry_names_sel=eps_disponibles,
            incluir_use=False,
            titulo="CallGraph_Simple",
        )
        (RUTA_RESULTADOS / "grafo_simple.dot").write_text(dot_simple, encoding="utf-8")
        print(f"Generado: {RUTA_RESULTADOS / 'grafo_simple.dot'}")

        print()
        print("Para renderizar:")
        print("  dot -Tpng  grafo_simple.dot   -o grafo_simple.png")
        print("  dot -Tsvg  grafo_completo.dot -o grafo_completo.svg")
        print()
        print("Para un ejecutable específico:")
        print("  python grafo_visual.py --list")
        print("  python grafo_visual.py --entry mcdes")


if __name__ == "__main__":
    main()
