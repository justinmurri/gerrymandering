"""Compute RMD and LRVS scores for ensemble JSONLs and human plans.

Usage:
    python process_RMD_MCMC.py --config config_UT.yaml
    python process_RMD_MCMC.py --config config_UT.yaml --ensembles recom1M harvard
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonlines as jl
import numpy as np
import pandas as pd
from gerrychain import Graph, Partition
from joblib import Parallel, delayed
from joblib_progress import joblib_progress

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    add_config_args,
    effective_subsample,
    filter_ensembles,
    get_pi_election,
    iter_chain_inputs,
    load_config,
    load_plans,
    project_root,
    resolve_output_path,
)


def r_percents_for_plan(obj: dict, graph: Graph, updaters: dict) -> list[float]:
    part = Partition(
        graph,
        assignment={node: obj["assignment"][node] for node in graph.nodes},
        updaters=updaters,
    )
    return sorted(part["PI"].percents("GOP"))


def compute_ensemble_rmd(
    plans: list[dict],
    graph: Graph,
    updaters: dict,
    n_jobs: int,
) -> pd.DataFrame:
    with joblib_progress(description="Computing R vote shares", total=len(plans)):
        r_percents = Parallel(n_jobs=n_jobs)(
            delayed(r_percents_for_plan)(obj, graph, updaters) for obj in plans
        )

    df = pd.DataFrame(r_percents)
    n_districts = len(r_percents[0])
    meds = df.iloc[:, :n_districts].median(axis=0)
    avgs = df.iloc[:, :n_districts].mean(axis=0)
    df["rmd_medians"] = np.sqrt(
        np.sum((df.iloc[:, :n_districts] - meds) ** 2, axis=1) / n_districts
    )
    df["rmd_averages"] = np.sqrt(
        np.sum((df.iloc[:, :n_districts] - avgs) ** 2, axis=1) / n_districts
    )
    return df, meds, avgs


def write_jsonl_records(df: pd.DataFrame, column: str | int, output_path: Path) -> None:
    if isinstance(column, int):
        df1 = df[[column]].copy()
    else:
        df1 = df[[column]].copy()
    df1.columns = ["scores"]
    df1["sample"] = df1.index
    df1 = df1[["sample", "scores"]]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(df1.to_dict(orient="records"))


def run_chain(
    chain_name: str,
    input_path: Path,
    lrvs_path: Path,
    rmd_medians_path: Path,
    graph: Graph,
    updaters: dict,
    subsample: int | None,
    seed: int,
    n_jobs: int,
) -> tuple[pd.DataFrame, pd.Series, pd.Series] | None:
    print(f"\n── {chain_name} ──────────────────────────────")
    if not input_path.exists():
        print(f"  Skipping: input not found at {input_path}")
        return None

    plans = load_plans(input_path, subsample, seed)
    if not plans:
        print(f"  Skipping: no plans found in {input_path}")
        return None

    print(f"  Input:  {input_path} ({len(plans)} plans)")
    df, meds, avgs = compute_ensemble_rmd(plans, graph, updaters, n_jobs)

    write_jsonl_records(df, 0, lrvs_path)
    write_jsonl_records(df, "rmd_medians", rmd_medians_path)
    print(f"  Done: {lrvs_path.name}, {rmd_medians_path.name}")
    return df, meds, avgs


def compute_human_rmd(
    cfg: dict,
    top_dir: Path,
    graph: Graph,
    updaters: dict,
    reference_name: str,
    reference_df: pd.DataFrame,
    meds: pd.Series,
    avgs: pd.Series,
) -> None:
    plan_names = cfg["human_plans"]["plan_names"]
    first_node = list(graph.nodes)[0]
    plan_name_to_assignment = {}
    for plan in plan_names:
        if plan not in graph.nodes[first_node]:
            print(f"  Warning: plan column {plan!r} not found on graph nodes; skipping")
            continue
        plan_name_to_assignment[plan] = [graph.nodes[node][plan] for node in graph.nodes]

    if not plan_name_to_assignment:
        print("  Skipping human RMD: no plan columns found on graph")
        return

    plan_to_scores: dict = {}
    for plan, assignment in plan_name_to_assignment.items():
        part = Partition(
            graph,
            assignment={i: val for i, val in enumerate(assignment)},
            updaters=updaters,
        )
        r_percents = sorted(part["PI"].percents("GOP"))
        rmd_median = float(np.sqrt(np.sum((r_percents - meds) ** 2)))
        rmd_average = float(np.sqrt(np.sum((r_percents - avgs) ** 2)))

        plan_to_scores[plan] = {
            "LRVS": r_percents[0],
            "RMD_median": rmd_median,
            "RMD_average": rmd_average,
            "PI": r_percents,
            f"RMD_median_{reference_name}_percentile": float(
                np.sum(reference_df["rmd_medians"] <= rmd_median) / len(reference_df)
            ),
        }

    output_path = top_dir / cfg["human_rmd"]["output"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(plan_to_scores, f, indent=4)
    print(f"  Human RMD written -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute RMD and LRVS scores for ensembles and human plans."
    )
    add_config_args(parser)
    parser.add_argument(
        "--reference-ensemble",
        default=None,
        help="Ensemble name for human-plan RMD reference (default: recom1M or first)",
    )
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

    election = get_pi_election(cfg, "election_for_rmd")
    updaters = {"PI": election}

    ensembles = filter_ensembles(cfg, args.ensembles)
    seed = cfg["performance"]["random_seed"]
    n_jobs = cfg["performance"]["n_jobs"]
    lrvs_template = cfg["metrics"]["rmd"]["outputs"]["lrvs"]
    rmd_template = cfg["metrics"]["rmd"]["outputs"]["rmd_medians"]

    reference_name = args.reference_ensemble
    if reference_name is None:
        names = [e["name"] for e in ensembles]
        reference_name = "recom1M" if "recom1M" in names else names[0]

    reference_result = None

    for ensemble in ensembles:
        subsample = effective_subsample(ensemble, cfg, "rmd")
        for chain_name, input_path in iter_chain_inputs(cfg, top_dir, ensemble):
            lrvs_path = resolve_output_path(cfg, top_dir, lrvs_template, name=chain_name)
            rmd_path = resolve_output_path(cfg, top_dir, rmd_template, name=chain_name)
            result = run_chain(
                chain_name,
                input_path,
                lrvs_path,
                rmd_path,
                graph,
                updaters,
                subsample,
                seed,
                n_jobs,
            )
            if result is not None and chain_name == reference_name:
                reference_result = (chain_name, *result)

    if reference_result is not None:
        ref_name, ref_df, meds, avgs = reference_result
        compute_human_rmd(cfg, top_dir, graph, updaters, ref_name, ref_df, meds, avgs)

    print("\nAll done.")


if __name__ == "__main__":
    main()
