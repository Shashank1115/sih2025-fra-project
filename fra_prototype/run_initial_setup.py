# run_initial_setup.py
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from ai_models.digitization import extract_info_from_image
from ai_models.asset_mapping import map_assets_from_satellite_image
from backend.database import create_database, save_data_to_db

def run_setup():
    # 1. Create the database
    create_database()

    # 2. Prepare sample data
    # IMPORTANT: Create a sample image file at 'sample_data/sample_doc.png'
    # with the text from the previous instructions.
    sample_doc_path = "sample_data/sample_doc.png"
    sample_satellite_image = "dummy_path.tif" # Not used by placeholder

    # 3. Run Digitization Model
    claim_data = extract_info_from_image(sample_doc_path)
    if claim_data and claim_data['coordinates'] != 'Unknown':
        lat, lon = map(float, claim_data['coordinates'].split(','))
        
        # Create GeoDataFrame for claims
        claim_gdf = gpd.GeoDataFrame(
            pd.DataFrame([claim_data]), 
            geometry=[Point(lon, lat)],
            crs="EPSG:4326"
        )
        save_data_to_db(claim_gdf.drop(columns=['coordinates']), 'fra_claims')

        # 4. Run Asset Mapping Model
        asset_gdf = map_assets_from_satellite_image(sample_satellite_image, (lat, lon))
        asset_gdf['village'] = claim_data['village'] # Assign village
        save_data_to_db(asset_gdf, 'fra_assets')
    else:
        print("Could not extract data from document. Setup aborted.")

if __name__ == "__main__":
    run_setup()