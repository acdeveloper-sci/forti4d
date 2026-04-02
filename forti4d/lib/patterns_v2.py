import re

# =============================================================================
# REGULAR EXPRESSION PATTERNS FOR FORTRAN (STRICT MODE & BACKWARD COMPATIBLE = PRODUCTION SAFE)
# =============================================================================

# Note on ^\s*: Although the reader does strip(), kept for defensive safety.
# Note on \b: Used to ensure whole-word matching (prevents 'integer_val' matching 'integer').
# Note: \b is used for word boundaries and re.IGNORECASE on all patterns.
# Capture groups (parentheses) are aligned to return the NAME in group(1).

# --- 1. Program Units ---
RE_PROGRAM = re.compile(r"^\s*program\b\s+(\w+)", re.IGNORECASE)
RE_MODULE = re.compile(r"^\s*module\b\s+(\w+)\s*(!.*)?$", re.IGNORECASE)
RE_SUBROUTINE = re.compile(r"^\s*(?:(?:pure|elemental|recursive)\s+)*subroutine\b\s+(\w+)", re.IGNORECASE)
RE_FUNCTION = re.compile(r"^\s*(?!end\b)(?:[\w\*\(\)]+\s+)*function\b\s+(\w+)", re.IGNORECASE)
RE_BLOCK_DATA = re.compile(r"^\s*block\s*data\b(?:\s+(\w+))?", re.IGNORECASE)

# --- 2. Data Structure Definitions ---
# FIXED: Now captures the optional name in group 1
RE_INTERFACE = re.compile(r"^\s*(?:abstract\s+)?interface\b(?:\s+(\w+))?", re.IGNORECASE)
RE_MODULE_PROCEDURE = re.compile(r"^\s*module\s*procedure\b", re.IGNORECASE)
# Detects TYPE definitions in both forms:
#   F90 with ::  →  TYPE [, attrs] :: name
#   F90/F95 without :: →  TYPE name
# Does NOT detect TYPE(name) (variable use) nor TYPE IS (...) (SELECT TYPE).
# Note: used only for detection (bool); derived_types.py uses its own
# local patterns to extract the name.
RE_TYPE_DEF = re.compile(
    r"^\s*type\b\s*"
    r"(?:"
    r"(?:,\s*[\w\s,()]+)?\s*::\s*\w+"   # F90 with :: (optional attributes)
    r"|"
    r"\w+(?!\w)(?!\s*\()"               # F90 without :: — (?!\w) prevents backtracking to prefix
    r")",
    re.IGNORECASE,
)
RE_ENUM_DEF = re.compile(r"^\s*enum\b\s*,\s*bind\s*\(", re.IGNORECASE)
RE_ENUMERATOR = re.compile(r"^\s*enumerator\b", re.IGNORECASE)

# --- 3. Declarations and Attributes ---
RE_VAR_DECL = re.compile(
    r"^\s*(?:integer|real|double\s+precision|complex|logical|character|type(?!\s*is)|class(?!\s*is)|procedure)\b",
    re.IGNORECASE,
)

# Specific Attributes (Added for Phase 2 Density)
RE_COMMON = re.compile(r"^\s*common\b", re.IGNORECASE)
RE_EQUIVALENCE = re.compile(r"^\s*equivalence\b", re.IGNORECASE)
RE_DATA = re.compile(r"^\s*data\b", re.IGNORECASE)
RE_NAMELIST = re.compile(r"^\s*namelist\b", re.IGNORECASE)

RE_Keep_Atomic = re.compile(
    r"^\s*(?:allocatable|dimension|external|intent|intrinsic|optional|parameter|pointer|private|public|save|target|volatile|value|protected)\b",
    re.IGNORECASE,
)

# Grouped Pattern (For backward compatibility with scripts using RE_ATTR_SPEC)
# Includes protected, enumerator, and legacy attrs.
# General Attributes (Backward compatibility for inventory.py)
RE_ATTR_SPEC = re.compile(
    r"^\s*(?:allocatable|dimension|external|intent|intrinsic|optional|parameter|pointer|private|public|save|target|volatile|value|protected|enumerator|common|equivalence|data|namelist)\b",
    re.IGNORECASE,
)

# Module Specifications
RE_USE = re.compile(r"^\s*use\b", re.IGNORECASE)
RE_IMPORT = re.compile(r"^\s*import\b", re.IGNORECASE)
RE_IMPLICIT = re.compile(r"^\s*implicit\b", re.IGNORECASE)

# --- 4. Control Flow ---
RE_IF_BLOCK = re.compile(r"^\s*(?:(\w+)\s*:\s*)?if\s*\(.*\)\s*then\b", re.IGNORECASE)

# FIXED: Adjusted to capture 'DO', 'DO WHILE' and 'DOWHILE' (compact form)
# Logic: 'do' optionally followed by space+while or attached+while
# RE_DO_LOOP = re.compile(r"^\s*(?:(\w+)\s*:\s*)?do\b", re.IGNORECASE)
RE_DO_LOOP = re.compile(r"^\s*(?:(\w+)\s*:\s*)?do(?:\s*while)?\b", re.IGNORECASE)

