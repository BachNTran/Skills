"""Mean and standard deviation of recorded battery-channel samples (mV)."""
import csv
import statistics
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[1] / "data" / "samples.csv")
with path.open() as f:
    mv = [int(row["mv"]) for row in csv.DictReader(f)]
print(f"n={len(mv)} mean={statistics.mean(mv):.1f} mV sigma={statistics.stdev(mv):.1f} mV")
