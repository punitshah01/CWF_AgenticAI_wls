#!/usr/bin/env python3
"""
misc/read_emon_csv.py — Extract numeric values from EMON socket/core view CSVs.

Reads an EMON EDP summary CSV (socket view or core view), skips the header row,
and prints all numeric values comma-separated on one line — matching the format
expected by the runner's CSV parser.

Usage:
  python3 misc/read_emon_csv.py <emon_csv_file>
  python3 misc/read_emon_csv.py emon__mpp_socket_view_summary.csv
  python3 misc/read_emon_csv.py emon__mpp_core_view_summary.csv
"""

import sys
from pathlib import Path


def extract_values(csv_path: Path) -> str:
    """Parse an EMON EDP CSV and return comma-separated numeric values."""
    lines = [ln.strip() for ln in csv_path.read_text().splitlines() if ln.strip()]
    if len(lines) < 2:
        return ""

    values = []
    for line in lines[1:]:          # skip header
        for field in line.split(",")[1:]:   # skip first column (row label)
            field = field.strip()
            if not field:
                continue
            try:
                num = float(field)
                if num >= 1:
                    values.append(f"{num:.2f}")
                else:
                    values.append(f"{num:.5f}")
            except ValueError:
                pass   # skip non-numeric cells

    return ",".join(values)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <emon_csv_file>", file=sys.stderr)
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"[ERROR] File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    print(extract_values(csv_path))


if __name__ == "__main__":
    main()
