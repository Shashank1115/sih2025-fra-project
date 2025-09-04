# asset_evaluator.py
import sqlite3
import geopandas as gpd
import pandas as pd
from shapely import wkt
from shapely.geometry import Point
from ai_models.groundwater_offline import groundwater_depth_near

DB_PATH = "fra_claims.db"

def evaluate_assets(buffer_km=1.0, groundwater_max_depth_m=15.0):
    conn = sqlite3.connect(DB_PATH)

    claims = pd.read_sql("SELECT * FROM fra_claims;", conn)
    assets = pd.read_sql("SELECT * FROM fra_assets;", conn)

    assets["geometry"] = assets["geometry"].apply(wkt.loads)
    assets = gpd.GeoDataFrame(assets, geometry="geometry", crs="EPSG:4326")

    results = []
    for _, claim in claims.iterrows():
        lat, lon = map(float, claim["coordinates"].split(","))
        claim_point = Point(lon, lat)

        # Buffer around claim
        buffer = gpd.GeoDataFrame(geometry=[claim_point.buffer(buffer_km / 111)], crs="EPSG:4326")
        claim_assets = gpd.overlay(assets, buffer, how="intersection")

        # Area in hectares
        claim_assets = claim_assets.to_crs(epsg=3857)
        farm_area   = claim_assets[claim_assets["asset_type"] == "cropland"].area.sum() / 10_000
        forest_area = claim_assets[claim_assets["asset_type"] == "forest"].area.sum() / 10_000
        water_area  = claim_assets[claim_assets["asset_type"] == "water_body"].area.sum() / 10_000
        urban_area  = claim_assets[claim_assets["asset_type"] == "urban"].area.sum() / 10_000
        barren_area = claim_assets[claim_assets["asset_type"] == "barren_land"].area.sum() / 10_000

        vegetation_area = farm_area + forest_area

        # --- Groundwater with fallback ---
        gw = groundwater_depth_near(lat, lon, max_km=100.0)  # normal cutoff
        gw_fallback = False

        if gw is None:
            gw = groundwater_depth_near(lat, lon, max_km=200.0)  # fallback (extended range)
            gw_fallback = gw is not None

        depth_m = gw["depth_m_bgl"] if gw else None
        gw_ok = (depth_m is not None) and (depth_m <= groundwater_max_depth_m)

        # --- Evaluation ---
        has_sufficient_land = vegetation_area >= 2
        has_water_surface = water_area > 0

        if has_sufficient_land and has_water_surface and gw_ok:
            status = f"✅ Sufficient (Veg={vegetation_area:.2f}ha, Water={water_area:.2f}ha, GW≤{groundwater_max_depth_m}m)"
        else:
            reasons = []
            if not has_sufficient_land: reasons.append(f"Veg={vegetation_area:.2f}ha<2")
            if not has_water_surface:  reasons.append("no surface water")
            if depth_m is None:
                reasons.append("GW=unknown")
            elif not gw_ok:
                reasons.append(f"GW={depth_m:.1f}m bgl>{groundwater_max_depth_m}")
            if gw_fallback:
                reasons.append(f"⚠ using nearest well {gw['distance_km']} km away")
            status = "❌ Insufficient (" + "; ".join(reasons) + ")"

        results.append({
            "patta_holder": claim["patta_holder"],
            "village": claim["village"],
            "coordinates": claim["coordinates"],
            "claim_status": claim["claim_status"],
            "vegetation_area(ha)": round(vegetation_area, 2),
            "water_area(ha)": round(water_area, 2),
            "urban_area(ha)": round(urban_area, 2),
            "barren_area(ha)": round(barren_area, 2),
            "groundwater_depth(m_bgl)": round(depth_m, 2) if depth_m is not None else None,
            "gw_distance_to_well_km": gw["distance_km"] if gw else None,
            "gw_measured_on": gw["when"] if gw else None,
            "gw_station_code": gw["station_code"] if gw else None,
            "evaluation": status
        })

    conn.close()
    return pd.DataFrame(results)


if __name__ == "__main__":
    df = evaluate_assets(buffer_km=1.0, groundwater_max_depth_m=15.0)
    print("\n📊 FRA Claim Evaluation:\n")
    print(df.to_string(index=False))
