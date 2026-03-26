# Interpreting the Results

## Start Here: `reporte_priorizacion.csv`

The prioritization report ranks every program unit by composite migration
risk. Open it first to orient the analysis — it tells you *where to look*
before you dig into the detail reports.

For deeper analysis, `reporte_consolidado.csv` is the primary analysis surface.
It has one row per program unit and 34 columns covering size, complexity,
coupling, density, reachability, COMMON block usage, and E4 symbol summary
(variable counts, formal arguments, IMPLICIT NONE status, EQUIVALENCE aliasing).

Open it in a spreadsheet. Sort, filter, and combine columns. The sections
below explain what combinations reveal.

---

## Size Metrics

### LOC vs SLOC_neto

`LOC` is the raw physical line count of the unit's line range. It includes
blanks, comments, and continuation lines. It overstates the actual amount
of code.

`SLOC_neto` counts only logical statements — the actual number of
instructions the compiler sees. Use this for comparing unit sizes.

**`Pct_Comentario`** measures documentation density. A unit with
`SLOC_neto > 50` and `Pct_Comentario < 5%` is likely underdocumented.

```
LOC = SLOC_neto + N_Blancos + N_Comentarios + N_Continuacion
```

### Interpreting SLOC_neto ranges

| Range | Typical interpretation |
| :--- | :--- |
| 1 – 30 | Small routine, easy to understand |
| 31 – 150 | Medium — manageable |
| 151 – 500 | Large — review complexity and coupling |
| > 500 | Very large — strong refactoring candidate |

---

## Complexity

### CC alone is not enough

McCabe CC counts decision points, but the same CC value means very different
things at different sizes. A unit with CC=50 and 1000 statements is much
less risky than one with CC=50 and 80 statements.

### CC_SLOC: complexity density

`CC_SLOC = CC / SLOC_neto` — cyclomatic complexity per logical statement.

This is the metric to sort by when looking for *dense* logic:

| CC_SLOC | Interpretation |
| :--- | :--- |
| < 0.05 | Low density — mostly sequential code |
| 0.05 – 0.15 | Normal |
| 0.15 – 0.30 | Dense conditional logic |
| > 0.30 | Very dense — hard to follow and test |

### CC can be misleading: the dispatcher pattern

A unit with a very high CC but structured as a large `SELECT CASE` / `IF-ELSE IF`
chain acting as a language or command dispatcher is mechanically complex
but structurally simple — each branch is independent. Confirm by checking
`Pct_Control` in the density columns: if the control percentage dominates
and `Fan_Out` is low, the unit is a dispatcher, not a tangled algorithm.

---

## Coupling

### Fan-In: reuse and fragility

`Fan_In` counts how many other units call or USE this one. High Fan-In means:

- The unit is widely reused — good
- Any change to it propagates risk to many callers — bad

Units with high Fan-In are the *core* of the system. Changes there require
thorough testing.

| Fan-In | Risk level |
| :--- | :--- |
| 0 | Not called — dead code or entry point |
| 1 – 4 | Low coupling |
| 5 – 9 | Moderate — changes need careful review |
| ≥ 10 | High — treat as core infrastructure |

### Fan-Out: dependency breadth

`Fan_Out` counts how many distinct units this one calls or USEs. High Fan-Out
means the unit coordinates many parts of the system — it is an orchestrator.
Orchestrators are hard to test in isolation.

### The dangerous combination

High CC + high Fan-In = **core knot**: complex logic that many callers depend on.
This is the highest-priority refactoring target.

Sort `reporte_consolidado.csv` by `CC × Fan_In` (computed column in a
spreadsheet) to surface these.

---

## Reachability

### `Estado` column

| Value | Meaning |
| :--- | :--- |
| `ENTRADA` | Entry point — a PROGRAM or IMPLICIT-MAIN unit |
| `ALCANZABLE` | Reachable from at least one entry point |
| `NO_ALCANZABLE` | Not reachable from any entry point — dead code candidate |

### Before deleting NO_ALCANZABLE units

Not all unreachable units are waste. Common false-positive patterns:

- **Alternative versions:** files named `*_old.f90`, `*_ori.f90`, or
  `* - Copie.f90` are often inactive copies kept as fallback. Confirm
  with `dep_00_ambiguedades.csv` — if the unit name also appears in another
  file, it is a duplicate, not necessarily dead.
- **Utility executables:** small programs in the same directory that are
  compiled separately and have no caller in the corpus. Check
  `analisis_nodos_criticos.csv` — if the file is classified as `ISLA`,
  this is likely the case.
- **External entry points:** units called from a Makefile, from a shell
  script, or from a test harness outside the corpus.

