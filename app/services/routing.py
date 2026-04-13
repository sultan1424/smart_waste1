"""
Routing service — wraps Aseel's OR-Tools CP-SAT model.
Called on-demand when collector clicks "Optimize Route".

Key differences from the notebook:
- Uses bin coordinates to compute haversine distances (no Excel needed)
- Accepts flagged bin IDs + fill levels from the DB
- Returns a structured result the API can serve directly
"""
from __future__ import annotations

import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants (same as Aseel's notebook) ─────────────────────────────────
AVG_SPEED_KMPH        = 30.0
DEFAULT_SERVICE_MIN   = 7
MAX_ROUTE_DISTANCE_KM = 120.0
MAX_SHIFT_HOURS       = 9.0
MIN_COVERAGE          = 0.90   # must serve >= 90% of flagged bins
ALPHA_DISTANCE        = 1
BETA_PRIORITY         = 1
PRIORITY_REWARD_SCALE = 1000

# Depot — Al Shatea St, Dammam (node "0" / label "1" in Aseel's notebook)
DEPOT = {"id": "DEPOT", "name": "Depot (Al Shatea St)", "lat": 26.4367, "lng": 50.1033}


# ── Haversine ─────────────────────────────────────────────────────────────

def _haversine_km(a: dict, b: dict) -> float:
    R = 6371.0
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    s = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a["lat"]))
         * math.cos(math.radians(b["lat"]))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(s), math.sqrt(1 - s))


def _build_dist_matrix(nodes: list[dict]) -> list[list[float]]:
    n = len(nodes)
    return [[_haversine_km(nodes[i], nodes[j]) for j in range(n)] for i in range(n)]


# ── Nearest-neighbour baseline ────────────────────────────────────────────

def _nn_route(depot_idx: int, candidates: list[int], D: list[list[float]]):
    unvisited = list(candidates)
    route = [depot_idx]
    cur = depot_idx
    total = 0.0
    while unvisited:
        best = min(unvisited, key=lambda j: D[cur][j])
        total += D[cur][best]
        route.append(best)
        unvisited.remove(best)
        cur = best
    total += D[cur][depot_idx]
    route.append(depot_idx)
    return route, total


# ── 2-opt improvement ─────────────────────────────────────────────────────

def _two_opt(route: list[int], D: list[list[float]]):
    r = list(route)
    n = len(r)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                d_before = D[r[i - 1]][r[i]] + D[r[j]][r[j + 1]]
                d_after  = D[r[i - 1]][r[j]] + D[r[i]][r[j + 1]]
                if d_after < d_before - 1e-9:
                    r[i:j + 1] = r[i:j + 1][::-1]
                    improved = True
    dist = sum(D[r[k]][r[k + 1]] for k in range(len(r) - 1))
    return r, dist


def _route_time_hours(dist_km: float, stops: int) -> float:
    return dist_km / AVG_SPEED_KMPH + (stops * DEFAULT_SERVICE_MIN / 60.0)


# ── CP-SAT solver (Aseel's full model) ───────────────────────────────────

