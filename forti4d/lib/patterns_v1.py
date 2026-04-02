import re

# =============================================================================
# REGULAR EXPRESSION PATTERNS FOR FORTRAN (STRICT MODE)
# =============================================================================

# --- 1. Program Units ---
# Matches: "PROGRAM main"
RE_PROGRAM = re.compile(r"^program\b\s+(\w+)", re.IGNORECASE)

# Matches: "MODULE physics" (Excludes "MODULE PROCEDURE")
RE_MODULE = re.compile(r"^module\b\s+(\w+)\s*(!.*)?$", re.IGNORECASE)

# Matches: "SUBROUTINE calc(a,b)" (Supports PURE, RECURSIVE... prefixes)
RE_SUBROUTINE = re.compile(r"^(?:(?:pure|elemental|recursive)\s+)*subroutine\b\s+(\w+)", re.IGNORECASE)

# Matches:
# 1. Optional prefixes (RECURSIVE, PURE, ELEMENTAL...)
# 2. Optional return type (INTEGER, REAL*8, TYPE(MyType))
# 3. The keyword FUNCTION
# 4. The name
RE_FUNCTION = re.compile(r"^(?!end\b)(?:[\w\*\(\)]+\s+)*function\b\s+(\w+)", re.IGNORECASE)

# Matches: "BLOCK DATA init"
RE_BLOCK_DATA = re.compile(r"^block\s*data\b(?:\s+(\w+))?", re.IGNORECASE)


# --- 2. Definitions and Scoping ---
# Matches: "TYPE :: Person" or "TYPE Person".
# Negative Lookahead (?!\() ensures it is not "TYPE(Person)" (variable declaration)
RE_TYPE_DEF = re.compile(r"^type\b\s*(?:,\s*[\w\s,]+)?(?:::)?\s*(\w+)\s*(?!\()", re.IGNORECASE)

# Matches: "INTERFACE" or "INTERFACE OPERATOR(+)"
RE_INTERFACE = re.compile(r"^interface\b(?:\s+(\w+))?", re.IGNORECASE)


# --- 3. Executable Constructs (Block Openers, with support for Construct Names) ---
# Prefix structure: (\w+:\s*)?  -> Optionally captures "name: "

# Matches: "name: IF (...) THEN" (THEN is mandatory)
RE_IF_BLOCK = re.compile(r"^(\w+:\s*)?if\b\s*\(.*\)\s*then\b\s*(!.*)?$", re.IGNORECASE)

# DO WHILE: "name: DO WHILE (cond)"
# Important: \s*\( ensures it is a construct and not an unusual variable
RE_DO_WHILE = re.compile(r"^(\w+:\s*)?do\b\s*while\b\s*\(", re.IGNORECASE)

# Matches: "DO", "DO 10", "DO i=1,10", "name: DO"
# Group 1: Construct name (optional). Group 2: Label (optional).
RE_DO = re.compile(r"^(\w+:\s*)?do\b(?:\s+(\d+))?", re.IGNORECASE)

RE_SELECT = re.compile(r"^(\w+:\s*)?select\b\s*(case|type)\b", re.IGNORECASE)
RE_ASSOCIATE = re.compile(r"^(\w+:\s*)?associate\b\s*\(", re.IGNORECASE)
RE_BLOCK = re.compile(r"^(\w+:\s*)?block\b\s*(!.*)?$", re.IGNORECASE)
RE_CRITICAL = re.compile(r"^(\w+:\s*)?critical\b\s*(\(|!|$)", re.IGNORECASE)
RE_FORALL_PREFIX = re.compile(r"^(\w+:\s*)?forall\b\s*\(", re.IGNORECASE)

# Future: differentiate Block: WHERE (mask) ... END WHERE (high complexity)
# from Statement: WHERE (mask) A = B (low complexity, atomic).
RE_WHERE_PREFIX = re.compile(r"^(\w+:\s*)?where\b\s*\(", re.IGNORECASE)


# --- 4. Boundaries (Spine) ---
RE_CONTAINS = re.compile(r"^contains\b\s*(!.*)?$", re.IGNORECASE)
RE_ELSE = re.compile(r"^else\b\s*(!.*)?$", re.IGNORECASE)
RE_ELSE_IF = re.compile(r"^else\b\s*if\b", re.IGNORECASE)  # Safe due to the 'if'
RE_ELSEWHERE = re.compile(r"^elsewhere\b\s*(!.*)?$", re.IGNORECASE)
RE_CASE = re.compile(r"^case\b\s*\(|^case\b\s+default\b", re.IGNORECASE)
RE_CLASS_IS = re.compile(r"^(class|type)\b\s+is\b\s*\(", re.IGNORECASE)
RE_ENTRY = re.compile(r"^entry\b\s+(\w+)", re.IGNORECASE)

