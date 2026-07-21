# reader_logical.py

## Purpose

Core Fortran line reader. Merges physical lines into logical lines, handling
continuation in both F77 fixed-form (column 6 marker) and F90 free-form
(`&` at end of line). Identifies comment lines and blank lines.

Not run directly. Imported by `inventory.py`, `profiler.py`, and `sloc.py`.

---

## API

### `read_logical_lines(filepath) → list[LogicalLine]`

Reads a Fortran source file and returns a list of `LogicalLine` objects.

**Format detection:** starts from the file extension, then refined by
content inspection via `detect_fortran_format()`.

- Extension hint — fixed-form: `.f`, `.for`, `.f77` / free-form: `.f90`,
  `.f95`, `.f03`, and all others.
- Content override: the first 50 non-blank lines are scanned for free-form
  indicators (`!` inline comment, alphabetic characters in columns 1–5,
  `::` declaration separator, `&` continuation at end of line). Any of these
  overrides the extension hint in either direction.

This handles scientific HPC code that uses `.F` (preprocessed fixed-form
extension) but is written in free-form F90+ syntax.

### `detect_fortran_format(filepath) → str`

Heuristic function that returns `"free"` or `"fixed"` based on content
inspection of the first 50 non-blank lines. Called internally by
`read_logical_lines`; not typically used directly.

### `LogicalLine` fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `start_line` | `int` | Physical line number where this logical line begins |
| `text` | `str` | Merged text of all physical lines (continuation markers removed, inline comments stripped) |
| `label` | `str \| None` | Numeric statement label if present (e.g. `100`) |
| `is_comment` | `bool` | `True` if this is a pure comment line |
| `raw_lines` | `list[(int, str)]` | List of `(line_number, raw_text)` for every physical line composing this logical line |

---

## Continuation Handling

**F90 free-form:** The `&` at the end of a line signals that the next line
continues the statement. An optional `&` at the start of the continuation line
is also consumed.

**F77 fixed-form:** Any non-space, non-zero character in column 6 (index 5)
marks the line as a continuation of the previous statement.

**Comments and blanks within continuations:** A comment or blank line
encountered while a free-form continuation is pending does not flush the
current statement buffer — it is registered as its own `LogicalLine` and
the buffer remains open.

---

## Notes

- Encoding: files are opened with `errors="ignore"` to handle non-UTF-8 bytes
  in legacy source files without crashing.
- Inline comments (`!` outside string literals) are stripped from `text` but
  are preserved in `raw_lines`.
- A blank line produces a `LogicalLine` with `is_comment=False` and
  `text=""` (empty after strip).
