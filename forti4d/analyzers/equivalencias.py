import csv
import re
from collections import defaultdict
from pathlib import Path

from forti4d.analyzers.inventario import cargar_inventario
from forti4d.config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
RUTA_AUDIT  = RUTA_RESULTADOS / "audit"
SALIDA_CSV  = RUTA_RESULTADOS / "equivalences.csv"

COLS = [
    "Archivo", "Unidad", "Tipo_Unidad",
    "Group_ID", "Position", "Var_Name", "N_Members", "Stmt_Lines",
]


# =============================================================================
# UNION-FIND
# =============================================================================

class UnionFind:
    """
    Union-Find con path compression para calcular componentes conexas.
    Los nodos son strings (nombres de variables en mayúsculas).
    """

    def __init__(self):
        self._parent = {}

    def _ensure(self, x):
        if x not in self._parent:
            self._parent[x] = x

    def find(self, x):
        self._ensure(x)
        while self._parent[x] != x:
            # Path compression (halving)
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def componentes(self):
        """
        Retorna dict {representante: [miembros ordenados]}.
        Cada clave es la raíz canónica del componente.
        """
        grupos = defaultdict(list)
        for nodo in self._parent:
            grupos[self.find(nodo)].append(nodo)
        return {rep: sorted(miembros) for rep, miembros in grupos.items()}


# =============================================================================
# PARSEO
# =============================================================================

def _extraer_nombre(ref):
    """
    De una referencia de variable (puede llevar subíndice),
    extrae solo el nombre: 'A(1)' → 'A', 'POINT' → 'POINT'.
    """
    ref = ref.strip()
    m = re.match(r"^(\w+)", ref)
    return m.group(1).upper() if m else ""


def _split_top(s):
    """
    Divide s por comas respetando paréntesis anidados.
    Igual que split_lista en simbolos.py — duplicado para evitar dependencia.
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


def parsear_equivalence(contenido):
    """
    Extrae todos los grupos de una sentencia EQUIVALENCE.
    Ejemplo: 'EQUIVALENCE (A,B(1)), (X,Y,Z)' → [['A','B'], ['X','Y','Z']]
    Cada grupo interno tiene ≥ 2 variables (grupos de 1 se ignoran).
    """
    # Quitar keyword EQUIVALENCE
    resto = re.sub(r"^\s*equivalence\s*", "", contenido.strip(), flags=re.IGNORECASE)

    grupos: list[list[str]] = []
    i = 0
    while i < len(resto):
        if resto[i] == "(":
            # Encontrar el cierre balanceado
            j, depth = i + 1, 1
            while j < len(resto) and depth > 0:
                if resto[j] == "(":
                    depth += 1
                elif resto[j] == ")":
                    depth -= 1
                j += 1
            inner = resto[i + 1: j - 1]
            refs = _split_top(inner)
            nombres = [_extraer_nombre(r) for r in refs]
            nombres = [n for n in nombres if n]
            if len(nombres) >= 2:
                grupos.append(nombres)
            i = j
        else:
            i += 1
    return grupos


# =============================================================================
# SCOPE RESOLUTION
# =============================================================================

def resolver_scope(n_linea: int, unidades_en_archivo: list) -> tuple:
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

def extraer_equivalencias():
    print("--- Extracción de Equivalencias ---")

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
            u["Start_Line"] = int(u["Start_Line"])
            u["End_Line"]   = int(u["End_Line"])
        except (ValueError, KeyError):
            u["Start_Line"] = 0
            u["End_Line"]   = 0
        mapa_unidades[archivo].append(u)

    filas = []
    n_grupos_total = 0
    archivos_ordenados = sorted(mapa_unidades.keys(), key=str.lower)

    # 2. Por archivo: recopilar EQUIVALENCE_STMT por (scope, tipo_unidad)
    for nombre_archivo in archivos_ordenados:
        debug_file = RUTA_AUDIT / f"{nombre_archivo}_DEBUG.csv"
        if not debug_file.exists():
            continue

        unidades_en_archivo = sorted(
            mapa_unidades[nombre_archivo], key=lambda u: u["Start_Line"]
        )

        # Acumular sentencias por unidad
        stmts_por_unidad: dict[tuple, list] = defaultdict(list)

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("Kind") != "EQUIVALENCE_STMT":
                    continue
                try:
                    n_linea = int(row["Linea"])
                except (ValueError, KeyError):
                    continue
                scope, tipo_u = resolver_scope(n_linea, unidades_en_archivo)
                stmts_por_unidad[(scope, tipo_u)].append(
                    (n_linea, row.get("Contenido", ""))
                )

        # 3. Por unidad: union-find sobre todos sus EQUIVALENCE
        for (scope, tipo_u), stmts in stmts_por_unidad.items():
            uf = UnionFind()
            # var → conjunto de líneas donde aparece
            var_lineas: dict[str, set] = defaultdict(set)

            for n_linea, contenido in stmts:
                grupos_stmt = parsear_equivalence(contenido)
                for grupo in grupos_stmt:
                    # Registrar línea para cada variable del grupo
                    for var in grupo:
                        var_lineas[var].add(n_linea)
                    # Unir todas las variables del grupo
                    for i in range(1, len(grupo)):
                        uf.union(grupo[0], grupo[i])

            # 4. Extraer componentes conexas y emitir filas
            componentes = uf.componentes()
            # Ordenar componentes por primer miembro para ID determinista
            grupos_ordenados = sorted(componentes.values(), key=lambda g: g[0])

            for id_grupo, miembros in enumerate(grupos_ordenados, 1):
                n_miembros = len(miembros)
                # Líneas de todas las sentencias que definen este grupo
                lineas_grupo = sorted(
                    {ln for var in miembros for ln in var_lineas.get(var, [])}
                )
                lineas_str = ";".join(str(l) for l in lineas_grupo)

                for posicion, nombre_var in enumerate(miembros, 1):
                    filas.append({
                        "Archivo":    nombre_archivo,
                        "Unidad":     scope,
                        "Tipo_Unidad": tipo_u,
                        "Group_ID":   id_grupo,
                        "Position":   posicion,
                        "Var_Name":   nombre_var,
                        "N_Members":  n_miembros,
                        "Stmt_Lines": lineas_str,
                    })

                n_grupos_total += 1

    # 5. Exportar
    _escribir_csv(SALIDA_CSV, filas, COLS)

    n_archivos = len({f["Archivo"] for f in filas})
    n_unidades = len({(f["Archivo"], f["Unidad"]) for f in filas})
    print(f"Archivos con EQUIVALENCE : {n_archivos}")
    print(f"Unidades con EQUIVALENCE : {n_unidades}")
    print(f"Grupos de aliasing       : {n_grupos_total}")
    print(f"Variables en grupos      : {len(filas)}")
    print()
    print(f"Generado:")
    print(f"  {SALIDA_CSV}")


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
    extraer_equivalencias()


if __name__ == "__main__":
    main()
