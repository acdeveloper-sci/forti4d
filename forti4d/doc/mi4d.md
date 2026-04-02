# MI4D: The 4-Dimensional Integral Model

## What is MI4D?

MI4D (Modelo Integral 4D) is a conceptual framework for static auditing of
Fortran source code. It proposes that a program is not a flat sequence of text,
but a **topological hyper-object** that exists simultaneously in four orthogonal
dimensions. A bug, a technical debt item, or a structural risk is defined as a
topological inconsistency — an invalid intersection between these dimensions.

This document maps the MI4D axes to the forti4d analysis pipeline. The full
formal specification is in `MI4D_Specification_Foundation_v2_7` (see
`workdoc_forti4d/theoretical_doc/`).

---

## The Four Axes

### Axis X — Physical Dimension (Storage Topology)

The material existence of code on disk. Organized as a strict containment
hierarchy: **Workspace → Path → Source File → Physical Line**.

- The atom of Axis X is the **physical line** (`L_phys`), identified by its
  local line number within a file.
- Each physical line also receives a **global coordinate** (`X_global`) —
  unique across the entire Workspace — assigned at analysis time.
- Axis X is **static and immutable** during analysis. It is agnostic to program
  logic. Two files are always disjoint sets of physical lines.

**forti4d coverage:** `reader_logical.py` resolves physical lines into logical
lines (handling continuation). `inventory.py` and `profiler.py` build the
physical map of the corpus (files, line ranges per unit).

---

### Axis Y — Logical Dimension (Executable Program Structure)

The **transformation of the fragmented physical space (X) into a continuous
logical flow (Y)**. Axis Y processes physical lines into logical lines
(`L_log`), resolves INCLUDE directives, and organizes the result into a
containment tree of program units.

The key structure is the **Traceability Map (ℳ)**: for every logical line
(`Seq_log`), ℳ records which physical lines compose it. This is the bridge
between the abstract model and the concrete source file — the inverse ℳ⁻¹
translates any detected inconsistency back to the exact file and line number
where a developer must intervene.

Axis Y also defines the **anatomy of a program unit**: the Specification Zone
(declarations), Execution Zone (executable statements), and Containment Zone
(CONTAINS). The "Sandwich Rule" — every construct has an explicit open and
close statement — governs structural integrity at this level.

**forti4d coverage:** `inventory.py` (unit tree, line ranges), `dependencies.py`
(call graph = inter-unit Y relationships), `profiler.py` (statement
classification within units), `sloc.py` (logical line counting per unit).

---

### Axis Z — Scope Dimension (Semantic Depth)

A **discrete ordinal scale** measuring the visibility and isolation of symbols.
Not a metric — a depth level:

| Level (Z) | Name | Description | Typical entities |
| :--- | :--- | :--- | :--- |
| 0 | Universal | Visible to the OS linker | External SUBROUTINEs, unnamed COMMON blocks |
| 1 | Interface | Public under contract (USE) | PUBLIC entities in MODULEs |
| 2 | Host (Owner) | Private to the unit, visible to children | Local variables of PROGRAM or MODULE |
| 3 | Contained (Inherited) | Internal sub-scope | Procedures after CONTAINS |
| 4 | Local (Ephemeral) | Maximum temporal privacy | Variables inside BLOCK…END BLOCK |

The dynamics of Axis Z follow a fluid analogy: **gravity** (Host Association —
symbols naturally "fall" from Z=2 to child scopes), **pumping** (Use Association
— USE forces symbols from Z=1 into Z=2), and **walls** (PRIVATE — blocks
symbols from reaching Z=1).

Every **Symbol** — the persistent semantic entity behind a name — lives in
Axis Z. Its identity is the pair `(name, scoping unit)`, not the name alone.
This is why two subroutines can have a local variable `I` that are completely
independent: same name, different Z coordinate.

**forti4d coverage:** `symbols.py` (variable/parameter/implicit declarations per
unit, Z=2–4), `derived_types.py` (TYPE definitions = named scoping units),
`equivalences.py` (EQUIVALENCE aliasing — a Z-level anomaly), `common_blocks.py`
(Z=0 coupling via COMMON).

---

### Axis T — State Dimension (Symbol Lifetime)

The **evolution of each symbol's validity** along the execution trajectory
(Control Flow Graph — CFG). Axis T answers the question: *at this point in the
program, is this variable's value trustworthy?*

