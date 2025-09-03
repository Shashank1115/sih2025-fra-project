# ai_models/asset_mapping.py
import geopandas as gpd
from shapely.geometry import Polygon


def map_assets_from_satellite_image(image_path, village_coords):
    """
    Placeholder function for AI-based asset mapping.
    MODIFIED to return 'forest_cover' and 'homestead' instead.
    """
    print(f"Simulating asset mapping for image: {image_path}")
    
    lat, lon = village_coords
    
    # Create different dummy polygons for the new assets
    forest_poly = Polygon([(lon + 0.02, lat + 0.02), (lon + 0.03, lat + 0.02), (lon + 0.03, lat + 0.03)])
    homestead_poly = Polygon([(lon - 0.01, lat - 0.01), (lon - 0.005, lat - 0.01), (lon - 0.01, lat - 0.005)])
    
    # MODIFIED asset data to return different assets
    asset_data = {
        'asset_type': ['forest_cover', 'homestead'],
        'geometry': [forest_poly, homestead_poly]
    }
    
    gdf = gpd.GeoDataFrame(asset_data, crs="EPSG:4326")
    return gdf