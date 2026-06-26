"""Compute total Democratic district wins by race for ensemble JSONLs.

Usage:
    python process_total_dem_wins.py --config config_UT.yaml
    python process_total_dem_wins.py --config config_UT.yaml --include-derivatives
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import jsonlines as jl
import numpy as np
from joblib import Parallel, delayed
from joblib_progress import joblib_progress

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    add_config_args,
    filter_ensembles,
    iter_chain_inputs,
    load_config,
    project_root,
    resolve_output_path,
)


def build_race_matrices(cfg: dict, df: gpd.GeoDataFrame):
    cols = cfg["columns"]
    dem_suffix = cols["party_dem_suffix"]
    gop_suffix = cols["party_gop_suffix"]
    race_names = cfg["elections"]["races"]

    dem_rep_pairs = [(f"{name}{dem_suffix}", f"{name}{gop_suffix}") for name in race_names]
    dem_count_matrix = df[[pair[0] for pair in dem_rep_pairs]].to_numpy()
    rep_count_matrix = df[[pair[1] for pair in dem_rep_pairs]].to_numpy()
    return race_names, dem_count_matrix, rep_count_matrix


def build_compute_score(race_names, dem_count_matrix, rep_count_matrix):
    def compute_score(obj):
        assignment = np.asarray(obj["assignment"], dtype=np.int32)
        race_totals = {name: 0 for name in race_names}
        always_r_count = 0

        for part in np.unique(assignment):
            mask = assignment == part
            dem_totals = dem_count_matrix[mask].sum(axis=0)
            rep_totals = rep_count_matrix[mask].sum(axis=0)
            dem_wins = dem_totals > rep_totals

            if not dem_wins.any():
                always_r_count += 1

            for i, race in enumerate(race_names):
                race_totals[race] += 1 if dem_wins[i] else 0

        return (
            {"sample": obj["sample"], "scores": race_totals},
            {"sample": obj["sample"], "always_r_count": always_r_count},
        )

    return compute_score


def run_chain(
    chain_name: str,
    input_path: Path,
    dem_wins_path: Path,
    always_r_path: Path,
    compute_score,
    n_jobs: int,
) -> None:
    print(f"\n── {chain_name} ──────────────────────────────")
    if not input_path.exists():
        print(f"  Skipping: input not found at {input_path}")
        return

    with jl.open(input_path) as reader:
        plans = list(reader)
    if not plans:
        print(f"  Skipping: no plans found in {input_path}")
        return

    print(f"  Input:  {input_path} ({len(plans)} plans)")

    with joblib_progress(description=f"Dem wins [{chain_name}]", total=len(plans)):
        scores = Parallel(n_jobs=n_jobs)(delayed(compute_score)(obj) for obj in plans)

    dem_singles, always_r_counts = zip(*scores)

    dem_wins_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(dem_wins_path, "w") as writer:
        writer.write_all(dem_singles)
    with jl.open(always_r_path, "w") as writer:
        writer.write_all(always_r_counts)

    print(f"  Done: {dem_wins_path.name}, {always_r_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Democratic district win counts for one or more ensembles."
    )
    add_config_args(parser)
    parser.add_argument(
        "--parquet", default=None, help="Override config metrics.dem_wins.geoparquet"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)

    parquet_path = (
        Path(args.parquet) if args.parquet else top_dir / cfg["metrics"]["dem_wins"]["geoparquet"]
    )
    print(f"Loading geoparquet from {parquet_path}")
    df = gpd.read_parquet(parquet_path).drop(columns=["geometry"])

    race_names, dem_count_matrix, rep_count_matrix = build_race_matrices(cfg, df)
    compute_score = build_compute_score(race_names, dem_count_matrix, rep_count_matrix)

    ensembles = filter_ensembles(cfg, args.ensembles)
    n_jobs = cfg["performance"]["n_jobs"]
    dem_template = cfg["metrics"]["dem_wins"]["outputs"]["dem_wins"]
    always_r_template = cfg["metrics"]["dem_wins"]["outputs"]["always_r"]

    for ensemble in ensembles:
        for chain_name, input_path in iter_chain_inputs(
            cfg, top_dir, ensemble, include_derivatives=args.include_derivatives
        ):
            dem_wins_path = resolve_output_path(cfg, top_dir, dem_template, name=chain_name)
            always_r_path = resolve_output_path(
                cfg, top_dir, always_r_template, name=chain_name
            )
            run_chain(
                chain_name, input_path, dem_wins_path, always_r_path, compute_score, n_jobs
            )

    print("\nAll done.")


if __name__ == "__main__":
    main()
