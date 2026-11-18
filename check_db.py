"""Quick sanity check: which database are we talking to, and what is in it?"""
import database

print("BACKEND:", database.backend_name())

print("\nALL TABLES:")
print(database.query("SELECT name FROM sqlite_master WHERE type='table'"))

for table in ("weather_observations", "weather_forecasts", "collector_runs"):
    print(f"\nCOLUMNS OF {table}:")
    for column in database.query(f"PRAGMA table_info({table})"):
        print(column)
