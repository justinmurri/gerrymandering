"""Compute Polsby-Popper scores for one or more ensemble JSONLs.

Usage:
    python process_polsby_ensemble.py --config config_UT.yaml
    python process_polsby_ensemble.py --config config_UT.yaml --ensembles recom1M harvard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jsonlines as jl
from gerrychain import GeographicPartition, Graph
from gerrychain.metrics import polsby_popper
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


def compute_score(obj: dict, graph: Graph) -> dict:
    part = GeographicPartition(
        graph, assignment={i: val for i, val in enumerate(obj["assignment"])}
    )
    return {"sample": obj["sample"], "scores": polsby_popper(part)}


def run_chain(
    chain_name: str,
    input_path: Path,
    output_path: Path,
    graph: Graph,
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

    with joblib_progress(description=f"Polsby-Popper [{chain_name}]", total=len(plans)):
        scores = Parallel(n_jobs=n_jobs)(
            delayed(compute_score)(obj, graph) for obj in plans
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(scores)

    print(f"  Done: wrote {len(scores)} scores -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Polsby-Popper scores for one or more ensembles."
    )
    add_config_args(parser)
    parser.add_argument("--graph", default=None, help="Override config metrics.polsby.graph")
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)

    if args.seed is not None:
        cfg["performance"]["random_seed"] = args.seed

    graph_path = Path(args.graph) if args.graph else top_dir / cfg["metrics"]["polsby"]["graph"]
    print(f"Loading graph from {graph_path}")
    graph = Graph.from_json(str(graph_path))

    ensembles = filter_ensembles(cfg, args.ensembles)
    seed = cfg["performance"]["random_seed"]
    n_jobs = cfg["performance"]["n_jobs"]
    output_template = cfg["metrics"]["polsby"]["output"]

    print(f"Running Polsby-Popper for {len(ensembles)} ensemble(s)")

    for ensemble in ensembles:
        subsample = effective_subsample(ensemble, cfg, "polsby")
        for chain_name, input_path in iter_chain_inputs(
            cfg, top_dir, ensemble, include_derivatives=args.include_derivatives
        ):
            output_path = resolve_output_path(
                cfg, top_dir, output_template, name=chain_name
            )
            run_chain(chain_name, input_path, output_path, graph, subsample, seed, n_jobs)

    print("\nAll done.")


if __name__ == "__main__":
    main()
