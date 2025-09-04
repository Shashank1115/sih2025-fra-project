# prepare_groundwater_csv.py
import os
import re
import pandas as pd

RAW = os.path.join("sample_data", "Atal_Jal_Disclosed_Ground_Water_Level-2015-2022.csv")
OUT = os.path.join("sample_data", "groundwater_levels.csv")

COL_LAT, COL_LON, COL_WELL = "Latitude", "Longitude", "Well_ID"

# Matches columns like "Pre-monsoon_2015 (meters below ground level)"
SEASON_RE = re.compile(r"^(Pre|Post)-monsoon_(\d{4}).*", re.IGNORECASE)

def find_seasonal_columns(df):
    found = []
    for c in df.columns:
        m = SEASON_RE.match(str(c).strip())
        if m:
            season = m.group(1).title()
            year = int(m.group(2))
            found.append((c, season, year))
    return found

def choose_latest_value(row, seasonal_cols):
    """
    Pick the most recent non-null water level for this row.
    Preference: higher year first, within same year Post before Pre.
    """
    # sort by year desc, Post first
    order = sorted(seasonal_cols, key=lambda t: (t[2], 1 if t[1]=="Pre" else 2), reverse=True)
    for col, season, year in order:
        val = row.get(col)
        if pd.notna(val):
            try:
                v = float(val)
                return v, f"{season}-monsoon_{year}"
            except Exception:
                continue
    return None, None

def main():
    if not os.path.exists(RAW):
        raise FileNotFoundError(f"Missing: {RAW}")

    # file uses latin1 encoding
    df = pd.read_csv(RAW, encoding="latin1")

    seasonal_cols = find_seasonal_columns(df)
    if not seasonal_cols:
        raise ValueError("❌ No seasonal water level columns found.")

    out_rows = []
    for _, row in df.iterrows():
        lat = pd.to_numeric(row.get(COL_LAT), errors="coerce")
        lon = pd.to_numeric(row.get(COL_LON), errors="coerce")
        well = row.get(COL_WELL)

        if pd.isna(lat) or pd.isna(lon):
            continue

        val, label = choose_latest_value(row, seasonal_cols)
        if val is None:
            continue

        out_rows.append({
            "StationCode": str(well) if pd.notna(well) else None,
            "Lat": float(lat),
            "Lon": float(lon),
            "WaterLevel_m_bgl": float(val),
            "Datetime": label,  # e.g. "Post-monsoon_2019"
        })

    if not out_rows:
        raise ValueError("❌ No wells with valid water levels found.")

    clean = pd.DataFrame(out_rows)

    # Drop duplicates, keep the most recent per well
    if "StationCode" in clean.columns and clean["StationCode"].notna().any():
        clean = clean.sort_values("Datetime").drop_duplicates(subset=["StationCode"], keep="last")
    else:
        clean["coord_key"] = clean["Lat"].round(5).astype(str) + "," + clean["Lon"].round(5).astype(str)
        clean = clean.sort_values("Datetime").drop_duplicates(subset=["coord_key"], keep="last")
        clean = clean.drop(columns=["coord_key"])

    clean.to_csv(OUT, index=False)
    print(f"✅ Saved cleaned groundwater CSV: {OUT} (rows={len(clean)})")
    print("   Example rows:")
    print(clean.head())

if __name__ == "__main__":
    main()