RE_SELECT_CASE = re.compile(r"^\s*(?:(\w+)\s*:\s*)?select\s*(?:case|type)\b", re.IGNORECASE)
RE_ASSOCIATE = re.compile(r"^\s*(?:(\w+)\s*:\s*)?associate\b", re.IGNORECASE)
RE_BLOCK_CONST = re.compile(r"^\s*(?:(\w+)\s*:\s*)?block\b", re.IGNORECASE)
RE_CRITICAL = re.compile(r"^\s*(?:(\w+)\s*:\s*)?critical\b", re.IGNORECASE)

RE_WHERE_BLOCK = re.compile(r"^\s*where\s*\(.*\)\s*then\b", re.IGNORECASE)
RE_FORALL_BLOCK = re.compile(r"^\s*forall\s*\(.*\)\s*then\b", re.IGNORECASE)

# Single Line Statements
# 1. Arithmetic IF (strict legacy): IF (expr) label1, label2, label3
# Matches: IF (...) number, number, number
RE_ARITHMETIC_IF = re.compile(r"^\s*if\s*\(.*\)\s*\d+\s*,\s*\d+\s*,\s*\d+", re.IGNORECASE)

# 2. Logical IF Single (single statement): IF (expr) action
# Definition: Starts with IF, has parentheses, and does NOT end in THEN.
# IMPORTANT: This pattern also covers Arithmetic IF. In code logic, validate Arithmetic first.

# Stops matching when there is no space after the closing condition parenthesis.
# RE_IF_SINGLE = re.compile(r"^\s*if\s*\(.*\)\s+(?!then\b)", re.IGNORECASE)
# Pattern corrected to check lexical delimiters ( and ) which can appear without spaces
RE_IF_SINGLE = re.compile(r"^\s*if\s*\(.*\)\s*(?!then\b)", re.IGNORECASE)

# Alias for backward compatibility (if your inventory used this name):
RE_LOGICAL_IF_PREFIX = RE_IF_SINGLE

# Single-line versions of Where/Forall

# Stops matching when there is no space after the closing condition parenthesis.

# Stops matching when there is no space after the closing condition parenthesis.
# RE_WHERE_SINGLE = re.compile(r"^\s*where\s*\(.*\)\s+(?!then\b)", re.IGNORECASE)
# RE_FORALL_SINGLE = re.compile(r"^\s*forall\s*\(.*\)\s+(?!then\b)", re.IGNORECASE)

# Pattern corrected to check lexical delimiters ( and ) which can appear without spaces
# FIXED: Changed \s+ to \s* to accept WHERE(mask)A=B
RE_WHERE_SINGLE = re.compile(r"^\s*where\s*\(.*\)\s*(?!then\b)", re.IGNORECASE)
# FIXED: Changed \s+ to \s* to accept FORALL(i=1:n)A(i)=0
RE_FORALL_SINGLE = re.compile(r"^\s*forall\s*\(.*\)\s*(?!then\b)", re.IGNORECASE)

# --- 5. Closings and Structure (Spine) ---
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

# --- 6. Actions and Helpers ---
# Contains both ALLOCATE and DEALLOCATE in one pattern
# RE_ALLOCATE = re.compile(r"^\s*(?:de)?allocate\b", re.IGNORECASE)

# PROPOSAL (High reuse)
RE_ALLOCATE = re.compile(r"^\s*allocate\b", re.IGNORECASE)
RE_DEALLOCATE = re.compile(r"^\s*deallocate\b", re.IGNORECASE)

RE_POINTER_OP = re.compile(r"^\s*(?:nullify\b|.*=>)", re.IGNORECASE)

# FIXED: 'end file' and 'back space' can appear separated
# RE_IO = re.compile(r"^\s*(?:read|write|print|open|close|inquire|backspace|endfile|rewind|format)\b", re.IGNORECASE)
RE_IO = re.compile(
    r"^\s*(?:read|write|print|open|close|inquire|back\s*space|end\s*file|rewind|format)\b", re.IGNORECASE
)

RE_INCLUDE = re.compile(r"^\s*include\b", re.IGNORECASE)  # Important for inventory

# Transfer of Control

# FIXED: 'go to' separated is very common in F77. Added \s*
# RE_CONTROL = re.compile(r"^\s*(?:call|goto|return|stop|cycle|exit|continue|pause|entry)\b", re.IGNORECASE)
RE_CONTROL = re.compile(r"^\s*(?:call|go\s*to|return|stop|cycle|exit|continue|pause|entry)\b", re.IGNORECASE)

RE_PARAMETER = re.compile(r"^\s*parameter\s*\(", re.IGNORECASE)

# --- Helpers ---
# Useful for dependencies.py (detect function calls inside expressions)
# Note: This is complex and usually requires additional logic; kept simple here.
RE_FUNC_CALL_CANDIDATE = re.compile(r"(\w+)\s*\(", re.IGNORECASE)

# BACKWARD COMPATIBILITY INVENTORY.PY
# --- 5. Closings (Endings) ---
# Matches "END", "END IF", "END SUBROUTINE Name"
RE_END_GENERIC = re.compile(
    r"^\s*end(?:\s+|)(program|module|subroutine|function|interface|type|do|if|select|associate|block\s*data|block|critical|where|forall|enum)?(?:\s+(\w+))?\s*(!.*)?$",
    re.IGNORECASE,
)
