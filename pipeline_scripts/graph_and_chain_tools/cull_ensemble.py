"""PB and road-connectivity culling for one canonical ensemble JSONL.

Usage:
    python cull_ensemble.py --config config_UT.yaml --input <canonical.jsonl> --name <ensemble_name>

Optional overrides (all default to config values):
    --pb / --no-pb          Override config preprocessing.cull.pb
    --roads queen rook      Override config preprocessing.cull.road_types
    --graph <path>          Override config preprocessing.cull.graph
"""

from __future__ import annotations

import argparse
from pathlib import Path

import jsonlines as jl
import yaml
from gerrychain import Graph, Partition
from gerrychain.constraints.contiguity import contiguous
from gerrychain.metrics import partisan_bias
from gerrychain.updaters import Election
from joblib import Parallel, delayed
from joblib_progress import joblib_progress
from tqdm import tqdm


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
        try:
            return obj.format_map(fmt)
        except KeyError:
            return obj
    elif isinstance(obj, dict):
        return {k: _resolve(v, fmt) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve(i, fmt) for i in obj]
    return obj


# ── Culling logic ─────────────────────────────────────────────────────────────

def cull_pb(
    input_path: Path,
    output_path: Path,
    graph_path: Path,
    pi_election: Election,
) -> int:
    graph = Graph.from_json(str(graph_path))
    updaters = {pi_election.name: pi_election}

    kept = []
    with jl.open(input_path) as reader:
        for obj in tqdm(reader, desc="PB culling"):
            assignment = {i: d for i, d in enumerate(obj["assignment"])}
            part = Partition(graph, assignment, updaters=updaters)
            if partisan_bias(part[pi_election.name]) == 0:
                kept.append(obj)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(kept)
    return len(kept)


def cull_roads(
    input_path: Path,
    output_path: Path,
    road_graph_path: Path,
    n_jobs: int,
) -> int:
    road_graph = Graph.from_json(str(road_graph_path))
    road_nodes = list(road_graph.nodes)

    with jl.open(input_path) as reader:
        plans = list(reader)

    def is_contiguous(obj: dict) -> bool:
        assignment = {n: obj["assignment"][n] for n in road_nodes}
        return contiguous(Partition(road_graph, assignment))

    with joblib_progress(description=f"Road cull {road_graph_path.name}", total=len(plans)):
        flags = Parallel(n_jobs=n_jobs)(delayed(is_contiguous)(obj) for obj in plans)

    kept = [obj for obj, ok in zip(plans, flags) if ok]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(kept)
    return len(kept)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="PB and road-connectivity culling for a canonical ensemble JSONL.")
    parser.add_argument("--config",  required=True, help="Path to pipeline config YAML (e.g. config_UT.yaml)")
    parser.add_argument("--input",   required=True, help="Canonical ensemble JSONL to cull")
    parser.add_argument("--name",    required=True, help="Ensemble name used in output filenames")
    # Optional overrides — if omitted, values come from the config
    parser.add_argument("--graph",   default=None,  help="Override config preprocessing.cull.graph")
    parser.add_argument("--pb",      action=argparse.BooleanOptionalAction, default=None,
                        help="Override config preprocessing.cull.pb (--pb / --no-pb)")
    parser.add_argument("--roads",   nargs="*",     choices=["queen", "rook"], default=None,
                        help="Override config preprocessing.cull.road_types")
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    cfg  = load_config(args.config)

    top_dir   = Path(__file__).resolve().parents[2]
    cull_cfg  = cfg["preprocessing"]["cull"]

    # Resolve settings: CLI flags take priority over config values
    do_pb      = args.pb     if args.pb    is not None else cull_cfg["pb"]
    road_types = args.roads  if args.roads is not None else cull_cfg["road_types"]
    graph_path = Path(args.graph) if args.graph else top_dir / cull_cfg["graph"]

    # Build the PI election object from config
    pi_cfg = next(
        pi for pi in cfg["elections"]["pi_types"]
        if pi["name"] == cfg["elections"]["election_for_pb_culling"]
    )
    pi_election = Election(
        pi_cfg["name"],
        {"Dem": pi_cfg["dem_col"], "GOP": pi_cfg["gop_col"]},
        alias=pi_cfg["name"],
    )

    # Output filename templates from config
    pb_template   = cfg["chain_derivatives"]["winnowed_pb"]
    road_template = cfg["chain_derivatives"]["winnowed_pb_roads"]

    n_jobs  = cfg["performance"]["n_jobs"]
    name    = args.name
    current = Path(args.input)

    if do_pb:
        pb_out = top_dir / pb_template.format(name=name, election=pi_election.name)
        n = cull_pb(current, pb_out, graph_path, pi_election)
        print(f"PB cull: kept {n} -> {pb_out}")
        current = pb_out

    for road_type in road_types:
        road_graph_path = top_dir / cfg["inputs"]["road_graphs"][road_type]
        road_out = top_dir / road_template.format(name=name, road_type=road_type)
        n = cull_roads(current, road_out, road_graph_path, n_jobs)
        print(f"Road cull ({road_type}): kept {n} -> {road_out}")


if __name__ == "__main__":
    main()