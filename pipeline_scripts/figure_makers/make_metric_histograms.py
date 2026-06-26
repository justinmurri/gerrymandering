"""Histogram figures for compactness, symmetry, RMD, LRVS, and split metrics.

Usage:
    python make_metric_histograms.py --config config_UT.yaml
    python make_metric_histograms.py --config config_UT.yaml --metrics polsby symmetry
    python make_metric_histograms.py --config config_UT.yaml --ensembles districtPairsRA harvard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    figures_dir,
    filter_ensembles,
    human_plan_scores_path,
    human_rmd_path,
    load_config,
    metric_output_path,
    project_root,
    resolve_ensemble_meta,
)
from plotting_utils import (  # noqa: E402
    add_human_vlines,
    int_hist,
    load_district_scores,
    load_human_plans,
    load_plan_level_scores,
    save_figure,
)

METRIC_SPECS = {
    "polsby": {"type": "district", "metric_key": "polsby", "human_key": "polsby_popper", "label": "Polsby-Popper"},
    "reock": {"type": "district", "metric_key": "reock", "human_key": "reock", "label": "Reock"},
    "symmetry": {"type": "symmetry", "metric_key": "symmetry", "human_keys": ["PB", "EG", "MM", "PG"]},
    "lrvs": {"type": "scalar", "metric_key": "rmd", "output_key": "lrvs", "human_rmd_key": "LRVS", "label": "LRVS"},
    "rmd": {"type": "scalar", "metric_key": "rmd", "output_key": "rmd_medians", "human_rmd_key": "RMD_median", "label": "RMD"},
    "splits": {
        "type": "split",
        "metric_key": "splits",
        "keys": [
            ("county_splits", "County Split Count"),
            ("muni_splits", "Municipality Split Count"),
            ("cut_edges", "Cut Edge Count"),
        ],
    },
}


def _histogram_basename(abbrev: str, file_tag: str | None, *parts: str) -> str:
    stem = "_".join(parts)
    if file_tag:
        # Match dem_wins / compactness_scatter: ensemble name only when --ensembles is set.
        return f"{file_tag}_{stem}.png"
    return f"{abbrev}_{stem}.png"


def _write_figure(fig_dir, filename: str) -> None:
    output = save_figure(fig_dir, filename)
    print(f"Wrote {output.name}")


def plot_district_metric(cfg, top_dir, fig_dir, human_plans, overlay_group, spec, *, file_tag: str | None = None):
    abbrev = cfg["state"]["abbrev"]
    _, ax = plt.subplots(figsize=(10, 6), dpi=300)
    plotted = False
    for chain_name in overlay_group:
        path = metric_output_path(cfg, top_dir, spec["metric_key"], chain_name)
        if not path.exists():
            print(f"Skipping {chain_name} {spec['metric_key']}: missing {path.name}")
            continue
        meta = resolve_ensemble_meta(cfg, chain_name)
        values = load_district_scores(path)
        n_plans = len(values) // cfg["state"]["n_districts"]
        ax.hist(values, bins=50, alpha=0.45, density=True, color=meta["color"], label=f"{meta['label']} (n={n_plans})")
        plotted = True

    if not plotted:
        plt.close()
        chains = ", ".join(overlay_group)
        print(f"Skipping {spec['metric_key']}_scores_histogram: no data for [{chains}]")
        return

    add_human_vlines(ax, human_plans, lambda s: s[spec["human_key"]], offset=0.0)
    ax.legend(bbox_to_anchor=(1.01, 0.5), loc="center left")
    ax.set_title(f"{spec['label']} Score Distribution")
    ax.set_xlabel(spec["label"])
    ax.set_ylabel("Density")
    _write_figure(fig_dir, _histogram_basename(abbrev, file_tag, f"{spec['metric_key']}_scores_histogram"))


def plot_symmetry(cfg, top_dir, fig_dir, human_plans, overlay_group, *, file_tag: str | None = None):
    abbrev = cfg["state"]["abbrev"]
    metrics = cfg.get("symmetry_metrics", ["PB", "EG", "MM", "PG"])
    for metric in metrics:
        _, ax = plt.subplots(figsize=(10, 6), dpi=300)
        plotted = False
        for chain_name in overlay_group:
            path = metric_output_path(cfg, top_dir, "symmetry", chain_name)
            if not path.exists():
                continue
            meta = resolve_ensemble_meta(cfg, chain_name)
            values = load_plan_level_scores(path, metric)
            ax.hist(values, bins=50, alpha=0.45, density=True, color=meta["color"], label=meta["label"])
            plotted = True
        if not plotted:
            plt.close()
            chains = ", ".join(overlay_group)
            print(f"Skipping {metric}_scores_histogram: no data for [{chains}]")
            continue
        add_human_vlines(ax, human_plans, lambda s, m=metric: s.get(m), offset=0.0)
        ax.legend(bbox_to_anchor=(1.01, 0.5), loc="center left")
        ax.set_title(f"{metric} Scores Distribution")
        ax.set_xlabel(f"{metric} Score")
        ax.set_ylabel("Density")
        _write_figure(fig_dir, _histogram_basename(abbrev, file_tag, f"{metric}_scores_histogram"))


def plot_scalar_metric(
    cfg,
    top_dir,
    fig_dir,
    human_plans,
    human_rmd,
    overlay_group,
    spec,
    *,
    metric_name: str,
    file_tag: str | None = None,
):
    abbrev = cfg["state"]["abbrev"]
    _, ax = plt.subplots(figsize=(10, 6), dpi=300)
    plotted = False
    for chain_name in overlay_group:
        path = metric_output_path(cfg, top_dir, spec["metric_key"], chain_name, output_key=spec["output_key"])
        if not path.exists():
            continue
        meta = resolve_ensemble_meta(cfg, chain_name)
        values = load_plan_level_scores(path)
        ax.hist(values, bins=50, alpha=0.45, density=True, color=meta["color"], label=meta["label"])
        plotted = True

    if not plotted:
        plt.close()
        chains = ", ".join(overlay_group)
        print(f"Skipping {metric_name}_histogram: no data for [{chains}]")
        return

    if human_rmd:
        add_human_vlines(
            ax,
            human_rmd,
            lambda s: s.get(spec["human_rmd_key"]),
            offset=0.01,
        )
    ax.legend(bbox_to_anchor=(1.01, 0.5), loc="center left")
    ax.set_title(f"{spec['label']} Scores Distribution")
    ax.set_xlabel(spec["label"])
    ax.set_ylabel("Density")
    _write_figure(fig_dir, _histogram_basename(abbrev, file_tag, f"{metric_name}_histogram"))


def plot_splits(cfg, top_dir, fig_dir, human_plans, overlay_group, *, file_tag: str | None = None):
    abbrev = cfg["state"]["abbrev"]
    for key, xlabel in METRIC_SPECS["splits"]["keys"]:
        _, ax = plt.subplots(figsize=(10, 6), dpi=300)
        plotted = False
        for chain_name in overlay_group:
            path = metric_output_path(cfg, top_dir, "splits", chain_name)
            if not path.exists():
                continue
            meta = resolve_ensemble_meta(cfg, chain_name)
            values = load_plan_level_scores(path, key)
            if not plotted:
                ax = int_hist(ax, values, f"{xlabel} Distribution", xlabel, meta["color"], meta["label"])
                plotted = True
            else:
                from plotting_utils import add_int_hist

                add_int_hist(ax, values, meta["color"], meta["label"])
        if not plotted:
            plt.close()
            chains = ", ".join(overlay_group)
            print(f"Skipping {key}_histogram: no data for [{chains}]")
            continue
        add_human_vlines(ax, human_plans, lambda s, k=key: s.get(k), offset=0.05)
        ax.legend(bbox_to_anchor=(1.01, 0.5), loc="center left")
        _write_figure(fig_dir, _histogram_basename(abbrev, file_tag, f"{key}_histogram"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate metric histogram figures.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--metrics", nargs="*", default=None)
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

    human_rmd = {}
    rmd_path = human_rmd_path(cfg, top_dir)
    if rmd_path.exists():
        import json

        with open(rmd_path) as f:
            human_rmd = json.load(f)

    metrics = args.metrics or cfg["figures"]["histogram"]["metrics"]

    if args.ensembles:
        filter_ensembles(cfg, args.ensembles)
        overlay_group = args.ensembles
        file_tag = args.ensembles[0] if len(args.ensembles) == 1 else "_".join(args.ensembles)
    else:
        overlay_group = cfg["figures"]["histogram"].get("overlay_group", ["harvard", "recom1M"])
        file_tag = None

    for metric in metrics:
        spec = METRIC_SPECS[metric]
        if spec["type"] == "district":
            plot_district_metric(
                cfg, top_dir, fig_dir, human_plans, overlay_group, spec, file_tag=file_tag
            )
        elif spec["type"] == "symmetry":
            plot_symmetry(cfg, top_dir, fig_dir, human_plans, overlay_group, file_tag=file_tag)
        elif spec["type"] == "scalar":
            plot_scalar_metric(
                cfg,
                top_dir,
                fig_dir,
                human_plans,
                human_rmd,
                overlay_group,
                spec,
                metric_name=metric,
                file_tag=file_tag,
            )
        elif spec["type"] == "split":
            plot_splits(cfg, top_dir, fig_dir, human_plans, overlay_group, file_tag=file_tag)
        print(f"Done: {metric}")


if __name__ == "__main__":
    main()
