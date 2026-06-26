""" Compute the partisan index (PI) multiple ways and attach the results to the graph.
    1) PI weighted by turnout (sum of each party's votes over all elections, divided by number of elections)
    2) PI median (median of each party's votes over all elections)
    3) PI unweighted (mean of each party's vote share over all elections, multiplied by mean number of voters in each election)
    Save the updated graph and geoparquet as new files with the _w_PIs suffix.

    Usage:
        python attach_PI_to_graph.py --config config_UT.yaml
"""

import argparse
from pathlib import Path

import numpy as np
import geopandas as gpd
import yaml
from gerrychain import Graph
from gerrychain.updaters import Election


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Attach Partisan Index columns to graph and geoparquet.")
    parser.add_argument("--config", required=True, help="Path to the pipeline config YAML (e.g. config_UT.yaml)")
    return parser.parse_args()


# ── Config loader ─────────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    fmt = {
        "abbrev":  cfg["state"]["abbrev"],
        "vintage": cfg["state"]["data_vintage"],
    }
    return _resolve(cfg, fmt)

def _resolve(obj, fmt):
    if isinstance(obj, str):
        # Only replace known keys; leave {name}, {election}, {road_type} etc. untouched
        try:
            return obj.format_map(fmt)
        except KeyError:
            return obj
    elif isinstance(obj, dict):
        return {k: _resolve(v, fmt) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve(i, fmt) for i in obj]
    return obj


# ── PI computation ────────────────────────────────────────────────────────────

def build_elections(election_names: list[str], dem_suffix: str, gop_suffix: str) -> list[Election]:
    """Create a gerrychain Election object for each race in the config."""
    return [
        Election(
            name,
            {"Dem": f"{name}{dem_suffix}", "GOP": f"{name}{gop_suffix}"},
            alias=name,
        )
        for name in election_names
    ]


def attach_pi_weighted(graph, all_elections: list[Election]) -> Election:
    """PI type 1: weight higher-turnout elections more heavily.
    Equivalent to summing all votes across elections and dividing by
    the number of elections."""
    for node in graph.nodes:
        dem = sum(graph.nodes[node][e.parties_to_columns["Dem"]] for e in all_elections)
        gop = sum(graph.nodes[node][e.parties_to_columns["GOP"]] for e in all_elections)
        graph.nodes[node]["PI_weighted_dem"] = dem / len(all_elections)
        graph.nodes[node]["PI_weighted_rep"] = gop / len(all_elections)

    return Election("PI_weighted", {"Dem": "PI_weighted_dem", "GOP": "PI_weighted_rep"}, alias="PI_1")


def attach_pi_median(graph, all_elections: list[Election]) -> Election:
    """PI type 2: median vote count across elections.
    Gives a 'typical' election, unskewed by a few high-turnout elections."""
    for node in graph.nodes:
        dem = np.median([graph.nodes[node][e.parties_to_columns["Dem"]] for e in all_elections])
        gop = np.median([graph.nodes[node][e.parties_to_columns["GOP"]] for e in all_elections])
        graph.nodes[node]["PI_median_dem"] = dem
        graph.nodes[node]["PI_median_rep"] = gop

    return Election("PI_median", {"Dem": "PI_median_dem", "GOP": "PI_median_rep"}, alias="PI_2")


def attach_pi_unweighted(graph, all_elections: list[Election]) -> Election:
    """PI type 3: unweighted mean vote share × mean total voters.
    Gives each election equal weight regardless of turnout."""
    epsilon = 1e-6  # avoid division by zero in zero-turnout precincts
    for node in graph.nodes:
        dem_shares, gop_shares = [], []
        for e in all_elections:
            dem_v = np.mean([graph.nodes[node][e.parties_to_columns["Dem"]] for e in all_elections])
            gop_v = np.mean([graph.nodes[node][e.parties_to_columns["GOP"]] for e in all_elections])
            total = dem_v + gop_v + epsilon
            dem_shares.append(dem_v / total)
            gop_shares.append(gop_v / total)
        mean_total = np.mean([
            graph.nodes[node][e.parties_to_columns["Dem"]] + graph.nodes[node][e.parties_to_columns["GOP"]]
            for e in all_elections
        ])
        graph.nodes[node]["PI_unweighted_dem"] = np.mean(dem_shares) * mean_total
        graph.nodes[node]["PI_unweighted_rep"] = np.mean(gop_shares) * mean_total

    return Election("PI_unweighted", {"Dem": "PI_unweighted_dem", "GOP": "PI_unweighted_rep"}, alias="PI_3")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    cfg = load_config(args.config)

    top_dir = Path(args.config).resolve().parent

    # Resolve input/output paths from config
    graph_in      = top_dir / cfg["inputs"]["graph_base"]
    graph_out     = top_dir / cfg["inputs"]["graph_with_pis"]
    parquet_in    = top_dir / cfg["inputs"]["geoparquet"]
    parquet_out   = top_dir / cfg["inputs"]["geoparquet_with_pis"]

    dem_suffix    = cfg["columns"]["party_dem_suffix"]   # e.g. "_dem"
    gop_suffix    = cfg["columns"]["party_gop_suffix"]   # e.g. "_rep"
    election_names = cfg["elections"]["races"]

    print(f"Loading graph from {graph_in}")
    graph = Graph.from_json(str(graph_in))

    # Build one Election object per race
    all_elections = build_elections(election_names, dem_suffix, gop_suffix)

    # Attach all three PI variants to the graph nodes
    pi_elections = [
        attach_pi_weighted(graph, all_elections),
        attach_pi_median(graph, all_elections),
        attach_pi_unweighted(graph, all_elections),
    ]

    # Save updated graph
    print(f"Saving graph with PIs to {graph_out}")
    graph.to_json(str(graph_out))

    # Attach PI columns to geoparquet and save
    print(f"Loading geoparquet from {parquet_in}")
    gdf = gpd.read_parquet(parquet_in)

    for election in pi_elections:
        gdf[election.name + dem_suffix] = [
            data[election.parties_to_columns["Dem"]] for _, data in graph.nodes(data=True)
        ]
        gdf[election.name + gop_suffix] = [
            data[election.parties_to_columns["GOP"]] for _, data in graph.nodes(data=True)
        ]

    print(f"Saving geoparquet with PIs to {parquet_out}")
    gdf.to_parquet(parquet_out)
    print("Done.")


if __name__ == "__main__":
    main()