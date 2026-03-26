import csv
import sys
import os
from forti4d.config import RUTA_RESULTADOS

# CONFIGURACIÓN
ARCHIVO_DENSIDAD    = RUTA_RESULTADOS / "reporte_densidad.csv"
ARCHIVO_IMPACTO     = RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"
SALIDA_ESTRATEGIA   = RUTA_RESULTADOS / "reporte_estrategia_migracion.csv"

# Fuentes opcionales E4 / alcanzabilidad (se usan si existen)
ALCANZABILIDAD_CSV  = RUTA_RESULTADOS / "reporte_alcanzabilidad.csv"
SIMBOLOS_IMPL_CSV   = RUTA_RESULTADOS / "simbolos_implicit.csv"
EQUIVALENCIAS_CSV   = RUTA_RESULTADOS / "equivalencias.csv"

# Penalización E4 sobre ICM (puntos aditivos, escala 0-100)
E4_PENALTY_MAX = 7.0   # máximo añadido al ICM por riesgo E4
W_E4_IMPL  = 0.70      # sin IMPLICIT NONE
W_E4_EQUIV = 0.30      # tiene EQUIVALENCE

# Mapa de Prioridad (Menor número = Mayor urgencia)
PRIORIDAD_MAP = {
    "MIGRACION_DIRECTA": 1,
    "MIGRACION_ESTANDAR": 2,
    "REEMPLAZAR_LIB": 3,
    "REFACTORIZAR_CORE": 4,
    "REESCRIBIR_AISLADO": 5,
    "ANALIZAR_UTILIDAD": 6,
    "ELIMINAR": 7,
}


# HELPERS
def to_float(val, default=0.0):
    """Convierte string a float de forma segura."""
    if not val or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def clip(val, max_val):
    """Simula el .clip() de numpy/pandas."""
    return min(val, max_val)


