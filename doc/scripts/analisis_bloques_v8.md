# analisis_bloques_v8.py

## Purpose

Diagnostic tool for block topology analysis. Takes one `audit/*_DEBUG.csv`
file at a time and prints a hierarchical tree of control-flow block nesting
(IF/DO/SELECT/WHERE/FORALL depth) per unit in that file.

Unlike all other scripts in the toolkit, this one **prints to stdout only**
and takes a single file as a command-line argument. It is not a batch pipeline
script.

---

## Usage

```bash
# Analyze one file
python analisis_bloques_v8.py audit/geolec.f90_DEBUG.csv

# Save output to bloques/
python analisis_bloques_v8.py audit/geolec.f90_DEBUG.csv > bloques/geolec.f90_bloques.txt

# Process all files in batch (bash)
for f in audit/*_DEBUG.csv; do
    python analisis_bloques_v8.py "$f" > bloques/$(basename "$f" _DEBUG.csv)_bloques.txt
done
```

---

## Inputs

- A single `audit/<filename>_DEBUG.csv` (passed as `sys.argv[1]`)
- `reporte_inventario.csv` (loaded via `cargar_inventario()` to get unit line ranges)

---

## Output (stdout)

A text tree showing block topology per unit. Example:

```
ANÁLISIS ESTRUCTURAL V10: geolec.f90
================================================================================

>> UNIDAD: GEOLEC (SUBROUTINE)
    1-   45 |  0 |                              IF_CONSTRUCT        | IF_CONSTRUCT:12, ...
    45-  120 |  1 | |_                          DO_CONSTRUCT        | DO_CONSTRUCT:8, ...
   120-  145 |  2 | | |_                        SELECT_CONSTRUCT    | CASE_STMT:5, ...
```

Columns: `start_line - end_line | depth | tree_indent type | top_3_kinds`

---

## Constructs Tracked

**Block openers:** `IF_CONSTRUCT`, `DO_CONSTRUCT`, `DO_WHILE_CONSTRUCT`,
`SELECT_CONSTRUCT`, `SELECT_TYPE_CONSTRUCT`, `BLOCK_CONSTRUCT`,
`INTERFACE_BLOCK`, `TYPE_DEFINITION`, `ASSOCIATE_CONSTRUCT`,
`FORALL_CONSTRUCT`, `WHERE_CONSTRUCT`, `CRITICAL_CONSTRUCT`

**Block closers:** `END_IF_STMT`, `END_DO_STMT`, `END_SELECT_STMT`,
`END_BLOCK_STMT`, `END_ASSOCIATE_STMT`, `END_FORALL_STMT`, `END_WHERE_STMT`,
`END_CRITICAL_STMT`, `END_INTERFACE_STMT`, `END_TYPE_STMT`,
`END_FUNCTION_STMT`, `END_SUBROUTINE_STMT`, `END_MODULE_STMT`,
`END_PROGRAM_STMT`

---

## Notes

- Requires `perfilador.py` to have been run first (reads from `audit/`).
- Output files are stored in `results/bloques/` after manual redirection.
  Migration of this path to `results/` is planned.
