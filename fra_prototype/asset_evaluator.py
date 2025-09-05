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
                "evaluation": "❌ Insufficient (invalid coordinates)"
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
                    # mapper doesn't accept kwargs -> call without them
                    detected_gdf = map_assets_from_satellite_image(claim_point)
            else:
                detected_gdf = map_assets_from_satellite_image(claim_point)
        except Exception as exc:
            print(f"WARNING: asset mapper failed for claim {claim.get('patta_holder')} ({coords_text}): {exc}")
            detected_gdf = gpd.GeoDataFrame(columns=["asset_type", "geometry"], geometry=[], crs="EPSG:4326")

        # default areas
        farm_area_ha = forest_area_ha = water_area_ha = urban_area_ha = barren_area_ha = 0.0

        if detected_gdf is not None and not detected_gdf.empty:
            # ensure CRS and convert to meters for intersection/area
            if detected_gdf.crs is None:
                detected_gdf = detected_gdf.set_crs(epsg=4326)
            try:
                detected_3857 = detected_gdf.to_crs(epsg=3857).copy()
            except Exception:
                detected_3857 = detected_gdf.copy()
                detected_3857.set_crs(epsg=4326, inplace=True)
                detected_3857 = detected_3857.to_crs(epsg=3857)

            # clip geometries to buffer
            try:
                detected_3857["geometry"] = detected_3857["geometry"].intersection(buff_geom_3857)
            except Exception:
                pass

            # drop empties
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
            evaluation = (f"✅ Sufficient (Veg={vegetation_area:.2f} ha, "
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
            # add a note about averaged wells if used (guard mean_dist_km)
            if k_used:
                mean_dist_str = f"{mean_dist_km:.1f} km" if (mean_dist_km is not None) else "unknown distance"
                reasons.append(f"GW sampled from {k_used} nearby wells (mean dist {mean_dist_str})")
            evaluation = "❌ Insufficient (" + "; ".join(reasons) + ")"

        results.append({
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
        })

    return pd.DataFrame(results)


if __name__ == "__main__":
    # basic CLI test
    df = evaluate_assets(buffer_km=1.0,
                         groundwater_max_depth_m=15.0,
                         gw_k=3,
                         gw_max_km=150.0,
                         mapper_kwargs={"grid_size": 2, "tile_size": (768, 768)})
    if df.empty:
        print("No claims found in database.")
    else:
        print("\n📊 FRA Claim Evaluation:\n")
        pd.set_option("display.max_columns", None)
        print(df.to_string(index=False))
