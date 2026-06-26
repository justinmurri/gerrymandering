"""Compute county/municipality split scores for ensemble JSONLs.

Usage:
    python process_split_scores.py --config config_UT.yaml
    python process_split_scores.py --config config_UT.yaml --include-derivatives
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jsonlines as jl
import numpy as np
from gerrychain import Graph
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


def precompute_edge_arrays(graph: Graph, county_col: str, municipality_col: str):
    edges = np.asarray(list(graph.edges()), dtype=np.int64)
    u = edges[:, 0]
    v = edges[:, 1]

    same_county_mask = np.fromiter(
        (
            graph.nodes[int(a)][county_col] == graph.nodes[int(b)][county_col]
            for a, b in edges
        ),
        dtype=bool,
        count=len(edges),
    )
    county_names = np.fromiter(
        (graph.nodes[int(a)][county_col] for a, _ in edges),
        dtype=object,
        count=len(edges),
    )

    same_place_mask = np.fromiter(
        (
            graph.nodes[int(a)][municipality_col] == graph.nodes[int(b)][municipality_col]
            for a, b in edges
        ),
        dtype=bool,
        count=len(edges),
    )
    place_names = np.fromiter(
        (graph.nodes[int(a)][municipality_col] for a, _ in edges),
        dtype=object,
        count=len(edges),
    )
    return u, v, same_county_mask, same_place_mask, county_names, place_names


def build_compute_score(u, v, same_county_mask, same_place_mask, county_names, place_names):
    def compute_score(obj):
        assignment = np.asarray(obj["assignment"], dtype=np.int32)
        cut = assignment[u] != assignment[v]
        return {
            "sample": obj["sample"],
            "scores": {
                "county_splits": len(set(county_names[cut & same_county_mask])),
                "muni_splits": len(set(place_names[cut & same_place_mask])),
                "cut_edges": int(cut.sum()),
            },
        }

    return compute_score


def run_chain(
    chain_name: str,
    input_path: Path,
    output_path: Path,
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

    with joblib_progress(description=f"Split scores [{chain_name}]", total=len(plans)):
        scores = Parallel(n_jobs=n_jobs)(delayed(compute_score)(obj) for obj in plans)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(scores)

    print(f"  Done: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute split scores for one or more ensembles."
    )
    add_config_args(parser)
    parser.add_argument("--graph", default=None, help="Override config metrics.symmetry.graph")
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)

    graph_path = (
        Path(args.graph) if args.graph else top_dir / cfg["metrics"]["symmetry"]["graph"]
    )
    print(f"Loading graph from {graph_path}")
    graph = Graph.from_json(str(graph_path))

    cols = cfg["columns"]
    u, v, same_county_mask, same_place_mask, county_names, place_names = precompute_edge_arrays(
        graph, cols["county"], cols["municipality"]
    )
    compute_score = build_compute_score(
        u, v, same_county_mask, same_place_mask, county_names, place_names
    )

    ensembles = filter_ensembles(cfg, args.ensembles)
    n_jobs = cfg["performance"]["n_jobs"]
    output_template = cfg["metrics"]["splits"]["output"]

    for ensemble in ensembles:
        for chain_name, input_path in iter_chain_inputs(
            cfg, top_dir, ensemble, include_derivatives=args.include_derivatives
        ):
            output_path = resolve_output_path(
                cfg, top_dir, output_template, name=chain_name
            )
            run_chain(chain_name, input_path, output_path, compute_score, n_jobs)

    print("\nAll done.")


if __name__ == "__main__":
    main()
