import sys
import os
import csv
from collections import defaultdict
from config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
ARCHIVO_IMPACTO    = RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"
ARCHIVO_INVENTARIO = RUTA_RESULTADOS / "reporte_inventario.csv"
ARCHIVO_SALIDA     = RUTA_RESULTADOS / "analisis_nodos_criticos.csv"

# ¿Cuántas llamadas entrantes convierten a una unidad en "CRÍTICA"?
UMBRAL_CRITICO = 10


def cargar_matriz():
    if not ARCHIVO_IMPACTO.exists():
        print(f"ERROR: No existe '{ARCHIVO_IMPACTO}'. Ejecuta dependencias.py primero.")
        sys.exit(1)

    data_por_archivo = defaultdict(list)

    print(f"Leyendo {ARCHIVO_IMPACTO}...")
    with open(ARCHIVO_IMPACTO, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            archivo = row.get("Archivo", "N/A").strip()

            # Filtro de archivos inválidos o múltiples
            if archivo in ("N/A", "EXTERNAL/LOCAL", "MULTIPLE_CANDIDATES") or ";" in archivo:
                continue

            try:
                fan_in = int(row.get("Fan_In", 0))
                fan_out = int(row.get("Fan_Out", 0))
            except ValueError:
                continue

            data_por_archivo[archivo].append(
                {
                    "Unidad": row.get("Unidad", "UNKNOWN"),
                    "Tipo": row.get("Tipo", "UNKNOWN").upper(),
                    "Fan_In": fan_in,
                    "Fan_Out": fan_out,
                }
            )

    return data_por_archivo


def cargar_archivos_inventario():
    """
    Devuelve el conjunto de todos los archivos conocidos y si contienen
    alguna unidad IMPLICIT-MAIN (para categorización posterior).
    """
    archivos_conocidos = set()
    archivos_con_implicit_main = set()

    if not ARCHIVO_INVENTARIO.exists():
        print(f"Advertencia: No existe '{ARCHIVO_INVENTARIO}'. Los ISLAs no se detectarán.")
        return archivos_conocidos, archivos_con_implicit_main

    with open(ARCHIVO_INVENTARIO, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            arch = row.get("Archivo", "").strip()
            if arch:
                archivos_conocidos.add(arch)
                if row.get("Tipo", "").upper() == "IMPLICIT-MAIN":
                    archivos_con_implicit_main.add(arch)

    return archivos_conocidos, archivos_con_implicit_main


def clasificar_archivo(nombre_archivo, unidades, tiene_implicit_main):
    """
    Determina el rol del archivo en la arquitectura.
    """
    total_unidades = len(unidades)

    if total_unidades > 0:
        fan_in_max = unidades[0]["Fan_In"]
        unidad_max_in = unidades[0]["Unidad"]
        fan_out_max = unidades[0]["Fan_Out"]
        unidad_max_out = unidades[0]["Unidad"]
    else:
        fan_in_max = 0
        unidad_max_in = "N/A"
        fan_out_max = 0
        unidad_max_out = "N/A"

    suma_fan_in = 0
    suma_fan_out = 0
    tiene_main = False

    for u in unidades:
        fi = u["Fan_In"]
        fo = u["Fan_Out"]

        suma_fan_in += fi
        suma_fan_out += fo

        if fi > fan_in_max:
            fan_in_max = fi
            unidad_max_in = u["Unidad"]

        if fo > fan_out_max:
            fan_out_max = fo
            unidad_max_out = u["Unidad"]

        tipo_str = u["Tipo"]
        if "PROGRAM" in tipo_str or "IMPLICIT-MAIN" in tipo_str:
            tiene_main = True

    # Categorización — orden de prioridad explícito
    categoria = "MIXTO"
    detalle = "Funcionalidad estándar"

    # Archivos con programa principal implícito: son ejecutables de entrada,
    # no rutinas de biblioteca — se categorizan aparte
    if tiene_implicit_main:
        categoria = "ENTRY_POINT"
        detalle = f"Programa principal implícito (Fan-Out: {fan_out_max})"

    elif suma_fan_in == 0 and suma_fan_out == 0:
        # Nunca llegaremos aquí desde dep_03 (los ISLAs no tienen entradas en la matriz),
        # pero sí desde los archivos inyectados como ISLA en main().
        categoria = "ISLA"
        detalle = "Archivo aislado (posible código muerto)"

    elif fan_in_max >= UMBRAL_CRITICO:
        categoria = "NODO_CRITICO"
        detalle = f"Alta centralidad (Max Fan-In: {fan_in_max})"

    elif fan_out_max >= UMBRAL_CRITICO:
        categoria = "ORQUESTADOR"
        detalle = f"Controlador de flujo (Max Fan-Out: {fan_out_max})"

    elif (suma_fan_in > 0 or suma_fan_out > 0) and fan_out_max < 5:
        # OBRERO: conectado pero de bajo impacto saliente.
        # Se acepta Fan_In=0 si al menos llama a algo (pure caller de bajo orden).
        categoria = "OBRERO"
        detalle = "Rutina de servicio o cálculo"

    return {
        "Archivo": nombre_archivo,
        "Categoria": categoria,
        "Fan_In_Max": fan_in_max,
        "Unidad_Max_In": unidad_max_in,
        "Fan_Out_Max": fan_out_max,
        "Unidad_Max_Out": unidad_max_out,
        "Total_Unidades": total_unidades,
        "Tiene_Main": "SI" if tiene_main else "NO",
        "Detalle": detalle,
    }


def main():
    print(f"--- Análisis de Arquitectura (Umbral: {UMBRAL_CRITICO}) ---")

    data = cargar_matriz()
    archivos_conocidos, archivos_con_implicit_main = cargar_archivos_inventario()

    if not data and not archivos_conocidos:
        print("No se encontraron datos para procesar.")
        return

    resultados = []
    conteos = defaultdict(int)

    archivos_procesados = set()

    for archivo, unidades in data.items():
        tiene_implicit_main = archivo in archivos_con_implicit_main
        res = clasificar_archivo(archivo, unidades, tiene_implicit_main)
        resultados.append(res)
        conteos[res["Categoria"]] += 1
        archivos_procesados.add(archivo)

    # Archivos del inventario que no tienen ninguna entrada en dep_03 → ISLAs
    for archivo in sorted(archivos_conocidos - archivos_procesados):
        res = {
            "Archivo": archivo,
            "Categoria": "ISLA",
            "Fan_In_Max": 0,
            "Unidad_Max_In": "N/A",
            "Fan_Out_Max": 0,
            "Unidad_Max_Out": "N/A",
            "Total_Unidades": 0,
            "Tiene_Main": "NO",
            "Detalle": "Archivo sin conexiones en la matriz de impacto",
        }
        resultados.append(res)
        conteos["ISLA"] += 1

    # Orden jerárquico para el reporte
    prioridad = {"NODO_CRITICO": 1, "ORQUESTADOR": 2, "ENTRY_POINT": 3, "MIXTO": 4, "OBRERO": 5, "ISLA": 6}
    resultados.sort(key=lambda x: prioridad.get(x["Categoria"], 99))

    columnas = [
        "Archivo",
        "Categoria",
        "Fan_In_Max",
        "Unidad_Max_In",
        "Fan_Out_Max",
        "Unidad_Max_Out",
        "Total_Unidades",
        "Tiene_Main",
        "Detalle",
    ]

    try:
        with open(ARCHIVO_SALIDA, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(resultados)

        print(f"Reporte generado exitosamente: {ARCHIVO_SALIDA}")
        print("\nEstadísticas de Categorías:")
        for cat in prioridad:
            count = conteos.get(cat, 0)
            if count:
                print(f"  - {cat:15}: {count}")

    except IOError as e:
        print(f"Error al escribir el reporte: {e}")


if __name__ == "__main__":
    main()
