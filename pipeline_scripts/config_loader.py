"""Shared config loading and path resolution for pipeline scripts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterator

import jsonlines as jl
import numpy as np
import yaml
from gerrychain.updaters import Election


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    fmt = {
        "abbrev": cfg["state"]["abbrev"],
        "vintage": cfg["state"]["data_vintage"],
    }
    return _resolve(cfg, fmt)


def _resolve(obj, fmt: dict):
    if isinstance(obj, str):
        try:
            return obj.format_map(fmt)
        except KeyError:
            return obj
    if isinstance(obj, dict):
        return {k: _resolve(v, fmt) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve(i, fmt) for i in obj]
    return obj


def project_root(config_path: str) -> Path:
    return Path(config_path).resolve().parent


def format_path(template: str, **kwargs) -> str:
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def resolve_output_path(cfg: dict, top_dir: Path, template: str, **kwargs) -> Path:
    return top_dir / format_path(template, **kwargs)


def filter_ensembles(cfg: dict, names: list[str] | None) -> list[dict]:
    all_ensembles = cfg["ensembles"]
    if not names:
        return all_ensembles
    known = {e["name"] for e in all_ensembles}
    unknown = set(names) - known
    if unknown:
        raise SystemExit(
            f"Unknown ensemble(s): {sorted(unknown)}. Valid names: {sorted(known)}"
        )
    return [e for e in all_ensembles if e["name"] in set(names)]


def load_plans(input_path: Path, subsample: int | None, seed: int) -> list[dict]:
    with jl.open(input_path) as reader:
        plans = list(reader)

    if subsample is None or subsample >= len(plans):
        return plans

    rng = np.random.default_rng(seed)
    indices = rng.choice(len(plans), size=subsample, replace=False)
    return [plans[i] for i in sorted(indices)]


def effective_subsample(ensemble: dict, cfg: dict, metric_key: str) -> int | None:
    if ensemble.get("subsample") is not None:
        return ensemble["subsample"]
    return cfg["performance"]["subsample"].get(metric_key)


def iter_chain_inputs(
    cfg: dict,
    top_dir: Path,
    ensemble: dict,
    *,
    include_derivatives: bool = False,
) -> Iterator[tuple[str, Path]]:
    name = ensemble["name"]
    yield name, top_dir / ensemble["chain_raw"]

    if not include_derivatives:
        return

    derivatives = cfg.get("chain_derivatives", {})
    election = cfg["elections"]["election_for_pb_culling"]

    pb_template = derivatives.get("winnowed_pb")
    if pb_template:
        pb_path = top_dir / format_path(pb_template, name=name, election=election)
        if pb_path.exists():
            yield f"{name}_winnowed_pb", pb_path

    road_template = derivatives.get("winnowed_pb_roads")
    if road_template:
        for road_type in cfg["preprocessing"]["cull"]["road_types"]:
            road_path = top_dir / format_path(
                road_template, name=name, road_type=road_type
            )
            if road_path.exists():
                yield f"{name}_winnowed_pb_winnowed_roads_{road_type}", road_path


def get_pi_election(cfg: dict, purpose: str) -> Election:
    pi_name = cfg["elections"][purpose]
    for pi in cfg["elections"]["pi_types"]:
        if pi["name"] == pi_name:
            return Election(
                pi["name"],
                {"Dem": pi["dem_col"], "GOP": pi["gop_col"]},
                alias=pi["name"],
            )
    raise KeyError(f"PI type {pi_name!r} not found in elections.pi_types")


def add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        required=True,
        help="Path to pipeline config YAML (e.g. config_UT.yaml)",
    )
    parser.add_argument(
        "--ensembles",
        nargs="*",
        default=None,
        help="Ensemble names to run (default: all ensembles in config)",
    )
    parser.add_argument(
        "--seed",
        default=None,
        type=int,
        help="Override config performance.random_seed",
    )
    parser.add_argument(
        "--include-derivatives",
        action="store_true",
        help="Also process winnowed PB / road-culled chain files when present",
    )


def figures_dir(cfg: dict, top_dir: Path) -> Path:
    return top_dir / cfg["figures"]["output_dir"]


def stats_dir(cfg: dict, top_dir: Path) -> Path:
    return top_dir / cfg["paths"]["stats_dir"]


def human_plan_scores_path(cfg: dict, top_dir: Path) -> Path:
    return top_dir / cfg["human_plans"]["output"]


def human_rmd_path(cfg: dict, top_dir: Path) -> Path:
    return top_dir / cfg["human_rmd"]["output"]


def geoparquet_path(cfg: dict, top_dir: Path) -> Path:
    return top_dir / cfg["inputs"]["geoparquet"]


def metric_output_path(
    cfg: dict,
    top_dir: Path,
    metric: str,
    chain_name: str,
    *,
    output_key: str = "output",
    **fmt,
) -> Path:
    spec = cfg["metrics"][metric]
    template = spec["outputs"][output_key] if "outputs" in spec else spec[output_key]
    return resolve_output_path(cfg, top_dir, template, name=chain_name, **fmt)


def ensemble_by_name(cfg: dict, name: str) -> dict | None:
    for ensemble in cfg["ensembles"]:
        if ensemble["name"] == name:
            return ensemble
    return None


def resolve_ensemble_meta(cfg: dict, chain_name: str) -> dict:
    """Label and color for a base ensemble or derivative chain name."""
    import sys

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from figure_makers.colors import colors as palette

    for ensemble in cfg["ensembles"]:
        base = ensemble["name"]
        if chain_name == base or chain_name.startswith(f"{base}_"):
            label = ensemble.get("label", base)
            if "{abbrev}" in label:
                label = label.format(abbrev=cfg["state"]["abbrev"])
            if chain_name != base:
                label = chain_name
            color_key = ensemble.get("color", "gray1")
            return {
                "name": chain_name,
                "base": base,
                "label": label,
                "color": palette.get(color_key, "#636363"),
            }
    return {"name": chain_name, "base": chain_name, "label": chain_name, "color": "#636363"}


def chain_names_for_table(cfg: dict, names: list[str] | None = None) -> list[str]:
    if names:
        return names
    return cfg.get("tables", {}).get("full_summary", {}).get(
        "ensembles",
        [e["name"] for e in cfg["ensembles"]],
    )


def subsample_for_scatter(cfg: dict, ensemble_name: str) -> bool:
    ensemble = ensemble_by_name(cfg, ensemble_name)
    if ensemble is None:
        return False
    subsample = ensemble.get("subsample")
    if subsample is None:
        return False
    scatter_cap = cfg["performance"]["subsample"].get("scatter", 10000)
    return subsample > scatter_cap


def pipeline_steps(cfg: dict, kind: str) -> list[str]:
    return cfg.get("pipeline", {}).get("steps", {}).get(kind, [])


def resolve_chain_path(
    cfg: dict,
    top_dir: Path,
    ensemble_name: str,
    *,
    chain_override: str | None = None,
    derivative: str = "raw",
) -> Path:
    """Resolve a chain JSONL path for an ensemble.

    derivative: raw | canonical | winnowed_pb
    """
    if chain_override:
        return Path(chain_override) if Path(chain_override).is_absolute() else top_dir / chain_override

    ensemble = ensemble_by_name(cfg, ensemble_name)
    if ensemble is None:
        raise SystemExit(f"Unknown ensemble: {ensemble_name!r}")

    derivatives = cfg.get("chain_derivatives", {})
    if derivative == "canonical" and derivatives.get("canonical"):
        path = top_dir / format_path(derivatives["canonical"], name=ensemble_name)
        if path.exists():
            return path
    if derivative == "winnowed_pb" and derivatives.get("winnowed_pb"):
        election = cfg["elections"]["election_for_pb_culling"]
        path = top_dir / format_path(derivatives["winnowed_pb"], name=ensemble_name, election=election)
        if path.exists():
            return path

    return top_dir / ensemble["chain_raw"]


def load_plan_from_chain(
    chain_path: Path,
    *,
    plan_index: int | None = None,
    sample: int | None = None,
) -> dict:
    import jsonlines as jl

    if plan_index is None and sample is None:
        plan_index = 0

    with jl.open(chain_path) as reader:
        for i, obj in enumerate(reader):
            if sample is not None and obj.get("sample") == sample:
                return obj
            if plan_index is not None and i == plan_index:
                return obj

    if sample is not None:
        raise ValueError(f"Sample {sample} not found in {chain_path}")
    raise ValueError(f"Plan index {plan_index} out of range in {chain_path}")
