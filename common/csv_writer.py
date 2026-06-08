#!/usr/bin/env python3
"""
CSV Writer — Intelligent header management (same contract as pnpwls).
Appends value rows; writes header only when file is new or format changed.
"""

from pathlib import Path
from typing import List


def write_csv_row(
    csv_file: Path,
    header_row: List[str],
    value_row: List[str],
    verbose: bool = True,
) -> bool:
    """
    Write one data row to a CSV.  Header is written only when:
      - File does not exist yet, OR
      - Existing file is empty, OR
      - Existing header column count differs from header_row length.

    Args:
        csv_file:   Destination path (parents created automatically).
        header_row: Column names.
        value_row:  Values — must be same length as header_row.
        verbose:    Print a message when header is written.

    Returns:
        True on success, False on any error.
    """
    if len(header_row) != len(value_row):
        raise ValueError(
            f"Header/value length mismatch: "
            f"header={len(header_row)}, values={len(value_row)}"
        )

    csv_file = Path(csv_file)
    csv_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        file_exists = csv_file.exists()
        write_header = not file_exists

        if file_exists:
            with open(csv_file, "r") as f:
                lines = [l for l in f.readlines() if l.strip()]
            if not lines:
                write_header = True
            else:
                # Find most recent header (last line starting with a non-numeric)
                for line in reversed(lines):
                    first_col = line.split(",")[0].strip().strip('"')
                    try:
                        float(first_col)
                    except ValueError:
                        # It's a header row; compare column count
                        existing_cols = len(line.strip().split(","))
                        if existing_cols != len(header_row):
                            write_header = True
                            if verbose:
                                print(
                                    f"[csv_writer] Column count changed "
                                    f"({existing_cols} -> {len(header_row)}), "
                                    f"writing new header."
                                )
                        break

        with open(csv_file, "a") as f:
            if write_header:
                if verbose:
                    print(f"[csv_writer] Writing header to {csv_file}")
                f.write(",".join(str(h) for h in header_row) + "\n")
            f.write(",".join(str(v) for v in value_row) + "\n")

        return True

    except Exception as exc:
        print(f"[csv_writer] ERROR writing {csv_file}: {exc}")
        return False
