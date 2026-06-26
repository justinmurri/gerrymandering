"""Collect metric scores for human-drawn districting plans.

Reads plan assignment columns from the graph JSON and writes a single JSON
summary used by tables and figure scripts.

Usage:
    python collect_human_plan_data.py --config config_UT.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
from gerrychain import GeographicPartition, Graph, Partition
from gerrychain.metrics import (
    efficiency_gap,
    mean_median,
    partisan_bias,
    partisan_gini,
    polsby_popper,
)
from gerrytools.scoring import reock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import get_pi_election, load_config, project_root  # noqa: E402
from process_split_scores import precompute_edge_arrays  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)


def build_dem_wins(assignment, race_names, dem_matrix, rep_matrix):
    assignment = np.asarray(assignment, dtype=np.int32)
    race_totals = {name: 0 for name in race_names}
    always_r_count = 0

    for part in np.unique(assignment):
        mask = assignment == part
        dem_totals = dem_matrix[mask].sum(axis=0)
        rep_totals = rep_matrix[mask].sum(axis=0)
        dem_wins = dem_totals > rep_totals
        if not dem_wins.any():
            always_r_count += 1
        for i, race in enumerate(race_names):
            race_totals[race] += 1 if dem_wins[i] else 0

    return race_totals, always_r_count


def compute_split_scores(
    assignment, u, v, same_county_mask, same_place_mask, county_names, place_names
):
    assignment = np.asarray(assignment, dtype=np.int32)
    cut = assignment[u] != assignment[v]
    return {
        "county_splits": len(set(county_names[cut & same_county_mask])),
        "muni_splits": len(set(place_names[cut & same_place_mask])),
        "cut_edges": int(cut.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect human plan metric scores.")
    parser.add_argument("--config", required=True, help="Path to pipeline config YAML")
    parser.add_argument("--graph", default=None, help="Override graph with PIs path")
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    cols = cfg["columns"]
    dem_suffix = cols["party_dem_suffix"]
    gop_suffix = cols["party_gop_suffix"]
    race_names = cfg["elections"]["races"]
    symmetry_metrics = cfg.get("symmetry_metrics", ["PB", "EG", "MM", "PG"])
    plan_names = cfg["human_plans"]["plan_names"]

    graph_path = (
        Path(args.graph) if args.graph else top_dir / cfg["metrics"]["symmetry"]["graph"]
    )
    parquet_path = top_dir / cfg["metrics"]["reock"]["geoparquet"]

    print(f"Loading graph from {graph_path}")
    graph = Graph.from_json(str(graph_path))
    gdf = gpd.read_parquet(parquet_path)
    geo_only = gdf[["geometry"]]

    dem_pairs = [(f"{r}{dem_suffix}", f"{r}{gop_suffix}") for r in race_names]
    df = gdf.drop(columns=["geometry"])
    dem_matrix = df[[p[0] for p in dem_pairs]].to_numpy()
    rep_matrix = df[[p[1] for p in dem_pairs]].to_numpy()

    election = get_pi_election(cfg, "election_for_symmetry")
    updaters = {"PI": election}
    metric_fns = {
        "PB": lambda part: partisan_bias(part["PI"]),
        "EG": lambda part: efficiency_gap(part["PI"]),
        "MM": lambda part: mean_median(part["PI"]),
        "PG": lambda part: partisan_gini(part["PI"]),
    }

    u, v, same_county_mask, same_place_mask, county_names, place_names = precompute_edge_arrays(
        graph, cols["county"], cols["municipality"]
    )

    results: dict = {}
    first_node = list(graph.nodes)[0]

    for plan in plan_names:
        if plan not in graph.nodes[first_node]:
            print(f"  Warning: skipping {plan!r} — column not found on graph nodes")
            continue

        assignment = [graph.nodes[node][plan] for node in graph.nodes]
        assignment_dict = {i: val for i, val in enumerate(assignment)}

        geo_part = GeographicPartition(graph, assignment=assignment_dict)
        polsby = polsby_popper(geo_part)

        geo_new = geo_only.copy()
        geo_new["assignment"] = assignment
        dissolved = geo_new.dissolve(by="assignment")
        reock_scores = reock().apply(dissolved)

        part = Partition(graph, assignment=assignment_dict, updaters=updaters)
        dem_wins, always_r = build_dem_wins(assignment, race_names, dem_matrix, rep_matrix)
        splits = compute_split_scores(
            assignment, u, v, same_county_mask, same_place_mask, county_names, place_names
        )

        results[plan] = {
            "polsby_popper": {str(k): v for k, v in polsby.items()},
            "reock": {str(k): v for k, v in reock_scores.items()},
            **splits,
            "dem_wins_by_race": dem_wins,
            "always_r_count": always_r,
            **{m: metric_fns[m](part) for m in symmetry_metrics},
        }
        print(f"  Scored {plan}")

    output_path = top_dir / cfg["human_plans"]["output"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=4)

    print(f"\nWrote {len(results)} human plans -> {output_path}")


if __name__ == "__main__":
    main()
