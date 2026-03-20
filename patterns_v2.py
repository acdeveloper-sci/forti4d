import re

# =============================================================================
# PATRONES DE EXPRESIÓN REGULAR PARA FORTRAN (STRICT MODE & BACKWARD COMPATIBLE = PRODUCTION SAFE)
# =============================================================================

# Nota sobre ^\s*: Aunque el reader hace strip(), se mantiene por seguridad defensiva.
# Nota sobre \b: Se usa para asegurar palabra completa (evitar que 'integer_val' sea 'integer')
# Nota: Se usa \b para límites de palabra y re.IGNORECASE en todos.
# Los grupos de captura (parentesis) están alineados para devolver el NOMBRE en group(1).

# --- 1. Unidades de Programa (Program Units) ---
RE_PROGRAM = re.compile(r"^\s*program\b\s+(\w+)", re.IGNORECASE)
RE_MODULE = re.compile(r"^\s*module\b\s+(\w+)\s*(!.*)?$", re.IGNORECASE)
RE_SUBROUTINE = re.compile(r"^\s*(?:(?:pure|elemental|recursive)\s+)*subroutine\b\s+(\w+)", re.IGNORECASE)
RE_FUNCTION = re.compile(r"^\s*(?!end\b)(?:[\w\*\(\)]+\s+)*function\b\s+(\w+)", re.IGNORECASE)
RE_BLOCK_DATA = re.compile(r"^\s*block\s*data\b(?:\s+(\w+))?", re.IGNORECASE)

# --- 2. Definiciones de Estructuras de Datos ---
# CORREGIDO: Ahora captura el nombre opcional en el grupo 1
RE_INTERFACE = re.compile(r"^\s*(?:abstract\s+)?interface\b(?:\s+(\w+))?", re.IGNORECASE)
RE_MODULE_PROCEDURE = re.compile(r"^\s*module\s*procedure\b", re.IGNORECASE)
RE_TYPE_DEF = re.compile(r"^\s*type\b\s*(?:,\s*[\w\s,()]+)?\s*::\s*(\w+)", re.IGNORECASE)
RE_ENUM_DEF = re.compile(r"^\s*enum\b\s*,\s*bind\s*\(", re.IGNORECASE)
RE_ENUMERATOR = re.compile(r"^\s*enumerator\b", re.IGNORECASE)

# --- 3. Declaraciones y Atributos ---
RE_VAR_DECL = re.compile(
    r"^\s*(?:integer|real|double\s+precision|complex|logical|character|type(?!\s*is)|class(?!\s*is)|procedure)\b",
    re.IGNORECASE,
)

# Atributos Específicos (Nuevos para Fase 2 Densidad)
RE_COMMON = re.compile(r"^\s*common\b", re.IGNORECASE)
RE_EQUIVALENCE = re.compile(r"^\s*equivalence\b", re.IGNORECASE)
RE_DATA = re.compile(r"^\s*data\b", re.IGNORECASE)
RE_NAMELIST = re.compile(r"^\s*namelist\b", re.IGNORECASE)

RE_Keep_Atomic = re.compile(
    r"^\s*(?:allocatable|dimension|external|intent|intrinsic|optional|parameter|pointer|private|public|save|target|volatile|value|protected)\b",
    re.IGNORECASE,
)

# Patrón Agrupado (Para compatibilidad con scripts viejos que usen RE_ATTR_SPEC)
# Incluye protected, enumerator, y los legacy.
# Atributos Generales (Compatibilidad hacia atrás para inventario.py)
RE_ATTR_SPEC = re.compile(
    r"^\s*(?:allocatable|dimension|external|intent|intrinsic|optional|parameter|pointer|private|public|save|target|volatile|value|protected|enumerator|common|equivalence|data|namelist)\b",
    re.IGNORECASE,
)

# Especificaciones de Módulo
RE_USE = re.compile(r"^\s*use\b", re.IGNORECASE)
RE_IMPORT = re.compile(r"^\s*import\b", re.IGNORECASE)
RE_IMPLICIT = re.compile(r"^\s*implicit\b", re.IGNORECASE)

# --- 4. Control de Flujo ---
RE_IF_BLOCK = re.compile(r"^\s*(?:(\w+)\s*:\s*)?if\s*\(.*\)\s*then\b", re.IGNORECASE)

# CORRECCIÓN: Se ajusta para capturar 'DO', 'DO WHILE' y 'DOWHILE' (compacto)
# La lógica es: 'do' seguido opcionalmente de espacio+while o pegado+while
# RE_DO_LOOP = re.compile(r"^\s*(?:(\w+)\s*:\s*)?do\b", re.IGNORECASE)
RE_DO_LOOP = re.compile(r"^\s*(?:(\w+)\s*:\s*)?do(?:\s*while)?\b", re.IGNORECASE)

RE_SELECT_CASE = re.compile(r"^\s*(?:(\w+)\s*:\s*)?select\s*(?:case|type)\b", re.IGNORECASE)
RE_ASSOCIATE = re.compile(r"^\s*(?:(\w+)\s*:\s*)?associate\b", re.IGNORECASE)
RE_BLOCK_CONST = re.compile(r"^\s*(?:(\w+)\s*:\s*)?block\b", re.IGNORECASE)
RE_CRITICAL = re.compile(r"^\s*(?:(\w+)\s*:\s*)?critical\b", re.IGNORECASE)

RE_WHERE_BLOCK = re.compile(r"^\s*where\s*\(.*\)\s*then\b", re.IGNORECASE)
RE_FORALL_BLOCK = re.compile(r"^\s*forall\s*\(.*\)\s*then\b", re.IGNORECASE)

