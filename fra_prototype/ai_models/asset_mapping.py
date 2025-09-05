# ai_models/asset_mapping.py
import os
import numpy as np
import cv2
import geopandas as gpd
from shapely.geometry import Polygon
from dotenv import load_dotenv
from sentinelhub import (
    SentinelHubRequest, DataCollection, MimeType, CRS, BBox, SHConfig
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
    raise ValueError("⚠️ Sentinel Hub credentials not set in .env")

# ============================================================
# Evalscripts
# ============================================================

# TRUECOLOR (B04,B03,B02)
EVALSCRIPT_TRUECOLOR = """//VERSION=3
function setup() {
  return {
    input: ["B04","B03","B02"],
    output: { bands: 3 }
  };
}
function evaluatePixel(s) { return [s.B04, s.B03, s.B02]; }
"""

# NDVI
EVALSCRIPT_NDVI = """//VERSION=3
function setup(){ return { input:["B08","B04"], output:{ bands:1 } }; }
function evaluatePixel(s){ return [(s.B08 - s.B04) / (s.B08 + s.B04)]; }
"""

# NDWI (McFeeters; G - NIR) using B03/B08
EVALSCRIPT_NDWI = """//VERSION=3
function setup(){ return { input:["B03","B08"], output:{ bands:1 } }; }
function evaluatePixel(s){ return [(s.B03 - s.B08) / (s.B03 + s.B08)]; }
"""

# MULTIBAND: Blue, Green, Red, NIR, SWIR1
EVALSCRIPT_MULTIBAND = """//VERSION=3
function setup() {
  return {
    input: ["B02","B03","B04","B08","B11"],
    output: { bands: 5 }
  };
}
function evaluatePixel(s) { return [s.B02, s.B03, s.B04, s.B08, s.B11]; }
"""

# ============================================================
# Helpers
# ============================================================

def _normalize_to_uint8(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr).astype(np.float32)
    mn, mx = np.nanmin(a), np.nanmax(a)
    if not np.isfinite(mn) or not np.isfinite(mx) or mx - mn < 1e-12:
        return np.zeros_like(a, dtype=np.uint8)
    a = (a - mn) / (mx - mn + 1e-12)
    return (a * 255).clip(0, 255).astype(np.uint8)

def save_mask(mask, filename, thresh=None):
    """
    Save either:
    - a binary/grayscale mask (thresh -> 0/255),
    - or a visualization of multi-band arrays (map to RGB).

    Handles 1, 3, 4, or >3 channel inputs safely for cv2.imwrite.
    """
    m = np.asarray(mask)

    # Binary threshold case
    if thresh is not None and m.ndim <= 2:
        out = (m > thresh).astype(np.uint8) * 255
        cv2.imwrite(filename, out)
        print(f"💾 Saved mask: {filename}")
        return

    # Single-band (float or int) -> normalize to 8-bit
    if m.ndim == 2 or (m.ndim == 3 and m.shape[2] == 1):
        band = m if m.ndim == 2 else m[..., 0]
        out = _normalize_to_uint8(band)
        cv2.imwrite(filename, out)
        print(f"💾 Saved mask: {filename}")
        return

    # 3- or 4-channel -> normalize first 3 channels and save as RGB
    if m.ndim == 3 and m.shape[2] in (3, 4):
        rgb = np.dstack([_normalize_to_uint8(m[:, :, 0]),
                         _normalize_to_uint8(m[:, :, 1]),
                         _normalize_to_uint8(m[:, :, 2])])
        cv2.imwrite(filename, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        print(f"💾 Saved preview: {filename}")
        return

    # >3 channels (e.g., B,G,R,NIR,SWIR1): build an RGB preview using R,G,B = 2,1,0
    if m.ndim == 3 and m.shape[2] > 3:
        # safe indexing even if fewer than 3 bands for some reason
        r_idx = 2 if m.shape[2] > 2 else 0
        g_idx = 1 if m.shape[2] > 1 else 0
        b_idx = 0
        rgb = np.dstack([_normalize_to_uint8(m[:, :, r_idx]),
                         _normalize_to_uint8(m[:, :, g_idx]),
                         _normalize_to_uint8(m[:, :, b_idx])])
        cv2.imwrite(filename, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        print(f"💾 Saved multiband preview (RGB from bands {r_idx},{g_idx},{b_idx}): {filename}")
        return

    # Fallback
    out = _normalize_to_uint8(np.squeeze(m))
    cv2.imwrite(filename, out)
    print(f"💾 Saved (fallback) mask: {filename}")


def clean_mask(binary_mask: np.ndarray, close_iters=2, open_iters=0, dilate_iters=3):
    """
    Connect thin linear features (rivers) and thicken slightly.
    Input/Output are 0/1 arrays.
    """
    m = (binary_mask > 0).astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    if close_iters:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel, iterations=close_iters)
    if open_iters:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel, iterations=open_iters)
    if dilate_iters:
        m = cv2.dilate(m, kernel, iterations=dilate_iters)
    return m

# ============================================================
# Fetch Index from Sentinel Hub
# ============================================================
def fetch_index(claim_geometry, evalscript, filename, size=(1536, 1536),
                time_interval=("2023-06-01", "2023-10-31")):
    """
    Generic fetcher for single or multi-band arrays.
    Saves a visualization PNG and returns (numpy array, bbox).
    """
    bounds = claim_geometry.bounds
    buffer_deg = 0.01  # ~500–1100 m depending on latitude
    bbox = (bounds[0]-buffer_deg, bounds[1]-buffer_deg,
            bounds[2]+buffer_deg, bounds[3]+buffer_deg)
    sh_bbox = BBox(bbox, crs=CRS.WGS84)

    request = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L2A,
            time_interval=time_interval,
            mosaicking_order="mostRecent",
        )],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=sh_bbox,
        size=size,
        config=sh_config,
    )

    data = request.get_data()[0]

    # robust preview save
    if data.ndim == 2:
        save_mask(data, filename)
    elif data.ndim == 3:
        if data.shape[2] == 1:
            save_mask(data[..., 0], filename)
        else:
            save_mask(data, filename)  # multi-band preview
    else:
        save_mask(np.squeeze(data), filename)

    return data, bbox

