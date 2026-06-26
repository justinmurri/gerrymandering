"""Democratic win count histogram figures.

Usage:
    python make_dem_win_figures.py --config config_UT.yaml
    python make_dem_win_figures.py --config config_UT.yaml --ensembles districtPairsRA harvard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jsonlines as jl
import matplotlib.pyplot as plt
import numpy as np
from gerrytools.plotting import districtr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    figures_dir,
    filter_ensembles,
    human_plan_scores_path,
    load_config,
    metric_output_path,
    project_root,
    resolve_ensemble_meta,
)
from plotting_utils import add_int_hist, int_hist, load_human_plans, save_figure  # noqa: E402

PLOT_SPECS = [
    ("dem_win_scores_histogram", "all_dem_win_scores", "Democratic Wins Distribution", "Democratic District Wins", False),
    ("dem_election_win_count_histogram", "total_dem_wins", "Total Democratic Wins Distribution", "Democratic Election Wins", True),
    ("dems_win_one_or_more_districts_in_election_histogram", "dems_win_at_least_one", "Democrat Win 1+ District Distribution", "Democrat 1+ District Wins", True),
    ("always_r_count_histogram", "always_r", "Always Republican District Count Distribution", "Always Republican Districts", True),
]


def collect_data(cfg, top_dir, chain_names, races):
    data = {name: {"all_dem_win_scores": [], "total_dem_wins": [], "dems_win_at_least_one": [], "always_r": []} for name in chain_names}

    for name in chain_names:
        dem_path = metric_output_path(cfg, top_dir, "dem_wins", name, output_key="dem_wins")
        always_r_path = metric_output_path(cfg, top_dir, "dem_wins", name, output_key="always_r")
        if not dem_path.exists():
            print(f"Skipping {name}: missing dem_wins")
            continue
        with jl.open(dem_path) as reader:
            for obj in reader:
                scores = obj["scores"]
                data[name]["all_dem_win_scores"].extend(list(scores.values()))
                data[name]["total_dem_wins"].append(sum(scores.values()))
                data[name]["dems_win_at_least_one"].append(sum(v > 0 for v in scores.values()))
        if always_r_path.exists():
            with jl.open(always_r_path) as reader:
                for obj in reader:
                    data[name]["always_r"].append(obj["always_r_count"])

    for name in chain_names:
        for key in data[name]:
            data[name][key] = np.array(data[name][key])
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Dem win count histogram figures.")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--ensembles",
        nargs="*",
        default=None,
        help="One ensemble → its own histogram; two+ → overlaid on one histogram",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    fig_dir = figures_dir(cfg, top_dir)
    human_plans = load_human_plans(human_plan_scores_path(cfg, top_dir))

    if args.ensembles:
        filter_ensembles(cfg, args.ensembles)
        plot_groups = [args.ensembles]
        plot_names = (
            [args.ensembles[0]]
            if len(args.ensembles) == 1
            else ["_".join(args.ensembles)]
        )
    else:
        plot_groups = cfg["figures"]["plot_groups"]
        plot_names = cfg["figures"].get(
            "plot_group_names", [f"group_{i}" for i in range(len(plot_groups))]
        )

    all_names = sorted({n for group in plot_groups for n in group})
    ensemble_data = collect_data(cfg, top_dir, all_names, cfg["elections"]["races"])

    for pi, group in enumerate(plot_groups):
        plot_name = plot_names[pi] if pi < len(plot_names) else f"group_{pi}"
        for suffix, data_key, title, xlabel, overlay_human in PLOT_SPECS:
            base = group[0]
            if data_key not in ensemble_data[base] or len(ensemble_data[base][data_key]) == 0:
                continue
            _, ax = plt.subplots(figsize=(10, 6), dpi=300)
            meta = resolve_ensemble_meta(cfg, base)
            ax = int_hist(ax, ensemble_data[base][data_key], title, xlabel, meta["color"], meta["label"])
            for name in group[1:]:
                if len(ensemble_data[name][data_key]) == 0:
                    continue
                m = resolve_ensemble_meta(cfg, name)
                add_int_hist(ax, ensemble_data[name][data_key], m["color"], m["label"])

            if overlay_human:
                colors = districtr(len(human_plans))
                for i, (plan, scores) in enumerate(human_plans.items()):
                    if data_key == "total_dem_wins":
                        val = sum(scores["dem_wins_by_race"].values())
                    elif data_key == "dems_win_at_least_one":
                        val = sum(v > 0 for v in scores["dem_wins_by_race"].values())
                    elif data_key == "always_r":
                        val = scores["always_r_count"]
                    else:
                        continue
                    ax.axvline(val + i * 0.05, label=plan, color=colors[i])

            ax.legend(bbox_to_anchor=(1.01, 0.5), loc="center left")
            save_figure(fig_dir, f"{plot_name}_{suffix}.png")
            print(f"Wrote {plot_name}_{suffix}.png")


if __name__ == "__main__":
    main()
