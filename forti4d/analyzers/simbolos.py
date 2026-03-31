import csv
import re
from collections import defaultdict
from pathlib import Path

from forti4d.analyzers.inventario import cargar_inventario
from forti4d.config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
RUTA_AUDIT    = RUTA_RESULTADOS / "audit"
SALIDA_VARS   = RUTA_RESULTADOS / "symbol_variables.csv"
SALIDA_FIRMAS = RUTA_RESULTADOS / "symbol_signatures.csv"
SALIDA_IMPL   = RUTA_RESULTADOS / "symbol_implicit.csv"

COLS_VARIABLES = [
    "Archivo", "Unidad", "Tipo_Unidad", "Linea",
    "Var_Name", "Fortran_Type", "Kind_Param", "Dimension",
    "Attributes", "Intent", "Initial_Value", "Is_Parameter", "In_Common", "Truncated",
]
COLS_FIRMAS = [
    "Archivo", "Unidad", "Tipo_Unidad", "Signature_Line",
    "Position", "Arg_Name", "Return_Type",
]
COLS_IMPLICIT = [
    "Archivo", "Unidad", "Tipo_Unidad", "Linea", "Rule", "Is_None",
]


# =============================================================================
# PATRONES DE EXTRACCIÓN (locales a este script — no pertenecen a patterns_v2)
# =============================================================================

# -- Firmas --
# SUBROUTINE: opcional PURE/ELEMENTAL/RECURSIVE, luego nombre y lista de args
RE_FIRMA_SUB = re.compile(
    r"^\s*(?:(?:pure|elemental|recursive)\s+)*subroutine\s+(\w+)\s*\(\s*(.*?)\s*\)",
    re.IGNORECASE,
)
# FUNCTION: cualquier prefijo (qualifiers + tipo de retorno), luego nombre y args
# El RESULT clause opcional se ignora por el $ greedy
RE_FIRMA_FUNC = re.compile(
    r"^\s*(.*?)\bfunction\s+(\w+)\s*\(\s*(.*?)\s*\)\s*(?:result\s*\(\s*\w+\s*\))?\s*$",
    re.IGNORECASE,
)

# -- Declaraciones F90 (con ::) --
RE_DECL_F90 = re.compile(r"^(.*?)\s*::\s*(.+)$")

