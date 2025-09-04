# frontend/app.py
import streamlit as st
import requests
import geopandas as gpd
import pandas as pd
import json
API_URL = "http://127.0.0.1:8000"


st.set_page_config(layout="wide")
st.title("FRA Data and Decision Support Prototype")

# --- Fetch list of villages for the dropdown ---
try:
    villages_res = requests.get(f"{API_URL}/api/villages", timeout=10)
    villages_res.raise_for_status()
    villages_df = pd.DataFrame(villages_res.json())
    village_list = villages_df['village'].tolist() if not villages_df.empty else []
except Exception as e:
    st.error(f"Connection to backend API failed: {e}")
    st.stop()

selected_village = st.sidebar.selectbox("Select a Village", village_list)

def geojson_to_gdf(geojson_obj):
    """Robustly convert a dict or text GeoJSON to GeoDataFrame."""
    if isinstance(geojson_obj, str):
        gj = json.loads(geojson_obj)
    else:
        gj = geojson_obj
    features = gj.get("features", [])
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

if selected_village:
    st.header(f"Data for {selected_village}")

    # --- Fetch and display data from API ---
    claims_res = requests.get(f"{API_URL}/api/claims/{selected_village}", timeout=20)
    assets_res = requests.get(f"{API_URL}/api/assets/{selected_village}", timeout=20)

    if claims_res.status_code == 200 and assets_res.status_code == 200:
        claims_gdf = geojson_to_gdf(claims_res.json())
        assets_gdf = geojson_to_gdf(assets_res.json())

        # --- FRA Atlas ---
        st.subheader("FRA Atlas")

        if not claims_gdf.empty:
            claims_gdf['lat'] = claims_gdf.geometry.y
            claims_gdf['lon'] = claims_gdf.geometry.x
            st.map(claims_gdf[['lat','lon']])
        else:
            st.write("No claim points to display on map.")

        col1, col2 = st.columns(2)
        with col1:
            st.write("Claims Data")
            st.dataframe(claims_gdf.drop(columns='geometry', errors='ignore'))
        with col2:
            st.write("Mapped Assets")
            st.dataframe(assets_gdf.drop(columns='geometry', errors='ignore'))

        # --- DSS demo (simple)
        st.subheader("Decision Support System (DSS) Recommendations")
        if not assets_gdf.empty:
            types = assets_gdf['asset_type'].astype(str).tolist()
            if any(t in types for t in ("cropland", "farm")):
                st.success("✅ PM-KISAN / livelihood support recommended (cropland present).")
            if "water_body" not in types:
                st.warning("⚠️ Prioritize Jal Shakti works (no surface water mapped).")
            else:
                st.info("ℹ️ Water body assets are present.")
        else:
            st.info("No asset data to generate recommendations.")
    else:
        st.error(f"Could not fetch data. Claims status: {claims_res.status_code}, Assets status: {assets_res.status_code}")