def _solve_with_ortools(
    nodes: list[dict],
    flagged_indices: set[int],
    priority_map: dict[int, int],
    depot_idx: int = 0,
    time_limit_sec: int = 30,
) -> Optional[dict]:
    """
    Run the CP-SAT formulation from Aseel's notebook.
    Returns solution dict or None if infeasible.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        logger.warning("ortools not installed — falling back to 2-opt heuristic")
        return None

    n_nodes   = len(nodes)
    V_labels  = list(range(n_nodes))
    N_labels  = [i for i in V_labels if i != depot_idx]

    D_km  = _build_dist_matrix(nodes)
    # Convert to metres (integers for CP-SAT)
    dist_m    = {(i, j): int(round(D_km[i][j] * 1000))
                 for i in V_labels for j in V_labels if i != j}
    travel_sec = {(i, j): int(round((dist_m[(i, j)] / 1000.0) / AVG_SPEED_KMPH * 3600))
                  for (i, j) in dist_m}
    service_sec = {i: int(DEFAULT_SERVICE_MIN * 60) for i in N_labels}

    f = {i: (1 if i in flagged_indices else 0) for i in N_labels}
    F_total = sum(f.values())
    coverage_req = math.ceil(MIN_COVERAGE * F_total) if F_total > 0 else 0

    D_max_m  = int(MAX_ROUTE_DISTANCE_KM * 1000)
    T_max_sec = int(MAX_SHIFT_HOURS * 3600)
    n = len(N_labels)

    model = cp_model.CpModel()

    x = {(i, j): model.NewBoolVar(f"x_{i}_{j}")
         for i in V_labels for j in V_labels if i != j}
    y = {i: model.NewBoolVar(f"y_{i}") for i in N_labels}
    u = {i: model.NewIntVar(1, n, f"u_{i}") for i in N_labels}

    def prio(i): return int(priority_map.get(i, 1))

    dist_term  = sum(ALPHA_DISTANCE * dist_m[(i, j)] * x[(i, j)] for (i, j) in x)
    prio_term  = sum(BETA_PRIORITY * PRIORITY_REWARD_SCALE * prio(i) * y[i] for i in N_labels)
    model.Minimize(dist_term - prio_term)

    for i in N_labels:
        model.Add(sum(x[(i, j)] for j in V_labels if j != i) == y[i])
        model.Add(sum(x[(j, i)] for j in V_labels if j != i) == y[i])

    model.Add(sum(x[(depot_idx, j)] for j in V_labels if j != depot_idx) == 1)
    model.Add(sum(x[(i, depot_idx)] for i in V_labels if i != depot_idx) == 1)

    for i in V_labels:
        for j in V_labels:
            if i != j and str(i) < str(j) and (i, j) in x and (j, i) in x:
                model.Add(x[(i, j)] + x[(j, i)] <= 1)

    model.Add(sum(dist_m[(i, j)] * x[(i, j)] for (i, j) in x) <= D_max_m)
    model.Add(
        sum(travel_sec[(i, j)] * x[(i, j)] for (i, j) in x) +
        sum(service_sec[i] * y[i] for i in N_labels)
        <= T_max_sec
    )
    if F_total > 0:
        model.Add(sum(f[i] * y[i] for i in N_labels) >= coverage_req)
    for i in N_labels:
        for j in N_labels:
            if i != j:
                model.Add(u[i] - u[j] + n * x[(i, j)] <= n - 1)
    for i in N_labels:
        model.Add(x[(depot_idx, i)] <= y[i])
        model.Add(x[(i, depot_idx)] <= y[i])
    model.Add(sum(y[i] for i in N_labels) >= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_sec
    solver.parameters.num_search_workers  = 4
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    served = [i for i in N_labels if solver.Value(y[i]) == 1]
    arcs   = [(i, j) for (i, j) in x if solver.Value(x[(i, j)]) == 1]

    # Reconstruct ordered route
    route = [depot_idx]
    cur = depot_idx
    visited = set()
    for _ in range(n_nodes + 5):
        nexts = [j for (i, j) in arcs if i == cur]
        if not nexts:
            break
        nxt = nexts[0]
        route.append(nxt)
        if nxt == depot_idx:
            break
        if nxt in visited:
            break
        visited.add(nxt)
        cur = nxt

    total_dist_m = sum(dist_m[(i, j)] * solver.Value(x[(i, j)]) for (i, j) in x)
    total_dist_km = total_dist_m / 1000.0
    total_travel_s = sum(travel_sec[(i, j)] * solver.Value(x[(i, j)]) for (i, j) in x)
    total_svc_s    = sum(service_sec[i] * solver.Value(y[i]) for i in N_labels)
    total_time_hr  = (total_travel_s + total_svc_s) / 3600.0
    flagged_served = sum(f[i] * solver.Value(y[i]) for i in N_labels)
    service_level  = (100.0 * flagged_served / F_total) if F_total > 0 else 100.0

    status_name = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE"}.get(status, "UNKNOWN")

    return {
        "solver_status":   status_name,
        "route_indices":   route,
        "served_indices":  served,
        "total_dist_km":   round(total_dist_km, 2),
        "total_time_hr":   round(total_time_hr, 2),
        "flagged_served":  flagged_served,
        "flagged_total":   F_total,
        "service_level_pct": round(service_level, 1),
    }


# ── 2-opt fallback ────────────────────────────────────────────────────────

def _solve_heuristic(
    nodes: list[dict],
    flagged_indices: set[int],
    depot_idx: int = 0,
) -> Optional[dict]:
    flagged_list = list(flagged_indices)
    if not flagged_list:
        return None

    D = _build_dist_matrix(nodes)
    required = math.ceil(MIN_COVERAGE * len(flagged_list))

    best_route, best_dist, best_served = None, float("inf"), 0
    candidates = list(flagged_list)

    for attempt in range(8):
        if attempt > 0:
            import random; random.shuffle(candidates)
        subset = list(candidates)
        while len(subset) >= required:
            r0, _ = _nn_route(depot_idx, subset, D)
            route, dist = _two_opt(r0, D)
            stops = len(subset)
            t = _route_time_hours(dist, stops)
            if dist <= MAX_ROUTE_DISTANCE_KM and t <= MAX_SHIFT_HOURS:
                if dist < best_dist:
                    best_dist   = dist
                    best_route  = route
                    best_served = stops
                break
            subset = subset[:-1]

    if not best_route or best_served < required:
        return None

    F_total = len(flagged_list)
    service_level = (100.0 * best_served / F_total) if F_total > 0 else 100.0

    return {
        "solver_status":    "HEURISTIC",
        "route_indices":    best_route,
        "served_indices":   [i for i in best_route if i != depot_idx],
        "total_dist_km":    round(best_dist, 2),
        "total_time_hr":    round(_route_time_hours(best_dist, best_served), 2),
        "flagged_served":   best_served,
        "flagged_total":    F_total,
        "service_level_pct": round(service_level, 1),
    }


# ── Public API ────────────────────────────────────────────────────────────

def optimize_route(
    bins: list[dict],
    flagged_bin_ids: list[str],
    priority_map: Optional[dict[str, int]] = None,
    use_ortools: bool = True,
    solver_time_limit: int = 30,
) -> dict:
    """
    Main entry point called from the FastAPI route.

    bins: list of {id, name, lat, lng}
    flagged_bin_ids: IDs of bins that need pickup
    priority_map: {bin_id: priority_score} — higher = more important
    """
    if not bins:
        return {"error": "no_bins"}

    # Build node list: depot first, then bins
    nodes = [DEPOT] + bins
    depot_idx = 0

    id_to_idx   = {n["id"]: i for i, n in enumerate(nodes)}
    flagged_set = {id_to_idx[bid] for bid in flagged_bin_ids if bid in id_to_idx}

    prio_int: dict[int, int] = {}
    if priority_map:
        for bid, score in priority_map.items():
            if bid in id_to_idx:
                prio_int[id_to_idx[bid]] = int(score)

    # Baseline (nearest-neighbour)
    D_km = _build_dist_matrix(nodes)
    _, baseline_dist = _nn_route(depot_idx, list(flagged_set), D_km)

    # Try OR-Tools first, fall back to 2-opt heuristic
    result = None
    if use_ortools:
        result = _solve_with_ortools(nodes, flagged_set, prio_int, depot_idx, solver_time_limit)
    if result is None:
        result = _solve_heuristic(nodes, flagged_set, depot_idx)
    if result is None:
        return {"error": "no_feasible_solution"}

    # Enrich with node names
    route_nodes = [
        {
            "index": idx,
            "id":    nodes[idx]["id"],
            "name":  nodes[idx]["name"],
            "lat":   nodes[idx]["lat"],
            "lng":   nodes[idx]["lng"],
            "is_depot": idx == depot_idx,
        }
        for idx in result["route_indices"]
    ]

    dist_saved_pct = (
        round((baseline_dist - result["total_dist_km"]) / baseline_dist * 100, 1)
        if baseline_dist > 0 else 0.0
    )

    return {
        "solver_status":      result["solver_status"],
        "route":              route_nodes,
        "total_dist_km":      result["total_dist_km"],
        "total_time_hr":      result["total_time_hr"],
        "bins_served":        result["flagged_served"],
        "bins_flagged":       result["flagged_total"],
        "service_level_pct":  result["service_level_pct"],
        "baseline_dist_km":   round(baseline_dist, 2),
        "dist_saved_pct":     dist_saved_pct,
        "constraints_met": {
            "distance": result["total_dist_km"] <= MAX_ROUTE_DISTANCE_KM,
            "time":     result["total_time_hr"] <= MAX_SHIFT_HOURS,
            "coverage": result["service_level_pct"] >= 90.0,
        },
    }