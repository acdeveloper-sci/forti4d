import re

# =============================================================================
# PATRONES DE EXPRESIÓN REGULAR PARA FORTRAN (STRICT MODE)
# =============================================================================

# --- 1. Unidades de Programa (Program Units) ---
# Captura: "PROGRAM main"
RE_PROGRAM = re.compile(r"^program\b\s+(\w+)", re.IGNORECASE)

# Captura: "MODULE fisica" (Excluye "MODULE PROCEDURE")
RE_MODULE = re.compile(r"^module\b\s+(\w+)\s*(!.*)?$", re.IGNORECASE)

# Captura: "SUBROUTINE cal(a,b)" (Soporta prefijos PURE, RECURSIVE...)
RE_SUBROUTINE = re.compile(r"^(?:(?:pure|elemental|recursive)\s+)*subroutine\b\s+(\w+)", re.IGNORECASE)

# Captura:
# 1. Prefijos opcionales (RECURSIVE, PURE, ELEMENTAL...)
# 2. Tipo de retorno opcional (INTEGER, REAL*8, TYPE(MyType))
# 3. La palabra FUNCTION
# 4. El nombre
RE_FUNCTION = re.compile(r"^(?!end\b)(?:[\w\*\(\)]+\s+)*function\b\s+(\w+)", re.IGNORECASE)

# Captura: "BLOCK DATA init"
RE_BLOCK_DATA = re.compile(r"^block\s*data\b(?:\s+(\w+))?", re.IGNORECASE)


# --- 2. Definiciones y Scoping ---
# Captura: "TYPE :: Persona" o "TYPE Persona".
# Negative Lookahead (?!\() asegura que no sea "TYPE(Persona)" (declaración variable)
RE_TYPE_DEF = re.compile(r"^type\b\s*(?:,\s*[\w\s,]+)?(?:::)?\s*(\w+)\s*(?!\()", re.IGNORECASE)

# Captura: "INTERFACE" o "INTERFACE OPERATOR(+)"
RE_INTERFACE = re.compile(r"^interface\b(?:\s+(\w+))?", re.IGNORECASE)


# --- 3. Constructos Ejecutables (Block Openers, con soporte para Construct Names)) ---
# Estructura del prefijo: (\w+:\s*)?  -> Captura "nombre: " opcionalmente

# Captura: "nombre: IF (...) THEN" (Obligatorio THEN)
RE_IF_BLOCK = re.compile(r"^(\w+:\s*)?if\b\s*\(.*\)\s*then\b\s*(!.*)?$", re.IGNORECASE)

# DO WHILE: "nombre: DO WHILE (cond)"
# Importante: \s*\( asegura que sea un constructo y no una variable rara
RE_DO_WHILE = re.compile(r"^(\w+:\s*)?do\b\s*while\b\s*\(", re.IGNORECASE)

# Captura: "DO", "DO 10", "DO i=1,10", "nombre: DO"
# Grupo 1: Nombre constructo (opcional). Grupo 2: Label (opcional).
RE_DO = re.compile(r"^(\w+:\s*)?do\b(?:\s+(\d+))?", re.IGNORECASE)

RE_SELECT = re.compile(r"^(\w+:\s*)?select\b\s*(case|type)\b", re.IGNORECASE)
RE_ASSOCIATE = re.compile(r"^(\w+:\s*)?associate\b\s*\(", re.IGNORECASE)
RE_BLOCK = re.compile(r"^(\w+:\s*)?block\b\s*(!.*)?$", re.IGNORECASE)
RE_CRITICAL = re.compile(r"^(\w+:\s*)?critical\b\s*(\(|!|$)", re.IGNORECASE)
RE_FORALL_PREFIX = re.compile(r"^(\w+:\s*)?forall\b\s*\(", re.IGNORECASE)

# A futuro, diferenciar Bloque: WHERE (mask) ... END WHERE (Complejidad alta)
# de Sentencia: WHERE (mask) A = B (Complejidad baja, atómico).
RE_WHERE_PREFIX = re.compile(r"^(\w+:\s*)?where\b\s*\(", re.IGNORECASE)


# --- 4. Fronteras (Spine) ---
RE_CONTAINS = re.compile(r"^contains\b\s*(!.*)?$", re.IGNORECASE)
RE_ELSE = re.compile(r"^else\b\s*(!.*)?$", re.IGNORECASE)
RE_ELSE_IF = re.compile(r"^else\b\s*if\b", re.IGNORECASE)  # Este es seguro por el 'if'
RE_ELSEWHERE = re.compile(r"^elsewhere\b\s*(!.*)?$", re.IGNORECASE)
RE_CASE = re.compile(r"^case\b\s*\(|^case\b\s+default\b", re.IGNORECASE)
RE_CLASS_IS = re.compile(r"^(class|type)\b\s+is\b\s*\(", re.IGNORECASE)
RE_ENTRY = re.compile(r"^entry\b\s+(\w+)", re.IGNORECASE)

