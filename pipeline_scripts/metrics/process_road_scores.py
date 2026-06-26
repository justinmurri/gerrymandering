"""Compute road-network discontiguity scores for ensemble JSONLs.

Usage:
    python process_road_scores.py --config config_UT.yaml
    python process_road_scores.py --config config_UT.yaml --ensembles recom1M
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jsonlines as jl
import numpy as np
from gerrychain import Graph, Partition
from joblib import Parallel, delayed
from joblib_progress import joblib_progress
from networkx import connected_components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    add_config_args,
    filter_ensembles,
    iter_chain_inputs,
    load_config,
    project_root,
    resolve_output_path,
)


def discontiguity_num(partition: Partition) -> int:
    num_districts = len(partition.parts.keys())
    total_pieces = sum(
        len(list(connected_components(partition.subgraphs[district])))
        for district in partition.parts.keys()
    )
    return total_pieces - num_districts


def discontiguity_scores(partition: Partition, pop_col: str) -> tuple[float, float]:
    weighted_discontiguity = 0.0
    discontiguity_score = 0.0

    for district in partition.parts.keys():
        subgraph = partition.subgraphs[district]
        components = list(connected_components(subgraph))
        if len(components) <= 1:
            continue

        component_pop = {
            i: sum(partition.graph.nodes[node][pop_col] for node in component)
            for i, component in enumerate(components)
        }
        main_component_index = max(component_pop, key=component_pop.get)
        district_pop = sum(component_pop.values())
        weighted_discontiguity += sum(
            component_pop[i] for i in range(len(components)) if i != main_component_index
        ) / district_pop
        discontiguity_score += sum(
            np.sqrt(component_pop[i] / district_pop)
            for i in range(len(components))
            if i != main_component_index
        )

    return weighted_discontiguity, discontiguity_score


def build_compute_scores(road_graph: Graph, road_nodes: list, pop_col: str):
    def compute_scores(obj):
        assignment = {n: obj["assignment"][n] for n in road_nodes}
        partition = Partition(road_graph, assignment)
        d_scores = discontiguity_scores(partition, pop_col)
        return {
            "sample": obj["sample"],
            "scores": {
                "excess_pieces": discontiguity_num(partition),
                "pop_weighted_discontiguity": d_scores[0],
                "discontiguity_score": d_scores[1],
            },
        }

    return compute_scores


def run_chain(
    chain_name: str,
    input_path: Path,
    output_path: Path,
    compute_scores,
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

    with joblib_progress(
        description=f"Road scores [{chain_name}]", total=len(plans)
    ):
        scores = Parallel(n_jobs=n_jobs)(
            delayed(compute_scores)(obj) for obj in plans
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(scores)

    print(f"  Done: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute road discontiguity scores for one or more ensembles."
    )
    add_config_args(parser)
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    pop_col = cfg["columns"]["pop100"]
    n_jobs = cfg["performance"]["n_jobs"]
    output_template = cfg["metrics"]["road_scores"]["output"]
    road_graph_templates = cfg["inputs"]["road_graphs"]

    ensembles = filter_ensembles(cfg, args.ensembles)

    for road_type in cfg["preprocessing"]["cull"]["road_types"]:
        road_path = top_dir / road_graph_templates[road_type]
        print(f"\nLoading road graph ({road_type}) from {road_path}")
        road_graph = Graph.from_json(str(road_path))
        road_nodes = list(road_graph.nodes)
        compute_scores = build_compute_scores(road_graph, road_nodes, pop_col)

        for ensemble in ensembles:
            for chain_name, input_path in iter_chain_inputs(
                cfg, top_dir, ensemble, include_derivatives=args.include_derivatives
            ):
                output_path = resolve_output_path(
                    cfg,
                    top_dir,
                    output_template,
                    name=chain_name,
                    road_type=road_type,
                )
                run_chain(chain_name, input_path, output_path, compute_scores, n_jobs)

    print("\nAll done.")


if __name__ == "__main__":
    main()