# -- Declaraciones F77 (sin ::): tipo base seguido de lista de variables --
RE_DECL_F77 = re.compile(
    r"^\s*(integer|real|double\s+precision|complex|logical|character|byte|type|class)"
    r"(\s*\*\s*\d+|\s*\(\s*(?:(?:kind|len)\s*=\s*)?\w+\s*\))?\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# -- PARAMETER standalone F77: PARAMETER (PI=3.14, N=100) --
RE_PARAM_F77 = re.compile(r"^\s*parameter\s*\(\s*(.*)\s*\)\s*$", re.IGNORECASE)

# -- IMPLICIT --
RE_IMPL_NONE = re.compile(r"^\s*implicit\s+none\b", re.IGNORECASE)
RE_IMPL_RULE = re.compile(r"^\s*implicit\s+(.*)", re.IGNORECASE)

# -- Atributos en prefijo F90 (para parsear antes de ::) --
RE_ATTR_INTENT  = re.compile(r"\bintent\s*\(\s*(in|out|inout)\s*\)", re.IGNORECASE)
RE_ATTR_DIM     = re.compile(r"\bdimension\s*\(([^)]+)\)", re.IGNORECASE)
RE_ATTR_SIMPLES = re.compile(
    r"\b(allocatable|pointer|save|target|external|intrinsic|optional|"
    r"volatile|value|parameter|public|private|protected)\b",
    re.IGNORECASE,
)

# Atributos standalone F90 sin :: (fix issue-2 Fortran híbrido)
# Ejemplo: DIMENSION X(100), POINTER :: P, ALLOCATABLE X
RE_ATTR_STANDALONE = re.compile(
    r"^\s*(dimension|allocatable|pointer|target|save|external|intrinsic|"
    r"optional|volatile|protected)\s+(.*)",
    re.IGNORECASE,
)


# =============================================================================
# FUNCIONES DE PARSEO
# =============================================================================

def extraer_kind_tipo(tipo_str: str) -> str:
    """
    Extrae el KIND o LEN del tipo manejando paréntesis anidados.
    Ejemplos:
      'REAL(8)'                          → '8'
      'INTEGER(KIND=4)'                  → '4'
      'REAL(KIND=selected_real_kind(15,307))' → 'selected_real_kind(15,307)'
      'CHARACTER(LEN=*)'                 → '*'
      'REAL*8'                           → '*8'
    """
    # Primero intentar notación con asterisco: REAL*8
    m_star = re.search(r"\*\s*(\d+)", tipo_str)
    if m_star and "(" not in tipo_str[:m_star.start()].lstrip():
        return "*" + m_star.group(1)

    # Buscar el primer '(' después del nombre del tipo
    i = tipo_str.find("(")
    if i == -1:
        return ""

    # Extraer contenido hasta el ')' balanceado
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
    # Quitar prefijo KIND= o LEN=
    raw = re.sub(r"^(?:kind|len)\s*=\s*", "", raw, flags=re.IGNORECASE)
    return raw


def split_lista(s: str) -> list:
    """
    Divide s por comas respetando paréntesis anidados.
    Ejemplo: 'A, B(10,5), C*4' → ['A', 'B(10,5)', 'C*4']
    En términos del MI4D: respeta los DELIMITER Agrupadores ()
    que crean sub-dominios cerrados en el flujo y'.
    """
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


def parsear_prefijo_tipo(prefijo: str) -> dict:
    """
    Extrae del prefijo de una declaración F90 (texto antes de ::):
      tipo_base, kind, dimension, intent, atributos, es_parametro.
    Ejemplo: 'INTEGER(KIND=4), INTENT(IN), DIMENSION(N)'
    → {tipo: 'INTEGER', kind: '4', intent: 'IN', dim: 'N', ...}
    """
    resultado = {
        "tipo": "", "kind": "", "dim": "",
        "intent": "", "attrs": [], "es_param": False,
    }
    partes = split_lista(prefijo.strip())
    if not partes:
        return resultado

    # Primera parte = tipo base (con posible KIND o LEN inline)
    tipo_str = partes[0].strip()
    m_base = re.match(r"(\w+(?:\s+\w+)*)", tipo_str, re.IGNORECASE)
    if m_base:
        resultado["tipo"] = m_base.group(1).strip().upper()

    # Kind inline: REAL(8), INTEGER(KIND=4), REAL(KIND=selected_real_kind(15,307))
    resultado["kind"] = extraer_kind_tipo(tipo_str)

    # Atributos (partes[1:])
    for attr in partes[1:]:
        attr = attr.strip()

        m_intent = RE_ATTR_INTENT.search(attr)
        if m_intent:
            resultado["intent"] = m_intent.group(1).upper()
            resultado["attrs"].append(f"INTENT({resultado['intent']})")
            continue

        m_dim = RE_ATTR_DIM.search(attr)
        if m_dim:
            resultado["dim"] = m_dim.group(1)
            resultado["attrs"].append(f"DIMENSION({m_dim.group(1)})")
            continue

        if re.match(r"^\s*parameter\s*$", attr, re.IGNORECASE):
            resultado["es_param"] = True
            resultado["attrs"].append("PARAMETER")
            continue

        m_simple = RE_ATTR_SIMPLES.match(attr)
        if m_simple:
            resultado["attrs"].append(attr.upper())

    return resultado


def parsear_var_entry(entry: str, tipo_base: str, kind_base: str, dim_base: str,
                      intent: str, attrs: list, es_param: bool) -> dict:
    """
    Parsea una entrada individual de la lista de variables.
    Ejemplos: 'X', 'X(10)', 'X(N,M)', 'X*4', 'PI = 3.14159'
    """
    entry = entry.strip()
    nombre = ""
    dim    = dim_base
    kind   = kind_base
    valor  = ""

    # Valor inicial (para PARAMETER inline: nombre = valor)
    if "=" in entry:
        idx = entry.index("=")
        valor = entry[idx + 1:].strip()
        entry = entry[:idx].strip()

    # Kind con asterisco F77 style: X*4
    m_star = re.match(r"^(\w+)\s*\*\s*(\d+)$", entry)
    if m_star:
        nombre = m_star.group(1)
        kind   = "*" + m_star.group(2)
    # Dimensión explícita: X(10) o X(N,M)
    elif "(" in entry:
        m_dim = re.match(r"^(\w+)\s*\((.+)\)\s*$", entry)
        if m_dim:
            nombre = m_dim.group(1)
            dim    = m_dim.group(2).strip()
        else:
            nombre = re.sub(r"\(.*", "", entry).strip()
    else:
        nombre = entry

    if not re.match(r"^\w+$", nombre):
        return {}

    return {
        "Var_Name":      nombre.upper(),
        "Fortran_Type":  tipo_base,
        "Kind_Param":    kind,
        "Dimension":     dim,
        "Attributes":    "|".join(attrs) if attrs else "",
        "Intent":        intent,
        "Initial_Value": valor,
        "Is_Parameter":  "YES" if (es_param or bool(valor)) else "NO",
        "In_Common":     "",   # se rellena en post-proceso
        "Truncated":     "NO",
    }


def parsear_declaracion(contenido: str, scope: str, tipo_unidad: str,
                         archivo: str, n_linea: int) -> list:
    """
    Parsea una sentencia VAR_DECLARATION.
    Discrimina F90 (con ::) vs F77 (sin ::) por presencia de '::'.
    """
    base = {
        "Archivo": archivo, "Unidad": scope,
        "Tipo_Unidad": tipo_unidad, "Linea": n_linea,
    }
    truncada = len(contenido) >= 118

    filas = []

    if "::" in contenido:
        # F90 con ::
        m = RE_DECL_F90.match(contenido.strip())
        if not m:
            return []
        info      = parsear_prefijo_tipo(m.group(1))
        lista_str = m.group(2).strip()

        # Si el tipo no es reconocido, aún extraemos con tipo vacío
        # (puede ser ALLOCATABLE :: x, y u otro atributo-only)
        for entry in split_lista(lista_str):
            fila = parsear_var_entry(
                entry, info["tipo"], info["kind"], info["dim"],
                info["intent"], info["attrs"], info["es_param"],
            )
            if fila:
                fila["Truncated"] = "YES" if truncada else "NO"
                filas.append({**base, **fila})
    else:
        # F77 sin :: — intentar tipo base primero
        m = RE_DECL_F77.match(contenido.strip())
        if not m:
            # Atributo standalone sin tipo: DIMENSION X(100), SAVE X, EXTERNAL PROC
            m_attr = RE_ATTR_STANDALONE.match(contenido.strip())
            if not m_attr:
                return []
            attr_nombre = m_attr.group(1).upper()
            lista_str   = m_attr.group(2).strip()
            # Quitar :: residual si existe (POINTER :: P sin tipo)
            lista_str = re.sub(r"^::\s*", "", lista_str)
            for entry in split_lista(lista_str):
                fila = parsear_var_entry(entry, "", "", "", "", [attr_nombre], False)
                if fila:
                    fila["Truncated"] = "YES" if truncada else "NO"
                    filas.append({**base, **fila})
            return filas

        tipo_base   = re.sub(r"\s+", " ", m.group(1).upper())  # DOUBLE PRECISION
        # Usar extraer_kind_tipo para normalizar: quita paréntesis externos y KIND=/LEN=
        kind_suffix = extraer_kind_tipo(m.group(1) + (m.group(2) or ""))
        lista_str   = m.group(3).strip()

        for entry in split_lista(lista_str):
            fila = parsear_var_entry(entry, tipo_base, kind_suffix, "", "", [], False)
            if fila:
                fila["Truncated"] = "YES" if truncada else "NO"
                filas.append({**base, **fila})

    return filas


def parsear_parameter(contenido: str, scope: str, tipo_unidad: str,
                       archivo: str, n_linea: int) -> list:
    """
    Parsea sentencia PARAMETER standalone (F77): PARAMETER (PI=3.14, N=100)
    """
    m = RE_PARAM_F77.match(contenido.strip())
    if not m:
        return []

    base = {
        "Archivo": archivo, "Unidad": scope,
        "Tipo_Unidad": tipo_unidad, "Linea": n_linea,
    }
    filas = []
    for entry in split_lista(m.group(1)):
        if "=" not in entry:
            continue
        nombre, valor = entry.split("=", 1)
        nombre = nombre.strip().upper()
        if not re.match(r"^\w+$", nombre):
            continue
        filas.append({
            **base,
            "Var_Name":      nombre,
            "Fortran_Type":  "",   # tipo implícito; no conocido aquí
            "Kind_Param":    "",
            "Dimension":     "",
            "Attributes":    "PARAMETER",
            "Intent":        "",
            "Initial_Value": valor.strip(),
            "Is_Parameter":  "YES",
            "In_Common":     "",
            "Truncated":     "NO",
        })
    return filas


def parsear_implicit(contenido: str, scope: str, tipo_unidad: str,
                      archivo: str, n_linea: int) -> dict:
    """
    Parsea sentencia IMPLICIT (NONE o regla de tipo).
    """
    es_none = bool(RE_IMPL_NONE.match(contenido.strip()))
    if es_none:
        regla = "NONE"
    else:
        m = RE_IMPL_RULE.match(contenido.strip())
        regla = m.group(1).strip() if m else contenido.strip()

    return {
        "Archivo": archivo, "Unidad": scope,
        "Tipo_Unidad": tipo_unidad, "Linea": n_linea,
        "Rule": regla, "Is_None": "YES" if es_none else "NO",
    }


def parsear_firma(contenido: str, kind: str, scope: str, tipo_unidad: str,
                  archivo: str, n_linea: int) -> list:
    """
    Extrae los argumentos formales de la cabecera de SUBROUTINE o FUNCTION.
    kind: 'SUBROUTINE_UNIT' o 'FUNCTION_UNIT'
    Retorna una fila por argumento (posicion 1-based).
    Si no tiene argumentos, retorna lista vacía.
    """
    tipo_retorno = ""

    if kind == "SUBROUTINE_UNIT":
        m = RE_FIRMA_SUB.match(contenido.strip())
        if not m:
            return []
        args_str = m.group(2).strip()
    else:
        m = RE_FIRMA_FUNC.match(contenido.strip())
        if not m:
            return []
        # Prefijo = qualifiers + tipo de retorno (si hay)
        prefijo = re.sub(
            r"\b(pure|elemental|recursive)\b", "", m.group(1), flags=re.IGNORECASE
        ).strip()
        tipo_retorno = prefijo.upper() if prefijo else ""
        args_str = m.group(3).strip()

    if not args_str:
        return []

    filas = []
    for i, arg in enumerate(split_lista(args_str), 1):
        arg_nombre = arg.strip().upper()
        if not arg_nombre or arg_nombre == "*":  # * = retorno alternativo F77
            continue
        filas.append({
            "Archivo":        archivo,
            "Unidad":         scope,
            "Tipo_Unidad":    tipo_unidad,
            "Signature_Line": n_linea,
            "Position":       i,
            "Arg_Name":       arg_nombre,
            "Return_Type":    tipo_retorno,
        })

    return filas


def extraer_vars_common(contenido: str) -> dict:
    """
    Extrae el mapeo var_name → block_name de una sentencia COMMON.
    Ejemplo: 'COMMON /A/ X, Y /B/ Z' → {'X': 'A', 'Y': 'A', 'Z': 'B'}
    """
    resultado = {}
    # Quitar keyword COMMON inicial
    resto = re.sub(r"^\s*common\s*", "", contenido.strip(), flags=re.IGNORECASE)
    if not resto:
        return resultado

    bloque_actual = "(BLANK)"
    vars_buffer   = []
    i = 0

    while i < len(resto):
        if resto[i] == "/":
            # Volcar buffer al bloque actual
            for v in split_lista("".join(vars_buffer)):
                m = re.match(r"\s*(\w+)", v)
                if m:
                    resultado[m.group(1).upper()] = bloque_actual
            vars_buffer = []
            # Leer nombre del bloque
            j = resto.find("/", i + 1)
            if j == -1:
                break
            nombre = resto[i + 1:j].strip()
            bloque_actual = nombre if nombre else "(BLANK)"
            i = j + 1
        else:
            vars_buffer.append(resto[i])
            i += 1

    # Volcar lo que queda
    for v in split_lista("".join(vars_buffer)):
        m = re.match(r"\s*(\w+)", v)
        if m:
            resultado[m.group(1).upper()] = bloque_actual

    return resultado


# =============================================================================
# SCOPE RESOLUTION
# =============================================================================

def resolver_scope(n_linea: int, unidades_en_archivo: list) -> tuple:
    """
    Retorna (nombre_unidad, tipo_unidad) para la línea n_linea.
    Cuando hay anidamiento, elige la unidad de inicio más tardío (más interna).
    """
    candidatos = [
        u for u in unidades_en_archivo
        if u["Start_Line"] <= n_linea <= u["End_Line"]
    ]
    if not candidatos:
        return "GLOBAL", "FILE_SCOPE"
    u = max(candidatos, key=lambda u: u["Start_Line"])
    return u["Name"], u.get("Type", "UNKNOWN")


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

# Kinds que interesan (valores tal como los escribe perfilador.py: .name del enum)
_KINDS_INTERES = {
    "SUBROUTINE_UNIT", "FUNCTION_UNIT",
    "VAR_DECLARATION", "PARAMETER_STMT",
    "IMPLICIT_STMT", "COMMON_STMT",
}


def extraer_simbolos():
    print("--- Extracción de Símbolos ---")

    # 1. Inventario
    try:
        inventario_lista = cargar_inventario()
    except Exception as e:
        print(f"ERROR cargando inventario: {e}")
        return

    if not inventario_lista:
        print("El inventario está vacío.")
        return

    # Agrupar unidades por archivo, asegurando tipos int
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

    filas_vars   = []
    filas_firmas = []
    filas_impl   = []

    # common_map[(archivo, unidad_upper)] = {VAR_NAME_UPPER: block_name}
    # se usa en post-proceso para rellenar En_Common en filas_vars
    common_map = defaultdict(dict)

    n_vars = n_firmas = n_impl = 0
    archivos_ordenados = sorted(mapa_unidades.keys(), key=str.lower)

    # 2. Procesar cada archivo
    for nombre_archivo in archivos_ordenados:
        debug_file = RUTA_AUDIT / f"{nombre_archivo}_DEBUG.csv"
        if not debug_file.exists():
            continue

        unidades_en_archivo = sorted(
            mapa_unidades[nombre_archivo], key=lambda u: u["Start_Line"]
        )

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                kind = row.get("Kind", "")
                if kind not in _KINDS_INTERES:
                    continue

                try:
                    n_linea = int(row["Linea"])
                except (ValueError, KeyError):
                    continue

                contenido = row.get("Contenido", "")
                scope, tipo_unidad = resolver_scope(n_linea, unidades_en_archivo)

                if kind in ("SUBROUTINE_UNIT", "FUNCTION_UNIT"):
                    nuevas = parsear_firma(
                        contenido, kind, scope, tipo_unidad, nombre_archivo, n_linea
                    )
                    filas_firmas.extend(nuevas)
                    n_firmas += len(nuevas)

                elif kind == "VAR_DECLARATION":
                    nuevas = parsear_declaracion(
                        contenido, scope, tipo_unidad, nombre_archivo, n_linea
                    )
                    filas_vars.extend(nuevas)
                    n_vars += len(nuevas)

                elif kind == "PARAMETER_STMT":
                    nuevas = parsear_parameter(
                        contenido, scope, tipo_unidad, nombre_archivo, n_linea
                    )
                    filas_vars.extend(nuevas)
                    n_vars += len(nuevas)

                elif kind == "IMPLICIT_STMT":
                    filas_impl.append(
                        parsear_implicit(contenido, scope, tipo_unidad, nombre_archivo, n_linea)
                    )
                    n_impl += 1

                elif kind == "COMMON_STMT":
                    mapping = extraer_vars_common(contenido)
                    common_map[(nombre_archivo, scope.upper())].update(mapping)

    # 3. Post-proceso: enriquecer filas_vars con In_Common
    for fila in filas_vars:
        clave = (fila["Archivo"], fila["Unidad"].upper())
        fila["In_Common"] = common_map.get(clave, {}).get(fila["Var_Name"], "")

    # 4. Exportar CSVs
    _escribir_csv(SALIDA_VARS,   filas_vars,   COLS_VARIABLES)
    _escribir_csv(SALIDA_FIRMAS, filas_firmas, COLS_FIRMAS)
    _escribir_csv(SALIDA_IMPL,   filas_impl,   COLS_IMPLICIT)

    # 5. Resumen en consola
    n_units_impl = len({(f["Archivo"], f["Unidad"]) for f in filas_impl})
    n_impl_none  = sum(1 for f in filas_impl if f["Is_None"] == "YES")
    n_con_common = len(common_map)

    print(f"Variables / constantes  : {n_vars}")
    print(f"Argumentos formales     : {n_firmas}")
    print(f"Sentencias IMPLICIT     : {n_impl}  ({n_impl_none} IMPLICIT NONE)")
    print(f"Unidades con COMMON map : {n_con_common}")
    print()
    print(f"Generados:")
    print(f"  {SALIDA_VARS}")
    print(f"  {SALIDA_FIRMAS}")
    print(f"  {SALIDA_IMPL}")


# =============================================================================
# HELPERS DE ESCRITURA
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
    extraer_simbolos()


if __name__ == "__main__":
    main()
