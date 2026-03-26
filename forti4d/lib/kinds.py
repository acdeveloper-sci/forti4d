from enum import Enum


class StatementKind(str, Enum):
    # --- PROGRAM UNITS (Nivel Superior) ---
    PROGRAM_UNIT = "program_unit"  # PROGRAM
    MODULE_UNIT = "module_unit"  # MODULE
    SUBROUTINE_UNIT = "subroutine_unit"  # SUBROUTINE
    FUNCTION_UNIT = "function_unit"  # FUNCTION
    BLOCK_DATA_UNIT = "block_data_unit"  # BLOCK DATA

    # --- SCOPING UNITS & DEFINITIONS (Definiciones) ---
    INTERFACE_BLOCK = "interface_block"  # INTERFACE
    TYPE_DEFINITION = "type_definition"  # TYPE (::)
    ENUM_DEF = "enum_definition"  # ENUM, BIND(C)

    # --- DECLARATIONS & SPECIFICATIONS ---
    VAR_DECLARATION = "var_declaration"  # INTEGER, REAL, LOGICAL...
    IMPLICIT_STMT = "implicit_stmt"  # IMPLICIT
    USE_STMT = "use_stmt"  # USE
    IMPORT_STMT = "import_stmt"  # IMPORT
    PARAMETER_STMT = "parameter_stmt"  # PARAMETER

    # --- LEGACY DATA MANAGEMENT ---
    COMMON_STMT = "common_stmt"  # COMMON /block/
    EQUIVALENCE_STMT = "equivalence_stmt"  # EQUIVALENCE (a,b)
    DATA_STMT = "data_stmt"  # DATA a /1/
    NAMELIST_STMT = "namelist_stmt"  # NAMELIST /group/
    INCLUDE_STMT = "include_stmt"  # INCLUDE 'file'

    # --- EXECUTABLE CONSTRUCTS (Bloques) ---
    IF_CONSTRUCT = "if_construct"  # IF (...) THEN
    DO_CONSTRUCT = "do_construct"  # DO
    DO_WHILE_CONSTRUCT = "do_while_construct"
    SELECT_CONSTRUCT = "select_construct"  # SELECT CASE / TYPE
    ASSOCIATE_CONSTRUCT = "associate_construct"  # ASSOCIATE
    BLOCK_CONSTRUCT = "block_construct"  # BLOCK
    CRITICAL_CONSTRUCT = "critical_construct"  # CRITICAL
    WHERE_CONSTRUCT = "where_construct"  # WHERE (...) Bloque
    FORALL_CONSTRUCT = "forall_construct"  # FORALL (...) Bloque

    # --- SPINE (Divisiones estructurales) ---
    CONTAINS_STMT = "contains_stmt"  # CONTAINS
    ELSE_STMT = "else_stmt"  # ELSE / ELSE IF / ELSEWHERE
    CASE_STMT = "case_stmt"  # CASE / CLASS IS / TYPE IS
    END_BLOCK_STMT = "end_block_stmt"  # Cualquier END explícito o implícito

    # --- ACTION STATEMENTS ---
    ALLOCATION_STMT = "allocation_stmt"  # ALLOCATE / DEALLOCATE
    POINTER_ACTION = "pointer_action"  # NULLIFY / =>
    IO_STMT = "io_stmt"  # READ, WRITE, PRINT, OPEN
    CONTROL_STMT = "control_stmt"  # CALL, GOTO, RETURN, STOP, CYCLE, EXIT, CONTINUE
    ASSIGNMENT_STMT = "assignment_stmt"  # a = b + c (Detectado por lógica, no regex directa)

    # --- UNKNOWN ---
    UNKNOWN = "unknown"

    # =====================================================

    ENTRY_STMT = "entry_stmt"  # ENTRY

    # --- SIMPLE STATEMENTS ---
    ACCESS_STMT = "access_stmt"  # PUBLIC / PRIVATE / PROTECTED (Sentencias)
    LOGICAL_IF_STMT = "logical_if_stmt"  # IF (x) y=1
    PREPROCESSOR_DIR = "preprocessor_dir"  # #ifdef, etc.
    COMMENT = "comment"  # Comentarios
    BLANK_LINE = "blank_line"  # Líneas en blanco o vacías

    # --- ENUM STRUCTURE ---
    END_ENUM_DEF = "end_enum_def"  # END ENUM
    ENUMERATOR_STMT = "enumerator_stmt"  # ENUMERATOR :: ...

    # --- CONTROL DE FLUJO ---
    GOTO_STMT = "goto_stmt"  # GO TO (Asignado/Computado/Incondicional)
    RETURN_STMT = "return_stmt"  # RETURN
    EXIT_STMT = "exit_stmt"  # EXIT
    CYCLE_STMT = "cycle_stmt"  # CYCLE
    STOP_STMT = "stop_stmt"  # STOP, ERROR STOP
    PAUSE_STMT = "pause_stmt"  # PAUSE
    CONTINUE_STMT = "continue_stmt"  # CONTINUE

    # --- ENTRADA / SALIDA (I/O) ---
    READ_STMT = "read_stmt"
    WRITE_STMT = "write_stmt"
    PRINT_STMT = "print_stmt"
    OPEN_STMT = "open_stmt"
    CLOSE_STMT = "close_stmt"
    INQUIRE_STMT = "inquire_stmt"
    FORMAT_STMT = "format_stmt"  # FORMAT (Es especial, suele ir etiquetado)
    FILE_POS_STMT = "file_position_stmt"  # REWIND / BACKSPACE / ENDFILE / FLUSH / WAIT


