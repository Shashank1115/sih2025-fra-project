import os
import numpy as np
import cv2  # OpenCV for computer vision
import geopandas as gpd
from shapely.geometry import Polygon
from dotenv import load_dotenv

from sentinelhub import (
    SentinelHubRequest,
    DataCollection,
    MimeType,
    CRS,
    BBox,
    SHConfig
)

# ============================================================
# Load Sentinel Hub credentials
# ============================================================
load_dotenv()

CLIENT_ID = os.getenv("SH_CLIENT_ID")
CLIENT_SECRET = os.getenv("SH_CLIENT_SECRET")

sh_config = SHConfig()
sh_config.sh_client_id = CLIENT_ID
sh_config.sh_client_secret = CLIENT_SECRET

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("⚠️ Sentinel Hub credentials not set in .env (SH_CLIENT_ID / SH_CLIENT_SECRET)")

# ============================================================
# Evalscript for True Color Sentinel-2
# ============================================================
evalscript_true_color = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B03", "B02"], // Red, Green, Blue
    output: { bands: 3 }
  };
}

function evaluatePixel(sample) {
  return [sample.B04, sample.B03, sample.B02];
}
"""

# ============================================================
# Image Enhancement Helpers
# ============================================================
def enhance_image(image_array):
    """Apply histogram equalization for better contrast."""
    if image_array.dtype != np.uint8:
        image_array = (255 * image_array).astype(np.uint8)

    img_yuv = cv2.cvtColor(image_array, cv2.COLOR_RGB2YUV)
    img_yuv[:, :, 0] = cv2.equalizeHist(img_yuv[:, :, 0])
    enhanced = cv2.cvtColor(img_yuv, cv2.COLOR_YUV2RGB)
    return enhanced


def gamma_correction(image, gamma=1.5):
    """Brighten image using gamma correction."""
    invGamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** invGamma) * 255
                      for i in np.arange(256)]).astype("uint8")
    return cv2.LUT(image, table)

# ============================================================
# Function to fetch satellite image
# ============================================================
def get_satellite_image_for_claim(claim_geometry, image_path="satellite_image.jpg"):
    # Expand bounding box around claim
    bounds = claim_geometry.bounds
    buffer = 0.008  # adjust zoom level

    bbox = BBox([
        bounds[0] - buffer,
        bounds[1] - buffer,
        bounds[2] + buffer,
        bounds[3] + buffer
    ], crs=CRS.WGS84)

    request = SentinelHubRequest(
        evalscript=evalscript_true_color,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,  # 🔑 better images (BOA)
                time_interval=("2023-01-01", "2023-10-30"),
                mosaicking_order="mostRecent"
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.JPG)],  # 🔑 switched to JPEG
        bbox=bbox,
        size=(1024, 1024),  # higher resolution than before
        config=sh_config,
    )

    image_data_list = request.get_data()
    if not image_data_list:
        print("❌ No image data returned")
        return None

    image_array = image_data_list[0]

    # --- Apply enhancements ---
    #image_array = enhance_image(image_array)
    image_array = gamma_correction(image_array, gamma=1.6)

    # Save as JPG
    cv2.imwrite(image_path, cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR))
    print(f"✅ Enhanced high-res satellite image saved at {image_path}")
    return image_path

# ============================================================
# Basic Asset Detection
# ============================================================
def detect_assets_in_image(image_path, image_bounds):
    """
    Uses basic computer vision (color segmentation) to detect water and vegetation.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"⚠️ Could not read image at {image_path}")
        return gpd.GeoDataFrame({'asset_type': [], 'geometry': []}, crs="EPSG:4326")

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Water detection (blue areas)
    lower_blue = np.array([100, 150, 50])
    upper_blue = np.array([140, 255, 255])
    water_mask = cv2.inRange(hsv, lower_blue, upper_blue)

    # Vegetation detection (green areas)
    lower_green = np.array([36, 50, 70])
    upper_green = np.array([89, 255, 255])
    veg_mask = cv2.inRange(hsv, lower_green, upper_green)

    assets_found = []
    if np.sum(water_mask) > 1000:
        assets_found.append("water_body")
    if np.sum(veg_mask) > 10000:
        assets_found.append("farm")

    # Dummy polygons for now (later can map via geo-transform)
    dummy_polygons = {
        'water_body': Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
        'farm': Polygon([(2, 2), (2, 3), (3, 3), (3, 2)])
    }

    geometries = [dummy_polygons.get(asset) for asset in assets_found]
    gdf = gpd.GeoDataFrame({'asset_type': assets_found}, geometry=geometries, crs="EPSG:4326")

    return gdf

# ============================================================
# Orchestrator
# ============================================================
def map_assets_from_satellite_image(claim_gdf):
    """
    Main orchestrator: fetch image + detect assets.
    """
    if claim_gdf.empty:
        return gpd.GeoDataFrame({'asset_type': [], 'geometry': []}, crs="EPSG:4326")

    claim_geometry = claim_gdf.geometry.iloc[0]
    image_path = get_satellite_image_for_claim(claim_geometry)

    if image_path:
        return detect_assets_in_image(image_path, claim_geometry.bounds)
    else:
        return gpd.GeoDataFrame({'asset_type': [], 'geometry': []}, crs="EPSG:4326")