# Single Line Statements
# 1. Arithmetic IF (Legacy estricto): IF (expr) label1, label2, label3
# Busca: IF (...) numero, numero, numero
RE_ARITHMETIC_IF = re.compile(r"^\s*if\s*\(.*\)\s*\d+\s*,\s*\d+\s*,\s*\d+", re.IGNORECASE)

# 2. Logical IF Single (Sentencia única): IF (expr) action
# Definición: Empieza por IF, tiene paréntesis, y NO termina en THEN.
# IMPORTANTE: Este patrón cubre al Arithmético también. En lógica de código, validar Arithmético primero.

# deja de validar cuando no hay espacio después del paréntesis que cierra la condición.
# RE_IF_SINGLE = re.compile(r"^\s*if\s*\(.*\)\s+(?!then\b)", re.IGNORECASE)
# patrón corregido por, fijarse en los delimitadores léxicos de condición ( y ) que pueden estar sin espacio
RE_IF_SINGLE = re.compile(r"^\s*if\s*\(.*\)\s*(?!then\b)", re.IGNORECASE)

# Alias para retro-compatibilidad (si tu inventario usaba este nombre):
RE_LOGICAL_IF_PREFIX = RE_IF_SINGLE

# Versiones de una línea de Where/Forall

# deja de validar cuando no hay espacio después del paréntesis que cierra la condición.

# deja de validar cuando no hay espacio después del paréntesis que cierra la condición.
# RE_WHERE_SINGLE = re.compile(r"^\s*where\s*\(.*\)\s+(?!then\b)", re.IGNORECASE)
# RE_FORALL_SINGLE = re.compile(r"^\s*forall\s*\(.*\)\s+(?!then\b)", re.IGNORECASE)

# patrón corregido por, fijarse en los delimitadores léxicos de condición ( y ) que pueden estar sin espacio
# CORRECCIÓN: Cambiado \s+ por \s* para aceptar WHERE(mask)A=B
RE_WHERE_SINGLE = re.compile(r"^\s*where\s*\(.*\)\s*(?!then\b)", re.IGNORECASE)
# CORRECCIÓN: Cambiado \s+ por \s* para aceptar FORALL(i=1:n)A(i)=0
RE_FORALL_SINGLE = re.compile(r"^\s*forall\s*\(.*\)\s*(?!then\b)", re.IGNORECASE)

# --- 5. Cierres y Estructura (Spine) ---
RE_CONTAINS = re.compile(r"^\s*contains\b", re.IGNORECASE)

# RE_END_BLOCK = re.compile(
#     r"^\s*end\s*(?:program|module|subroutine|function|interface|type|do|if|select|associate|block|critical|where|forall|enum)?\b",
#     re.IGNORECASE,
# )
RE_END_BLOCK = re.compile(
    r"^\s*end(?:\s+|)(?:program|module|subroutine|function|interface|type|do|if|select|associate|block|critical|where|forall|enum)?\b",
    re.IGNORECASE,
)

RE_ELSE = re.compile(r"^\s*else\s*(?:if\s*\(.*\)\s*then)?\b|^\s*elsewhere\b", re.IGNORECASE)
RE_CASE = re.compile(r"^\s*case\b|^\s*class\s*is\b|^\s*type\s*is\b", re.IGNORECASE)

# --- 6. Acciones y Helpers ---
# Tiene ALLOCATE y DEALLOCATE en un sólo patrón
# RE_ALLOCATE = re.compile(r"^\s*(?:de)?allocate\b", re.IGNORECASE)

# PROPUESTA (Alta reutilización)
RE_ALLOCATE = re.compile(r"^\s*allocate\b", re.IGNORECASE)
RE_DEALLOCATE = re.compile(r"^\s*deallocate\b", re.IGNORECASE)

RE_POINTER_OP = re.compile(r"^\s*(?:nullify\b|.*=>)", re.IGNORECASE)

# CORRECCIÓN: 'end file' y 'back space' pueden ir separados
# RE_IO = re.compile(r"^\s*(?:read|write|print|open|close|inquire|backspace|endfile|rewind|format)\b", re.IGNORECASE)
RE_IO = re.compile(
    r"^\s*(?:read|write|print|open|close|inquire|back\s*space|end\s*file|rewind|format)\b", re.IGNORECASE
)

RE_INCLUDE = re.compile(r"^\s*include\b", re.IGNORECASE)  # Importante para inventario

# Control de Transferencia

# CORRECCIÓN: 'go to' separado es muy común en F77. Se añade \s*
# RE_CONTROL = re.compile(r"^\s*(?:call|goto|return|stop|cycle|exit|continue|pause|entry)\b", re.IGNORECASE)
RE_CONTROL = re.compile(r"^\s*(?:call|go\s*to|return|stop|cycle|exit|continue|pause|entry)\b", re.IGNORECASE)

RE_PARAMETER = re.compile(r"^\s*parameter\s*\(", re.IGNORECASE)

# --- Helpers ---
# Útil para dependencias.py (detectar llamadas a funciones dentro de expresiones)
# Nota: Este es complejo y suele requerir lógica adicional, se mantiene simple aquí.
RE_FUNC_CALL_CANDIDATE = re.compile(r"(\w+)\s*\(", re.IGNORECASE)

# RETROCOMPATIBILIDAD INVENTARIO.PY
# --- 5. Cierres (Endings) ---
# Captura "END", "END IF", "END SUBROUTINE Nombre"
RE_END_GENERIC = re.compile(
    r"^\s*end(?:\s+|)(program|module|subroutine|function|interface|type|do|if|select|associate|block\s*data|block|critical|where|forall|enum)?(?:\s+(\w+))?\s*(!.*)?$",
    re.IGNORECASE,
)
