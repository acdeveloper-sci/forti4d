import csv
import sys
import os
from config import RUTA_RESULTADOS

# CONFIGURACIÓN
ARCHIVO_DENSIDAD  = RUTA_RESULTADOS / "reporte_densidad.csv"
ARCHIVO_IMPACTO   = RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"
SALIDA_ESTRATEGIA = RUTA_RESULTADOS / "reporte_estrategia_migracion.csv"

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


def definir_estrategia(row, ivc, icm):
    """Motor de Reglas (Idéntico a la versión anterior)."""
    fan_in = row["Fan_In"]
    tipo = row["Tipo"]
    pct_io = row["Pct_IO"]
    pct_declar = row["Pct_Declar"]

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

            # D. ICM (15% Control + 45% Legacy + 20% Fan-Out + 20% Fan-In)
            icm = (0.15 * pct_control) + (0.45 * score_legacy) + (0.20 * score_acople) + (0.20 * score_fanin)
            icm = round(icm, 1)

            # D. IVC
            ivc = pct_calculo

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
                "Pct_IO": pct_io,  # Necesario para reglas
                "Pct_Declar": pct_declar,  # Necesario para reglas
                "Fan_In": fan_in,
                "Fan_Out": fan_out,
            }

            # Aplicar Reglas
            estrategia, explicacion = definir_estrategia(fila_procesada, ivc, icm)

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
