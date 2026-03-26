import csv
import sys
from collections import defaultdict, deque

from forti4d.analyzers.inventario import cargar_inventario
from forti4d.config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
GRAFO_CSV  = RUTA_RESULTADOS / "dep_02_grafo_unidades.csv"
SALIDA_CSV = RUTA_RESULTADOS / "reporte_alcanzabilidad.csv"


# =============================================================================
# CONSTRUCCIÓN DEL GRAFO
# =============================================================================

def cargar_grafo():
    """
    Devuelve:
      grafo      : dict  nodo_grafo (str) -> set de nodos_grafo destino (str)
      nodos_upper: dict  nombre.upper() -> nombre_en_grafo  (para lookup)

    Los nodos del grafo están en mayúsculas (subroutines/functions) o con
    el prefijo 'MAIN__archivo.f90' (para IMPLICIT-MAIN).
    """
    grafo = defaultdict(set)

    try:
        with open(GRAFO_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                origen  = row.get("Unidad_Origen", "").strip()
                destino = row.get("Unidad_Destino", "").strip()
                tipo    = row.get("Tipo_Dep", "").strip()
                if origen and destino and tipo in ("CALL", "USE", "FUNC_CALL"):
                    grafo[origen].add(destino)
    except FileNotFoundError:
        print(f"ERROR: No se encuentra {GRAFO_CSV}")
        sys.exit(1)

    # Índice case-insensitive con todos los nodos del grafo
    todos = set(grafo.keys())
    for dests in grafo.values():
        todos |= dests
    nodos_upper = {n.upper(): n for n in todos}

    return grafo, nodos_upper


def nodo_en_grafo(unidad_inventario: dict, nodos_upper: dict) -> str:
    """
    Devuelve el nombre del nodo en el grafo correspondiente a una unidad
    del inventario, o '' si no se puede mapear.

    Reglas:
      - IMPLICIT-MAIN  ->  "MAIN__<archivo>"  (igual que dependencias.py)
      - demás tipos    ->  nombre en mayúsculas (el grafo usa caps)
    """
    tipo    = unidad_inventario.get("Tipo", "")
    nombre  = unidad_inventario.get("Nombre", "")
    archivo = unidad_inventario.get("Archivo", "")

    if tipo == "IMPLICIT-MAIN":
        candidato = f"MAIN__{archivo}"
    else:
        candidato = nombre.upper()

    # Verificar que el nodo existe realmente en el grafo
    return nodos_upper.get(candidato.upper(), "")


# =============================================================================
# ANÁLISIS DE ALCANZABILIDAD (BFS)
# =============================================================================

def calcular_alcanzabilidad(grafo: dict, semillas: list) -> dict:
    """
    BFS desde cada semilla (nombre de nodo en el grafo).
    Devuelve visited: nodo_grafo -> set de semillas que lo alcanzan.
    """
    visited = defaultdict(set)

    for semilla in semillas:
        if semilla not in grafo and semilla not in {d for ds in grafo.values() for d in ds}:
            # nodo aislado: solo se alcanza a sí mismo
            visited[semilla].add(semilla)
            continue

        cola = deque([semilla])
        seen = {semilla}
        while cola:
            actual = cola.popleft()
            visited[actual].add(semilla)
            for vecino in grafo.get(actual, []):
                if vecino not in seen:
                    seen.add(vecino)
                    cola.append(vecino)

    return visited


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def analizar_alcanzabilidad():
    print("--- Análisis de Alcanzabilidad / Dead Code ---")

    # 1. Cargar inventario
    try:
        inventario_lista = cargar_inventario()
    except Exception as e:
        print(f"ERROR cargando inventario: {e}")
        return

    if not inventario_lista:
        print("El inventario está vacío.")
        return

    # 2. Identificar entry points
    eps_unidades = [
        u for u in inventario_lista
        if u.get("Tipo") in ("PROGRAM", "IMPLICIT-MAIN")
        and u.get("Padre", "GLOBAL") == "GLOBAL"
    ]

    if not eps_unidades:
        print("No se encontraron entry points (PROGRAM / IMPLICIT-MAIN).")
        return

    print(f"Entry points detectados: {len(eps_unidades)}")

    # 3. Cargar grafo con índice case-insensitive
    grafo, nodos_upper = cargar_grafo()
    print(f"Grafo cargado: {sum(len(v) for v in grafo.values())} aristas "
          f"({len(grafo)} nodos origen)")

    # 4. Mapear entry points a nodos del grafo y preparar semillas para BFS
    #    ep_label: el nombre legible del entry point (para la columna Via_Entradas)
    semillas    = []    # nodos del grafo usados como semilla
    ep_label    = {}    # nodo_grafo -> label legible

    for u in eps_unidades:
        nodo = nodo_en_grafo(u, nodos_upper)
        label = u["Nombre"]
        if nodo:
            semillas.append(nodo)
            ep_label[nodo] = label
            print(f"  {label:25} -> nodo grafo: {nodo}")
        else:
            # El entry point no aparece en el grafo en absoluto
            # (ninguna dependencia saliente ni entrante registrada)
            semillas.append(label)   # usamos el nombre inventario
            ep_label[label] = label
            print(f"  {label:25} -> (sin nodo en grafo)")

    # 5. BFS
    visited = calcular_alcanzabilidad(grafo, semillas)

    # 6. Construir índice inverso: nodo_grafo -> labels de entry points
    #    Para convertir nodos visitados a labels legibles
    def ep_labels_for(nodo_grafo: str) -> list:
        return sorted(ep_label.get(ep, ep) for ep in visited.get(nodo_grafo, set()))

    # 7. Clasificar todas las unidades del inventario
    #
    # Lógica de estado:
    #   ENTRADA        : es un entry point
    #   ALCANZABLE     : aparece en visited (via nodo grafo o nombre inventario)
    #                    o su padre es alcanzable/entrada (alcanzabilidad transitiva)
    #   NO_ALCANZABLE  : ninguno de los anteriores
    #
    # El inventario puede contener nombres en minúsculas/mixtos; el grafo usa
    # mayúsculas.  Construimos un índice upper(nodo) -> nodo para búsqueda.
    visited_upper = {k.upper(): k for k in visited}

    def esta_alcanzado(nombre_inv: str) -> str:
        """Devuelve el nodo del grafo si el nombre inventario está visitado."""
        return visited_upper.get(nombre_inv.upper(), "")

    filas  = []
    conteo = {"ALCANZABLE": 0, "NO_ALCANZABLE": 0, "ENTRADA": 0}

    for u in inventario_lista:
        nombre = u["Nombre"]
        tipo   = u.get("Tipo", "UNKNOWN")
        padre  = u.get("Padre", "GLOBAL")
        arch   = u.get("Archivo", "")

        # Calcular nodo grafo equivalente para esta unidad
        nodo_g = nodo_en_grafo(u, nodos_upper)

        # ¿Es un entry point?
        if u in eps_unidades:
            estado = "ENTRADA"
            via    = nombre
            razon  = "Entry point (PROGRAM/IMPLICIT-MAIN)"

        # ¿Aparece en visited por su nodo grafo?
        elif nodo_g and nodo_g in visited:
            estado = "ALCANZABLE"
            via    = "; ".join(ep_labels_for(nodo_g))
            razon  = ""

        # ¿Su nombre directo (minúsculas) aparece en visited?
        elif esta_alcanzado(nombre):
            nodo_enc = esta_alcanzado(nombre)
            estado = "ALCANZABLE"
            via    = "; ".join(ep_labels_for(nodo_enc))
            razon  = ""

        # ¿Su padre (módulo contenedor) es alcanzable o entry point?
        elif padre != "GLOBAL":
            padre_nodo = nodo_en_grafo(
                {"Tipo": "MODULE", "Nombre": padre, "Archivo": ""},
                nodos_upper
            ) or padre
            if padre_nodo in visited or esta_alcanzado(padre):
                nodo_padre = padre_nodo if padre_nodo in visited else esta_alcanzado(padre)
                estado = "ALCANZABLE"
                via    = "; ".join(ep_labels_for(nodo_padre))
                razon  = f"Contenido en módulo alcanzable: {padre}"
            elif padre in [u2["Nombre"] for u2 in eps_unidades]:
                estado = "ALCANZABLE"
                via    = padre
                razon  = f"Contenido en entry point: {padre}"
            else:
                estado = "NO_ALCANZABLE"
                via    = ""
                razon  = f"Módulo contenedor no alcanzado: {padre}"
        else:
            estado = "NO_ALCANZABLE"
            via    = ""
            nodo_en_g = nodo_g or nombre.upper()
            if nodo_en_g in {k for k in grafo} | {d for ds in grafo.values() for d in ds}:
                razon = "En grafo pero no alcanzada desde ningún entry point"
            else:
                razon = "No aparece en el grafo de dependencias"

        conteo[estado] += 1
        filas.append({
            "Archivo":      arch,
            "Unidad":       nombre,
            "Tipo":         tipo,
            "Padre":        padre,
            "Estado":       estado,
            "Via_Entradas": via,
            "Razon":        razon,
        })

    # 8. Ordenar: NO_ALCANZABLE primero, luego ENTRADA, luego ALCANZABLE
    orden = {"NO_ALCANZABLE": 0, "ENTRADA": 1, "ALCANZABLE": 2}
    filas.sort(key=lambda x: (orden[x["Estado"]], x["Archivo"].lower(), x["Unidad"].lower()))

    # 9. Exportar
    columnas = ["Archivo", "Unidad", "Tipo", "Padre", "Estado", "Via_Entradas", "Razon"]
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)

    # 10. Resumen en consola
    total  = len(filas)
    n_dead = conteo["NO_ALCANZABLE"]
    n_live = conteo["ALCANZABLE"]
    n_ep   = conteo["ENTRADA"]

    print(f"\nTotal unidades analizadas : {total}")
    print(f"  ENTRADA               : {n_ep}")
    print(f"  ALCANZABLE            : {n_live}")
    print(f"  NO_ALCANZABLE (dead)  : {n_dead}  ({n_dead/total*100:.1f}%)")

    if n_dead > 0:
        print("\nUnidades NO alcanzables desde ningún entry point:")
        muertas = [r for r in filas if r["Estado"] == "NO_ALCANZABLE"]
        # Agrupar por archivo para legibilidad
        arch_actual = None
        for r in muertas:
            if r["Archivo"] != arch_actual:
                arch_actual = r["Archivo"]
                print(f"\n  [{arch_actual}]")
            tipo_str  = f"[{r['Tipo']}]"
            padre_str = f" (en {r['Padre']})" if r["Padre"] != "GLOBAL" else ""
            print(f"    {r['Unidad']:30} {tipo_str}{padre_str}")

    print(f"\nGenerado: {SALIDA_CSV}")


if __name__ == "__main__":
    analizar_alcanzabilidad()
