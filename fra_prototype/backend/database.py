# backend/database.py
import sqlite3
import pandas as pd
import geopandas as gpd

DB_PATH = "fra_database.sqlite"

def create_database():
    """Creates a standard SQLite database without SpatiaLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create claims table with a TEXT column for geometry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fra_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patta_holder TEXT,
        village TEXT,
        claim_status TEXT,
        geometry TEXT
    );
    """)

    # Create assets table with a TEXT column for geometry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fra_assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        village TEXT,
        asset_type TEXT,
        geometry TEXT
    );
    """)
    conn.commit()
    conn.close()
    print("Standard SQLite database created successfully.")

def save_data_to_db(gdf, table_name):
    """Saves a GeoDataFrame to the database, storing geometry as WKT text."""
    conn = sqlite3.connect(DB_PATH)
    
    # Convert geometry to Well-Known Text (WKT) string format
    gdf['geometry'] = gdf['geometry'].apply(lambda x: x.wkt)
    
    gdf.to_sql(table_name, conn, if_exists='append', index=False)
    conn.close()
    print(f"Data saved to table '{table_name}'.")