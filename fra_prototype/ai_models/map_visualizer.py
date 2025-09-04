# ai_models/map_visualizer.py
import folium
import geopandas as gpd
import pandas as pd
import sqlite3
import webbrowser
from shapely import wkt
from ai_models.groundwater_offline import groundwater_depth_near

DB_PATH = "fra_claims.db"
OUTPUT_PATH = "sample_data/claim_assets_map.html"

# Asset type → color mapping
ASSET_COLORS = {
    "forest": "darkgreen",
    "cropland": "green",
    "water_body": "blue",
    "urban": "red",
    "barren_land": "gray"
}

def generate_claim_asset_map(claim_gdf, asset_gdf, output_path=OUTPUT_PATH):
    """
    Generates an interactive folium map showing:
    - Claim location (marker)
    - Detected assets (polygons)
    - Nearest groundwater well (if available)
    """

    # Claim lat/lon
    lat = claim_gdf.geometry.y.iloc[0]
    lon = claim_gdf.geometry.x.iloc[0]
    patta_holder = claim_gdf["patta_holder"].iloc[0] if "patta_holder" in claim_gdf else "Unknown"
    village = claim_gdf["village"].iloc[0] if "village" in claim_gdf else "Unknown"

    m = folium.Map(location=[lat, lon], zoom_start=14)

    # Add claim marker
    folium.Marker(
        location=[lat, lon],
        popup=f"Claim: {patta_holder} ({village})",
        tooltip="Claim Location",
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(m)

    # Add asset polygons with colors
    for _, row in asset_gdf.iterrows():
        asset_type = row.get("asset_type", "unknown")
        color = ASSET_COLORS.get(asset_type, "black")

        folium.GeoJson(
            row["geometry"].__geo_interface__,
            name=asset_type,
            tooltip=asset_type,
            style_function=lambda x, c=color: {
                "color": c,
                "weight": 2,
                "fillOpacity": 0.4
            }
        ).add_to(m)

    # Add nearest groundwater well
    try:
        gw = groundwater_depth_near(lat, lon, max_km=100.0)
        if gw:
            gw_popup = (
                f"Station: {gw['station_code']}<br>"
                f"Depth: {gw['depth_m_bgl']} m bgl<br>"
                f"Measured: {gw['when']}<br>"
                f"Distance: {gw['distance_km']} km"
            )
            folium.Marker(
                location=[gw["well_lat"], gw["well_lon"]],
                popup=gw_popup,
                tooltip="Nearest GW Well",
                icon=folium.Icon(color="blue", icon="tint")
            ).add_to(m)
    except Exception as e:
        print(f"⚠️ Could not add groundwater well: {e}")

    # Save and open map
    m.save(output_path)
    print(f"🗺️ Claim + assets map saved at {output_path}")
    webbrowser.open(output_path)
    return output_path


if __name__ == "__main__":
    # Load latest claim + assets from DB
    conn = sqlite3.connect(DB_PATH)

    claims = pd.read_sql("SELECT * FROM fra_claims ORDER BY rowid DESC LIMIT 1;", conn)
    assets = pd.read_sql("SELECT * FROM fra_assets;", conn)

    conn.close()

    if claims.empty:
        print("⚠️ No claims found in DB.")
    else:
        # Convert WKT to geometry
        assets["geometry"] = assets["geometry"].apply(wkt.loads)
        assets = gpd.GeoDataFrame(assets, geometry="geometry", crs="EPSG:4326")

        claim_gdf = gpd.GeoDataFrame(
            claims,
            geometry=gpd.points_from_xy(
                claims["coordinates"].str.split(",").str[1].astype(float),
                claims["coordinates"].str.split(",").str[0].astype(float)
            ),
            crs="EPSG:4326"
        )

        generate_claim_asset_map(claim_gdf, assets)
