# check_nearest_wells.py
"""
Usage:
  python check_nearest_wells.py                 -> interactive prompt for lat,lon
  python check_nearest_wells.py 22.3352 77.1025 -> use CLI args (lat lon)
  python check_nearest_wells.py --file pts.csv  -> read points CSV with columns lat,lon
  python check_nearest_wells.py --lat 13.13 --lon 78.12 --n 10
"""

import pandas as pd
import math
import argparse
import sys

CSV_PATH = "sample_data/groundwater_levels.csv"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def nearest_wells_for_point(df, lat, lon, n=5):
    # compute distances vectorized for speed
    dists = df.apply(lambda r: haversine(lat, lon, float(r["Lat"]), float(r["Lon"])), axis=1)
    df2 = df.copy()
    df2["dist_km"] = dists
    df2 = df2.sort_values("dist_km").head(n)
    return df2[["StationCode", "Lat", "Lon", "WaterLevel_m_bgl", "Datetime", "dist_km"]]

def load_wells(csv_path=CSV_PATH):
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ Groundwater CSV not found: {csv_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        sys.exit(1)
    # ensure numeric columns
    df = df.rename(columns=lambda c: c.strip())
    if "Lat" not in df.columns or "Lon" not in df.columns:
        print("❌ CSV missing 'Lat' or 'Lon' columns.")
        sys.exit(1)
    return df

def run_single(lat, lon, n):
    df = load_wells()
    res = nearest_wells_for_point(df, lat, lon, n=n)
    if res.empty:
        print("No wells found in CSV.")
        return
    print(f"\n🔍 Nearest {n} wells to ({lat:.6f}, {lon:.6f}):\n")
    print(res.to_string(index=False, formatters={
        "dist_km": lambda v: f"{v:.3f}",
        "WaterLevel_m_bgl": lambda v: f"{v:.2f}" if pd.notna(v) else "NA"
    }))

def run_from_file(points_csv, n):
    pts = pd.read_csv(points_csv)
    if not {"lat","lon"}.issubset(set(pts.columns.str.lower())):
        # try capitalized
        if not {"Lat","Lon"}.issubset(set(pts.columns)):
            print("❌ points CSV must contain 'lat,lon' (or 'Lat','Lon') columns.")
            sys.exit(1)
        else:
            pts = pts.rename(columns={"Lat":"lat","Lon":"lon"})
    else:
        # normalize to lowercase column names
        pts = pts.rename(columns={c:c.lower() for c in pts.columns})
    df = load_wells()
    for i, row in pts.iterrows():
        lat = float(row["lat"]); lon = float(row["lon"])
        print(f"\n=== Point #{i+1}: {lat},{lon} ===")
        res = nearest_wells_for_point(df, lat, lon, n=n)
        if res.empty:
            print("  No wells found.")
        else:
            print(res.to_string(index=False, formatters={
                "dist_km": lambda v: f"{v:.3f}",
                "WaterLevel_m_bgl": lambda v: f"{v:.2f}" if pd.notna(v) else "NA"
            }))

def main():
    parser = argparse.ArgumentParser(description="Find nearest groundwater wells from cleaned Atal Jal CSV")
    parser.add_argument("lat", nargs="?", type=float, help="Latitude (decimal degrees)")
    parser.add_argument("lon", nargs="?", type=float, help="Longitude (decimal degrees)")
    parser.add_argument("--n", type=int, default=5, help="Number of nearest wells to return")
    parser.add_argument("--file", "-f", help="CSV file with points (columns: lat,lon) to query")
    args = parser.parse_args()

    if args.file:
        run_from_file(args.file, args.n)
        return

    if args.lat is None or args.lon is None:
        # interactive prompt
        try:
            s = input("Enter coordinates (lat,lon) or press Enter to quit: ").strip()
            if not s:
                print("No input. Exiting.")
                return
            parts = [p.strip() for p in s.replace(",", " ").split()]
            if len(parts) < 2:
                print("Please enter both lat and lon, separated by space or comma.")
                return
            lat = float(parts[0]); lon = float(parts[1])
            run_single(lat, lon, args.n)
        except Exception as e:
            print(f"Input error: {e}")
            return
    else:
        run_single(args.lat, args.lon, args.n)

if __name__ == "__main__":
    main()
