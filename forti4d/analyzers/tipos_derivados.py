import csv
import re
from collections import defaultdict
from pathlib import Path

from forti4d.analyzers.inventario import cargar_inventario
from forti4d.config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
RUTA_AUDIT     = RUTA_RESULTADOS / "audit"
SALIDA_TIPOS   = RUTA_RESULTADOS / "tipos_definicion.csv"
SALIDA_COMPS   = RUTA_RESULTADOS / "tipos_componentes.csv"

COLS_TIPOS = [
    "Archivo", "Unidad", "Tipo_Unidad",
    "Linea_Inicio", "Linea_Fin", "Nombre_Tipo", "N_Componentes",
]
COLS_COMPS = [
    "Archivo", "Nombre_Tipo",
    "Linea", "Posicion", "Nombre_Comp",
    "Tipo_Fortran", "Kind_Param", "Dimension", "Atributos",
]


# =============================================================================
# PATRONES DE EXTRACCIÓN (locales)
# =============================================================================

# Nombre de la definición: TYPE nombre  o  TYPE :: nombre  (F90)
RE_TIPO_NOMBRE = re.compile(r"^\s*type\b\s*(?:::\s*)?(\w+)", re.IGNORECASE)

# Cierre de bloque TYPE: END TYPE [nombre_opcional]
RE_END_TYPE = re.compile(r"^\s*end\s*type\b", re.IGNORECASE)

# Declaración F90 con ::
RE_DECL_F90 = re.compile(r"^(.*?)\s*::\s*(.+)$")

