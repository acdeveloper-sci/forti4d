import sys
import os
import csv
import re
from pathlib import Path
from typing import List, Set, Dict

try:
    from forti4d.lib.reader_logical import read_logical_lines
    from forti4d.lib.patterns_v1 import (
        RE_PROGRAM,
        RE_MODULE,
        RE_SUBROUTINE,
        RE_FUNCTION,
        RE_BLOCK_DATA,
        RE_END_GENERIC,
        RE_INTERFACE,
    )
except ImportError as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
from forti4d.config import CARPETA_CODIGO, RUTA_RESULTADOS

ARCHIVO_SALIDA = RUTA_RESULTADOS / "reporte_inventario.csv"

# --- LISTAS DE AUDITORÍA (Reporte) ---
LISTA_LEGACY = ["COMMON", "EQUIVALENCE", "PAUSE", "ENTRY", "ASSIGN", "GO TO", "COMPUTED GOTO", "ARITHMETIC IF"]
LISTA_IO = ["READ", "WRITE", "PRINT", "OPEN", "CLOSE", "INQUIRE", "BACKSPACE", "REWIND", "NAMELIST"]
LISTA_CUSTOM = ["ALLOCATE", "DEALLOCATE", "DATA", "STOP"]

# --- LISTA DE ACTIVACIÓN DE IMPLICIT MAIN (Jerarquía Fortran) ---
# Basado en el documento "Jerarquía y Orden de Sentencias".
# Si encontramos esto y no hay unidad abierta, ES un programa principal implícito.
TRIGGERS_ESPECIFICACION = [
    "USE",
    "IMPORT",
    "IMPLICIT",
    "INTEGER",
    "REAL",
    "DOUBLE PRECISION",
    "COMPLEX",
    "LOGICAL",
    "CHARACTER",
    "BYTE",
    "TYPE",
    "CLASS",
    "PROCEDURE",
    "DIMENSION",
    "PARAMETER",
    "EXTERNAL",
    "INTRINSIC",
    "SAVE",
    "TARGET",
    "POINTER",
    "PUBLIC",
    "PRIVATE",
    "OPTIONAL",
    "INTENT",
    "VOLATILE",
    "ASYNCHRONOUS",
    "PROTECTED",
    "DATA",
    "FORMAT",
    "ENTRY",
    "NAMELIST",
    "COMMON",
    "EQUIVALENCE",
]
# Las sentencias ejecutables también disparan (IF, DO, CALL, etc), pero esas
# se capturan o por flags o por descarte. Estas son las declarativas críticas.


def compilar_lista(palabras):
    if not palabras:
        return None
    pattern = r"\b(" + "|".join(re.escape(p) for p in palabras) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


RE_LEGACY = compilar_lista(LISTA_LEGACY)
RE_IO = compilar_lista(LISTA_IO)
RE_CUSTOM = compilar_lista(LISTA_CUSTOM)

# Patrón Maestro de Inicio Implícito
RE_IMPLICIT_START = compilar_lista(TRIGGERS_ESPECIFICACION)

# Si patterns.py no tiene RE_END_INTERFACE, lo ideal es agregarlo allá.
# Pero para efectos de este script, definamos uno robusto que acepte nombres opcionales:
# Este regex busca: "END", espacios, "INTERFACE", y opcionalmente más cosas (nombre)
RE_END_INTERFACE = re.compile(r"^\s*END\s*INTERFACE\b", re.IGNORECASE)


class UnidadDetectada:

    def __init__(self, tipo: str, nombre: str, linea_inicio: int, padre: str = "GLOBAL"):
        self.tipo = tipo
        self.nombre = nombre
        self.linea_inicio = linea_inicio
        self.padre = padre
        self.linea_fin = -1
        self.flags_legacy: Set[str] = set()
        self.flags_io: Set[str] = set()
        self.flags_custom: Set[str] = set()

    @property
    def total_lineas(self):
        if self.linea_fin == -1:
            return "?"
        return self.linea_fin - self.linea_inicio + 1


