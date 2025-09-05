# asset_evaluator.py
import sqlite3
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely import wkt
from ai_models.groundwater_offline import groundwater_stats

# import the mapper implemented at ai_models/asset_mapping.py
from ai_models.asset_mapping import map_assets_from_satellite_image

DB_PATH = "fra_claims.db"


def recommend_schemes(row, max_schemes=4):
    """
    Priority recommender that scores candidate schemes using simple weights
    and returns the top `max_schemes` schemes for a claim row.

    Inputs:
      row : dict-like (a result_row from evaluate_assets or a DataFrame row)
      max_schemes : int, maximum schemes to return

    Returns:
      list of scheme names (length <= max_schemes)
    """
    # safe extractors
    veg = row.get("vegetation_area(ha)") if isinstance(row, dict) else row["vegetation_area(ha)"]
    wat = row.get("water_area(ha)") if isinstance(row, dict) else row["water_area(ha)"]
    urb = row.get("urban_area(ha)") if isinstance(row, dict) else row["urban_area(ha)"]
    bar = row.get("barren_area(ha)") if isinstance(row, dict) else row["barren_area(ha)"]
    gw  = row.get("groundwater_depth(m_bgl)") if isinstance(row, dict) else row["groundwater_depth(m_bgl)"]

    # normalize None -> 0 for numeric comparison where appropriate
    veg = 0.0 if veg is None else float(veg)
    wat = 0.0 if wat is None else float(wat)
    urb = 0.0 if urb is None else float(urb)
    bar = 0.0 if bar is None else float(bar)
    # gw: None stays None (we need to check existence)
    
    # scoring dict
    scores = {}

    # --- Agriculture & Farmer support ---
    # PM-KISAN (high priority if meaningful cropland/vegetation)
    scores["PM-KISAN"] = 2.0 if veg >= 2.0 else (1.0 if veg >= 0.5 else 0.0)
    # PMFBY (crop insurance) — needs cropland
    scores["PMFBY"] = 1.5 if veg >= 1.0 else 0.5 if veg >= 0.2 else 0.0
    # Soil Health / NMSA (agri improvements)
    scores["Soil Health Card"] = 1.0 if veg >= 0.5 else 0.0
    scores["NMSA"] = 1.2 if veg >= 1.0 else 0.4 if veg > 0 else 0.0

    # --- Water & Irrigation ---
    # Jal Jeevan Mission (piped water) — surface water presence raises priority
    scores["Jal Jeevan Mission"] = 2.0 if wat > 0.0 else (1.0 if (gw is not None and gw <= 15) else 0.2)
    # PMKSY irrigation support
    scores["PMKSY"] = 1.5 if (wat > 0.0 or (gw is not None and gw <= 15) or veg >= 2.0) else 0.2
    # MGNREGA Water Works
    scores["MGNREGA Water Works"] = 1.4 if (wat > 0.0 or bar > 0.1 or (gw is not None and gw > 15)) else 0.3

    # --- Housing & Basic Services (if settlements detected) ---
    scores["PMAY-G"] = 2.0 if urb >= 1.0 else (1.0 if urb >= 0.2 else 0.0)
    scores["Saubhagya (electrification)"] = 1.0 if urb > 0.0 else 0.3
    scores["PM Ujjwala"] = 0.8 if urb > 0.0 else 0.4
    scores["PMGSY (rural roads)"] = 1.0 if urb > 0.0 or veg > 1.0 else 0.2

    # --- Land reclamation & livelihood ---
    scores["MGNREGA Land Dev"] = 1.5 if bar > 0.2 else 0.5 if bar > 0.05 else 0.0
    scores["RKVY"] = 1.0 if bar > 0.1 or veg > 0.5 else 0.0
    scores["ITDP/TSP"] = 1.0 if veg < 2.0 and (urb > 0.0 or bar > 0.0) else 0.4

    # --- Special forest/tribal schemes ---
    scores["MFP Scheme (TRIFED)"] = 1.8 if veg >= 1.0 else 0.5
    scores["Van Dhan Yojana"] = 1.5 if veg >= 1.0 else 0.4
    scores["Green India Mission"] = 1.2 if veg >= 1.0 else 0.2

    # --- Safety-net / livelihood diversification when land/water poor ---
    poor_land = (veg < 2.0) and (wat == 0.0) and (gw is None or gw > 15)
    if poor_land:
        scores["Jal Shakti (check dams/borewells)"] = 1.8
        scores["NRLM (SHG / livelihoods)"] = 1.6
        scores["Skill India"] = 1.0
    else:
        scores["Jal Shakti (check dams/borewells)"] = 0.6 if (wat == 0.0 and (gw is None or gw > 15)) else 0.2
        scores["NRLM (SHG / livelihoods)"] = 0.6 if veg < 2.0 else 0.2
        scores["Skill India"] = 0.4

    # --- Small extras (electable when high combined score) ---
    scores["PM Fasal Bima Yojana (detailed)"] = scores.get("PMFBY", 0.0)  # aliasing to keep options
    scores["Minor Irrigation / Micro-irrigation"] = 1.0 if veg >= 1.0 and (wat > 0.0 or (gw is not None and gw <= 15)) else 0.3

    # Remove any zero-score schemes and sort by score desc
    scored = [(scheme, float(score)) for scheme, score in scores.items() if score and score > 0.0]

    if not scored:
        return []

    # sort by score desc, tie-breaker: custom priority list (higher priority earlier)
    priority_order = [
        "PM-KISAN", "Jal Jeevan Mission", "PMAY-G", "PMFBY",
        "MGNREGA Water Works", "MFP Scheme (TRIFED)", "NRLM (SHG / livelihoods)",
        "MGNREGA Land Dev", "PMKSY", "Van Dhan Yojana", "NMSA", "Soil Health Card"
    ]
    def sort_key(item):
        name, s = item
        # higher score first; if tie, priority_order index (lower is better)
        try:
            pr = priority_order.index(name)
        except ValueError:
            pr = len(priority_order) + 10
        return (-s, pr)

    scored.sort(key=sort_key)

    # pick top N unique canonical names (avoid alias duplicates)
    chosen = []
    seen_canonical = set()
    alias_map = {
        "PM Fasal Bima Yojana (detailed)": "PMFBY",
    }

    for name, s in scored:
        canonical = alias_map.get(name, name)
        if canonical in seen_canonical:
            continue
        chosen.append(canonical)
        seen_canonical.add(canonical)
        if len(chosen) >= max_schemes:
            break

    return chosen


