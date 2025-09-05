
# ai_models/map_visualizer.py
import folium
import geopandas as gpd
import pandas as pd
import sqlite3
import webbrowser
from shapely import wkt
from ai_models.groundwater_offline import groundwater_k_nearest

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

def _ensure_gdf_geometry(asset_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """If geometry column contains WKT strings, convert to shapely geometry objects."""
    if asset_gdf is None:
        return gpd.GeoDataFrame(columns=["asset_type", "geometry"], geometry=[], crs="EPSG:4326")
    gdf = asset_gdf.copy()
    if "geometry" in gdf.columns and gdf.geometry.dtype == object:
        # If values are WKT strings, convert; if already geometry, leave as-is.
        sample = gdf["geometry"].iloc[0] if len(gdf) > 0 else None
        if isinstance(sample, str):
            gdf["geometry"] = gdf["geometry"].apply(lambda x: wkt.loads(x) if x is not None else None)
    # ensure GeoDataFrame and CRS
    if not isinstance(gdf, gpd.GeoDataFrame):
        gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    return gdf

def generate_claim_asset_map(claim_gdf, asset_gdf, output_path=OUTPUT_PATH,
                             gw_k=3, gw_max_km=100.0):
    """
    Generates an interactive folium map showing:
    - Claim location (marker)
    - Detected assets (polygons)
    - Nearest groundwater wells (up to gw_k)
    """

    if claim_gdf is None or claim_gdf.empty:
        raise ValueError("claim_gdf is empty or None")

    # Extract claim point (expects geometry is Point with x=lon, y=lat)
    claim_pt = claim_gdf.geometry.iloc[0]
    lon, lat = claim_pt.x, claim_pt.y

    patta_holder = claim_gdf.get("patta_holder", pd.Series(["Unknown"])).iloc[0]
    village = claim_gdf.get("village", pd.Series(["Unknown"])).iloc[0]

    m = folium.Map(location=[lat, lon], zoom_start=14)

    # Add claim marker
    folium.Marker(
        location=[lat, lon],
        popup=f"<b>Claim:</b> {patta_holder} <br/><b>Village:</b> {village}",
        tooltip="Claim Location",
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(m)

    # Prepare assets GeoDataFrame
    asset_gdf = _ensure_gdf_geometry(asset_gdf)

    # Add asset polygons with colors
    if not asset_gdf.empty:
        for _, row in asset_gdf.iterrows():
            geom = row.get("geometry")
            if geom is None:
                continue
            asset_type = row.get("asset_type", "unknown")
            color = ASSET_COLORS.get(asset_type, "black")

            # style_function closure captures color per feature
            folium.GeoJson(
                geom.__geo_interface__ if hasattr(geom, "__geo_interface__") else geom,
                name=asset_type,
                tooltip=str(asset_type),
                style_function=(lambda c: (lambda feature: {
                    "color": c,
                    "weight": 2,
                    "fillOpacity": 0.4
                }))(color)
            ).add_to(m)

    # Add nearest groundwater wells (up to gw_k)
    try:
        wells = groundwater_k_nearest(lat, lon, k=gw_k, max_km=gw_max_km)
    except Exception as e:
        wells = []
        print(f"⚠️ groundwater lookup failed: {e}")

    if wells:
        # Add markers for each sampled well; highlight the closest
        wells_sorted = sorted(wells, key=lambda w: w["distance_km"])
        closest = wells_sorted[0]

        # Popup for the closest well
        gw_popup = (
            f"<b>Nearest GW Well</b><br>"
            f"Station: {closest.get('station_code')}<br>"
            f"Depth: {closest.get('depth_m_bgl')} m bgl<br>"
            f"Measured: {closest.get('when')}<br>"
            f"Distance: {closest.get('distance_km')} km"
        )
        folium.Marker(
            location=[closest["well_lat"], closest["well_lon"]],
            popup=gw_popup,
            tooltip="Nearest GW Well",
            icon=folium.Icon(color="blue", icon="tint")
        ).add_to(m)

        # Add other wells (if any) as smaller markers
        for w in wells_sorted[1:]:
            popup = (
                f"Station: {w.get('station_code')}<br>"
                f"Depth: {w.get('depth_m_bgl')} m bgl<br>"
                f"Measured: {w.get('when')}<br>"
                f"Distance: {w.get('distance_km')} km"
            )
            folium.CircleMarker(
                location=[w["well_lat"], w["well_lon"]],
                radius=4,
                color="blue",
                fill=True,
                fill_opacity=0.7,
                popup=popup,
                tooltip="Nearby GW well"
            ).add_to(m)

        # Add a small legend item as a marker with summary
        summary_html = f"GW sample: {len(wells_sorted)} wells, closest {closest['distance_km']} km, avg depth TBD"
        folium.map.Marker(
            [lat, lon],
            icon=folium.DivIcon(html=f"""<div style="font-size:12px;background:white;padding:4px;border-radius:4px">{summary_html}</div>""")
        ).add_to(m)

    # Save and open map
    m.save(output_path)
    print(f"🗺️ Claim + assets map saved at {output_path}")

    # try opening in default browser (non-blocking)
    try:
        webbrowser.open(output_path)
    except Exception:
        pass

    return output_path


if __name__ == "__main__":
    # Load latest claim + assets from DB
    conn = sqlite3.connect(DB_PATH)
    claims = pd.read_sql("SELECT * FROM fra_claims ORDER BY id DESC LIMIT 1;", conn)
    assets = pd.read_sql("SELECT * FROM fra_assets;", conn)
    conn.close()

    if claims.empty:
        print("⚠️ No claims found in DB.")
    else:
        # Convert assets geometry WKT -> shapely geometry if needed
        if "geometry" in assets.columns:
            assets["geometry"] = assets["geometry"].apply(lambda g: wkt.loads(g) if isinstance(g, str) else g)
            assets_gdf = gpd.GeoDataFrame(assets, geometry="geometry", crs="EPSG:4326")
        else:
            assets_gdf = gpd.GeoDataFrame(columns=list(assets.columns)+["geometry"], geometry=[], crs="EPSG:4326")

        # Build claim GeoDataFrame (expects 'coordinates' as "lat,lon")
        coords_split = claims["coordinates"].str.split(",", expand=True)
        claims_gdf = gpd.GeoDataFrame(
            claims,
            geometry=gpd.points_from_xy(coords_split[1].astype(float), coords_split[0].astype(float)),
            crs="EPSG:4326"
        )

        generate_claim_asset_map(claims_gdf, assets_gdf)
