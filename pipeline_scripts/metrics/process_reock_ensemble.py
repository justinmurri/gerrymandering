"""Compute Reock scores for one or more ensemble JSONLs.

Usage:
    python process_reock_ensemble.py --config config_UT.yaml
    python process_reock_ensemble.py --config config_UT.yaml --ensembles recom1M harvard
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import jsonlines as jl
from gerrytools.scoring import reock
from joblib import Parallel, delayed
from joblib_progress import joblib_progress

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    add_config_args,
    effective_subsample,
    filter_ensembles,
    iter_chain_inputs,
    load_config,
    load_plans,
    project_root,
    resolve_output_path,
)

warnings.filterwarnings("ignore", category=UserWarning)


def compute_score(obj: dict, geo_only: gpd.GeoDataFrame) -> dict:
    geo_new = geo_only.copy()
    geo_new["assignment"] = obj["assignment"]
    dissolved = geo_new.dissolve(by="assignment")
    return {"sample": obj["sample"], "scores": reock().apply(dissolved)}


def run_chain(
    chain_name: str,
    input_path: Path,
    output_path: Path,
    geo_only: gpd.GeoDataFrame,
    subsample: int | None,
    seed: int,
    n_jobs: int,
) -> None:
    print(f"\n── {chain_name} ──────────────────────────────")
    if not input_path.exists():
        print(f"  Skipping: input not found at {input_path}")
        return

    plans = load_plans(input_path, subsample, seed)
    if not plans:
        print(f"  Skipping: no plans found in {input_path}")
        return

    print(f"  Input:  {input_path} ({len(plans)} plans)")
    print(f"  Output: {output_path}")

    with joblib_progress(description=f"Reock [{chain_name}]", total=len(plans)):
        scores = Parallel(n_jobs=n_jobs)(
            delayed(compute_score)(obj, geo_only) for obj in plans
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(scores)

    print(f"  Done: wrote {len(scores)} scores -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Reock scores for one or more ensembles."
    )
    add_config_args(parser)
    parser.add_argument(
        "--parquet", default=None, help="Override config metrics.reock.geoparquet"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)

    if args.seed is not None:
        cfg["performance"]["random_seed"] = args.seed

    parquet_path = (
        Path(args.parquet) if args.parquet else top_dir / cfg["metrics"]["reock"]["geoparquet"]
    )
    print(f"Loading geoparquet from {parquet_path}")
    gdf = gpd.read_parquet(parquet_path)
    geo_only = gdf[["geometry"]]

    ensembles = filter_ensembles(cfg, args.ensembles)
    seed = cfg["performance"]["random_seed"]
    n_jobs = cfg["performance"]["n_jobs"]
    output_template = cfg["metrics"]["reock"]["output"]

    print(f"Running Reock for {len(ensembles)} ensemble(s)")

    for ensemble in ensembles:
        subsample = effective_subsample(ensemble, cfg, "reock")
        for chain_name, input_path in iter_chain_inputs(
            cfg, top_dir, ensemble, include_derivatives=args.include_derivatives
        ):
            output_path = resolve_output_path(
                cfg, top_dir, output_template, name=chain_name
            )
            run_chain(
                chain_name, input_path, output_path, geo_only, subsample, seed, n_jobs
            )

    print("\nAll done.")


if __name__ == "__main__":
    main()
