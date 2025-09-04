# test_database.py
import sqlite3
import pandas as pd

DB_PATH = "fra_claims.db"  # make sure this matches the DB name you are using

def show_database_contents():
    conn = sqlite3.connect(DB_PATH)

    # Show tables
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
    print("\n📋 Tables in database:")
    print(tables)

    # Show claims
    claims = pd.read_sql("SELECT * FROM fra_claims;", conn)
    print("\n🌍 FRA CLAIMS:")
    print(claims)

    # Show assets
    assets = pd.read_sql("SELECT * FROM fra_assets;", conn)
    print("\n🏗️ FRA ASSETS:")
    print(assets)

    conn.close()

if __name__ == "__main__":
    show_database_contents()
