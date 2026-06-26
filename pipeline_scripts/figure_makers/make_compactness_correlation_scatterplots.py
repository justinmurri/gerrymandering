"""Scatterplots of compactness vs partisan metrics, with Pearson correlation.

Usage:
    python make_compactness_correlation_scatterplots.py --config config_UT.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from gerrytools.plotting import districtr

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
    subsample_for_scatter,
)
from correlation import load_compactness, load_lrvs, load_symmetry  # noqa: E402

COMPACTNESS_SOURCES = [
    {"key": "polsby_mean", "label": "Polsby-Popper (mean)", "suffix": "polsby"},
    {"key": "reock_mean", "label": "Reock (mean)", "suffix": "reock"},
]
Y_METRICS = [
    {"key": "PB", "label": "Partisan Bias (PB)"},
    {"key": "EG", "label": "Efficiency Gap (EG)"},
    {"key": "LRVS", "label": "LRVS"},
]
SYMMETRY_KEYS = ["PB", "EG", "MM", "PG"]


def merge_records(cfg, top_dir, chain_name, compactness_suffix):
    compactness_path = metric_output_path(cfg, top_dir, compactness_suffix, chain_name)
    if not compactness_path.exists():
        return []

    compactness_rows = load_compactness(compactness_path)
    sample_ids = {s for s, _ in compactness_rows}
    sym_path = metric_output_path(cfg, top_dir, "symmetry", chain_name)
    sym_map = load_symmetry(sym_path) if sym_path.exists() else {}
    lrvs_path = metric_output_path(cfg, top_dir, "rmd", chain_name, output_key="lrvs")
    lrvs_values = load_lrvs(lrvs_path) if lrvs_path.exists() else []

    records = []
    for row_index, (sample, compactness_value) in enumerate(compactness_rows):
        if sample not in sym_map:
            continue
        record = {"sample": sample, "compactness": compactness_value}
        for key in SYMMETRY_KEYS:
            record[key] = sym_map[sample][key]
        if row_index < len(lrvs_values):
            record["LRVS"] = lrvs_values[row_index]
        records.append(record)
    return records


def load_human_points(cfg, top_dir):
    with open(human_plan_scores_path(cfg, top_dir)) as f:
        plan_scores = json.load(f)
    lrvs_by_plan = {}
    rmd_path = human_rmd_path(cfg, top_dir)
    if rmd_path.exists():
        with open(rmd_path) as f:
            lrvs_by_plan = {plan: data["LRVS"] for plan, data in json.load(f).items()}

    points = {}
    for plan, scores in plan_scores.items():
        points[plan] = {
            "polsby_mean": float(np.mean(list(scores["polsby_popper"].values()))),
            "reock_mean": float(np.mean(list(scores["reock"].values()))),
            "PB": scores["PB"],
            "EG": scores["EG"],
            "LRVS": lrvs_by_plan.get(plan),
        }
    return points


def maybe_subsample(records, cfg, chain_name):
    if not subsample_for_scatter(cfg, chain_name):
        return records
    cap = cfg["performance"]["subsample"]["scatter"]
    if len(records) <= cap:
        return records
    rng = np.random.default_rng(cfg["performance"]["random_seed"])
    idx = rng.choice(len(records), size=cap, replace=False)
    return [records[i] for i in idx]


def plot_scatter(x, y, label, color, x_label, y_label, output_path, human_x=None, human_y=None, human_labels=None):
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    corr = float(np.corrcoef(x, y)[0, 1]) if len(x) > 1 else float("nan")
    ax.scatter(x, y, s=12, alpha=0.15, color=color, label=label)
    if human_x and human_y:
        ax.scatter(human_x, human_y, s=60, marker="*", c=districtr(len(human_x)), edgecolors="black", linewidths=0.4, zorder=3, label="Human plans")
        if human_labels:
            for hx, hy, lbl in zip(human_x, human_y, human_labels):
                ax.annotate(lbl, (hx, hy), textcoords="offset points", xytext=(4, 4), fontsize=6)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(f"{x_label} vs {y_label}\n{label} (r = {corr:.3f}, n = {len(x)})")
    ax.legend(loc="best")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compactness correlation scatterplots.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--ensembles", nargs="*", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    fig_dir = figures_dir(cfg, top_dir)
    human_points = load_human_points(cfg, top_dir)
    human_labels = sorted(human_points.keys())

    ensemble_names = args.ensembles or cfg["tables"]["compactness_correlation"]["ensembles"]
    if args.ensembles:
        filter_ensembles(cfg, args.ensembles)

    for chain_name in ensemble_names:
        meta = resolve_ensemble_meta(cfg, chain_name)
        for compactness_source in COMPACTNESS_SOURCES:
            records = maybe_subsample(merge_records(cfg, top_dir, chain_name, compactness_source["suffix"]), cfg, chain_name)
            if not records:
                continue
            compactness_key = compactness_source["key"]
            for y_metric in Y_METRICS:
                y_key = y_metric["key"]
                paired = [(r["compactness"], r[y_key]) for r in records if y_key in r and r[y_key] is not None]
                if len(paired) < 2:
                    continue
                x_vals = np.array([p[0] for p in paired])
                y_vals = np.array([p[1] for p in paired])
                hx, hy, hl = [], [], []
                for plan in human_labels:
                    if human_points[plan].get(compactness_key) is None or human_points[plan].get(y_key) is None:
                        continue
                    hx.append(human_points[plan][compactness_key])
                    hy.append(human_points[plan][y_key])
                    hl.append(plan)
                output = fig_dir / f"{chain_name}_{compactness_source['suffix']}_vs_{y_key}_scatter.png"
                plot_scatter(x_vals, y_vals, meta["label"], meta["color"], compactness_source["label"], y_metric["label"], output, hx, hy, hl)
                print(f"Wrote {output.name}")


if __name__ == "__main__":
    main()
