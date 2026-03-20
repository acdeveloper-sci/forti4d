# * ATENCIÓN
# * ESTE CÓDIGO VIENE DEL INTENTO DE PROYECTO UBICADO EN
# * D:\Documents\fiverr\violeta_m1969\job01\revision\forttools-dev\hbf\hbf-core
# * Este archivo es lo que corresponde a
# *   hbf\hbf-core\src\hbf\core\lines
# *
# * En sí el proyecto consta de dos librerías independientes,
# * uno la base y el otro las herramientas
# *   hbf\hbf-core\src\hbf\core
# *   hbf\hbf-core\src\hbf\tools
# *
# * Tomé el reader.py como base para este, colocando el dataclass LogicalLine dentro,
# * porque este lector de archivos de código fuente Fortran ya está muy pulido
# * para crear script que hagan cosas directas y confiables sin mucho aparataje
# * arquitectónico como en ese proyecto
#
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple, Optional, List


@dataclass(frozen=True)
class LogicalLine:
    start_line: int
    text: str
    label: Optional[str]
    is_comment: bool
    raw_lines: List[Tuple[int, str]]


# HELPERS


def split_by_symbol_outof_quotation(text: str, symbol: str) -> Tuple[str, str]:
    """
    Divide el texto por el símbolo solo si no está dentro de comillas.
    """
    in_quoting = None
    for i, c in enumerate(text):
        if c in ('"', "'"):
            if in_quoting is None:
                in_quoting = c
            elif in_quoting == c:
                in_quoting = None
        elif c == symbol and in_quoting is None:
            return text[:i], text[i + 1 :]
    return text, ""


def strip_inline_comment(line: str, comment_char: str = "!") -> Tuple[str, str]:
    """
    Separa código y comentarios respetando strings.
    """
    code, comment = split_by_symbol_outof_quotation(line, comment_char)
    return code, comment


# def remove_continuation_chars(line: str, format_type: str) -> str:
#     """
#     Elimina caracteres de continuación y espacios extra.
#     """
#     if format_type == "free":
#         # Usamos strip_inline_comment para aislar el código seguro
#         code, _ = strip_inline_comment(line)
#         code = code.rstrip()
#         if code.endswith("&"):
#             code = code[:-1].rstrip()
#         if code.strip().startswith("&"):
#             code = code.strip()[1:].strip()
#         return code
#     elif format_type == "fixed":
#         # En fijo, la marca está en col 6 (fuera del contenido útil)
#         # o el contenido útil empieza en col 7. Esta función limpia el contenido.
#         return line
#     return line


def remove_continuation_chars(line: str, format_type: str) -> str:
    """
    Elimina caracteres de continuación según el formato.
    En 'free', quita el '&' al final (y el '&' inicial si existe).
    En 'fixed', devuelve el contenido a partir de la columna 7 (limpiando la col 6).
    """
    if format_type == "free":
        code, _ = strip_inline_comment(line)
        code = code.rstrip()
        # Quitar ampersand al final
        if code.endswith("&"):
            code = code[:-1].rstrip()
        # Quitar ampersand al inicio (opcional en F90+ pero válido)
        if code.strip().startswith("&"):
            code = code.strip()[1:].strip()
        return code

    elif format_type == "fixed":
        # Si la línea es lo suficientemente larga, el código real empieza en la col 7 (índice 6)
        # La columna 6 (índice 5) es la marca que DEBEMOS ignorar.
        if len(line) >= 6:
            return line[6:]
        return ""  # Línea demasiado corta para tener código en formato fijo

    return line


def has_continuation_char(line: str, format_type: str) -> bool:
    """
    Detecta si la línea actual solicita continuación en la SIGUIENTE (Estilo F90 '&').
    """
    if format_type == "free":
        code, _ = strip_inline_comment(line)
        return code.rstrip().endswith("&")
    elif format_type == "fixed":
        # En fixed, la línea actual NUNCA dice "continuaré".
        # Es la siguiente la que dice "soy continuación".
        return False
    return False


