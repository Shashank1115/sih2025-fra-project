# backend/database.py
import sqlite3
import geopandas as gpd
import os

DB_PATH = "fra_claims.db"

def create_database():
    """Create SQLite database with FRA claims and assets tables"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Claims table
    cursor.execute("""
        CREATE TABLE fra_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patta_holder TEXT,
            village TEXT,
            coordinates TEXT,
            claim_status TEXT,
            geometry TEXT
        )
    """)

    # Assets table
    cursor.execute("""
        CREATE TABLE fra_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT,
            village TEXT,
            geometry TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("Standard SQLite database created successfully.")


def save_data_to_db(gdf, table_name):
    """Save a GeoDataFrame to SQLite as WKT geometry"""
    conn = sqlite3.connect(DB_PATH)

    # Convert Shapely geometry to WKT strings
    if "geometry" in gdf.columns:
        gdf = gdf.copy()
        gdf["geometry"] = gdf["geometry"].apply(lambda geom: geom.wkt if geom else None)

    gdf.to_sql(table_name, conn, if_exists="append", index=False)
    conn.close()
    print(f"Data saved to table '{table_name}'.")

