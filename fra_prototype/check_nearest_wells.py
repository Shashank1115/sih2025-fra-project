# check_nearest_wells.py
import pandas as pd
import math

CSV_PATH = "sample_data/groundwater_levels.csv"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def nearest_wells(lat, lon, n=5):
    df = pd.read_csv(CSV_PATH)
    df["dist_km"] = df.apply(lambda r: haversine(lat, lon, r["Lat"], r["Lon"]), axis=1)
    df = df.sort_values("dist_km").head(n)
    return df[["StationCode", "Lat", "Lon", "WaterLevel_m_bgl", "Datetime", "dist_km"]]

if __name__ == "__main__":
    # try Harda
    print("🔍 Nearest wells to Harda (22.3352,77.1025):")
    print(nearest_wells(22.3352, 77.1025))

    # try Mehsana, Gujarat
    print("\n🔍 Nearest wells to Mehsana (23.5871,72.3693):")
    print(nearest_wells(23.5871, 72.3693))

    # try Kolar, Karnataka
    print("\n🔍 Nearest wells to Kolar (13.1367,78.1290):")
    print(nearest_wells(13.1367, 78.1290))
