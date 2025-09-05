# ai_models/groundwater_offline.py
import pandas as pd
import math
from typing import Optional, Dict, Any, List
from pathlib import Path

CSV_PATH = Path("sample_data/groundwater_levels.csv")


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Haversine distance in kilometers between two lat/lon points.
    """
    R = 6371.0
    from math import radians, sin, cos, asin, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def _load_wells(csv_path: Path = CSV_PATH) -> pd.DataFrame:
    """
    Load cleaned groundwater CSV and ensure required columns exist & numeric types.
    Expected columns (case-sensitive): 'StationCode', 'Lat', 'Lon', 'WaterLevel_m_bgl', 'Datetime'
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Groundwater CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    # Normalize column names (strip whitespace)
    df.rename(columns=lambda c: c.strip(), inplace=True)

    required = {"Lat", "Lon", "WaterLevel_m_bgl"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV missing required columns. Found: {list(df.columns)}; required: {required}")

    # Coerce numeric types and drop invalid rows
    df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
    df["Lon"] = pd.to_numeric(df["Lon"], errors="coerce")
    df["WaterLevel_m_bgl"] = pd.to_numeric(df["WaterLevel_m_bgl"], errors="coerce")

    df = df.dropna(subset=["Lat", "Lon"]).reset_index(drop=True)
    return df


def groundwater_k_nearest(lat: float, lon: float, k: int = 3, max_km: Optional[float] = 150.0,
                          csv_path: Path = CSV_PATH) -> List[Dict[str, Any]]:
    """
    Return up to k nearest wells within max_km radius.
    If max_km is None, do not filter by distance.
    Each returned dict contains:
      - station_code, depth_m_bgl (float or None), when, distance_km (float), well_lat, well_lon
    """
    df = _load_wells(csv_path)

    # Compute distances vectorized
    df = df.copy()
    df["dist_km"] = df.apply(lambda r: _haversine(float(lat), float(lon), float(r["Lat"]), float(r["Lon"])), axis=1)

    if max_km is not None:
        df = df[df["dist_km"] <= float(max_km)]

    if df.empty:
        return []

    df = df.sort_values("dist_km").head(max(1, int(k)))

    wells: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        wells.append({
            "station_code": str(r.get("StationCode")) if "StationCode" in r.index else None,
            "depth_m_bgl": float(r["WaterLevel_m_bgl"]) if pd.notna(r["WaterLevel_m_bgl"]) else None,
            "when": r.get("Datetime") if "Datetime" in r.index else None,
            "distance_km": round(float(r["dist_km"]), 3),
            "well_lat": float(r["Lat"]),
            "well_lon": float(r["Lon"]),
        })
    return wells


def groundwater_stats(lat: float, lon: float, k: int = 3, max_km: Optional[float] = 150.0,
                      csv_path: Path = CSV_PATH) -> Optional[Dict[str, Any]]:
    """
    Aggregate the k-nearest wells (within max_km) and return:
      - avg_depth_m_bgl (float) (None if no valid depths),
      - min_distance_km (float),
      - k_used (int),
      - samples (list of well dicts)
    Returns None if no wells found within max_km.
    """
    wells = groundwater_k_nearest(lat, lon, k=k, max_km=max_km, csv_path=csv_path)
    if not wells:
        return None

    depths = [w["depth_m_bgl"] for w in wells if w["depth_m_bgl"] is not None]
    avg_depth = round(sum(depths)/len(depths), 2) if depths else None
    min_dist = min(w["distance_km"] for w in wells) if wells else None

    return {
        "avg_depth_m_bgl": avg_depth,
        "min_distance_km": min_dist,
        "k_used": len(wells),
        "samples": wells,
    }


# ----------------- CLI quick test -----------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Query nearest groundwater wells (Atal Jal CSV).")
    p.add_argument("--coords", type=str, help="lat,lon")
    p.add_argument("--lat", type=float)
    p.add_argument("--lon", type=float)
    p.add_argument("-k", type=int, default=3)
    p.add_argument("--max-km", type=float, default=150.0)
    args = p.parse_args()

    if args.coords:
        try:
            lat_s, lon_s = args.coords.split(",")
            lat = float(lat_s.strip()); lon = float(lon_s.strip())
        except Exception as e:
            raise SystemExit(f"Invalid --coords format: {e}")
    elif args.lat is not None and args.lon is not None:
        lat = args.lat; lon = args.lon
    else:
        s = input("Enter coordinates (lat,lon): ").strip()
        lat_s, lon_s = s.split(",")
        lat = float(lat_s); lon = float(lon_s)

    stats = groundwater_stats(lat, lon, k=args.k, max_km=args.max_km)
    if not stats:
        print("No wells found within the requested radius.")
    else:
        print(f"\nAverage depth (k={stats['k_used']}): {stats['avg_depth_m_bgl']} m bgl")
        print(f"Nearest distance: {stats['min_distance_km']} km")
        print("Samples:")
        for w in stats["samples"]:
            print(f"  - {w['station_code']}: depth={w['depth_m_bgl']} m (dist={w['distance_km']} km) when={w['when']}")