def cargar_alcanzabilidad():
    """Retorna dict (Archivo, Unidad) → Estado. Vacío si el CSV no existe."""
    result = {}
    if not ALCANZABILIDAD_CSV.exists():
        return result
    with open(ALCANZABILIDAD_CSV, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            clave = (row.get("Archivo", "").strip(), row.get("Unidad", "").strip())
            result[clave] = row.get("Estado", "").strip()
    return result


def cargar_e4():
    """
    Retorna (impl_none_set, equiv_set):
      impl_none_set — (Archivo, Unidad) que tienen IMPLICIT NONE (Es_None == SI)
      equiv_set     — (Archivo, Unidad) que tienen al menos un grupo EQUIVALENCE
    Ambos vacíos si los CSVs no existen.
    """
    impl_none_set = set()
    if SIMBOLOS_IMPL_CSV.exists():
        with open(SIMBOLOS_IMPL_CSV, encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                if row.get("Es_None", "").strip() == "SI":
                    clave = (row.get("Archivo", "").strip(), row.get("Unidad", "").strip())
                    impl_none_set.add(clave)

    equiv_set = set()
    if EQUIVALENCIAS_CSV.exists():
        with open(EQUIVALENCIAS_CSV, encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                clave = (row.get("Archivo", "").strip(), row.get("Unidad", "").strip())
                equiv_set.add(clave)

    return impl_none_set, equiv_set


def cargar_impacto():
    """Carga la matriz de impacto en un diccionario para búsqueda rápida."""
    impacto_map = {}

    if not ARCHIVO_IMPACTO.exists():
        print(f"ERROR: No se encuentra {ARCHIVO_IMPACTO}")
        sys.exit(1)

    with open(ARCHIVO_IMPACTO, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Usamos una tupla (Archivo, Unidad) como clave única (Composite Key)
            clave = (row["Archivo"], row["Unidad"])
            impacto_map[clave] = {"Fan_In": to_float(row.get("Fan_In", 0)), "Fan_Out": to_float(row.get("Fan_Out", 0))}
    return impacto_map


def definir_estrategia(row, ivc, icm, estado_alcanz=""):
    """Motor de Reglas."""
    fan_in = row["Fan_In"]
    tipo = row["Tipo"]
    pct_io = row["Pct_IO"]
    pct_declar = row["Pct_Declar"]

    # Regla -1: Código muerto confirmado por análisis de alcanzabilidad
    if estado_alcanz == "NO_ALCANZABLE":
        return "ELIMINAR", "Código muerto confirmado por análisis de alcanzabilidad"

    # Regla 0: Código Muerto / Punto de Entrada sin detectar
    # MODULE y BLOCK DATA se excluyen: son USEd, no CALLed → Fan_In siempre 0 en análisis de llamadas
    if fan_in == 0 and tipo not in ["PROGRAM", "IMPLICIT-MAIN", "MODULE", "BLOCK DATA"]:
        fan_out = row["Fan_Out"]
        if fan_out > 0:
            # Llama a otras unidades pero nadie la llama internamente → posible entry point externo
            return "ANALIZAR_UTILIDAD", "Sin llamantes internos pero activa (posible entry point)"
        # fan_out == 0: isla completa sin conexiones internas
        if ivc > 25:
            return "ANALIZAR_UTILIDAD", "Sin conexiones internas pero con cálculo sustancial"
        return "ELIMINAR", "Isla sin conexiones y lógica trivial (posible código muerto)"

    # Regla 1: Joyas de Cálculo
    if ivc > 50 and icm < 30:
        return "MIGRACION_DIRECTA", "Joya: Algoritmo puro y aislado"

    # Regla 2: Infraestructura
    if (pct_io > 30 or pct_declar > 40) and ivc < 20:
        return "REEMPLAZAR_LIB", "Burocracia: Sustituir por Librerías Modernas"

    # Regla 3: Nudos Críticos
    if icm > 25 and fan_in > 5:
        return "REFACTORIZAR_CORE", "Nudo Gordiano: Alto riesgo y alta dependencia"

    # Regla 4: Nudos Aislados
    if icm > 20:
        return "REESCRIBIR_AISLADO", "Complejo pero de bajo impacto sistémico"

    return "MIGRACION_ESTANDAR", "Lógica de negocio regular"


def main():
    print("--- Análisis Cruzado de Migración (Standard Lib) ---")

    # 1. Cargar datos de Dependencias en memoria (Hash Map)
    print("Cargando matriz de impacto...")
    mapa_impacto = cargar_impacto()

    # 1b. Fuentes opcionales
    mapa_alcanz = cargar_alcanzabilidad()
    impl_none_set, equiv_set = cargar_e4()
    if mapa_alcanz:
        print(f"  Alcanzabilidad cargada: {len(mapa_alcanz)} unidades")
    if impl_none_set or equiv_set:
        print(f"  E4: {len(impl_none_set)} con IMPLICIT NONE, {len(equiv_set)} con EQUIVALENCE")

    # 2. Procesar Densidad y Cruzar
    if not ARCHIVO_DENSIDAD.exists():
        print(f"ERROR: No se encuentra {ARCHIVO_DENSIDAD}")
        sys.exit(1)

    resultados = []

    print("Procesando y clasificando unidades...")
    with open(ARCHIVO_DENSIDAD, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Recuperar datos del CSV de densidad y convertir tipos
            archivo = row["Archivo"]
            unidad = row["Unidad"]
            pct_control = to_float(row.get("Pct_Control", 0))
            pct_legacy = to_float(row.get("Pct_Legacy", 0))
            pct_calculo = to_float(row.get("Pct_Calculo", 0))
            pct_io = to_float(row.get("Pct_IO", 0))
            pct_declar = to_float(row.get("Pct_Declar", 0))

            # Buscar datos de impacto (JOIN manual)
            clave = (archivo, unidad)
            datos_impacto = mapa_impacto.get(clave, {"Fan_In": 0.0, "Fan_Out": 0.0})

            fan_in = datos_impacto["Fan_In"]
            fan_out = datos_impacto["Fan_Out"]

            # Calcular Índices
            # A. Score Acople saliente (Tope 20 deps -> 100 pts)
            score_acople = clip(fan_out * 5, 100.0)

            # B. Score Acople entrante (Tope 20 callers -> 100 pts)
            score_fanin = clip(fan_in * 5, 100.0)

            # C. Score Legacy (Tope 25% lineas -> 100 pts)
            score_legacy = clip(pct_legacy * 4, 100.0)

            # D. ICM base (15% Control + 45% Legacy + 20% Fan-Out + 20% Fan-In)
            icm = (0.15 * pct_control) + (0.45 * score_legacy) + (0.20 * score_acople) + (0.20 * score_fanin)

            # D2. Penalización E4 (aditiva, max E4_PENALTY_MAX puntos)
            clave = (archivo, unidad)
            sin_impl_none = clave not in impl_none_set
            tiene_equiv   = clave in equiv_set
            e4_penalty = E4_PENALTY_MAX * (
                W_E4_IMPL  * (1.0 if sin_impl_none else 0.0) +
                W_E4_EQUIV * (1.0 if tiene_equiv   else 0.0)
            )
            icm = round(icm + e4_penalty, 1)

            # E. IVC
            ivc = pct_calculo

            # Estado de alcanzabilidad (vacío si CSV no disponible)
            estado_alcanz = mapa_alcanz.get(clave, "")

            # Crear objeto fila enriquecido
            fila_procesada = {
                "Archivo": archivo,
                "Unidad": unidad,
                "Tipo": row["Tipo"],
                "ICM": icm,
                "IVC": ivc,
                "Pct_Calculo": pct_calculo,
                "Pct_Control": pct_control,
                "Pct_Legacy": pct_legacy,
                "Pct_IO": pct_io,
                "Pct_Declar": pct_declar,
                "Fan_In": fan_in,
                "Fan_Out": fan_out,
                "Estado_Alcanz": estado_alcanz,
            }

            # Aplicar Reglas
            estrategia, explicacion = definir_estrategia(fila_procesada, ivc, icm, estado_alcanz)

            fila_procesada["Estrategia"] = estrategia
            fila_procesada["Explicacion"] = explicacion
            fila_procesada["Prioridad_Num"] = PRIORIDAD_MAP.get(estrategia, 99)

            resultados.append(fila_procesada)

    # 3. Ordenamiento (Sort)
    # Equivalente a df.sort_values(['Prioridad_Num', 'IVC'], ascending=[True, False])
    # En Python sort es estable, ordenamos primero por criterio secundario, luego primario (o usamos tupla con negativo)
    print("Ordenando resultados por prioridad...")
    resultados.sort(key=lambda x: (x["Prioridad_Num"], -x["IVC"]))

    # 4. Exportar a CSV
    columnas_salida = [
        "Prioridad_Num",
        "Estrategia",
        "Archivo",
        "Unidad",
        "Tipo",
        "ICM",
        "IVC",
        "Pct_Calculo",
        "Pct_Control",
        "Pct_Legacy",
        "Fan_In",
        "Fan_Out",
        "Estado_Alcanz",
        "Explicacion",
    ]

    try:
        with open(SALIDA_ESTRATEGIA, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columnas_salida, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(resultados)

        print(f"✅ ÉXITO: Reporte generado en '{SALIDA_ESTRATEGIA}'")

        # Generar pequeño resumen en consola
        conteo = {}
        for r in resultados:
            est = r["Estrategia"]
            conteo[est] = conteo.get(est, 0) + 1

        print("\n--- RESUMEN DE ESTRATEGIA ---")
        for k, v in sorted(conteo.items()):
            print(f"{k}: {v}")

    except Exception as e:
        print(f"❌ Error escribiendo archivo: {e}")


if __name__ == "__main__":
    main()