# =============================================================================
# TAXONOMÍA (GRUPOS) - AQUÍ ESTÁ LA MAGIA
# =============================================================================

# Grupo: Unidades Principales (Arquitectura)
PROGRAM_UNITS = {
    StatementKind.PROGRAM_UNIT,
    StatementKind.MODULE_UNIT,
    StatementKind.SUBROUTINE_UNIT,
    StatementKind.FUNCTION_UNIT,
    StatementKind.BLOCK_DATA_UNIT,
}

LEGACY_DATA = {
    StatementKind.COMMON_STMT,
    StatementKind.EQUIVALENCE_STMT,
    StatementKind.DATA_STMT,
    StatementKind.NAMELIST_STMT,
}

CALCULATION_ACTIONS = {
    StatementKind.ASSIGNMENT_STMT,
    StatementKind.WHERE_CONSTRUCT,
    StatementKind.FORALL_CONSTRUCT,
}

IO_ACTIONS = {
    StatementKind.IO_STMT,
}

# Grupo: Unidades de Alcance (Donde se definen variables locales)
SCOPING_UNITS = PROGRAM_UNITS | {
    StatementKind.INTERFACE_BLOCK,
    StatementKind.TYPE_DEFINITION,
    StatementKind.ENUM_DEF,
}

# Grupo: Constructos Ejecutables (Lógica anidable)
EXECUTABLE_CONSTRUCTS = {
    StatementKind.IF_CONSTRUCT,
    StatementKind.DO_CONSTRUCT,
    StatementKind.DO_WHILE_CONSTRUCT,
    StatementKind.SELECT_CONSTRUCT,
    StatementKind.ASSOCIATE_CONSTRUCT,
    StatementKind.BLOCK_CONSTRUCT,
    StatementKind.CRITICAL_CONSTRUCT,
    StatementKind.WHERE_CONSTRUCT,
    StatementKind.FORALL_CONSTRUCT,
}

# Grupo: Apertura de Bloque (Indentación +1)
BLOCK_OPENERS = SCOPING_UNITS | EXECUTABLE_CONSTRUCTS

# Grupo: Declaraciones (No ejecutables)
DECLARATION_STMTS = {
    StatementKind.VAR_DECLARATION,
    StatementKind.USE_STMT,
    StatementKind.IMPLICIT_STMT,
    StatementKind.ACCESS_STMT,
    StatementKind.FORMAT_STMT,
}
