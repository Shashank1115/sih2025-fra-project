# backend/database.py
import sqlite3
import geopandas as gpd
import os

DB_PATH = "fra_claims.db"

def create_database():
    """Create SQLite database with FRA claims and assets tables (fresh)."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Claims table
    cur.execute("""
        CREATE TABLE fra_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patta_holder TEXT,
            village TEXT,
            coordinates TEXT,  -- "lat,lon"
            claim_status TEXT,
            geometry TEXT       -- WKT of claim point (optional)
        )
    """)

    # Assets table (link to claim_id + village)
    cur.execute("""
        CREATE TABLE fra_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER,
            asset_type TEXT,
            village TEXT,
            geometry TEXT,
            FOREIGN KEY (claim_id) REFERENCES fra_claims(id)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Standard SQLite database created.")

def save_data_to_db(gdf, table_name):
    """Save a GeoDataFrame to SQLite as WKT geometry."""
    if gdf is None or gdf.empty:
        print(f"ℹ️ No rows to save for '{table_name}'.")
        return

    conn = sqlite3.connect(DB_PATH)
    df = gdf.copy()

    if "geometry" in df.columns:
        df["geometry"] = df["geometry"].apply(lambda geom: geom.wkt if geom is not None else None)

    df.to_sql(table_name, conn, if_exists="append", index=False)
    conn.close()
    print(f"💾 Data saved to table '{table_name}'.")
