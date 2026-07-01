import sqlite3
import os
from datetime import datetime, timedelta

db_path = "instance/volstruisgids.db"
print(f"DB path: {db_path}")
print(f"DB size: {os.path.getsize(db_path)} bytes")
print(f"Exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

print("\n=== TABLES ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for row in c.fetchall():
    print("  ", row[0])

print("\n=== ALL SITESTAT ===")
c.execute("SELECT key, value, updated_at FROM site_stats ORDER BY key")
for row in c.fetchall():
    print(row)

print("\n=== DAILY_VIEW KEYS ONLY ===")
c.execute("SELECT key, value, updated_at FROM site_stats WHERE key LIKE 'daily_views_%' ORDER BY key DESC")
daily = c.fetchall()
print(f"Total daily keys: {len(daily)}")
for row in daily:
    print("  ", row)

print("\n=== LISTINGS ACTIVITY ===")
c.execute("SELECT COUNT(*), SUM(COALESCE(views, 0)), MAX(COALESCE(views, 0)) FROM listings")
print("  count, sum_views, max_views:", c.fetchone())

print("\n=== Listings created per day (most recent 15) ===")
c.execute("""
    SELECT date(created_at) as d, COUNT(*) as cnt 
    FROM listings 
    GROUP BY d 
    ORDER BY d DESC 
    LIMIT 15
""")
for r in c.fetchall():
    print("  ", r)

print("\n=== ENGAGEMENT ===")
c.execute("SELECT COUNT(*) FROM comments")
print("  comments:", c.fetchone()[0])
c.execute("SELECT COUNT(*) FROM likes")
print("  likes:", c.fetchone()[0])
c.execute("SELECT COUNT(*) FROM messages")
print("  messages:", c.fetchone()[0])

print("\n=== Monthly keys ===")
c.execute("SELECT key, value FROM site_stats WHERE key LIKE 'views_%' ORDER BY key DESC")
for r in c.fetchall():
    print("  ", r)

print("\n=== total_views ===")
c.execute("SELECT value, updated_at FROM site_stats WHERE key='total_views'")
print("  ", c.fetchone())

conn.close()
print("\n=== Done ===")
