# * NOTE
# * THIS CODE ORIGINATED FROM AN EARLIER PROJECT LOCATED AT
# * forttools-dev\hbf\hbf-core
# * This file corresponds to
# *   hbf\hbf-core\src\hbf\core\lines
# *
# * The project consists of two independent libraries,
# * one the base and the other the tools:
# *   hbf\hbf-core\src\hbf\core
# *   hbf\hbf-core\src\hbf\tools
# *
# * reader.py was taken as the base for this file, placing the LogicalLine dataclass inside,
# * because this Fortran source code file reader is already well-polished
# * for writing scripts that do direct and reliable tasks without much architectural
# * scaffolding as in that original project.
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
    Splits text at the symbol only if it is not inside quotes.
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
    Separates code and comments respecting strings.
    """
    code, comment = split_by_symbol_outof_quotation(line, comment_char)
    return code, comment


def remove_continuation_chars(line: str, format_type: str) -> str:
    """
    Removes continuation characters according to format.
    In 'free', strips the trailing '&' (and leading '&' if present).
    In 'fixed', returns content starting from column 7 (stripping col 6).
    """
    if format_type == "free":
        code, _ = strip_inline_comment(line)
        code = code.rstrip()
        # Strip trailing ampersand
        if code.endswith("&"):
            code = code[:-1].rstrip()
        # Strip leading ampersand (optional in F90+ but valid)
        if code.strip().startswith("&"):
            code = code.strip()[1:].strip()
        return code

    elif format_type == "fixed":
        # If the line is long enough, real code starts at col 7 (index 6)
        # Column 6 (index 5) is the continuation marker and MUST be ignored.
        if len(line) >= 6:
            return line[6:]
        return ""  # Line too short to contain code in fixed format

    return line


def has_continuation_char(line: str, format_type: str) -> bool:
    """
    Detects whether the current line requests continuation on the NEXT line (F90 '&' style).
    """
    if format_type == "free":
        code, _ = strip_inline_comment(line)
        return code.rstrip().endswith("&")
    elif format_type == "fixed":
        # In fixed format, the current line NEVER says "I will continue".
        # It is the next line that says "I am a continuation".
        return False
    return False


def extract_label_from_line(line: str, format_type: str) -> Optional[str]:
    """
    Extracts the numeric label from the statement.
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


# FORMAT DETECTION