---

## Statement Density Profile

The four percentage columns (`Pct_Calculo`, `Pct_Control`, `Pct_IO`,
`Pct_Legacy`) describe *what kind of work* a unit does.

| Profile | Typical pattern |
| :--- | :--- |
| High `Pct_Calculo` | Pure algorithm — good candidate for direct migration |
| High `Pct_Control` | Logic-heavy dispatcher or workflow coordinator |
| High `Pct_IO` | I/O-bound routine — consider replacing with library calls |
| High `Pct_Legacy` | Heavy use of COMMON, GOTO, EQUIVALENCE — refactor first |

These percentages feed directly into the `ICM` and `IVC` indices computed
by `analisis_cruzado.py`, which translates them into a recommended
migration strategy (`reporte_estrategia_migracion.csv`).

---

## COMMON Blocks

If `N_Common_Bloques > 0`, the unit shares global data with other units
through F77 COMMON blocks. Check `common_acoplamiento.csv` for the risk
level of each block.

COMMON blocks are implicit global variables: changing the size, type, or
order of variables in one unit's COMMON declaration silently breaks all
other units that reference the same block. Units with `Riesgo = ALTO`
in `common_acoplamiento.csv` should be refactored to use explicit interfaces
(module variables or subroutine arguments) before any other change.

---

## E4 Symbol Risk Signals

Three columns in `reporte_consolidado.csv` (and `reporte_priorizacion.csv`)
flag scope-level risk factors that complicate safe migration:

### `Implicit_None`

`SI` — the unit has `IMPLICIT NONE`. All variables are explicitly typed.
Migration is safer.

`NO` or blank — the unit relies on Fortran's default typing (variables
starting with I–N are INTEGER, all others REAL). Undeclared variables may
exist. Any rename or extraction operation can silently change types.

### `Tiene_Equiv`

`SI` — the unit contains `EQUIVALENCE` statements. Two or more variables
share the same memory address. This creates implicit aliasing that breaks
type inference and makes it unsafe to rename, extract, or reorder variables
without full alias analysis.

Check `equivalencias.csv` for the full aliasing groups.

### `N_Vars_Locales` / `N_Args_Formales`

High `N_Vars_Locales` combined with low `Pct_Comentario` indicates a unit
with many undocumented variables — high cognitive load for migration.

High `N_Args_Formales` increases interface complexity. Units with many
arguments and no `IMPLICIT NONE` are the hardest to type-annotate correctly.

---

## Using the Call Graph Alongside the CSV

The graph (`grafo_visual.py`) answers questions the CSV cannot:

- **Who calls this unit?** Find the node, follow incoming edges.
- **What does this entry point depend on?** Run with `--entry <name>` — the
  resulting subgraph shows the full transitive dependency tree of that
  executable.
- **Do two executables share dependencies?** Run with `--entry ep1 ep2` —
  yellow nodes are shared; they are the integration risk between the two
  programs.

---

## Prioritization: Putting It Together

`reporte_priorizacion.csv` (from `priorizacion.py`) provides a ranked list
directly. Units are sorted by composite score across five signals: CC,
Fan-In, legacy density, clone state, and E4 scope risk (no IMPLICIT NONE +
EQUIVALENCE). Use this as the starting point for migration planning.

For manual analysis, the following sequence surfaces the same issues:

1. **Dead code first:** Filter `Estado = NO_ALCANZABLE`. Confirm each case
   (see notes above). Remove confirmed dead code to reduce the analysis
   surface before anything else.

2. **Core knots:** Sort by `CC × Fan_In` descending. Units at the top are
   complex *and* widely called — the highest change-risk items.

3. **Scope risk:** Filter `Implicit_None ≠ SI` or `Tiene_Equiv = SI`.
   These units carry hidden type ambiguity or memory aliasing — address
   before any refactoring.

4. **Undocumented large units:** Filter `SLOC_neto > 100` and
   `Pct_Comentario < 5%`. These are maintenance liabilities — hard to
   understand without documentation.

5. **Legacy hotspots:** Filter `Pct_Legacy > 10%` and `Fan_In > 3`.
   COMMON/GOTO/EQUIVALENCE code that is also widely called is the
   riskiest to modify.

6. **Isolated algorithms:** Filter `Pct_Calculo > 50%` and `Fan_In < 3`
   and `Pct_Legacy < 5%` and `Implicit_None = SI`. These are the easiest
   units to extract, test, and migrate — start here if the goal is
   modernization.

`reporte_estrategia_migracion.csv` (from `analisis_cruzado.py`) applies a
rule-based approach automatically and provides a recommended action for
every unit.
