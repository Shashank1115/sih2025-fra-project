# run_initial_setup.py
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

from backend.database import create_database, save_data_to_db
from ai_models.digitization import extract_info_from_image
from ai_models.asset_mapping import map_assets_from_satellite_image
from ai_models.map_visualizer import generate_claim_asset_map   # ✅ import here


def run_setup():
    # Step 1: Create database
    create_database()

    # Step 2: OCR from claim document
    sample_doc_path = "sample_data/sample_doc.png"
    claim_data = extract_info_from_image(sample_doc_path)

    if claim_data and claim_data["coordinates"] != "Unknown":
        try:
            lat, lon = map(float, claim_data["coordinates"].split(","))
        except ValueError:
            print("❌ Error: Invalid coordinates format in document")
            return

        # Step 3: Create GeoDataFrame
        claim_gdf = gpd.GeoDataFrame(
            pd.DataFrame([claim_data]),
            geometry=[Point(lon, lat)],
            crs="EPSG:4326"
        )

        # Save claims data
        save_data_to_db(claim_gdf, "fra_claims")
        print(f"📍 Claim saved with coords: {lat},{lon}")

        # Step 4: Asset mapping
        print("\n--- Starting Real Asset Mapping ---")
        asset_gdf = map_assets_from_satellite_image(claim_gdf)

        if not asset_gdf.empty:
            asset_gdf["village"] = claim_data["village"]
            save_data_to_db(asset_gdf, "fra_assets")
            print("✅ Assets successfully detected and saved to database.")

            # Step 5: Generate claim + assets map
            map_path = generate_claim_asset_map(claim_gdf, asset_gdf)
            print(f"🗺️ Claim + assets map generated: {map_path}")
        else:
            print("ℹ️ No assets were detected in the satellite image.")

    else:
        print("❌ Could not extract claim data from document.")


if __name__ == "__main__":
    run_setup()
