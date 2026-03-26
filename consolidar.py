"""
consolidar.py
Fusiona todos los reportes por-unidad en un único CSV con una fila por unidad.

Fuentes (todas opcionales salvo reporte_inventario.csv):
  reporte_inventario.csv    → base + Legacy/IO flags
  reporte_sloc.csv          → LOC, SLOC, densidad de comentario
  reporte_complejidad.csv   → CC, nivel de complejidad
  dep_03_matriz_impacto.csv → Fan_In, Fan_Out
  reporte_densidad.csv      → perfiles de sentencias (% cálculo/control/IO…)
  reporte_alcanzabilidad.csv→ estado ALCANZABLE / NO_ALCANZABLE / ENTRADA
  common_uso.csv            → COMMON blocks usados (agregado por unidad)
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path
from config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
INVENTARIO  = RUTA_RESULTADOS / "reporte_inventario.csv"
SLOC        = RUTA_RESULTADOS / "reporte_sloc.csv"
COMPLEJIDAD = RUTA_RESULTADOS / "reporte_complejidad.csv"
IMPACTO     = RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"
DENSIDAD    = RUTA_RESULTADOS / "reporte_densidad.csv"
ALCANZ      = RUTA_RESULTADOS / "reporte_alcanzabilidad.csv"
COMMON_USO  = RUTA_RESULTADOS / "common_uso.csv"
SIMB_VARS   = RUTA_RESULTADOS / "simbolos_variables.csv"
SIMB_FIRMAS = RUTA_RESULTADOS / "simbolos_firmas.csv"
SIMB_IMPL   = RUTA_RESULTADOS / "simbolos_implicit.csv"
TIPOS_DEF   = RUTA_RESULTADOS / "tipos_definicion.csv"

SALIDA_CSV  = RUTA_RESULTADOS / "reporte_consolidado.csv"


# =============================================================================
# HELPERS DE LECTURA
# =============================================================================

def leer_csv(ruta: str, clave_fn) -> dict:
    """
    Lee un CSV y devuelve un dict keyed por clave_fn(row).
    Si la clave se repite, la última fila gana (comportamiento merge).
    Devuelve {} si el archivo no existe (fuente opcional).
    """
    p = Path(ruta)
    if not p.exists():
        return {}
    result = {}
    with open(ruta, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = clave_fn(row)
            if k:
                result[k] = row
    return result


def leer_csv_multi(ruta: str, clave_fn) -> dict:
    """
    Como leer_csv pero acumula varias filas por clave en una lista.
    """
    p = Path(ruta)
    if not p.exists():
        return {}
    result = defaultdict(list)
    with open(ruta, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = clave_fn(row)
            if k:
                result[k].append(row)
    return dict(result)


def clave_au(row: dict) -> tuple:
    """Clave (Archivo, Unidad) — usada por la mayoría de fuentes."""
    a = row.get("Archivo", "").strip()
    u = row.get("Unidad", "").strip()
    return (a, u) if a and u else None


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# =============================================================================
# CARGA DE FUENTES
# =============================================================================

def cargar_fuentes():
    print("Cargando fuentes...")

    # Inventario: clave = (Archivo, Nombre)  ← el inventario usa "Nombre"
    inv_raw = {}
    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)

    if not INVENTARIO.exists():
        print(f"ERROR: {INVENTARIO} no encontrado.")
        sys.exit(1)
    with open(INVENTARIO, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = row.get("Archivo", "").strip()
            n = row.get("Nombre",  "").strip()
            if a and n:
                inv_raw[(a, n)] = row

    sloc_data  = leer_csv(SLOC,        clave_au)
    cc_data    = leer_csv(COMPLEJIDAD,  clave_au)
    dens_data  = leer_csv(DENSIDAD,     clave_au)
    alcanz_data= leer_csv(ALCANZ,       clave_au)

    # dep_03: clave = (Archivo, Unidad) — columnas en orden distinto
    imp_data = {}
    if IMPACTO.exists():
        with open(IMPACTO, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                a = row.get("Archivo", "").strip()
                u = row.get("Unidad",  "").strip()
                if a and u:
                    imp_data[(a, u)] = row

    # common_uso: varias filas por unidad (una por bloque)
    common_multi = leer_csv_multi(COMMON_USO, clave_au)

    # símbolos E4: varias filas por unidad
    vars_multi   = leer_csv_multi(SIMB_VARS,   clave_au)
    firmas_multi = leer_csv_multi(SIMB_FIRMAS, clave_au)
    impl_multi   = leer_csv_multi(SIMB_IMPL,   clave_au)

    # tipos derivados: clave = (Archivo, Unidad_host)
    def clave_tipo(row):
        a = row.get("Archivo", "").strip()
        u = row.get("Unidad",  "").strip()
        return (a, u) if a and u else None
    tipos_multi = leer_csv_multi(TIPOS_DEF, clave_tipo)

    print(f"  inventario   : {len(inv_raw)} unidades")
    print(f"  sloc         : {len(sloc_data)} entradas")
    print(f"  complejidad  : {len(cc_data)} entradas")
    print(f"  densidad     : {len(dens_data)} entradas")
    print(f"  alcanzabilidad: {len(alcanz_data)} entradas")
    print(f"  impacto      : {len(imp_data)} entradas")
    print(f"  common_uso   : {len(common_multi)} unidades con COMMON")
    print(f"  simbolos_vars: {sum(len(v) for v in vars_multi.values())} vars en {len(vars_multi)} unidades")
    print(f"  simbolos_firmas: {sum(len(v) for v in firmas_multi.values())} args en {len(firmas_multi)} unidades")
    print(f"  tipos_def    : {sum(len(v) for v in tipos_multi.values())} tipos en {len(tipos_multi)} unidades")

    return (inv_raw, sloc_data, cc_data, dens_data, alcanz_data, imp_data,
            common_multi, vars_multi, firmas_multi, impl_multi, tipos_multi)


# =============================================================================
# CONSTRUCCIÓN DEL CONSOLIDADO
# =============================================================================

def construir_filas(inv_raw, sloc_data, cc_data, dens_data, alcanz_data, imp_data,
                    common_multi, vars_multi, firmas_multi, impl_multi, tipos_multi):
    filas = []

    for (archivo, nombre), inv in inv_raw.items():
        k = (archivo, nombre)

        # ---- IDENTIDAD ----
        tipo  = inv.get("Tipo",  "UNKNOWN")
        padre = inv.get("Padre", "GLOBAL")

        # ---- SLOC ----
        sl = sloc_data.get(k, {})
        loc          = safe_int(sl.get("LOC", inv.get("Lineas_Total", 0)))
        sloc_fisico  = safe_int(sl.get("SLOC_fisico"))
        sloc_neto    = safe_int(sl.get("SLOC_neto"))
        n_comentarios= safe_int(sl.get("N_Comentarios"))
        n_continuacion= safe_int(sl.get("N_Continuacion"))
        pct_coment   = safe_float(sl.get("Pct_Comentario"))

        # ---- COMPLEJIDAD ----
        cc_row  = cc_data.get(k, {})
        cc      = safe_int(cc_row.get("CC", 1))
        cc_nivel= cc_row.get("Interpretacion", "")
        # CC/SLOC: densidad de complejidad por sentencia
        cc_sloc = round(cc / sloc_neto, 3) if sloc_neto > 0 else 0.0

        # ---- IMPACTO (Fan-In / Fan-Out) ----
        imp = imp_data.get(k, {})
        fan_in  = safe_int(imp.get("Fan_In"))
        fan_out = safe_int(imp.get("Fan_Out"))

        # ---- DENSIDAD ----
        dn = dens_data.get(k, {})
        pct_calculo = safe_float(dn.get("Pct_Calculo"))
        pct_control = safe_float(dn.get("Pct_Control"))
        pct_io      = safe_float(dn.get("Pct_IO"))
        pct_legacy  = safe_float(dn.get("Pct_Legacy"))

        # ---- ALCANZABILIDAD ----
        al = alcanz_data.get(k, {})
        estado      = al.get("Estado", "")
        via_entradas= al.get("Via_Entradas", "")

        # ---- COMMON BLOCKS ----
        common_rows  = common_multi.get(k, [])
        n_common_bloq= len(common_rows)
        common_bloq  = "; ".join(sorted(r.get("Bloque", "") for r in common_rows))

        # ---- SÍMBOLOS E4 ----
        var_rows   = vars_multi.get(k, [])
        n_vars_loc = sum(1 for r in var_rows if r.get("Es_Parametro") == "NO")
        n_params   = sum(1 for r in var_rows if r.get("Es_Parametro") == "SI")
        n_args     = len(firmas_multi.get(k, []))
        impl_rows  = impl_multi.get(k, [])
        impl_none  = "SI" if any(r.get("Es_None") == "SI" for r in impl_rows) else (
                     "NO" if impl_rows else "")
        n_tipos    = len(tipos_multi.get(k, []))

        # ---- FLAGS del inventario ----
        legacy_flags = inv.get("Legacy", "").strip()
        io_flags     = inv.get("IO",     "").strip()

        filas.append({
            # Identidad
            "Archivo":        archivo,
            "Unidad":         nombre,
            "Tipo":           tipo,
            "Padre":          padre,
            # Tamaño
            "LOC":            loc,
            "SLOC_fisico":    sloc_fisico,
            "SLOC_neto":      sloc_neto,
            "N_Comentarios":  n_comentarios,
            "N_Continuacion": n_continuacion,
            "Pct_Comentario": pct_coment,
            # Complejidad
            "CC":             cc,
            "CC_Nivel":       cc_nivel,
            "CC_SLOC":        cc_sloc,
            # Acoplamiento estructural
            "Fan_In":         fan_in,
            "Fan_Out":        fan_out,
            # Perfil de sentencias
            "Pct_Calculo":    pct_calculo,
            "Pct_Control":    pct_control,
            "Pct_IO":         pct_io,
            "Pct_Legacy":     pct_legacy,
            # COMMON blocks
            "N_Common_Bloques": n_common_bloq,
            "Common_Bloques":   common_bloq,
            # Alcanzabilidad
            "Estado":         estado,
            "Via_Entradas":   via_entradas,
            # Símbolos E4
            "N_Vars_Locales":    n_vars_loc,
            "N_Params":          n_params,
            "N_Args_Formales":   n_args,
            "Implicit_None":     impl_none,
            "N_Tipos_Derivados": n_tipos,
            # Flags de auditoría
            "Legacy_Flags":   legacy_flags,
            "IO_Flags":       io_flags,
        })

    return filas


# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

COLUMNAS = [
    "Archivo", "Unidad", "Tipo", "Padre",
    "LOC", "SLOC_fisico", "SLOC_neto", "N_Comentarios", "N_Continuacion", "Pct_Comentario",
    "CC", "CC_Nivel", "CC_SLOC",
    "Fan_In", "Fan_Out",
    "Pct_Calculo", "Pct_Control", "Pct_IO", "Pct_Legacy",
    "N_Common_Bloques", "Common_Bloques",
    "Estado", "Via_Entradas",
    "N_Vars_Locales", "N_Params", "N_Args_Formales", "Implicit_None", "N_Tipos_Derivados",
    "Legacy_Flags", "IO_Flags",
]


def main():
    print("=== Consolidación de Reportes ===\n")

    fuentes = cargar_fuentes()
    filas   = construir_filas(*fuentes)

    if not filas:
        print("Sin filas para exportar.")
        return

    # Ordenar: primero por archivo, luego por Linea_Inicio implícita en el
    # orden del inventario (preservada por ser un dict en Python 3.7+)
    # Para el CSV final: orden alfabético por archivo + unidad
    filas.sort(key=lambda r: (r["Archivo"].lower(), r["Unidad"].lower()))

    with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    # Resumen
    total = len(filas)
    con_cc     = sum(1 for r in filas if r["CC_Nivel"])
    sin_sloc   = sum(1 for r in filas if r["SLOC_neto"] == 0)
    muertas    = sum(1 for r in filas if r["Estado"] == "NO_ALCANZABLE")
    criticas   = sum(1 for r in filas if r["CC_Nivel"] == "CRITICA")
    sin_coment = sum(1 for r in filas if r["Pct_Comentario"] == 0 and r["SLOC_neto"] > 10)

    print(f"\nConsolidado generado: {SALIDA_CSV}")
    print(f"  Filas totales           : {total}")
    print(f"  Con métricas CC         : {con_cc}")
    print(f"  Unidades NO alcanzables : {muertas}")
    print(f"  CC nivel CRITICA        : {criticas}")
    print(f"  Sin comentarios (>10 sl): {sin_coment}")
    print(f"  Sin SLOC (vacías/error) : {sin_sloc}")

    # Top riesgo: CC alto + Fan_In alto + pocos comentarios
    print("\nTop 10 candidatos a refactorizar (CC × Fan_In):")
    top = sorted(filas, key=lambda r: -(r["CC"] * max(r["Fan_In"], 1)))
    for r in top[:10]:
        print(f"  CC={r['CC']:5}  Fan_In={r['Fan_In']:3}  {r['Pct_Comentario']:4.1f}%coment  "
              f"{r['Archivo']:25} {r['Unidad']}")


if __name__ == "__main__":
    main()
