import sys
import os
import csv
from collections import Counter, defaultdict
from statistics import mean, median
from config import RUTA_RESULTADOS

# Archivos de entrada
INVENTARIO   = RUTA_RESULTADOS / "reporte_inventario.csv"
DEPENDENCIAS = RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"

# Fuentes opcionales E4
SIMBOLOS_IMPL_CSV = RUTA_RESULTADOS / "simbolos_implicit.csv"
EQUIVALENCIAS_CSV = RUTA_RESULTADOS / "equivalencias.csv"
COMMON_USO_CSV    = RUTA_RESULTADOS / "common_uso.csv"
SIMBOLOS_VARS_CSV = RUTA_RESULTADOS / "simbolos_variables.csv"

# Salidas
OUT_MD  = RUTA_RESULTADOS / "RESUMEN_PROYECTO.md"
OUT_CSV = RUTA_RESULTADOS / "estadisticas_por_archivo.csv"


def cargar_datos():
    if not INVENTARIO.exists():
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
    if DEPENDENCIAS.exists():
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


def cargar_scope_health():
    """
    Carga los CSVs E4 opcionales y retorna cuatro estructuras:
      impl_none_set  — set (Archivo, Unidad) con IMPLICIT NONE
      equiv_set      — set (Archivo, Unidad) con al menos un grupo EQUIVALENCE
      common_set     — set (Archivo, Unidad) con al menos un bloque COMMON
      vars_count     — Counter (Archivo, Unidad) → nº de variables locales (excl. PARAMETERs)
    Cualquiera puede estar vacío si el CSV correspondiente no existe.
    """
    impl_none_set = set()
    if SIMBOLOS_IMPL_CSV.exists():
        with open(SIMBOLOS_IMPL_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("Es_None", "").strip() == "SI":
                    impl_none_set.add((row.get("Archivo", "").strip(), row.get("Unidad", "").strip()))

    equiv_set = set()
    if EQUIVALENCIAS_CSV.exists():
        with open(EQUIVALENCIAS_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                equiv_set.add((row.get("Archivo", "").strip(), row.get("Unidad", "").strip()))

    common_set = set()
    if COMMON_USO_CSV.exists():
        with open(COMMON_USO_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                common_set.add((row.get("Archivo", "").strip(), row.get("Unidad", "").strip()))

    vars_count = Counter()
    if SIMBOLOS_VARS_CSV.exists():
        with open(SIMBOLOS_VARS_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("Es_Parametro", "").strip() != "SI":
                    clave = (row.get("Archivo", "").strip(), row.get("Unidad", "").strip())
                    vars_count[clave] += 1

    return impl_none_set, equiv_set, common_set, vars_count


def calcular_scope_stats(inv_rows, impl_none_set, equiv_set, common_set, vars_count):
    """
    Calcula las métricas de salud del scope a partir de los datos E4.
    Retorna None si no hay datos E4 disponibles.
    """
    if not (impl_none_set or equiv_set or common_set or vars_count):
        return None

    total = len(inv_rows)
    unidades = [(r["Archivo"], r["Nombre"] if "Nombre" in r else r.get("Unidad", "")) for r in inv_rows]

    n_impl_none = sum(1 for u in unidades if u in impl_none_set)
    n_equiv     = sum(1 for u in unidades if u in equiv_set)
    n_common    = sum(1 for u in unidades if u in common_set)
    n_clean     = sum(
        1 for u in unidades
        if u in impl_none_set and u not in equiv_set and u not in common_set
    )

    top5_vars = vars_count.most_common(5)

    return {
        "total":       total,
        "n_impl_none": n_impl_none,
        "n_equiv":     n_equiv,
        "n_common":    n_common,
        "n_clean":     n_clean,
        "top5_vars":   top5_vars,
        "has_data":    True,
    }


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


def generar_reporte_markdown(stats, scope_stats=None):
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

        # 5. SALUD DEL SCOPE (E4)
        if scope_stats and scope_stats.get("has_data"):
            ss = scope_stats
            total = ss["total"]
            pct = lambda n: f"{(n/total*100):.1f}%" if total else "—"
            f.write("## 5. Salud del Scope (E4)\n\n")
            f.write("| Indicador | Unidades | % del total |\n")
            f.write("| :--- | :---: | :---: |\n")
            f.write(f"| Con IMPLICIT NONE | {ss['n_impl_none']} | {pct(ss['n_impl_none'])} |\n")
            f.write(f"| Sin IMPLICIT NONE (riesgo de tipo) | {total - ss['n_impl_none']} | {pct(total - ss['n_impl_none'])} |\n")
            f.write(f"| Con EQUIVALENCE (aliasing) | {ss['n_equiv']} | {pct(ss['n_equiv'])} |\n")
            f.write(f"| Con COMMON blocks | {ss['n_common']} | {pct(ss['n_common'])} |\n")
            f.write(f"| Scope limpio (IMPLICIT NONE, sin EQUIV, sin COMMON) | {ss['n_clean']} | {pct(ss['n_clean'])} |\n")
            f.write("\n")
            if ss["top5_vars"]:
                f.write("### Top 5 unidades por densidad de variables locales\n\n")
                f.write("| Unidad | Archivo | Vars locales |\n")
                f.write("| :--- | :--- | :---: |\n")
                for (arch, unidad), n in ss["top5_vars"]:
                    f.write(f"| {unidad} | {arch} | {n} |\n")
                f.write("\n")

        # 6. ESTRUCTURA (Dependencias)
        top_usados = stats["top_usados"]
        # Filtrar UNKNOWN para el reporte ejecutivo si se desea,
        # pero a veces es útil ver qué desconocido es muy usado.

        if top_usados:
            f.write("## 6. Unidades Críticas (más reutilizadas, mayor Fan-In)\n")
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
            f.write("## 7. Unidades Orquestadoras (mayor complejidad, mayor Fan-Out)\n")
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

    impl_none_set, equiv_set, common_set, vars_count = cargar_scope_health()
    scope_stats = calcular_scope_stats(inv, impl_none_set, equiv_set, common_set, vars_count)
    if scope_stats:
        print(f"  E4: {scope_stats['n_impl_none']}/{scope_stats['total']} IMPLICIT NONE, "
              f"{scope_stats['n_equiv']} EQUIV, {scope_stats['n_common']} COMMON, "
              f"{scope_stats['n_clean']} scope-limpias")

    generar_reporte_markdown(stats, scope_stats)
    generar_csv_archivos(stats)


if __name__ == "__main__":
    main()
