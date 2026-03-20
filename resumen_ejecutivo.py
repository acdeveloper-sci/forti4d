import sys
import os
import csv
from collections import Counter, defaultdict
from statistics import mean, median

# Archivos de entrada
INVENTARIO = "reporte_inventario.csv"
DEPENDENCIAS = "dep_03_matriz_impacto.csv"  # Usamos la matriz ya calculada para agilizar

# Salidas
OUT_MD = "RESUMEN_PROYECTO.md"
OUT_CSV = "estadisticas_por_archivo.csv"


def cargar_datos():
    if not os.path.exists(INVENTARIO):
        print(f"ERROR: No se encuentra {INVENTARIO}")
        sys.exit(1)

    inv_rows = []
    # CAMBIO 1: utf-8-sig para leer correctamente acentos si vienen de Excel
    with open(INVENTARIO, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convertir números con seguridad
            try:
                # Si viene vacío o con '?', ponemos 0
                val = row.get("Lineas_Total", "0").strip()
                if not val.isdigit():
                    val = "0"
                row["Lineas_Total"] = int(val)
            except ValueError:
                row["Lineas_Total"] = 0
            inv_rows.append(row)

    dep_rows = []
    if os.path.exists(DEPENDENCIAS):
        # CAMBIO 2: utf-8-sig para leer dependencias
        with open(DEPENDENCIAS, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    row["Fan_In"] = int(row["Fan_In"])
                except ValueError:
                    row["Fan_In"] = 0
                try:
                    row["Fan_Out"] = int(row["Fan_Out"])
                except ValueError:
                    row["Fan_Out"] = 0
                dep_rows.append(row)

    return inv_rows, dep_rows


def calcular_resumen(inv_rows, dep_rows):
    stats = {
        "total_archivos": 0,
        "total_lineas": sum(r["Lineas_Total"] for r in inv_rows if r.get("Padre", "GLOBAL") == "GLOBAL"),
        "total_unidades": len(inv_rows),
        "unidades_por_tipo": Counter(),
        "archivos_map": defaultdict(
            lambda: {"lineas": 0, "unidades": 0, "tipos": set(), "legacy_flags": 0, "io_flags": 0}
        ),
        "top_usados": [],
        "legacy_count": 0,
        "unidades_con_legacy": 0,
        "top_legacy": Counter(),
        "io_count": 0,
        "unidades_con_io": 0,
        "top_io": Counter(),
        "implicit_main_count": 0,
    }

    archivos_unicos = set()

    for r in inv_rows:
        arch = r["Archivo"]
        tipo = r["Tipo"]
        lineas = r["Lineas_Total"]

        archivos_unicos.add(arch)
        stats["unidades_por_tipo"][r["Tipo"]] += 1

        # Stats por archivo - LOC solo en unidades raíz para evitar doble conteo
        # (unidades anidadas comparten el rango de líneas de su padre)
        stats["archivos_map"][arch]["lineas_p"] = lineas
        if r.get("Padre", "GLOBAL") == "GLOBAL":
            stats["archivos_map"][arch]["lineas"] += lineas
        stats["archivos_map"][arch]["unidades"] += 1
        stats["archivos_map"][arch]["tipos"].add(tipo)

        # Auditoría Flags
        has_legacy = bool(r.get("Legacy") and r["Legacy"].strip())
        has_io = bool(r.get("IO") and r["IO"].strip())

        # Legacy
        if has_legacy:
            stats["unidades_con_legacy"] += 1
            items = [x.strip() for x in r["Legacy"].split(",")]
            for it in items:
                if it:
                    stats["legacy_count"] += 1
                    stats["top_legacy"][it] += 1
                    stats["archivos_map"][arch]["legacy_flags"] += 1

        # IO
        if has_io:
            stats["unidades_con_io"] += 1
            items = [x.strip() for x in r["IO"].split(",")]
            for it in items:
                if it:
                    stats["io_count"] += 1
                    stats["top_io"][it] += 1
                    stats["archivos_map"][arch]["io_flags"] += 1

        if tipo == "IMPLICIT-MAIN":
            stats["implicit_main_count"] += 1

    stats["total_archivos"] = len(archivos_unicos)
    # stats["total_lineas"] = sum(d["lineas"] for d in stats["archivos_map"].values())

    # Top Dependencias - utilización (Fan-In alto)
    # Ordenamos por Fan-In descendente
    dep_rows_sorted = sorted(dep_rows, key=lambda x: x["Fan_In"], reverse=True)
    stats["top_usados"] = dep_rows_sorted[:15]  # Top 15

    # Top Dependencias - complejidad (Fan-Out alto)
    # Ordenamos por Fan-Out descendente
    dep_rows_sorted = sorted(dep_rows, key=lambda x: x["Fan_Out"], reverse=True)
    stats["top_complejos"] = dep_rows_sorted[:15]  # Top 15

    return stats


def generar_reporte_markdown(stats):
    # CAMBIO 3: utf-8-sig para generar el reporte MD compatible con Windows
    with open(OUT_MD, "w", encoding="utf-8-sig") as f:
        f.write("# RESUMEN EJECUTIVO DE CÓDIGO FUENTE DEL PROYECTO FORTRAN\n\n")

        # 1. VISIÓN GLOBAL
        f.write("## 1. Métricas Globales\n")
        f.write(f"- **Total Archivos**: {stats['total_archivos']}\n")
        f.write(f"- **Total Líneas de Código (LOC)**: {stats['total_lineas']:,}\n")
        f.write(f"- **Total Unidades de Programa**: {stats['total_unidades']}\n")
        if stats["total_archivos"] > 0:
            avg_loc = stats["total_lineas"] / stats["total_archivos"]
            f.write(f"- **Promedio LOC por archivo**: {avg_loc:.1f}\n\n")

        # 2. DISTRIBUCIÓN POR TIPO
        f.write("## 2. Distribución por Tipo de Unidad\n")
        f.write("| Tipo | Cantidad | % del Total |\n")
        f.write("| :--- | :---: | :---: |\n")
        for tipo, count in stats["unidades_por_tipo"].most_common():
            pct = (count / stats["total_unidades"]) * 100
            f.write(f"| {tipo} | {count} | {pct:.1f}% |\n")
        f.write("\n")

        # 3. TOP MONOLITOS
        f.write("## 3. Top 10 Archivos Más Grandes (Monolitos)\n")
        # Ordenar archivos por líneas
        top_files = sorted(stats["archivos_map"].items(), key=lambda x: x[1]["lineas"], reverse=True)[:10]
        f.write("| Archivo | Líneas | Unidades | Tipos Contenidos |\n")
        f.write("| :--- | :---: | :---: | :--- |\n")
        for nombre, data in top_files:
            tipos_str = ", ".join(sorted(data["tipos"]))
            f.write(f"| {nombre} | {data['lineas']} | {data['unidades']} | {tipos_str} |\n")
        f.write("\n")

        # 4. SALUD DEL CÓDIGO
        f.write("## 4. Indicadores de Salud (Legacy)\n")
        pct_legacy = (stats["unidades_con_legacy"] / stats["total_unidades"]) * 100 if stats["total_unidades"] else 0
        f.write(f"- **Unidades con código Legacy (COMMON/GOTO/etc.):** {stats['unidades_con_legacy']} ({pct_legacy:.1f}%)\n")
        if not stats["top_legacy"]:
            f.write("_No se detectaron sentencias Legacy configuradas (COMMON, GOTO, etc)._\n\n")
        else:
            f.write("Las siguientes construcciones antiguas fueron detectadas:\n\n")
            f.write("  | Sentencia | Apariciones |\n")
            f.write("  | :--- | :---: |\n")
            for item, count in stats["top_legacy"].most_common():
                f.write(f"  | {item} | {count} |\n")

        pct_io = (stats["unidades_con_io"] / stats["total_unidades"]) * 100 if stats["total_unidades"] else 0
        f.write(f"- **Unidades con I/O Intensivo (OPEN/READ/CLOSE/etc.):** {stats['unidades_con_io']} ({pct_io:.1f}%)\n")
        if not stats["top_io"]:
            f.write("_No se detectaron sentencias I/O configuradas (OPEN, READ, CLOSE, etc)._\n\n")
        else:
            f.write("Las siguientes construcciones I/O fueron detectadas:\n\n")
            f.write("  | Sentencia | Apariciones |\n")
            f.write("  | :--- | :---: |\n")
            for item, count in stats["top_io"].most_common():
                f.write(f"  | {item} | {count} |\n")
        f.write(f"- **Programas Principales Implícitos:** {stats['implicit_main_count']} (Candidatos a refactorizar)\n")
        f.write("\n")

        # 5. ESTRUCTURA (Dependencias)
        top_usados = stats["top_usados"]
        # Filtrar UNKNOWN para el reporte ejecutivo si se desea,
        # pero a veces es útil ver qué desconocido es muy usado.

        if top_usados:
            f.write("## 5. Unidades Críticas (más reutilizadas, mayor Fan-In)\n")
            f.write("Unidades que son el 'corazón' del sistema.\n\n")
            f.write("| Unidad | Tipo | Archivo | Es llamada por (veces) |\n")
            f.write("| :--- | :--- | :--- | :---: |\n")
            for d in top_usados:
                f.write(f"| {d['Unidad']} | {d.get('Tipo','?')} | {d.get('Archivo','?')} | {d.get('Fan_In',0)} |\n")
            f.write("\n")

        top_complejos = stats["top_complejos"]
        # Filtrar UNKNOWN para el reporte ejecutivo si se desea,
        # pero a veces es útil ver qué desconocido es muy usado.

        if top_complejos:
            f.write("## 6. Unidades Orquestadoras (mayor complejidad, mayor Fan-Out)\n")
            f.write("Unidades que coordinan el flujo y dependen de muchas partes del sistema.\n\n")
            f.write("| Unidad | Tipo | Archivo | Llama a (nº dependencias) |\n")
            f.write("| :--- | :--- | :--- | :---: |\n")
            for d in top_complejos:
                f.write(f"| {d['Unidad']} | {d.get('Tipo','?')} | {d.get('Archivo','?')} | {d.get('Fan_Out',0)} |\n")
            f.write("\n")

    print(f"Generado reporte ejecutivo: {OUT_MD}")


def generar_csv_archivos(stats):
    # CAMBIO 4: utf-8-sig para el CSV final
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Archivo", "Total_Lineas", "Total_Unidades", "Tiene_Legacy", "Tiene_IO", "Tipos_Presentes"])

        # Ordenar alfabéticamente
        for nombre, data in sorted(stats["archivos_map"].items()):
            writer.writerow(
                [
                    nombre,
                    data["lineas"],
                    data["unidades"],
                    "SI" if data["legacy_flags"] > 0 else "NO",
                    "SI" if data["io_flags"] > 0 else "NO",
                    ";".join(sorted(data["tipos"])),
                ]
            )
    print(f"Generado CSV detallado: {OUT_CSV}")


def main():
    print("Generando Resumen Ejecutivo...")
    inv, dep = cargar_datos()
    stats = calcular_resumen(inv, dep)
    generar_reporte_markdown(stats)
    generar_csv_archivos(stats)


if __name__ == "__main__":
    main()
