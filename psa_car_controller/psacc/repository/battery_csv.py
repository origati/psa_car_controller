import csv
import os
from datetime import datetime, timezone

CSV_FILE = "battery_readings.csv"
_HEADER = ["timestamp", "vin", "source", "level", "level_bms", "autonomy"]
_last = {}  # (vin, source) -> (level, level_bms, autonomy)


def record(vin, source, level=None, level_bms=None, autonomy=None, timestamp=None):
    key = (vin, source)
    new_vals = (level, level_bms, autonomy)
    if _last.get(key) == new_vals:
        return
    _last[key] = new_vals
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    write_header = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(_HEADER)
        w.writerow([
            timestamp.isoformat(),
            vin,
            source,
            level if level is not None else "",
            level_bms if level_bms is not None else "",
            autonomy if autonomy is not None else "",
        ])
