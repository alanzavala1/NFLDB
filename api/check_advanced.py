"""Run this to see what advanced stat tables and columns exist in the DB."""
from database import get_connection

conn = get_connection()

tables = [
    "pfr_pass", "pfr_rush", "pfr_rec", "pfr_def",
    "ngs_passing", "ngs_rushing", "ngs_receiving",
    "snap_counts",
]

for table in tables:
    try:
        cols = [r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()]
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"\n{'='*60}")
        print(f"  {table}  ({count:,} rows)")
        print(f"{'='*60}")
        for c in sorted(cols):
            print(f"  {c}")
    except Exception as e:
        print(f"\n  {table}: NOT FOUND ({e})")
