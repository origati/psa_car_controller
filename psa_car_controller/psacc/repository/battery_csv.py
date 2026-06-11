import csv
import os
import threading
from datetime import datetime, timezone

# Configurable amb env var; per defecte el CWD del servei (comportament original).
CSV_FILE = os.environ.get("BATTERY_CSV_PATH", "battery_readings.csv")
_HEADER = ["timestamp", "vin", "source", "level", "level_bms", "autonomy"]
# record() es crida des del thread MQTT i el thread de refresc alhora.
_lock = threading.Lock()
_last = {}     # (vin, source) -> (level, level_bms, autonomy)
_last_ts = {}  # (vin, source) -> datetime


def record(vin, source, level=None, level_bms=None, autonomy=None, timestamp=None):
    key = (vin, source)
    new_vals = (level, level_bms, autonomy)
    with _lock:
        if _last.get(key) == new_vals:
            return
        _last[key] = new_vals
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        _last_ts[key] = timestamp
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


def get_last(vin):
    """Returns the last known api and mqtt readings for a VIN, with timestamps."""
    result = {}
    with _lock:
        for source in ("api", "mqtt"):
            key = (vin, source)
            if key not in _last:
                continue
            vals = _last[key]
            ts = _last_ts.get(key)
            entry = {"autonomy": vals[2], "ts": ts.isoformat() if ts else None}
            if source == "api":
                entry["level"] = vals[0]
            else:
                entry["level_bms"] = vals[1]
            result[source] = entry
    return result
