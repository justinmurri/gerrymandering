"""Build a combined CSV summary of human plans and ensemble statistics.

Usage:
    python make_plan_table.py --config config_UT.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonlines as jl
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    chain_names_for_table,
    human_plan_scores_path,
    load_config,
    metric_output_path,
    project_root,
    resolve_ensemble_meta,
)

FLAT_METRICS = ["PB", "EG", "MM", "PG", "county_splits", "muni_splits", "cut_edges", "always_r_count"]


def _mean(values: dict) -> float:
    return sum(values.values()) / len(values)


def _min(values: dict) -> float:
    return min(values.values())


def _avg(values: list[float]) -> float:
    return float(np.mean(values))


def _load_optional(path: Path | None) -> bool:
    return path is not None and path.exists()


def _mean_symmetry(path: Path, metrics: list[str]) -> dict[str, float]:
    totals = {metric: [] for metric in metrics}
    with jl.open(path) as reader:
        for obj in reader:
            for metric in metrics:
                totals[metric].append(obj["scores"][metric])
    return {metric: _avg(values) for metric, values in totals.items()}


def _mean_dem_wins(path: Path, races: list[str]) -> dict[str, float]:
    totals = {race: [] for race in races}
    with jl.open(path) as reader:
        for obj in reader:
            for race in races:
                totals[race].append(obj["scores"][race])
    return {race: _avg(values) for race, values in totals.items()}


def _mean_scalar(path: Path, field: str) -> float:
    values: list[float] = []
    with jl.open(path) as reader:
        for obj in reader:
            values.append(obj[field])
    return _avg(values)


def _mean_splits(path: Path) -> dict[str, float]:
    totals = {key: [] for key in ("county_splits", "muni_splits", "cut_edges")}
    with jl.open(path) as reader:
        for obj in reader:
            for key in totals:
                totals[key].append(obj["scores"][key])
    return {key: _avg(values) for key, values in totals.items()}


def _mean_compactness(path: Path) -> tuple[float, float]:
    plan_means: list[float] = []
    plan_mins: list[float] = []
    with jl.open(path) as reader:
        for obj in reader:
            values = list(obj["scores"].values())
            plan_means.append(sum(values) / len(values))
            plan_mins.append(min(values))
    return _avg(plan_means), _avg(plan_mins)


def _count_lines(path: Path) -> int:
    with jl.open(path) as reader:
        return sum(1 for _ in reader)


def build_human_row(plan_name: str, scores: dict, races: list[str], include_compactness: bool) -> dict:
    row: dict = {
        "row_type": "human",
        "plan": plan_name,
        "ensemble": None,
        "label": plan_name,
        "n_plans": None,
    }
    for metric in FLAT_METRICS:
        row[metric] = scores.get(metric)

    dem_wins = scores["dem_wins_by_race"]
    row["total_dem_wins"] = sum(dem_wins.values())
    row["races_with_dem_win"] = sum(v > 0 for v in dem_wins.values())
    for race in races:
        row[f"{race}_dem_wins"] = dem_wins[race]

    if include_compactness:
        row["polsby_mean"] = _mean(scores["polsby_popper"])
        row["polsby_min"] = _min(scores["polsby_popper"])
        row["reock_mean"] = _mean(scores["reock"])
        row["reock_min"] = _min(scores["reock"])
    return row


def build_ensemble_row(cfg: dict, top_dir: Path, chain_name: str, races: list[str], include_compactness: bool) -> dict | None:
    meta = resolve_ensemble_meta(cfg, chain_name)
    symmetry_path = metric_output_path(cfg, top_dir, "symmetry", chain_name)
    if not _load_optional(symmetry_path):
        print(f"Skipping {chain_name}: missing {symmetry_path.name}")
        return None

    symmetry_metrics = cfg.get("symmetry_metrics", ["PB", "EG", "MM", "PG"])
    row: dict = {
        "row_type": "ensemble",
        "plan": None,
        "ensemble": chain_name,
        "label": meta["label"],
        "n_plans": _count_lines(symmetry_path),
    }
    row.update(_mean_symmetry(symmetry_path, symmetry_metrics))

    splits_path = metric_output_path(cfg, top_dir, "splits", chain_name)
    if _load_optional(splits_path):
        row.update(_mean_splits(splits_path))

    always_r_path = metric_output_path(cfg, top_dir, "dem_wins", chain_name, output_key="always_r")
    if _load_optional(always_r_path):
        row["always_r_count"] = _mean_scalar(always_r_path, "always_r_count")

    dem_wins_path = metric_output_path(cfg, top_dir, "dem_wins", chain_name, output_key="dem_wins")
    if _load_optional(dem_wins_path):
        dem_avgs = _mean_dem_wins(dem_wins_path, races)
        for race in races:
            row[f"{race}_dem_wins"] = dem_avgs[race]
        row["total_dem_wins"] = sum(dem_avgs.values())
        row["races_with_dem_win"] = sum(v > 0 for v in dem_avgs.values())

    if include_compactness:
        polsby_path = metric_output_path(cfg, top_dir, "polsby", chain_name)
        reock_path = metric_output_path(cfg, top_dir, "reock", chain_name)
        if _load_optional(polsby_path):
            row["polsby_mean"], row["polsby_min"] = _mean_compactness(polsby_path)
        if _load_optional(reock_path):
            row["reock_mean"], row["reock_min"] = _mean_compactness(reock_path)

    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Build human + ensemble summary CSV.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    races = cfg["elections"]["races"]
    include_compactness = cfg.get("tables", {}).get("full_summary", {}).get("include_compactness", True)

    human_path = human_plan_scores_path(cfg, top_dir)
    with open(human_path) as f:
        human_data = json.load(f)
    human_rows = [
        build_human_row(name, scores, races, include_compactness)
        for name, scores in sorted(human_data.items())
    ]

    ensemble_rows = []
    for chain_name in chain_names_for_table(cfg):
        row = build_ensemble_row(cfg, top_dir, chain_name, races, include_compactness)
        if row is not None:
            ensemble_rows.append(row)

    human_df = pd.DataFrame(human_rows)
    ensemble_df = pd.DataFrame(ensemble_rows)
    combined = pd.concat([human_df, ensemble_df], ignore_index=True, sort=False) if not ensemble_df.empty else human_df

    column_order = [
        "row_type", "plan", "ensemble", "label", "n_plans",
        *FLAT_METRICS, "total_dem_wins", "races_with_dem_win",
        *[f"{race}_dem_wins" for race in races],
        *(
            ["polsby_mean", "polsby_min", "reock_mean", "reock_min"]
            if include_compactness
            else []
        ),
    ]
    cols = [c for c in column_order if c in combined.columns]
    combined = combined[cols]

    output = Path(args.output) if args.output else top_dir / cfg["tables"]["full_summary"]["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False, float_format="%.4f")

    n_human = (combined["row_type"] == "human").sum()
    n_ensemble = (combined["row_type"] == "ensemble").sum()
    print(f"Wrote {len(combined)} rows to {output} ({n_human} human, {n_ensemble} ensemble)")


if __name__ == "__main__":
    main()