# --- 5. Cierres (Endings) ---
# Captura "END", "END IF", "END SUBROUTINE Nombre"
# RE_END_GENERIC = re.compile(r"^end\b\s*(\w+)?(?:\s+(\w+))?\s*(!.*)?$", re.IGNORECASE)
# Permite ENDPROGRAM, END SUBROUTINE, END, etc.
# RE_END_GENERIC = re.compile(
#     r"^\s*end(?:\s+|)(program|module|subroutine|function|block\s*data)?(?:\s+(\w+))?\s*(!.*)?$", re.IGNORECASE
# )
RE_END_GENERIC = re.compile(
    r"^\s*end(?:\s+|)(program|module|subroutine|function|interface|type|do|if|select|associate|block\s*data|block|critical|where|forall|enum)?(?:\s+(\w+))?\s*(!.*)?$",
    re.IGNORECASE,
)

# --- 6. Sentencias Simples Clave ---
RE_USE = re.compile(r"^use\b\s+(\w+)", re.IGNORECASE)
RE_IMPLICIT = re.compile(r"^implicit\b\s+", re.IGNORECASE)
RE_CALL = re.compile(r"^call\b\s+(\w+)", re.IGNORECASE)

# --- 7. Nuevos Patrones Extendidos (Blindados contra Asignaciones) ---

# Constructo ENUM: Exigimos la coma del BIND(C) para evitar 'enum = 1'
RE_ENUM = re.compile(r"^enum\b\s*,", re.IGNORECASE)

# Control de Flujo
# GOTO: Exigimos dígito o paréntesis después. Evita 'goto = 1'
RE_GOTO = re.compile(r"^go\s*to\b\s*[\d\(]", re.IGNORECASE)
# RETURN: Usamos negative lookahead (?!\s*=) para asegurar que no sigue un igual
RE_RETURN = re.compile(r"^return\b(?!\s*=)", re.IGNORECASE)
RE_EXIT_CYCLE = re.compile(r"^(exit|cycle)\b(?!\s*=)", re.IGNORECASE)
RE_STOP_PAUSE = re.compile(r"^(error\s+stop|stop|pause)\b(?!\s*=)", re.IGNORECASE)
RE_CONTINUE = re.compile(r"^continue\b(?!\s*=)", re.IGNORECASE)

# I/O: Exigimos paréntesis o asterisco (o formato)
RE_IO_TRANSFER = re.compile(r"^(read|write|print)\b\s*[\(\*]", re.IGNORECASE)
RE_FILE_OPEN = re.compile(r"^(open|close|inquire)\b\s*\(", re.IGNORECASE)
RE_FILE_POS = re.compile(r"^(backspace|endfile|rewind|flush|wait)\b\s*\(", re.IGNORECASE)
RE_FORMAT = re.compile(r"^format\s*\(", re.IGNORECASE)

# Otros
RE_ACCESS_STMT = re.compile(r"^(public|private|protected)\b(?!\s*=)", re.IGNORECASE)
RE_ALLOCATION = re.compile(r"^(allocate|deallocate|nullify)\b\s*\(", re.IGNORECASE)
RE_IMPORT = re.compile(r"^import\b", re.IGNORECASE)
RE_PARAMETER_STMT = re.compile(r"^parameter\s*\(", re.IGNORECASE)
RE_ENUMERATOR = re.compile(r"^enumerator\b", re.IGNORECASE)

# RE_VAR_DECL = re.compile(r"^(integer|real|complex|logical|character|type\s*\()", re.IGNORECASE)

# MEJORA: Agregamos DATA, COMMON, NAMELIST, EQUIVALENCE a Declaraciones
# Nota: parameter, allocatable, etc son atributos o statements
# 1. Tipos de Datos (Incluyendo Double Precision)
RE_DATA_TYPE = re.compile(
    r"^(?:integer|real|complex|logical|character|double\s+precision|type\b\s*\()\b", re.IGNORECASE
)

# 2. Otros Atributos/Especificaciones
RE_COMMON = re.compile(r"^common\b", re.IGNORECASE)
RE_EQUIVALENCE = re.compile(r"^equivalence\b", re.IGNORECASE)
RE_DATA = re.compile(r"^data\b", re.IGNORECASE)
RE_NAMELIST = re.compile(r"^namelist\b", re.IGNORECASE)
RE_INCLUDE = re.compile(r"^include\b", re.IGNORECASE)
RE_ATTR_SPEC = re.compile(
    r"^(?:parameter|external|intrinsic|save|dimension|intent|optional|target|pointer|allocatable)\b",
    re.IGNORECASE,
)

# --- IFs Especiales (Para el futuro paso de lógica) ---
RE_ARITHMETIC_IF = re.compile(r"^if\b\s*\(.*\)\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", re.IGNORECASE)

# Busca IF (...) pero se asegura de que lo que sigue NO sea la palabra THEN
# (?! ... ) es el negative lookahead.
# \s*then\b es lo que queremos prohibir al final de la estructura.
RE_LOGICAL_IF_PREFIX = re.compile(r"^if\b\s*\(.*\)(?!\s*then\b)", re.IGNORECASE)
