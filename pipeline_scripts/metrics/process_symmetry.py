"""Compute partisan symmetry metrics (PB, EG, MM, PG) for ensemble JSONLs.

Usage:
    python process_symmetry.py --config config_UT.yaml
    python process_symmetry.py --config config_UT.yaml --include-derivatives
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jsonlines as jl
from gerrychain import Graph, Partition
from gerrychain.metrics import efficiency_gap, mean_median, partisan_bias, partisan_gini
from joblib import Parallel, delayed
from joblib_progress import joblib_progress

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    add_config_args,
    filter_ensembles,
    get_pi_election,
    iter_chain_inputs,
    load_config,
    load_plans,
    project_root,
    resolve_output_path,
)


def build_compute_score(updaters: dict, metrics: list[str]):
    metric_fns = {
        "PB": lambda part: partisan_bias(part["PI"]),
        "EG": lambda part: efficiency_gap(part["PI"]),
        "MM": lambda part: mean_median(part["PI"]),
        "PG": lambda part: partisan_gini(part["PI"]),
    }

    def compute_score(obj: dict, graph: Graph) -> dict:
        part = Partition(
            graph,
            assignment={i: val for i, val in enumerate(obj["assignment"])},
            updaters=updaters,
        )
        return {
            "sample": obj["sample"],
            "scores": {m: metric_fns[m](part) for m in metrics},
        }

    return compute_score


def run_chain(
    chain_name: str,
    input_path: Path,
    output_path: Path,
    graph: Graph,
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
    print(f"  Output: {output_path}")

    with joblib_progress(description=f"Symmetry [{chain_name}]", total=len(plans)):
        scores = Parallel(n_jobs=n_jobs)(
            delayed(compute_score)(obj, graph) for obj in plans
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(scores)

    print(f"  Done: wrote {len(scores)} scores -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute symmetry metrics for one or more ensembles."
    )
    add_config_args(parser)
    parser.add_argument("--graph", default=None, help="Override config metrics.symmetry.graph")
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)

    if args.seed is not None:
        cfg["performance"]["random_seed"] = args.seed

    graph_path = (
        Path(args.graph) if args.graph else top_dir / cfg["metrics"]["symmetry"]["graph"]
    )
    print(f"Loading graph from {graph_path}")
    graph = Graph.from_json(str(graph_path))

    election = get_pi_election(cfg, "election_for_symmetry")
    updaters = {"PI": election}
    metrics = cfg.get("symmetry_metrics", ["PB", "EG", "MM", "PG"])
    compute_score = build_compute_score(updaters, metrics)

    ensembles = filter_ensembles(cfg, args.ensembles)
    n_jobs = cfg["performance"]["n_jobs"]
    output_template = cfg["metrics"]["symmetry"]["output"]

    for ensemble in ensembles:
        for chain_name, input_path in iter_chain_inputs(
            cfg,
            top_dir,
            ensemble,
            include_derivatives=args.include_derivatives,
        ):
            output_path = resolve_output_path(
                cfg, top_dir, output_template, name=chain_name
            )
            run_chain(chain_name, input_path, output_path, graph, compute_score, n_jobs)

    print("\nAll done.")


if __name__ == "__main__":
    main()
