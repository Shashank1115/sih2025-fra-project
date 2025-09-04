# backend/scheme_engine.py
from typing import Dict, List, Tuple

"""
This is a simple, explainable rule engine that:
- reads computed metrics per-claim (areas, groundwater),
- suggests schemes with reasons, and
- emits a priority score (0-100).
You can tune thresholds in ONE place (CONFIG).
"""

CONFIG = {
    "veg_min_ha": 2.0,            # minimum vegetation (cropland+forest) hectares
    "water_min_ha": 0.05,         # any surface water in buffer
    "gw_ok_m": 15.0,              # depth to water table considered "ok" (m bgl)
    "gw_far_km_flag": 100.0,      # warn if nearest well further than this
}

def score_band(x: float, lo: float, hi: float, invert: bool = False) -> float:
    """
    Map x into [0..1] between lo and hi. If invert=True, higher x => lower score.
    """
    if hi == lo:
        return 0.0
    t = (x - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return (1.0 - t) if invert else t

def recommend(row: Dict) -> Tuple[List[Dict], float]:
    """
    Input: row from evaluator (dict).
    Output:
      - list of recommendations: [{scheme, reason, priority(0-100)}]
      - overall_priority: single float (0..100)
    """
    veg = float(row.get("vegetation_area(ha)", 0) or 0)
    water = float(row.get("water_area(ha)", 0) or 0)
    barren = float(row.get("barren_area(ha)", 0) or 0)
    urban = float(row.get("urban_area(ha)", 0) or 0)
    gw_depth = row.get("groundwater_depth(m_bgl)")
    gw_dist = row.get("gw_distance_to_well_km")

    gw_known = (gw_depth is not None)
    gw_ok = gw_known and (gw_depth <= CONFIG["gw_ok_m"])

    # ---- Base needs scoring (0..100) ----
    # Needs score increases if water is low, groundwater is deep, vegetation is low, barren is high
    water_need = 1.0 - score_band(water, 0.0, 0.5)            # 0ha->need=1, ≥0.5ha->need≈0
    gw_need    = 0.0 if gw_ok else (0.7 if gw_known else 0.5) # if unknown: mid need
    veg_need   = 1.0 - score_band(veg, 0.0, 5.0)              # <5ha => higher need
    barren_need= score_band(barren, 0.0, 5.0)                 # more barren => higher need

    needs_score = (0.35*water_need + 0.35*gw_need + 0.20*veg_need + 0.10*barren_need)
    overall_priority = round(needs_score * 100, 1)

    # ---- Scheme rules (examples; adjust per policy as needed) ----
    recs: List[Dict] = []

    # 1) Jal Jeevan Mission / Local Water Infra
    if (water < CONFIG["water_min_ha"]) or (gw_known and gw_depth > CONFIG["gw_ok_m"]):
        reason = []
        if water < CONFIG["water_min_ha"]:
            reason.append(f"surface water low ({water:.2f} ha)")
        if gw_known and gw_depth > CONFIG["gw_ok_m"]:
            reason.append(f"groundwater deep ({gw_depth:.1f} m bgl)")
        if not gw_known:
            reason.append("groundwater unknown")
        pr = min(95, overall_priority + 10)
        recs.append({
            "scheme": "Rural Water Infra (e.g., Jal Jeevan Mission works/MGNREGA water conservation)",
            "reason": "; ".join(reason),
            "priority": pr
        })

    # 2) Land Development (MGNREGA/Watershed)
    if barren > 0.2:
        pr = min(90, overall_priority + 5)
        recs.append({
            "scheme": "MGNREGA Watershed/Soil & Moisture Conservation",
            "reason": f"barren land {barren:.2f} ha; recommend contour trenching, farm ponds",
            "priority": pr
        })

    # 3) Livelihood / Agroforestry (CSS / State Missions)
    if veg >= CONFIG["veg_min_ha"]:
        pr = min(85, overall_priority)
        recs.append({
            "scheme": "Agroforestry / Allied livelihood support (NHB/Horticulture/State Mission)",
            "reason": f"adequate vegetation base ({veg:.2f} ha) for diversification",
            "priority": pr
        })

    # 4) Convergence flag (DAJGUA placeholder)
    if (water < CONFIG["water_min_ha"]) or (not gw_ok):
        pr = min(88, overall_priority + 5)
        recs.append({
            "scheme": "District Convergence (multi-dept) – water/irrigation priority",
            "reason": "combine line departments to address water stress",
            "priority": pr
        })

    # warn on far groundwater station
    if gw_dist and gw_dist > CONFIG["gw_far_km_flag"]:
        recs.append({
            "scheme": "Data gap note",
            "reason": f"nearest groundwater station is far ({gw_dist} km) – prioritize local survey",
            "priority": 50
        })

    # sort recommendations by priority
    recs.sort(key=lambda x: x["priority"], reverse=True)
    return recs, overall_priority