def evaluate_assets(buffer_km=1.0,
                    groundwater_max_depth_m=15.0,
                    gw_k=3,
                    gw_max_km=150.0,
                    mapper_kwargs=None):
    """
    Evaluate FRA claims by area of assets around a claim and groundwater.

    mapper_kwargs: optional dict forwarded to mapper if it accepts them.
    """
    if mapper_kwargs is None:
        mapper_kwargs = {}

    # load claims and (optionally) precomputed assets table
    conn = sqlite3.connect(DB_PATH)
    claims = pd.read_sql("SELECT * FROM fra_claims;", conn)
    try:
        assets = pd.read_sql("SELECT * FROM fra_assets;", conn)
    except Exception:
        assets = pd.DataFrame()
    conn.close()

    # prepare assets_gdf just for compatibility (not used by mapper)
    if assets.empty:
        assets_gdf = gpd.GeoDataFrame(columns=["asset_type", "geometry"], geometry=[], crs="EPSG:4326")
    else:
        if "geometry" in assets.columns:
            assets = assets.copy()
            assets["geometry"] = assets["geometry"].apply(lambda g: wkt.loads(g) if pd.notna(g) else None)
            assets_gdf = gpd.GeoDataFrame(assets, geometry="geometry", crs="EPSG:4326")
        else:
            assets_gdf = gpd.GeoDataFrame(columns=list(assets.columns) + ["geometry"], geometry=[], crs="EPSG:4326")

    results = []

    if claims.empty:
        return pd.DataFrame(results)

    for _, claim in claims.iterrows():
        coords_text = claim.get("coordinates", "")
        try:
            parts = [c.strip() for c in coords_text.split(",")]
            if len(parts) != 2:
                raise ValueError("invalid coords")
            # original data used "lat,lon" — handle that first, otherwise try reversed
            lat = float(parts[0]); lon = float(parts[1])
        except Exception:
            try:
                lon = float(parts[0]); lat = float(parts[1])
            except Exception:
                lat = lon = None

        if lat is None or lon is None:
            results.append({
                "patta_holder": claim.get("patta_holder"),
                "village": claim.get("village"),
                "coordinates": coords_text,
                "claim_status": claim.get("claim_status"),
                "vegetation_area(ha)": None,
                "water_area(ha)": None,
                "urban_area(ha)": None,
                "barren_area(ha)": None,
                "groundwater_depth(m_bgl)": None,
                "gw_distance_to_well_km": None,
                "gw_k_used": 0,
                "evaluation": "❌ Insufficient (invalid coordinates)",
                "recommended_schemes": []
            })
            continue

        # build claim point GeoDataFrame (Point expects lon, lat)
        claim_point = gpd.GeoDataFrame(
            [{"patta_holder": claim.get("patta_holder"), "village": claim.get("village")}],
            geometry=[Point(lon, lat)],
            crs="EPSG:4326"
        )

        # buffer in meters (EPSG:3857)
        claim_3857 = claim_point.to_crs(epsg=3857)
        buffer_m = float(buffer_km) * 1000.0
        buff_geom_3857 = claim_3857.geometry.iloc[0].buffer(buffer_m)

        # call mapper. Some mappers may not accept kwargs, so fall back gracefully.
        try:
            if mapper_kwargs:
                try:
                    detected_gdf = map_assets_from_satellite_image(claim_point, **mapper_kwargs)
                except TypeError:
                    detected_gdf = map_assets_from_satellite_image(claim_point)
            else:
                detected_gdf = map_assets_from_satellite_image(claim_point)
        except Exception as exc:
            print(f"WARNING: asset mapper failed for claim {claim.get('patta_holder')} ({coords_text}): {exc}")
            detected_gdf = gpd.GeoDataFrame(columns=["asset_type", "geometry"], geometry=[], crs="EPSG:4326")

        # default areas
        farm_area_ha = forest_area_ha = water_area_ha = urban_area_ha = barren_area_ha = 0.0

        if detected_gdf is not None and not detected_gdf.empty:
            if detected_gdf.crs is None:
                detected_gdf = detected_gdf.set_crs(epsg=4326)
            try:
                detected_3857 = detected_gdf.to_crs(epsg=3857).copy()
            except Exception:
                detected_3857 = detected_gdf.copy()
                detected_3857.set_crs(epsg=4326, inplace=True)
                detected_3857 = detected_3857.to_crs(epsg=3857)

            try:
                detected_3857["geometry"] = detected_3857["geometry"].intersection(buff_geom_3857)
            except Exception:
                pass

            detected_3857 = detected_3857[~detected_3857.geometry.is_empty & detected_3857.geometry.notna()].copy()
            if not detected_3857.empty:
                detected_3857["area_m2"] = detected_3857.geometry.area
                detected_3857["area_ha"] = detected_3857["area_m2"] / 10000.0

                def area_sum(asset_type):
                    subset = detected_3857[detected_3857["asset_type"] == asset_type]
                    if subset.empty:
                        return 0.0
                    return float(subset["area_ha"].sum())

                farm_area_ha = area_sum("cropland")
                forest_area_ha = area_sum("forest")
                water_area_ha = area_sum("water_body")
                urban_area_ha = area_sum("urban")
                barren_area_ha = area_sum("barren_land")

        vegetation_area = farm_area_ha + forest_area_ha

        # groundwater
        gw_info = groundwater_stats(lat, lon, k=gw_k, max_km=gw_max_km)
        if gw_info:
            depth_m = gw_info.get("avg_depth_m_bgl")
            mean_dist_km = gw_info.get("mean_distance_km")
            k_used = gw_info.get("k_used", 0)
        else:
            depth_m = None
            mean_dist_km = None
            k_used = 0

        gw_ok = (depth_m is not None) and (depth_m <= groundwater_max_depth_m)

        # decision rule
        has_sufficient_land = (vegetation_area >= 2.0)
        has_surface_water = (water_area_ha > 0.0)

        if has_sufficient_land and (has_surface_water or gw_ok):
            evaluation = (f" Sufficient (Veg={vegetation_area:.2f} ha, "
                          f"SurfaceWater={water_area_ha:.2f} ha, "
                          f"GW={'OK' if gw_ok else 'No' if depth_m is None else f'{depth_m:.1f}m'})")
        else:
            reasons = []
            if not has_sufficient_land:
                reasons.append(f"Vegetation={vegetation_area:.2f} ha < 2")
            if not (has_surface_water or gw_ok):
                if not has_surface_water:
                    reasons.append("no surface water")
                if depth_m is None:
                    reasons.append("GW=unknown")
                else:
                    reasons.append(f"GW={depth_m:.1f} m bgl > {groundwater_max_depth_m} m")
            if k_used:
                mean_dist_str = f"{mean_dist_km:.1f} km" if (mean_dist_km is not None) else "unknown distance"
                reasons.append(f"GW sampled from {k_used} nearby wells (mean dist {mean_dist_str})")
            evaluation = " Insufficient (" + "; ".join(reasons) + ")"

        result_row = {
            "patta_holder": claim.get("patta_holder"),
            "village": claim.get("village"),
            "coordinates": claim.get("coordinates"),
            "claim_status": claim.get("claim_status"),
            "vegetation_area(ha)": round(vegetation_area, 2),
            "water_area(ha)": round(water_area_ha, 2),
            "urban_area(ha)": round(urban_area_ha, 2),
            "barren_area(ha)": round(barren_area_ha, 2),
            "groundwater_depth(m_bgl)": round(depth_m, 2) if depth_m is not None else None,
            "gw_distance_to_well_km": round(mean_dist_km, 2) if mean_dist_km is not None else None,
            "gw_k_used": int(k_used),
            "evaluation": evaluation
        }

        # add scheme recommendations
        result_row["recommended_schemes"] = recommend_schemes(result_row)
        results.append(result_row)

    return pd.DataFrame(results)


if __name__ == "__main__":
    df = evaluate_assets(buffer_km=1.0,
                         groundwater_max_depth_m=15.0,
                         gw_k=3,
                         gw_max_km=150.0)

    if df.empty:
        print("No claims found in database.")
    else:
        print("\n📊 FRA Claim Evaluation:\n")

        for _, row in df.iterrows():
            print("=" * 80)
            print(f"Patta Holder : {row['patta_holder']} ({row['village']})")
            print(f"Coordinates  : {row['coordinates']} | Status: {row['claim_status']}")
            print(f"Vegetation   : {row['vegetation_area(ha)']} ha")
            print(f"Water Bodies : {row['water_area(ha)']} ha")
            print(f"Urban Area   : {row['urban_area(ha)']} ha")
            print(f"Barren Land  : {row['barren_area(ha)']} ha")
            print(f"Groundwater  : {row['groundwater_depth(m_bgl)']} m (avg of {row['gw_k_used']} wells)")
            print(f"Evaluation   : {row['evaluation']}")
            schemes = row["recommended_schemes"]
            if isinstance(schemes, list):
                schemes = ", ".join(schemes)
            print(f"Schemes      : {schemes}")
        print("=" * 80)