def detect_fortran_format(filepath: str) -> str:
    """
    Heuristically detects fixed-form vs free-form by scanning the first 50
    non-blank lines. Returns 'free' on first match, 'fixed' if none found.

    Free-form indicators (any one is sufficient):
    - '!' anywhere in the line (not valid in strict F77)
    - Alphabetic character in columns 1-5 (F77 only allows digits/spaces
      there, except C/c/* in column 1 for comments)
    - '::' attribute separator (F90+)
    - '&' at end of code portion (F90 line continuation)
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= 50:
                    break
                raw = line.rstrip("\n")
                if not raw.strip():
                    continue
                first_char = raw[0] if raw else ""
                if first_char.upper() in ("C", "*"):
                    continue  # classic F77 comment — not indicative
                if "!" in raw:
                    return "free"
                label_field = raw[:5] if len(raw) >= 5 else raw
                if any(c.isalpha() for c in label_field):
                    return "free"
                if "::" in raw:
                    return "free"
                if raw.split("!")[0].rstrip().endswith("&"):
                    return "free"
    except Exception:
        pass
    return "fixed"


# LOGICAL LINE READER (CORE LOGIC)


def read_logical_lines(filepath: str) -> List[LogicalLine]:
    """
    Reads a Fortran file and returns a list of LogicalLine.
    Implements "Deferred Registration" to robustly handle line continuation
    in Fixed (F77) and Free (F90) formats.
    """
    path_obj = Path(filepath)

    # Format detection: extension-based initial guess, refined by content heuristic.
    # Scientific code frequently uses .f/.F extensions with free-form F90+ syntax,
    # or .f90 with fixed-form F77 syntax. Content takes precedence over extension.
    is_fixed_format = path_obj.suffix.lower() in (".f", ".for", ".f77")
    if is_fixed_format:
        if detect_fortran_format(filepath) == "free":
            is_fixed_format = False
    else:
        # .f90/.f95 etc. — check if file actually uses fixed-form syntax
        if detect_fortran_format(filepath) == "fixed":
            is_fixed_format = True

    format_type = "fixed" if is_fixed_format else "free"

    vlines: List[LogicalLine] = []

    # Buffer State (Logical Line under construction)
    buffer_content: List[str] = []
    buffer_raw_lines: List[Tuple[int, str]] = []
    logical_start_num: Optional[int] = None

    # Continuation State (Persists between iterations)
    # Indicates whether the PREVIOUS line ended with '&' (requesting continuation)
    expecting_f90_continuation = False

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            raw_physical_line = line.rstrip("\n")

            # A) F77 marker detection (Column 6)
            #    Must be done before cleaning, because it determines code vs. continuation.
            is_f77_continuation_mark = False
            if is_fixed_format and len(raw_physical_line) >= 6:
                if raw_physical_line[5] not in (" ", "0"):
                    is_f77_continuation_mark = True

            # --- 1. Comment Detection (Pre-filter) ---
            # Identify whether this is a "pure" comment (entire line)

            # B) Comment Detection (Robust Hybrid Logic)
            is_logical_comment = False

            if is_fixed_format:
                # Case 1: Classic comment in Column 1
                if len(raw_physical_line) > 0 and raw_physical_line[0].upper() in ("C", "*", "!"):
                    is_logical_comment = True
                # Case 2: Modern indented comment (! anywhere)
                # NOTE: Only if NOT a continuation line (Col 6 empty)
                elif not is_f77_continuation_mark:
                    # Strip margins (cols 1-6) and look for !
                    content_part = raw_physical_line[6:] if len(raw_physical_line) >= 6 else ""
                    if content_part.strip().startswith("!"):
                        is_logical_comment = True
            else:
                # Free Format
                code_part, comment_part = strip_inline_comment(raw_physical_line)
                if not code_part.strip() and comment_part.strip():
                    is_logical_comment = True

            # C) Ignore completely empty lines (no code or comment)
            # if not raw_physical_line.strip():
            #     continue

            # C) Blank Line Detection
            # We define "blank" as a line with no visible characters
            is_blank_line = not raw_physical_line.strip()

            # -----------------------------------------------------------------
            # 2. HANDLING NON-EXECUTABLE LINES (COMMENTS AND BLANK) AND FLUSHING
            # -----------------------------------------------------------------
            if is_logical_comment or is_blank_line:
                # 2.1 CONDITIONAL FLUSH
                # If there is a pending buffer and we are NOT expecting explicit continuation (F90 &),
                # this intermediate line confirms the previous statement ended.
                # Note: If expecting_f90_continuation is True, we do NOT flush; the blank/comment line
                # is inserted "in the middle" of the logical construct (interleaved).

                if buffer_content and not expecting_f90_continuation:
                    # FLUSH PREVIOUS BUFFER
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
                    # Note: We do NOT reset expecting_f90_continuation because a comment
                    # should NOT break a pending continuation (if any).

                # 2.2 REGISTER CURRENT LINE
                # Registered faithfully.
                # - If comment: is_comment=True
                # - If blank: is_comment=False (It is whitespace; the classifier will say COMMENT or nothing)

                vlines.append(
                    LogicalLine(
                        start_line=line_num,
                        text=raw_physical_line,
                        label=None,
                        is_comment=is_logical_comment,
                        raw_lines=[(line_num, raw_physical_line)],
                    )
                )
                continue  # Move to the next line

            # 3. CODE LOGIC (ACCUMULATION)

            #    Continuation Signal Detection (Current Line)

            # A) F90 Signal: Ampersand at end
            # (This signal looks "forward": I request that the next line continues me)
            # Detect whether THIS line requests F90 continuation (Ampersand at end)
            current_line_requests_continuation = has_continuation_char(raw_physical_line, format_type)

            # Merge Decision
            # Should we merge this line into the existing buffer?
            # Only if there is an open buffer AND (it is F77 continuation OR the previous requested F90 continuation)
            should_merge = False
            if buffer_content:  # Can only be a continuation if something was started
                if is_f77_continuation_mark or expecting_f90_continuation:
                    should_merge = True

            # Action Execution
            # Content preparation
            processed_code = remove_continuation_chars(raw_physical_line, format_type)

            # Extra adjustment for Fixed: Strip first 6 columns if code
            # if is_fixed_format and len(processed_code) >= 6:
            #     processed_code = processed_code[6:]

            # Extra cleanup: Remove inline comments that remain
            processed_code = strip_inline_comment(processed_code)[0].strip()

            if should_merge:
                # ACCUMULATE into existing buffer
                buffer_content.append(processed_code.strip())
                buffer_raw_lines.append((line_num, raw_physical_line))

            else:
                # BREAK (FLUSH): Save previous and start new

                # a) If there was a previous buffer, close and save it
                if buffer_content:
                    final_text = " ".join(buffer_content)

                    # Label from the first physical line of the group
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

                # b) Start new buffer with the current line
                if processed_code:  # Only if code remains (extra protection)
                    logical_start_num = line_num
                    buffer_content = [processed_code.strip()]
                    buffer_raw_lines = [(line_num, raw_physical_line)]
                else:
                    # If nothing remained after cleaning (rare, but possible if strip failed above), reset
                    buffer_content = []
                    buffer_raw_lines = []

            # 5. Update State for the next iteration
            # The "expectation" for the next line depends on whether THIS line ended in &
            expecting_f90_continuation = current_line_requests_continuation

    # --- FINAL FLUSH (At end of file) ---
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