# --- 5. Closings (Endings) ---
# Matches "END", "END IF", "END SUBROUTINE Name"
# RE_END_GENERIC = re.compile(r"^end\b\s*(\w+)?(?:\s+(\w+))?\s*(!.*)?$", re.IGNORECASE)
# Allows ENDPROGRAM, END SUBROUTINE, END, etc.
# RE_END_GENERIC = re.compile(
#     r"^\s*end(?:\s+|)(program|module|subroutine|function|block\s*data)?(?:\s+(\w+))?\s*(!.*)?$", re.IGNORECASE
# )
RE_END_GENERIC = re.compile(
    r"^\s*end(?:\s+|)(program|module|subroutine|function|interface|type|do|if|select|associate|block\s*data|block|critical|where|forall|enum)?(?:\s+(\w+))?\s*(!.*)?$",
    re.IGNORECASE,
)

# --- 6. Key Simple Statements ---
RE_USE = re.compile(r"^use\b\s+(\w+)", re.IGNORECASE)
RE_IMPLICIT = re.compile(r"^implicit\b\s+", re.IGNORECASE)
RE_CALL = re.compile(r"^call\b\s+(\w+)", re.IGNORECASE)

# --- 7. Extended Patterns (Protected Against Assignments) ---

# ENUM construct: We require the BIND(C) comma to avoid 'enum = 1'
RE_ENUM = re.compile(r"^enum\b\s*,", re.IGNORECASE)

# Control Flow
# GOTO: We require a digit or parenthesis after. Avoids 'goto = 1'
RE_GOTO = re.compile(r"^go\s*to\b\s*[\d\(]", re.IGNORECASE)
# RETURN: Uses negative lookahead (?!\s*=) to ensure no equals sign follows
RE_RETURN = re.compile(r"^return\b(?!\s*=)", re.IGNORECASE)
RE_EXIT_CYCLE = re.compile(r"^(exit|cycle)\b(?!\s*=)", re.IGNORECASE)
RE_STOP_PAUSE = re.compile(r"^(error\s+stop|stop|pause)\b(?!\s*=)", re.IGNORECASE)
RE_CONTINUE = re.compile(r"^continue\b(?!\s*=)", re.IGNORECASE)

# I/O: We require parentheses or asterisk (or format)
RE_IO_TRANSFER = re.compile(r"^(read|write|print)\b\s*[\(\*]", re.IGNORECASE)
RE_FILE_OPEN = re.compile(r"^(open|close|inquire)\b\s*\(", re.IGNORECASE)
RE_FILE_POS = re.compile(r"^(backspace|endfile|rewind|flush|wait)\b\s*\(", re.IGNORECASE)
RE_FORMAT = re.compile(r"^format\s*\(", re.IGNORECASE)

# Other
RE_ACCESS_STMT = re.compile(r"^(public|private|protected)\b(?!\s*=)", re.IGNORECASE)
RE_ALLOCATION = re.compile(r"^(allocate|deallocate|nullify)\b\s*\(", re.IGNORECASE)
RE_IMPORT = re.compile(r"^import\b", re.IGNORECASE)
RE_PARAMETER_STMT = re.compile(r"^parameter\s*\(", re.IGNORECASE)
RE_ENUMERATOR = re.compile(r"^enumerator\b", re.IGNORECASE)

# RE_VAR_DECL = re.compile(r"^(integer|real|complex|logical|character|type\s*\()", re.IGNORECASE)

# IMPROVEMENT: Added DATA, COMMON, NAMELIST, EQUIVALENCE to Declarations
# Note: parameter, allocatable, etc. are attributes or statements
# 1. Data Types (Including Double Precision)
RE_DATA_TYPE = re.compile(
    r"^(?:integer|real|complex|logical|character|double\s+precision|type\b\s*\()\b", re.IGNORECASE
)

# 2. Other Attributes/Specifications
RE_COMMON = re.compile(r"^common\b", re.IGNORECASE)
RE_EQUIVALENCE = re.compile(r"^equivalence\b", re.IGNORECASE)
RE_DATA = re.compile(r"^data\b", re.IGNORECASE)
RE_NAMELIST = re.compile(r"^namelist\b", re.IGNORECASE)
RE_INCLUDE = re.compile(r"^include\b", re.IGNORECASE)
RE_ATTR_SPEC = re.compile(
    r"^(?:parameter|external|intrinsic|save|dimension|intent|optional|target|pointer|allocatable)\b",
    re.IGNORECASE,
)

# --- Special IFs (For future logic pass) ---
RE_ARITHMETIC_IF = re.compile(r"^if\b\s*\(.*\)\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", re.IGNORECASE)

# Matches IF (...) but ensures what follows is NOT the keyword THEN
# (?! ... ) is the negative lookahead.
# \s*then\b is what we want to prohibit at the end of the structure.
RE_LOGICAL_IF_PREFIX = re.compile(r"^if\b\s*\(.*\)(?!\s*then\b)", re.IGNORECASE)
