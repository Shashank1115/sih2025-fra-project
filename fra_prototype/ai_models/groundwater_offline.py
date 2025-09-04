# ai_models/groundwater_offline.py
import os, math
import pandas as pd

CSV_PATH = os.path.join("sample_data", "groundwater_levels.csv")

def _hav(lat1, lon1, lat2, lon2):
    R = 6371.0
    from math import radians, sin, cos, asin, sqrt
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2*R*asin(sqrt(a))

def groundwater_depth_near(lat: float, lon: float, max_km: float = 50.0):
    """Find nearest well within max_km from cleaned Atal Jal CSV."""
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}, run prepare_groundwater_csv.py first")

    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return None

    # quick coarse filter
    box = df[(df["Lat"].between(lat-1, lat+1)) & (df["Lon"].between(lon-1, lon+1))].copy()
    if box.empty:
        box = df

    best_row, best_d = None, 1e9
    for _, r in box.iterrows():
        d = _hav(lat, lon, float(r["Lat"]), float(r["Lon"]))
        if d < best_d and d <= max_km:
            best_d = d; best_row = r

    if best_row is None:
        return None

    return {
        "depth_m_bgl": float(best_row["WaterLevel_m_bgl"]),
        "distance_km": round(best_d, 2),
        "when": (str(best_row["Datetime"]) if "Datetime" in best_row and pd.notna(best_row["Datetime"]) else None),
        "station_code": (str(best_row["StationCode"]) if "StationCode" in best_row and pd.notna(best_row["StationCode"]) else None),
        "well_lat": float(best_row["Lat"]),
        "well_lon": float(best_row["Lon"]),
    }
