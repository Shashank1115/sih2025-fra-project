# backend/api.py
import sqlite3
import json
from typing import Optional, List, Dict, Any

import geopandas as gpd
import pandas as pd
from shapely import wkt
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = "fra_claims.db"

app = FastAPI(title="FRA Atlas API")

# --- CORS for local Streamlit/other frontends ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # localhost dev convenience
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Helpers ----------
def _sql_df(sql: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(sql, conn)
    conn.close()
    return df

def _claims_df() -> pd.DataFrame:
    return _sql_df("SELECT * FROM fra_claims")

def _assets_df() -> pd.DataFrame:
    return _sql_df("SELECT * FROM fra_assets")

def _assets_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    if df.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    df = df.copy()
    df["geometry"] = df["geometry"].apply(wkt.loads)
    return gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

def _points_from_coordinates(df: pd.DataFrame) -> gpd.GeoDataFrame:
    if df.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    # handle "lat,lon" (your current format)
    latlon = df["coordinates"].str.split(",", expand=True).astype(float)
    df = df.copy()
    df["lat"] = latlon[0]
    df["lon"] = latlon[1]
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    return gdf

# ---------- Dashboard ----------
@app.get("/summary")
def summary():
    claims = _claims_df()
    assets = _assets_df()

    total_claims = len(claims)
    granted = int((claims["claim_status"].str.lower() == "granted").sum()) if not claims.empty else 0
    pending = total_claims - granted

    if not assets.empty:
        gdf = _assets_gdf(assets).to_crs(epsg=3857)
        areas = {}
        for t in ["cropland", "forest", "water_body", "urban", "barren_land"]:
            a = gdf[gdf["asset_type"] == t].area.sum() / 10_000
            areas[t] = round(float(a), 2)
    else:
        areas = {t: 0.0 for t in ["cropland", "forest", "water_body", "urban", "barren_land"]}

    return {
        "claims": total_claims,
        "granted": granted,
        "pending": pending,
        "areas_ha": areas,
    }

# ---------- GeoJSON feeds (native) ----------
@app.get("/claims_geojson")
def claims_geojson(status: Optional[str] = None, village: Optional[str] = None):
    df = _claims_df()
    if df.empty:
        return JSONResponse({"type": "FeatureCollection", "features": []})
    gdf = _points_from_coordinates(df)
    if status:
        gdf = gdf[gdf["claim_status"].str.lower() == status.lower()]
    if village:
        gdf = gdf[gdf["village"].str.contains(village, case=False, na=False)]
    return JSONResponse(gdf.__geo_interface__)

@app.get("/assets_geojson")
def assets_geojson(asset_type: Optional[str] = None, village: Optional[str] = None):
    df = _assets_df()
    if df.empty:
        return JSONResponse({"type": "FeatureCollection", "features": []})
    if asset_type:
        df = df[df["asset_type"] == asset_type]
    if village:
        df = df[df["village"].str.contains(village, case=False, na=False)]
    gdf = _assets_gdf(df)
    return JSONResponse(gdf.__geo_interface__)

# ---------- COMPAT routes for Streamlit (expects /api/...) ----------
@app.get("/api/villages")
def api_villages():
    df = _claims_df()
    v = sorted([x for x in df["village"].dropna().unique().tolist()]) if not df.empty else []
    return [{"village": x} for x in v]

@app.get("/api/claims/{village}")
def api_claims_by_village(village: str):
    df = _claims_df()
    if df.empty:
        return JSONResponse({"type": "FeatureCollection", "features": []})
    dfv = df[df["village"].str.lower() == village.lower()]
    if dfv.empty:
        return JSONResponse({"type": "FeatureCollection", "features": []})
    gdf = _points_from_coordinates(dfv)
    return JSONResponse(gdf.__geo_interface__)

@app.get("/api/assets/{village}")
def api_assets_by_village(village: str):
    df = _assets_df()
    if df.empty:
        return JSONResponse({"type": "FeatureCollection", "features": []})
    dfv = df[df["village"].str.lower() == village.lower()]
    if dfv.empty:
        return JSONResponse({"type": "FeatureCollection", "features": []})
    gdf = _assets_gdf(dfv)
    return JSONResponse(gdf.__geo_interface__)

# ---------- Home / Atlas ----------
@app.get("/")
def home():
    html = """<html><body>
        <h3>FRA Atlas API</h3>
        <ul>
          <li><a href="/summary">/summary</a></li>
          <li><a href="/claims_geojson">/claims_geojson</a></li>
          <li><a href="/assets_geojson">/assets_geojson</a></li>
          <li><a href="/api/villages">/api/villages</a> (compat)</li>
          <li><a href="/api/claims/YourVillage">/api/claims/&lt;village&gt;</a> (compat)</li>
          <li><a href="/api/assets/YourVillage">/api/assets/&lt;village&gt;</a> (compat)</li>
        </ul>
    </body></html>"""
    return HTMLResponse(html)