def mask_to_geopolygons(mask, bbox, min_area=200):
    """
    Convert a binary mask (0/1 or 0/255) to polygons in EPSG:4326.
    min_area: minimum contour area in pixels.
    """
    minx, miny, maxx, maxy = bbox
    if mask.ndim == 3:
        mask = mask[..., 0]
    m = (mask > 0).astype(np.uint8)

    contours, _ = cv2.findContours(m * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h, w = m.shape
    polygons = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue
        coords = []
        for pt in contour:
            x, y = pt[0]
            lon = minx + (x / w) * (maxx - minx)
            lat = maxy - (y / h) * (maxy - miny)
            coords.append((lon, lat))
        if len(coords) > 2:
            polygons.append(Polygon(coords))
    return polygons

def fetch_rgb(claim_geometry, filename="truecolor_satellite.png",
              size=(1024, 1024),
              time_interval=("2023-06-01","2023-10-31")):
    """Save a proper 8-bit truecolor image."""
    bounds = claim_geometry.bounds
    buffer = 0.01
    bbox = (bounds[0]-buffer, bounds[1]-buffer, bounds[2]+buffer, bounds[3]+buffer)
    sh_bbox = BBox(bbox, crs=CRS.WGS84)

    request = SentinelHubRequest(
        evalscript=EVALSCRIPT_TRUECOLOR,
        input_data=[SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L2A,
            time_interval=time_interval,
            mosaicking_order="mostRecent"
        )],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=sh_bbox,
        size=size,
        config=sh_config,
    )

    data = request.get_data()[0]  # float reflectance 0..~1
    # to 8-bit RGB
    img = (_normalize_to_uint8(data) if data.ndim == 2
           else np.dstack([_normalize_to_uint8(data[:, :, i]) for i in range(3)]))
    cv2.imwrite(filename, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    print(f"🛰️ Saved true color satellite image at {filename}")
    return filename, bbox

# ============================================================
# Detect Assets
# ============================================================
def detect_assets(claim_geometry):
    """
    Detect forest, cropland, water_body, urban, barren_land around a claim.

    Improvements:
      - Higher-res fetch so rivers are not 1px.
      - MNDWI (Green vs SWIR1) + NDWI hybrid for water.
      - Morphology + tiny min_area keep thin rivers.
    """
    # Indices
    ndvi_raw, bbox = fetch_index(claim_geometry, EVALSCRIPT_NDVI, "debug_ndvi.png")
    ndwi_raw, _    = fetch_index(claim_geometry, EVALSCRIPT_NDWI, "debug_ndwi.png")

    # Multiband: Blue, Green, Red, NIR, SWIR1
    multiband, _ = fetch_index(claim_geometry, EVALSCRIPT_MULTIBAND, "debug_multiband.png")
    blue  = multiband[:, :, 0].astype(np.float32)
    green = multiband[:, :, 1].astype(np.float32)
    red   = multiband[:, :, 2].astype(np.float32)
    nir   = multiband[:, :, 3].astype(np.float32)
    swir1 = multiband[:, :, 4].astype(np.float32)

    # squeeze single-band arrays
    ndvi = ndvi_raw[..., 0] if ndvi_raw.ndim == 3 else ndvi_raw
    ndwi = ndwi_raw[..., 0] if ndwi_raw.ndim == 3 else ndwi_raw

    eps = 1e-6

    # Built-up (NDBI) and bare soil (BSI)
    ndbi = (swir1 - nir) / (swir1 + nir + eps)
    bsi  = ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue) + eps)

    save_mask(ndbi, "debug_ndbi.png")
    save_mask(bsi,  "debug_bsi.png")

    # ---- Water: MNDWI (Xu 2006) + NDWI hybrid ----
    mndwi = (green - swir1) / (green + swir1 + eps)
    save_mask(mndwi, "debug_mndwi.png")

    # Looser thresholds to capture rivers + exclude vegetation
    water_raw = (mndwi > -0.05) | ((ndwi > 0.05) & (ndvi < 0.30) & (bsi < 0.0))
    water_mask = clean_mask(water_raw.astype(np.uint8), close_iters=2, open_iters=0, dilate_iters=3)
    save_mask(water_mask, "debug_water_mask.png")

    # Truecolor for reference
    fetch_rgb(claim_geometry, "truecolor_satellite.png")

    # --- Classification to polygons ---
    geoms, types = [], []

    # Forest
    for poly in mask_to_geopolygons((ndvi > 0.50).astype(np.uint8), bbox, min_area=200):
        geoms.append(poly); types.append("forest")

    # Cropland
    for poly in mask_to_geopolygons(((ndvi > 0.20) & (ndvi <= 0.50)).astype(np.uint8), bbox, min_area=200):
        geoms.append(poly); types.append("cropland")

    # Water (small min_area so thin rivers survive)
    for poly in mask_to_geopolygons(water_mask, bbox, min_area=5):
        geoms.append(poly); types.append("water_body")

    # Urban
    for poly in mask_to_geopolygons((ndbi > 0.20).astype(np.uint8), bbox, min_area=200):
        geoms.append(poly); types.append("urban")

    # Barren
    for poly in mask_to_geopolygons((bsi > 0.20).astype(np.uint8), bbox, min_area=200):
        geoms.append(poly); types.append("barren_land")

    return gpd.GeoDataFrame({"asset_type": types}, geometry=geoms, crs="EPSG:4326")

# ============================================================
# Orchestrator
# ============================================================
def map_assets_from_satellite_image(claim_gdf):
    """
    Given a claim GeoDataFrame (EPSG:4326, point geometry), detect assets and return a GeoDataFrame.
    """
    if claim_gdf.empty:
        return gpd.GeoDataFrame(columns=["asset_type", "geometry"], crs="EPSG:4326")

    claim_geometry = claim_gdf.geometry.iloc[0]
    asset_gdf = detect_assets(claim_geometry)
    return asset_gdf

