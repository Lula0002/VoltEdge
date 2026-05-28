"""Import training data from CSV into the ML database.

Use this to bulk-load historical data before starting the app.
The CSV must have these columns:
  - duration_minutes  (integer)
  - temperature       (float, °C)
  - hour_of_day       (integer, 0-23)
  - actual_energy_kwh (float)

Usage:
    python scripts/import_ml_data.py path/to/your_data.csv

If the database already has data, new rows are appended (no duplicates removed).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Add src to path so we can import the ML data store
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analytics_service.ml_data_store import add_training_data


def import_csv(filepath: str) -> int:
    """Import rows from a CSV file. Returns the number of rows imported."""
    count = 0
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            add_training_data(
                duration_minutes=int(row["duration_minutes"]),
                temperature=float(row["temperature"]),
                hour_of_day=int(row["hour_of_day"]),
                actual_energy_kwh=float(row["actual_energy_kwh"]),
            )
            count += 1
    return count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_ml_data.py <csv_file>")
        sys.exit(1)

    path = sys.argv[1]
    if not Path(path).exists():
        print(f"File not found: {path}")
        sys.exit(1)

    n = import_csv(path)
    print(f"Imported {n} training data points into ML database.")