def mask_strings(text: str) -> str:
    text = re.sub(r"'[^']*'", "''", text)
    text = re.sub(r'"[^"]*"', '""', text)
    return text


# Agregar esto en src/inventario.py


def cargar_inventario(ruta_csv=None):
    """
    Lee el reporte CSV generado por este mismo script y devuelve la estructura
    completa de datos (SSOT) necesaria para otros análisis.

    Retorna:
        list[dict]: Lista de diccionarios con claves originales
                    ('Archivo', 'Tipo', 'Nombre', 'Linea_Inicio', etc.)
    """
    import csv
    from pathlib import Path

    if ruta_csv is None:
        ruta_csv = RUTA_RESULTADOS / "reporte_inventario.csv"

    ruta_csv = Path(ruta_csv)
    datos_recuperados = []

    if not ruta_csv.exists():
        print(f"Advertencia: No se encontró el archivo de inventario: {ruta_csv}")
        return []

    try:
        with ruta_csv.open(mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Conversión de tipos crítica para el perfilador
                try:
                    # Usamos las claves EXACTAS que definiste en la generación del CSV
                    row["Linea_Inicio"] = int(row["Linea_Inicio"])
                    row["Linea_Fin"] = int(row["Linea_Fin"])
                    row["Lineas_Total"] = int(row["Lineas_Total"])
                except (ValueError, KeyError) as e:
                    # Si falla, mantenemos 0 para no romper la ejecución, pero avisamos si es debug
                    row["Linea_Inicio"] = 0
                    row["Linea_Fin"] = 0
                    row["Lineas_Total"] = 0

                datos_recuperados.append(row)

    except Exception as e:
        print(f"Error crítico leyendo el inventario: {e}")
        return []

    return datos_recuperados


def auditar_archivo(ruta_archivo: Path) -> List[Dict]:
    try:
        logical_lines = read_logical_lines(str(ruta_archivo))
    except Exception as e:
        return [{"Archivo": ruta_archivo.name, "Tipo": "ERROR", "Nombre": str(e)}]

    if not logical_lines:
        return []

    unidades = []
    stack = []

    # Control para no crear múltiples Implicit Main si hay código disperso
    implicit_main_active = False
    # Control para no crear unidades de definiciones que están dentro de INTERFACE
    dentro_de_interface = False

    for lline in logical_lines:
        if lline.is_comment:
            continue

        text_raw = lline.text.strip()
        text_safe = mask_strings(text_raw)  # Para buscar keywords sin falsos positivos
        line_num = lline.start_line

        # LÓGICA DE INTERFACE considerando cuando definen una genérica (tiene dentro MODULE PROCEDURE)

        # 0.1. Chequeo de Estado: ¿Entramos o salimos de una INTERFACE?
        m_interface = RE_INTERFACE.match(text_safe)
        if m_interface:
            # Si tiene nombre (Grupo 1), es una Interface Genérica.
            # LA REGISTRAMOS como unidad, hija del módulo actual.
            nombre_interface = m_interface.group(1)

            if nombre_interface:
                parent_name = stack[-1].nombre if stack else "GLOBAL"
                # Creamos la unidad "GENERIC_INTERFACE"
                nueva_interface = UnidadDetectada("GENERIC_INTERFACE", nombre_interface, line_num, parent_name)
                # Asumimos que la interface termina donde dice END INTERFACE,
                # pero como vamos a ignorar el contenido, no la metemos al stack principal
                # para que no interfiera con la lógica de cierre de subrutinas internas.
                # Simplemente la guardamos y activamos el flag de ignorar.

                # OJO: Para simplificar, le ponemos linea_fin en la misma línea o '?'
                # porque no vamos a trackear su END con el stack normal.
                nueva_interface.linea_fin = line_num
                unidades.append(nueva_interface)

            dentro_de_interface = True
            continue  # Saltamos esta línea

        if RE_END_INTERFACE.match(text_safe):
            dentro_de_interface = False
            continue  # Saltamos esta línea y volvemos a detectar normal

        # 0.2. Si estamos dentro de una interfaz, IGNORAMOS todo
        #    porque son solo prototipos, no código real.
        if dentro_de_interface:
            continue

        # FIN LÓGICA INTERFACE

        # 1. DETECCIÓN DE APERTURAS EXPLÍCITAS
        # Estas tienen prioridad máxima sobre el Implicit Main.
        m_prog = RE_PROGRAM.match(text_safe)
        m_mod = RE_MODULE.match(text_safe)
        m_sub = RE_SUBROUTINE.match(text_safe)
        m_func = RE_FUNCTION.match(text_safe)
        m_bd = RE_BLOCK_DATA.match(text_safe)

        # DETERMINAR EL PADRE ACTUAL
        # Si el stack tiene elementos, el tope es nuestro padre (ej: Module)
        parent_name = stack[-1].nombre if stack else "GLOBAL"

        nueva = None
        if m_prog:
            nueva = UnidadDetectada("PROGRAM", m_prog.group(1), line_num, parent_name)
        elif m_mod:
            nueva = UnidadDetectada("MODULE", m_mod.group(1), line_num, parent_name)
        elif m_sub:
            nueva = UnidadDetectada("SUBROUTINE", m_sub.group(1), line_num, parent_name)
        elif m_func:
            nueva = UnidadDetectada("FUNCTION", m_func.group(1), line_num, parent_name)
        elif m_bd:
            nueva = UnidadDetectada("BLOCK DATA", m_bd.group(1) or "data", line_num, parent_name)

        if nueva:
            stack.append(nueva)
            unidades.append(nueva)
            # Si entramos a una unidad explícita, "pausamos" la noción de estar en el nivel implícito
            # hasta que esta unidad se cierre.
            continue

        # Solo recuerda que Implicit Main también tendría padre "GLOBAL" por defecto.

        # 2. DETECCIÓN DE CIERRES (END)
        match_end = RE_END_GENERIC.match(text_safe)
        if match_end:
            kw = match_end.group(1) or ""
            if stack:
                top = stack[-1]
                # Lógica: Un END cierra lo que está en el tope.
                # Si el tope es IMPLICIT-MAIN, solo se cierra si encontramos un END puro
                # (o END PROGRAM si fueramos laxos, pero END puro es lo estándar).

                # Coincidencia de tipo (Subroutine con End Subroutine) O End genérico
                match_type = (kw.upper() in top.tipo) if kw else True

                if match_type:
                    cerrada = stack.pop()
                    cerrada.linea_fin = line_num

                    if cerrada.tipo == "IMPLICIT-MAIN":
                        implicit_main_active = False  # Ya cerramos el main, no esperamos más código
                    continue

        # 3. LÓGICA DE ACTIVACIÓN DE IMPLICIT MAIN (Jerarquía)
        # Si el stack está vacío, significa que estamos "al aire libre".
        # Cualquier sentencia válida aquí DEBE disparar el Implicit Main.

        if not stack:
            # ¿Es una línea vacía o irrelevante? (Ya filtramos comentarios)
            if not text_safe:
                continue

            # Buscamos Triggers de Especificación o Ejecución
            is_spec_trigger = RE_IMPLICIT_START.search(text_safe)

            # También consideramos flags de IO/Legacy como triggers (sentencias ejecutables)
            is_exec_trigger = False
            if RE_IO and RE_IO.search(text_safe):
                is_exec_trigger = True
            if RE_LEGACY and RE_LEGACY.search(text_safe):
                is_exec_trigger = True
            if RE_CUSTOM and RE_CUSTOM.search(text_safe):
                is_exec_trigger = True

            # Trigger "Catch-all" para asignaciones (x = 1) o Calls
            # Si tiene un '=' o empieza con 'call', es ejecutable casi seguro.
            is_assign = ("=" in text_safe) or (text_safe.lower().startswith("call"))

            if is_spec_trigger or is_exec_trigger or is_assign:
                if not implicit_main_active:
                    # Nace el IMPLICIT-MAIN
                    main_implicito = UnidadDetectada("IMPLICIT-MAIN", ruta_archivo.stem, line_num)
                    # Lo insertamos cronológicamente. Si es el primero, va al inicio.
                    unidades.append(main_implicito)
                    stack.append(main_implicito)
                    implicit_main_active = True
                else:
                    # Caso raro: Habíamos cerrado un Implicit Main y aparece más código suelto.
                    # Fortran no permite dos Main Programs. Asumimos que es continuación o error,
                    # reabrimos el último o creamos nuevo. Por simplicidad, reabrimos si es necesario
                    # o reportamos alerta. Aquí creamos uno nuevo para no mezclar.
                    pass

        # 4. CAPTURA DE FLAGS (Contenido)
        if stack:
            current = stack[-1]

            # Flags Legacy
            if RE_LEGACY:
                for m in RE_LEGACY.findall(text_safe):
                    current.flags_legacy.add(m.upper())
            # Flags IO
            if RE_IO:
                for m in RE_IO.findall(text_safe):
                    current.flags_io.add(m.upper())
            # Flags Custom
            if RE_CUSTOM:
                for m in RE_CUSTOM.findall(text_safe):
                    current.flags_custom.add(m.upper())

    # Cierre final de seguridad
    last_line = logical_lines[-1].start_line if logical_lines else 0
    for u in stack:
        if u.linea_fin == -1:
            u.linea_fin = last_line

    # GENERAR FILAS
    rows = []
    for u in unidades:
        # Filtro de ruido para Implicit Main vacíos (si se creó por error sin contenido real)
        if u.tipo == "IMPLICIT-MAIN":
            has_content = u.flags_legacy or u.flags_io or u.flags_custom
            # Solo filtramos si NO detectamos ninguna línea de código válida dentro.
            # Pero con la nueva lógica, solo se crea si hay trigger.
            # Aun así, mantenemos el filtro si el usuario quiere ignorar mains sin 'auditoria'
            pass

        rows.append(
            {
                "Archivo": ruta_archivo.name,
                "Tipo": u.tipo,
                "Nombre": u.nombre,
                "Padre": u.padre,
                "Linea_Inicio": u.linea_inicio,
                "Linea_Fin": u.linea_fin,
                "Lineas_Total": u.total_lineas,
                "Legacy": ", ".join(sorted(u.flags_legacy)),
                "IO": ", ".join(sorted(u.flags_io)),
                "Custom": ", ".join(sorted(u.flags_custom)),
            }
        )
    return rows


def main():
    path_fuente = CARPETA_CODIGO
    if not path_fuente.exists():
        print(f"Error: No existe '{CARPETA_CODIGO}'")
        return

    archivos = sorted([f for f in path_fuente.rglob("*") if f.suffix.lower() in (".f90", ".f", ".for", ".f95")])
    print(f"--- Inventario V4 (Jerarquía Fortran) ---")

    datos = []
    for archivo in archivos:
        datos.extend(auditar_archivo(archivo))

    if datos:
        campos = [
            "Archivo",
            "Tipo",
            "Nombre",
            "Padre",
            "Linea_Inicio",
            "Linea_Fin",
            "Lineas_Total",
            "Legacy",
            "IO",
            "Custom",
        ]
        ARCHIVO_SALIDA.parent.mkdir(parents=True, exist_ok=True)
        with open(ARCHIVO_SALIDA, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(datos)
        print(f"Reporte generado: {ARCHIVO_SALIDA}")


if __name__ == "__main__":
    main()
