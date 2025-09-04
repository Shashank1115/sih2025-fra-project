# run_initial_setup.py
import sqlite3
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

from backend.database import create_database, save_data_to_db, DB_PATH
from ai_models.digitization import extract_info_from_image
from ai_models.asset_mapping import map_assets_from_satellite_image
from ai_models.map_visualizer import generate_claim_asset_map


SAMPLE_DOC_PATH = "sample_data/sample_doc.png"


def _insert_claim_and_get_id(claim_row: dict) -> int:
    """
    Inserts one claim row via save_data_to_db (so schema stays consistent),
    then returns the auto-incremented 'id' for the last inserted claim.
    """
    # Build GeoDataFrame for the claim
    lat, lon = map(float, claim_row["coordinates"].split(","))
    claim_gdf = gpd.GeoDataFrame(
        pd.DataFrame([claim_row]),
        geometry=[Point(lon, lat)],  # (x=lon, y=lat)
        crs="EPSG:4326"
    )

    # Save claim
    save_data_to_db(claim_gdf, "fra_claims")

    # Fetch its id
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, patta_holder, village, coordinates FROM fra_claims ORDER BY id DESC LIMIT 1;"
    ).fetchone()
    conn.close()

    if not row:
        raise RuntimeError("Failed to retrieve inserted claim id.")

    claim_id = int(row[0])
    return claim_id


def run_setup():
    # 1) Fresh database (WARNING: this clears existing DB)
    create_database()

    # 2) OCR extract from sample document
    claim_data = extract_info_from_image(SAMPLE_DOC_PATH)
    if not claim_data or claim_data.get("coordinates", "Unknown") == "Unknown":
        print("❌ Could not extract claim data from document.")
        return

    # Basic coordinate validation
    try:
        lat, lon = map(float, claim_data["coordinates"].split(","))
    except Exception:
        print("❌ Error: Invalid coordinates format in document (expected 'lat,lon').")
        return

    # Normalize minimal fields
    claim_data.setdefault("patta_holder", "Unknown")
    claim_data.setdefault("village", "Unknown")
    claim_data.setdefault("claim_status", "Unknown")

    # 3) Insert claim and get its id
    claim_id = _insert_claim_and_get_id(claim_data)
    print(f"📍 Claim saved (id={claim_id}) with coords: {lat},{lon}")

    # Build claim_gdf for mapping
    claim_gdf = gpd.GeoDataFrame(
        [{"id": claim_id, **claim_data}],
        geometry=[Point(lon, lat)],
        crs="EPSG:4326"
    )

    # 4) Asset mapping
    print("\n--- Starting Real Asset Mapping ---")
    asset_gdf = map_assets_from_satellite_image(claim_gdf)

    # 5) Save assets with claim_id + village
    if asset_gdf is not None and not asset_gdf.empty:
        asset_gdf = asset_gdf.copy()
        asset_gdf["claim_id"] = claim_id
        asset_gdf["village"] = claim_data["village"]
        save_data_to_db(asset_gdf, "fra_assets")
        print("✅ Assets successfully detected and saved to database.")

        # 6) Generate claim + assets map (opens HTML in your browser from map_visualizer)
        map_path = generate_claim_asset_map(claim_gdf, asset_gdf)
        print(f"🗺️ Claim + assets map generated: {map_path}")
    else:
        print("ℹ️ No assets were detected in the satellite image.")


if __name__ == "__main__":
    run_setup()
