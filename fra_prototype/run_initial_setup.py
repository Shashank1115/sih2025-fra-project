# run_initial_setup.py
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

from backend.database import create_database, save_data_to_db
from ai_models.digitization import extract_info_from_image
from ai_models.asset_mapping import get_satellite_image_for_claim, map_assets_from_satellite_image
from ai_models.map_visualizer import generate_claim_map


def run_setup():
    # Step 1: Create fresh database
    create_database()

    # Step 2: Extract info from the sample document
    sample_doc_path = "sample_data/sample_doc.png"
    claim_data = extract_info_from_image(sample_doc_path)

    if not claim_data:
        print("❌ Could not extract data from document. Setup aborted.")
        return

    if claim_data["coordinates"] == "Unknown":
        print("❌ No valid coordinates found in document. Setup aborted.")
        return

    try:
        lat, lon = map(float, claim_data["coordinates"].split(","))
    except ValueError:
        print("❌ Coordinates not in valid 'lat,lon' format.")
        return

    # Step 3: Create GeoDataFrame
    claim_gdf = gpd.GeoDataFrame(
        pd.DataFrame([claim_data]),
        geometry=[Point(lon, lat)],
        crs="EPSG:4326"
    )

    # Save claims data
    save_data_to_db(claim_gdf, "fra_claims")
    print("📍 Claim saved with coords:", claim_data["coordinates"])

    # Step 4: Generate claim location map
    map_path = generate_claim_map(lat, lon, claim_data["patta_holder"], claim_data["village"], claim_data["claim_status"])
    print(f"🗺️ Claim map generated: {map_path}")

    # Step 5: Fetch satellite image
    print("\n--- Starting Real Asset Mapping ---")
    image_path = get_satellite_image_for_claim(claim_gdf.geometry.iloc[0])

    if not image_path:
        print("❌ Failed to fetch satellite image. Skipping asset detection.")
        return

    print(f"🌍 Satellite image ready at {image_path}")

    # Step 6: Detect assets
    asset_gdf = map_assets_from_satellite_image(claim_gdf)

    if not asset_gdf.empty:
        asset_gdf["village"] = claim_data["village"]
        save_data_to_db(asset_gdf, "fra_assets")
        print("✅ Assets successfully detected and saved to database.")
    else:
        print("ℹ️ No assets were detected in the satellite image.")


if __name__ == "__main__":
    run_setup()
