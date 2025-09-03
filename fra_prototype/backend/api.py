# backend/api.py
from flask import Flask, jsonify
import sqlite3
import pandas as pd
import geopandas as gpd
from shapely import wkt

app = Flask(__name__)
DB_PATH = "fra_database.sqlite"

def query_db_to_gdf(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    # Convert WKT text back to geometry
    df['geometry'] = df['geometry'].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    return gdf

@app.route('/api/villages', methods=['GET'])
def get_villages():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT DISTINCT village FROM fra_claims;", conn)
    conn.close()
    return jsonify(df.to_dict(orient='records'))

@app.route('/api/claims/<village_name>', methods=['GET'])
def get_claims(village_name):
    gdf = query_db_to_gdf("SELECT * FROM fra_claims WHERE village = ?;", (village_name,))
    return gdf.to_json()

@app.route('/api/assets/<village_name>', methods=['GET'])
def get_assets(village_name):
    gdf = query_db_to_gdf("SELECT * FROM fra_assets WHERE village = ?;", (village_name,))
    return gdf.to_json()

if __name__ == '__main__':
    app.run(debug=True, port=5000)