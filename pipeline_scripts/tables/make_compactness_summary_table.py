"""Summary table of Polsby and Reock stats for any configured ensembles.

Usage:
    python make_compactness_summary_table.py --config config_UT.yaml
    python make_compactness_summary_table.py --config config_UT.yaml --ensembles districtPairsRA harvard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jsonlines as jl
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    load_config,
    metric_output_path,
    project_root,
    resolve_ensemble_meta,
)


def _count_lines(path: Path) -> int:
    with jl.open(path) as reader:
        return sum(1 for _ in reader)


def _compactness_stats(path: Path) -> tuple[float, float, float, float]:
    plan_means: list[float] = []
    plan_mins: list[float] = []
    all_values: list[float] = []

    with jl.open(path) as reader:
        for obj in reader:
            values = list(obj["scores"].values())
            all_values.extend(values)
            plan_means.append(sum(values) / len(values))
            plan_mins.append(min(values))

    return (
        float(np.mean(plan_means)),
        float(np.mean(plan_mins)),
        float(np.min(all_values)),
        float(np.max(all_values)),
    )


def default_ensemble_names(cfg: dict) -> list[str]:
    table_cfg = cfg.get("tables", {}).get("compactness_summary", {})
    if table_cfg.get("ensembles"):
        return table_cfg["ensembles"]
    return [e["name"] for e in cfg["ensembles"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compactness summary table for any ensembles.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--ensembles", nargs="*", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    ensemble_names = args.ensembles or default_ensemble_names(cfg)
    rows: list[dict] = []

    for name in ensemble_names:
        polsby_path = metric_output_path(cfg, top_dir, "polsby", name)
        reock_path = metric_output_path(cfg, top_dir, "reock", name)
        if not polsby_path.exists() or not reock_path.exists():
            print(f"Skipping {name}: missing score files")
            continue

        meta = resolve_ensemble_meta(cfg, name)
        polsby_mean, polsby_min, polsby_gmin, polsby_gmax = _compactness_stats(polsby_path)
        reock_mean, reock_min, reock_gmin, reock_gmax = _compactness_stats(reock_path)

        rows.append(
            {
                "ensemble": name,
                "label": meta["label"],
                "n_plans": _count_lines(polsby_path),
                "polsby_mean_of_plan_means": polsby_mean,
                "polsby_mean_of_plan_mins": polsby_min,
                "polsby_min_district": polsby_gmin,
                "polsby_max_district": polsby_gmax,
                "reock_mean_of_plan_means": reock_mean,
                "reock_mean_of_plan_mins": reock_min,
                "reock_min_district": reock_gmin,
                "reock_max_district": reock_gmax,
            }
        )

    if not rows:
        raise SystemExit("No compactness score files found. Run polsby and reock metrics first.")

    output = top_dir / cfg["tables"]["compactness_summary"]["output"]
    df = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, float_format="%.4f")
    print(f"Wrote {len(df)} rows to {output}")


if __name__ == "__main__":
    main()
