# frontend/app.py
import streamlit as st
import requests
import geopandas as gpd
import pandas as pd

API_URL = "http://127.0.0.1:5000"

st.set_page_config(layout="wide")
st.title("FRA Data and Decision Support Prototype")

# --- Fetch list of villages for the dropdown ---
try:
    villages_res = requests.get(f"{API_URL}/api/villages")
    if villages_res.status_code == 200:
        villages_df = pd.DataFrame(villages_res.json())
        village_list = villages_df['village'].tolist() if not villages_df.empty else []
    else:
        village_list = []
        st.error(f"Failed to fetch villages. Status code: {villages_res.status_code}")
except requests.exceptions.ConnectionError:
    st.error("Connection to backend API failed. Is the API running?")
    st.stop()


selected_village = st.sidebar.selectbox("Select a Village", village_list)

if selected_village:
    st.header(f"Data for {selected_village}")
    
    # --- Fetch and display data from API ---
    claims_res = requests.get(f"{API_URL}/api/claims/{selected_village}")
    assets_res = requests.get(f"{API_URL}/api/assets/{selected_village}")
    
    if claims_res.status_code == 200 and assets_res.status_code == 200:
        claims_gdf = gpd.read_file(claims_res.text)
        assets_gdf = gpd.read_file(assets_res.text)
        
        # --- The FRA Atlas ---
        st.subheader("FRA Atlas")
        
        if not claims_gdf.empty:
            claims_gdf['lat'] = claims_gdf.geometry.y
            claims_gdf['lon'] = claims_gdf.geometry.x
            st.map(claims_gdf)
        else:
            st.write("No claim data to display on map.")

        col1, col2 = st.columns(2)
        with col1:
            st.write("Claims Data")
            st.dataframe(claims_gdf.drop(columns='geometry') if 'geometry' in claims_gdf.columns else claims_gdf)
        with col2:
            st.write("Mapped Assets")
            st.dataframe(assets_gdf.drop(columns='geometry') if 'geometry' in assets_gdf.columns else assets_gdf)

        # --- The DSS Engine ---
        st.subheader("Decision Support System (DSS) Recommendations")
        
        if not assets_gdf.empty:
            if 'farm' in assets_gdf['asset_type'].tolist():
                 st.success("✅ Recommendation: This village has farms. Target residents for PM-KISAN enrollment.")
            if 'water_body' not in assets_gdf['asset_type'].tolist():
                st.warning("⚠️ Recommendation: This village has few visible water bodies. Prioritize for interventions under Jal Shakti (e.g., borewells).")
            else:
                st.info("ℹ️ Water body assets are present.")
        else:
            st.info("No asset data to generate recommendations.")
            
    else:
        st.error("Could not fetch data for the selected village.")