def extract_label_from_line(line: str, format_type: str) -> Optional[str]:
    """
    Extrae la etiqueta numérica de la sentencia.
    """
    if format_type == "fixed":
        label_field = line[0:5].strip()
        if label_field and label_field.isdigit():
            return label_field
    elif format_type == "free":
        match = re.match(r"^\s*(\d+)\s+", line)
        if match:
            return match.group(1)
    return None


# LECTOR DE LÍNEAS LÓGICAS (CORE LOGIC)


def read_logical_lines(filepath: str) -> List[LogicalLine]:
    """
    Lee un archivo Fortran y retorna una lista de LogicalLine.
    Implementa "Registro Diferido" para manejar robustamente la continuación de líneas
    en formatos Fijo (F77) y Libre (F90).
    """
    path_obj = Path(filepath)

    # Detección de formato
    is_fixed_format = path_obj.suffix.lower() in [".f", ".for", ".f77"]
    format_type = "fixed" if is_fixed_format else "free"

    vlines: List[LogicalLine] = []

    # Estado del Buffer (Línea Lógica en construcción)
    buffer_content: List[str] = []
    buffer_raw_lines: List[Tuple[int, str]] = []
    logical_start_num: Optional[int] = None

    # Estado de Continuación (Persistencia entre iteraciones)
    # Indica si la línea ANTERIOR terminó con un '&' (solicitando continuación)
    expecting_f90_continuation = False

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            raw_physical_line = line.rstrip("\n")

            # A) Detección de marca F77 (Columna 6)
            #    Vital hacerlo antes de limpiar, porque define si es código o continuación.
            is_f77_continuation_mark = False
            if is_fixed_format and len(raw_physical_line) >= 6:
                if raw_physical_line[5] not in (" ", "0"):
                    is_f77_continuation_mark = True

            # --- 1. Detección de Comentarios (Filtro Previo) ---
            # Identificamos si es un comentario "puro" (toda la línea)

            # B) Detección de Comentarios (Lógica Robusta Híbrida)
            is_logical_comment = False

            if is_fixed_format:
                # Caso 1: Comentario clásico en Columna 1
                if len(raw_physical_line) > 0 and raw_physical_line[0].upper() in ("C", "*", "!"):
                    is_logical_comment = True
                # Caso 2: Comentario moderno indentado (! en cualquier parte)
                # OJO: Solo si NO es una línea de continuación (Col 6 vacía)
                elif not is_f77_continuation_mark:
                    # Quitamos márgenes (cols 1-6) y buscamos !
                    content_part = raw_physical_line[6:] if len(raw_physical_line) >= 6 else ""
                    if content_part.strip().startswith("!"):
                        is_logical_comment = True
            else:
                # Formato Libre
                code_part, comment_part = strip_inline_comment(raw_physical_line)
                if not code_part.strip() and comment_part.strip():
                    is_logical_comment = True

            # C) Ignorar líneas totalmente vacías (sin código ni comentario)
            # if not raw_physical_line.strip():
            #     continue

            # C) Detección de Línea Vacía (Blank Line)
            # Definimos "vacía" como línea sin caracteres visibles
            is_blank_line = not raw_physical_line.strip()

            # -----------------------------------------------------------------
            # 2. MANEJO DE LÍNEAS NO EJECUTABLES (COMENTARIOS Y VACÍAS) Y FLUSHING
            # -----------------------------------------------------------------
            if is_logical_comment or is_blank_line:
                # 2.1 FLUSH CONDICIONAL
                # Si hay buffer pendiente y NO estamos esperando continuación explícita (F90 &),
                # esta línea intermedia confirma que la sentencia anterior terminó.
                # Nota: Si expecting_f90_continuation es True, NO flusheamos; la línea vacía/comentario
                # se inserta "en medio" de la construcción lógica (intercalada).

                if buffer_content and not expecting_f90_continuation:
                    # FLUSH BUFFER ANTERIOR
                    final_text = " ".join(buffer_content)
                    first_raw = buffer_raw_lines[0][1]
                    label = extract_label_from_line(first_raw, format_type) or None

                    vlines.append(
                        LogicalLine(
                            start_line=logical_start_num,  # type: ignore
                            text=final_text,
                            label=label,
                            is_comment=False,
                            raw_lines=list(buffer_raw_lines),
                        )
                    )
                    buffer_content = []
                    buffer_raw_lines = []
                    # Nota: No reseteamos expecting_f90_continuation porque un comentario
                    # NO debería romper una continuación pendiente (si es que la hubiera).

                # 2.2 REGISTRO DE LA LÍNEA ACTUAL
                # Se registra fielmente.
                # - Si es comentario: is_comment=True
                # - Si es vacía: is_comment=False (Es whitespace, el classifier dirá que es COMMENT o nada)

                vlines.append(
                    LogicalLine(
                        start_line=line_num,
                        text=raw_physical_line,
                        label=None,
                        is_comment=is_logical_comment,
                        raw_lines=[(line_num, raw_physical_line)],
                    )
                )
                continue  # Pasamos a la siguiente línea

            # 3. LÓGICA DE CÓDIGO (ACUMULACIÓN)

            #    Detección de Señales de Continuación (Current Line)

            # A) Señal F90: Ampersand al final
            # (Esta señal mira "hacia adelante": Pido que la siguiente me continúe)
            # Detectar si ESTA línea pide continuación F90 (Ampersand al final)
            # Usamos el HELPER como solicitaste
            current_line_requests_continuation = has_continuation_char(raw_physical_line, format_type)

            # Decisión de Fusión (Merge Decision)
            # ¿Debemos unir esta línea al buffer existente?
            # Solo si hay un buffer abierto Y (es cont F77 O la anterior pidió cont F90)
            # ¿Unimos al buffer? Solo si hay buffer Y (es cont F77 O la anterior pidió cont F90)
            should_merge = False
            if buffer_content:  # Solo puede ser continuación si ya hay algo empezado
                if is_f77_continuation_mark or expecting_f90_continuation:
                    should_merge = True

            # Ejecución de Acción
            # Preparación del contenido
            processed_code = remove_continuation_chars(raw_physical_line, format_type)

            # Ajuste extra para Fijo: Cortar las primeras 6 columnas si es código
            # if is_fixed_format and len(processed_code) >= 6:
            #     processed_code = processed_code[6:]

            # Limpieza Extra: Quitar comentarios inline que quedaron
            processed_code = strip_inline_comment(processed_code)[0].strip()

            if should_merge:
                # ACUMULAR en el buffer existente
                buffer_content.append(processed_code.strip())
                buffer_raw_lines.append((line_num, raw_physical_line))

            else:
                # RUPTURA (FLUSH): Registrar lo anterior y empezar nuevo

                # a) Si había un buffer previo, lo cerramos y guardamos
                if buffer_content:
                    final_text = " ".join(buffer_content)

                    # Etiqueta de la primera línea física del grupo
                    first_raw = buffer_raw_lines[0][1]
                    label = extract_label_from_line(first_raw, format_type) or ""

                    vlines.append(
                        LogicalLine(
                            start_line=logical_start_num,  # type: ignore
                            text=final_text,
                            label=label,
                            is_comment=False,
                            raw_lines=list(buffer_raw_lines),
                        )
                    )

                # b) Iniciar nuevo buffer con la línea actual
                if processed_code:  # Solo si quedó algo de código (protección extra)
                    logical_start_num = line_num
                    buffer_content = [processed_code.strip()]
                    buffer_raw_lines = [(line_num, raw_physical_line)]
                else:
                    # Si al limpiar no quedó nada (raro, pero posible si strip falló arriba), reset
                    buffer_content = []
                    buffer_raw_lines = []

            # 5. Actualizar Estado para la próxima vuelta
            # La "expectativa" para la siguiente línea depende de si ESTA línea terminó en &
            expecting_f90_continuation = current_line_requests_continuation

    # --- FLUSH FINAL (Al terminar el archivo) ---
    if buffer_content:
        final_text = " ".join(buffer_content)
        first_raw = buffer_raw_lines[0][1]
        label = extract_label_from_line(first_raw, format_type) or ""

        vlines.append(
            LogicalLine(
                start_line=logical_start_num,  # type: ignore
                text=final_text,
                label=label,
                is_comment=False,
                raw_lines=list(buffer_raw_lines),
            )
        )

    return vlines