Each symbol, at every point `Seq_log`, holds one of four states:

| State | Symbol | Meaning |
| :--- | :--- | :--- |
| Undefined | Ω | Memory allocated but value indeterminate. Reading here is a critical error. |
| Defined | Δ | The symbol holds a valid, explicitly assigned value. |
| Static/Saved | Σ | Value persists across calls (SAVE attribute or initialized in declaration). |
| Dead/Deallocated | † | Out of scope or explicitly freed (DEALLOCATE). |

The trajectory of a symbol S is the function `τ_S : Seq_log → {Ω, Δ, Σ, †}`.
A **topological inconsistency** is any point 4D `(X_global, Seq_log, Z, τ_S)`
where the state is incompatible with the operation performed — for example,
reading a symbol in state Ω, or writing to an INTENT(IN) argument.

When a branch construct (IF, SELECT CASE) splits a trajectory, both paths may
produce different states. If one branch leaves a symbol in Ω and another in Δ,
the merge point produces an ambiguous state (Ω|Δ) — the basis for detecting
*Conditional Define* errors.

**forti4d coverage (partial):** `reachability.py` detects the extreme case of
Ω for entire units (dead code — units never reached from any entry point).
`complexity.py` measures CFG branching depth (McCabe CC) without tracking
symbol states. Full Axis T analysis (Use Before Define, Conditional Define,
INTENT violations) is planned for a future release.

---

## The Six Projection Planes

Two axes combined produce a **projection plane** — a 2D view that reveals a
specific category of inconsistencies:

| Plane | Axes | What it reveals | forti4d coverage |
| :--- | :--- | :--- | :--- |
| XY | Physical × Logical | INCLUDE chains, fragmentation, traceability map | `profiler.py` (audit CSVs), `reader_logical.py` |
| YZ | Logical × Scope | Shadowing, implicit typing (Phantom Scope), Privacy Leak | `symbols.py` (`Implicit_None`), `cross_analysis.py` |
| XZ | Physical × Scope | Orphan modules, dead definitions at file level | `reachability.py`, `structure_analysis.py` |
| YT | Logical × State | Use Before Define, Conditional Define, Post-Deallocation | `complexity.py` (CFG structure only) — partial |
| XT | Physical × State | Dead code, Spurious SAVE | `reachability.py` — partial |
| ZT | Scope × State | SAVE violations, INTENT(IN/OUT) inconsistencies, global mutable state | `symbols.py` (attributes only) — partial |

---

## Pipeline Stage Mapping

The MI4D specification defines five internal analysis stages (E1–E5). The
forti4d pipeline maps to these stages as follows:

| MI4D Stage | Component | Axis built | forti4d scripts |
| :--- | :--- | :--- | :--- |
| E1 | PhysicalManager | X | `reader_logical.py`, `inventory.py` |
| E2 | StructuralParser | Y | `inventory.py`, `dependencies.py`, `profiler.py` |
| E3 | LexerDML | sub-plane (x′, y′) | `profiler.py` (statement classification) |
| E4 | ScopeManager | Z | `symbols.py`, `derived_types.py`, `equivalences.py`, `common_blocks.py` |
| E5 | FlowAnalyzer | T | `reachability.py`, `complexity.py` (partial) |

Supporting and reporting scripts (`sloc.py`, `clones.py`, `consolidate.py`,
`cross_analysis.py`, `structure_analysis.py`, `prioritization.py`,
`visual_graph.py`, `html_report.py`) operate on the outputs of E1–E5 to produce
structured reports and metrics. They do not extend the model axes directly but
provide projections, aggregations, and risk scoring derived from the 4D geometry.

---

## Implementation Status

forti4d v0.7 implements Axes X, Y, and the foundational layer of Z. Axis T is
partially addressed through dead-code detection (reachability) and CFG
complexity measurement. Full symbol-state tracking (Use Before Define, INTENT
validation, Conditional Define detection) is the primary scope of future
development.

| Axis | Status in v0.7 |
| :--- | :--- |
| X — Physical | Complete |
| Y — Structural | Complete |
| Z — Scope | Foundational (declarations, visibility attributes, EQUIVALENCE, COMMON) |
| T — State | Partial (dead code + CFG depth; no symbol-state tracking) |