# Declaración F77 sin ::: tipo base + lista
RE_DECL_F77 = re.compile(
    r"^\s*(integer|real|double\s+precision|complex|logical|character|byte)"
    r"(\s*\*\s*\d+|\s*\(\s*(?:(?:kind|len)\s*=\s*)?\w+\s*\))?\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# Atributos simples en prefijo F90
RE_ATTR_DIM     = re.compile(r"\bdimension\s*\(([^)]+)\)", re.IGNORECASE)
RE_ATTR_SIMPLES = re.compile(
    r"\b(allocatable|pointer|save|target|volatile|private|public|protected)\b",
    re.IGNORECASE,
)


# =============================================================================
# FUNCIONES DE PARSEO
# =============================================================================

def extraer_kind(tipo_str: str) -> str:
    """Extrae KIND/LEN de un especificador de tipo, manejando paréntesis anidados."""
    m_star = re.search(r"\*\s*(\d+)", tipo_str)
    if m_star and "(" not in tipo_str[:m_star.start()].lstrip():
        return "*" + m_star.group(1)

    i = tipo_str.find("(")
    if i == -1:
        return ""

    depth, contenido = 0, []
    for ch in tipo_str[i + 1:]:
        if ch == "(":
            depth += 1
            contenido.append(ch)
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
            contenido.append(ch)
        else:
            contenido.append(ch)

    raw = "".join(contenido).strip()
    raw = re.sub(r"^(?:kind|len)\s*=\s*", "", raw, flags=re.IGNORECASE)
    return raw


def split_lista(s: str) -> list:
    """Divide por comas respetando paréntesis anidados."""
    partes, actual, depth = [], [], 0
    for ch in s:
        if ch == "(":
            depth += 1
            actual.append(ch)
        elif ch == ")":
            depth -= 1
            actual.append(ch)
        elif ch == "," and depth == 0:
            partes.append("".join(actual).strip())
            actual = []
        else:
            actual.append(ch)
    if actual:
        partes.append("".join(actual).strip())
    return [p for p in partes if p]


def parsear_componente(contenido: str, n_linea: int, pos_inicial: int) -> list:
    """
    Parsea una línea VAR_DECLARATION dentro del cuerpo de un TYPE.
    Retorna lista de dicts con los campos de componente.
    """
    filas = []

    if "::" in contenido:
        # F90 con ::
        m = RE_DECL_F90.match(contenido.strip())
        if not m:
            return []
        prefijo   = m.group(1).strip()
        lista_str = m.group(2).strip()

        # Extraer tipo base del prefijo
        partes_pref = split_lista(prefijo)
        tipo_base   = ""
        kind_base   = ""
        dim_base    = ""
        attrs       = []

        if partes_pref:
            tipo_str  = partes_pref[0].strip()
            m_base    = re.match(r"(\w+(?:\s+\w+)*)", tipo_str, re.IGNORECASE)
            tipo_base = m_base.group(1).upper() if m_base else ""
            kind_base = extraer_kind(tipo_str)

        for attr in partes_pref[1:]:
            m_dim = RE_ATTR_DIM.search(attr)
            if m_dim:
                dim_base = m_dim.group(1)
                attrs.append(f"DIMENSION({m_dim.group(1)})")
                continue
            m_s = RE_ATTR_SIMPLES.match(attr.strip())
            if m_s:
                attrs.append(attr.strip().upper())

        for entry in split_lista(lista_str):
            row = _parsear_entry(entry, tipo_base, kind_base, dim_base, attrs,
                                 n_linea, pos_inicial + len(filas))
            if row:
                filas.append(row)
    else:
        # F77 sin ::
        m = RE_DECL_F77.match(contenido.strip())
        if not m:
            return []
        tipo_base = re.sub(r"\s+", " ", m.group(1).upper())
        kind_base = extraer_kind(m.group(1) + (m.group(2) or ""))
        lista_str = m.group(3).strip()

        for entry in split_lista(lista_str):
            row = _parsear_entry(entry, tipo_base, kind_base, "", [],
                                 n_linea, pos_inicial + len(filas))
            if row:
                filas.append(row)

    return filas


def _parsear_entry(entry: str, tipo: str, kind: str, dim: str, attrs: list,
                   n_linea: int, posicion: int) -> dict:
    """Extrae nombre, dimensión e info de una entrada individual de la lista."""
    entry = entry.strip()
    # Quitar valor inicial (componentes con inicializadores: comp = valor)
    if "=" in entry:
        entry = entry[:entry.index("=")].strip()

    nombre = ""
    dim_local = dim

    m_star = re.match(r"^(\w+)\s*\*\s*(\d+)$", entry)
    if m_star:
        nombre = m_star.group(1)
        kind   = "*" + m_star.group(2)
    elif "(" in entry:
        m_dim = re.match(r"^(\w+)\s*\((.+)\)\s*$", entry)
        if m_dim:
            nombre    = m_dim.group(1)
            dim_local = m_dim.group(2).strip()
        else:
            nombre = re.sub(r"\(.*", "", entry).strip()
    else:
        nombre = entry

    if not re.match(r"^\w+$", nombre):
        return {}

    return {
        "Linea":       n_linea,
        "Posicion":    posicion,
        "Nombre_Comp": nombre.upper(),
        "Tipo_Fortran": tipo,
        "Kind_Param":  kind,
        "Dimension":   dim_local,
        "Atributos":   "|".join(attrs) if attrs else "",
    }


# =============================================================================
# SCOPE RESOLUTION
# =============================================================================

def resolver_scope(n_linea: int, unidades_en_archivo: list) -> tuple:
    """Retorna (nombre_unidad, tipo_unidad) para n_linea."""
    candidatos = [
        u for u in unidades_en_archivo
        if u["Linea_Inicio"] <= n_linea <= u["Linea_Fin"]
    ]
    if not candidatos:
        return "GLOBAL", "FILE_SCOPE"
    u = max(candidatos, key=lambda u: u["Linea_Inicio"])
    return u["Nombre"], u.get("Tipo", "UNKNOWN")


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

_KINDS_TIPO = {"TYPE_DEFINITION", "VAR_DECLARATION", "END_BLOCK_STMT"}


def extraer_tipos():
    print("--- Extracción de Tipos Derivados ---")

    # 1. Inventario
    try:
        inventario_lista = cargar_inventario()
    except Exception as e:
        print(f"ERROR cargando inventario: {e}")
        return

    if not inventario_lista:
        print("El inventario está vacío.")
        return

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

    filas_tipos = []
    filas_comps = []
    archivos_ordenados = sorted(mapa_unidades.keys(), key=str.lower)

    # 2. Procesar cada archivo con máquina de estados
    for nombre_archivo in archivos_ordenados:
        debug_file = RUTA_AUDIT / f"{nombre_archivo}_DEBUG.csv"
        if not debug_file.exists():
            continue

        unidades_en_archivo = sorted(
            mapa_unidades[nombre_archivo], key=lambda u: u["Linea_Inicio"]
        )

        tipo_activo = None   # dict mientras estamos dentro de un TYPE body

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                kind = row.get("Kind", "")
                if kind not in _KINDS_TIPO:
                    continue

                try:
                    n_linea = int(row["Linea"])
                except (ValueError, KeyError):
                    continue

                contenido = row.get("Contenido", "")

                if kind == "TYPE_DEFINITION":
                    m = RE_TIPO_NOMBRE.match(contenido)
                    if not m:
                        continue
                    host_unit, host_tipo = resolver_scope(n_linea, unidades_en_archivo)
                    tipo_activo = {
                        "Archivo":      nombre_archivo,
                        "Unidad":       host_unit,
                        "Tipo_Unidad":  host_tipo,
                        "Linea_Inicio": n_linea,
                        "Linea_Fin":    n_linea,   # se actualiza al cerrar
                        "Nombre_Tipo":  m.group(1).upper(),
                        "componentes":  [],
                    }

                elif tipo_activo is not None:
                    if kind == "END_BLOCK_STMT" and RE_END_TYPE.match(contenido):
                        tipo_activo["Linea_Fin"] = n_linea
                        # Emitir definición
                        comps = tipo_activo["componentes"]
                        filas_tipos.append({
                            "Archivo":      tipo_activo["Archivo"],
                            "Unidad":       tipo_activo["Unidad"],
                            "Tipo_Unidad":  tipo_activo["Tipo_Unidad"],
                            "Linea_Inicio": tipo_activo["Linea_Inicio"],
                            "Linea_Fin":    tipo_activo["Linea_Fin"],
                            "Nombre_Tipo":  tipo_activo["Nombre_Tipo"],
                            "N_Componentes": len(comps),
                        })
                        for comp in comps:
                            filas_comps.append({
                                "Archivo":     nombre_archivo,
                                "Nombre_Tipo": tipo_activo["Nombre_Tipo"],
                                **comp,
                            })
                        tipo_activo = None

                    elif kind == "VAR_DECLARATION":
                        pos_ini = len(tipo_activo["componentes"]) + 1
                        nuevos  = parsear_componente(contenido, n_linea, pos_ini)
                        tipo_activo["componentes"].extend(nuevos)

    # 3. Exportar CSVs
    _escribir_csv(SALIDA_TIPOS, filas_tipos, COLS_TIPOS)
    _escribir_csv(SALIDA_COMPS, filas_comps, COLS_COMPS)

    n_tipos = len(filas_tipos)
    n_comps = len(filas_comps)
    print(f"Tipos derivados         : {n_tipos}")
    print(f"Componentes totales     : {n_comps}")
    print()
    print("Generados:")
    print(f"  {SALIDA_TIPOS}")
    print(f"  {SALIDA_COMPS}")


# =============================================================================
# HELPERS
# =============================================================================

def _escribir_csv(ruta: Path, filas: list, columnas: list):
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    print(f"  → {ruta.name}  ({len(filas)} filas)")


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def main():
    extraer_tipos()


if __name__ == "__main__":
    main()
