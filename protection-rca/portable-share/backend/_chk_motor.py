import sqlite3
from pathlib import Path
from collections import Counter

c = sqlite3.connect("protection_rca_local.db")
c.row_factory = sqlite3.Row
ev = c.execute(
    "SELECT id, event_id, description, feeder FROM events WHERE event_id LIKE ?",
    ("%00015%",),
).fetchone()
print("event", dict(ev) if ev else None)
if not ev:
    raise SystemExit(0)
eid = ev["id"]
for r in c.execute(
    "SELECT original_filename, storage_key FROM event_files WHERE event_id=?",
    (eid,),
):
    print(r["original_filename"], "->", r["storage_key"])

# channels from DB
rows = c.execute(
    "SELECT name, channel_type FROM comtrade_channels WHERE comtrade_file_id IN "
    "(SELECT id FROM comtrade_files WHERE event_id=?)",
    (eid,),
).fetchall()
print("channels", len(rows))
for r in rows:
    if str(r["channel_type"]).upper() == "DIGITAL":
        print(" D", r["name"])

from protection.digital_targets import infer_target_role, infer_element_code
print("\ninference:")
for r in rows:
    if str(r["channel_type"]).upper() != "DIGITAL":
        continue
    n = r["name"]
    print(f"  {n!r} -> {infer_target_role(n)} / {infer_element_code(n)}")
