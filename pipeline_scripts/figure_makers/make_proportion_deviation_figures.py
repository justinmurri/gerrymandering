"""Seats-votes plots and deviation-from-proportion histograms.

Usage:
    python make_proportion_deviation_figures.py --config config_UT.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import jsonlines as jl
import matplotlib.pyplot as plt
import numpy as np
from gerrytools.plotting import districtr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    figures_dir,
    filter_ensembles,
    geoparquet_path,
    human_plan_scores_path,
    load_config,
    metric_output_path,
    project_root,
    resolve_ensemble_meta,
    subsample_for_scatter,
)


def statewide_dem_vote_share(gdf, race, dem_suffix, gop_suffix):
    dem = gdf[f"{race}{dem_suffix}"].sum()
    rep = gdf[f"{race}{gop_suffix}"].sum()
    return float(dem / (dem + rep))


def plan_metrics(dem_wins, vote_shares, races, n_districts):
    seat_shares = {race: dem_wins[race] / n_districts for race in races}
    deviations = {race: seat_shares[race] - vote_shares[race] for race in races}
    return {
        "seat_shares": seat_shares,
        "deviations": deviations,
        "mean_deviation": float(np.mean(list(deviations.values()))),
    }


def load_ensemble_plans(path, subsample, cap, seed):
    with jl.open(path) as reader:
        plans = [obj["scores"] for obj in reader]
    if subsample and len(plans) > cap:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(plans), size=cap, replace=False)
        plans = [plans[i] for i in idx]
    return plans


def add_proportionality_guides(ax, band):
    ax.axvspan(-band, band, alpha=0.1, color="green", zorder=0)
    ax.axvline(band, color="green", linestyle=":", linewidth=1.2, label=f"±½ seat ({band:.2g}%)")
    ax.axvline(-band, color="green", linestyle=":", linewidth=1.2)
    ax.axvline(0, color="black", linestyle="--", linewidth=1, label="Perfect proportionality")


def main() -> None:
    parser = argparse.ArgumentParser(description="Proportion deviation figures.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--ensembles", nargs="*", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    fig_dir = figures_dir(cfg, top_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    prop_cfg = cfg["figures"]["proportion_deviation"]
    races = cfg["elections"]["races"]
    plot_races = prop_cfg.get("plot_races", ["pres_20", "pres_24"])
    n_districts = cfg["state"]["n_districts"]
    max_dev = prop_cfg.get("max_deviation_pct", 50.0 / n_districts)
    subsample_cap = prop_cfg.get("subsample_size", cfg["performance"]["subsample"]["scatter"])
    seed = cfg["performance"]["random_seed"]
    dem_suffix = cfg["columns"]["party_dem_suffix"]
    gop_suffix = cfg["columns"]["party_gop_suffix"]

    gdf = gpd.read_parquet(geoparquet_path(cfg, top_dir))
    vote_shares = {race: statewide_dem_vote_share(gdf, race, dem_suffix, gop_suffix) for race in races}

    ensemble_names = args.ensembles or prop_cfg.get("ensembles", [e["name"] for e in cfg["ensembles"][:2]])
    if args.ensembles:
        filter_ensembles(cfg, args.ensembles)
    ensemble_records = {}
    ensemble_deviations = {race: {} for race in plot_races}
    ensemble_mean_devs = {}

    for name in ensemble_names:
        path = metric_output_path(cfg, top_dir, "dem_wins", name, output_key="dem_wins")
        if not path.exists():
            print(f"Skipping {name}: missing dem_wins")
            continue
        plans = load_ensemble_plans(path, subsample_for_scatter(cfg, name), subsample_cap, seed)
        records = [plan_metrics(scores, vote_shares, races, n_districts) for scores in plans]
        ensemble_records[name] = records
        ensemble_mean_devs[name] = [r["mean_deviation"] for r in records]
        for race in plot_races:
            ensemble_deviations[race][name] = [r["deviations"][race] for r in records]

    with open(human_plan_scores_path(cfg, top_dir)) as f:
        human_wins = {n: s["dem_wins_by_race"] for n, s in json.load(f).items()}
    human_records = {n: plan_metrics(w, vote_shares, races, n_districts) for n, w in human_wins.items()}

    for race in plot_races:
        human_devs = {n: r["deviations"][race] for n, r in human_records.items()}
        vote_pct = vote_shares[race] * 100

        fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
        for name in ensemble_names:
            if name not in ensemble_deviations[race]:
                continue
            meta = resolve_ensemble_meta(cfg, name)
            ax.hist(np.array(ensemble_deviations[race][name]) * 100, bins=12, alpha=0.45, density=True, color=meta["color"], label=meta["label"])
        colors = districtr(len(human_devs))
        for i, (plan, dev) in enumerate(sorted(human_devs.items())):
            ax.axvline(dev * 100 + i * 0.05, color=colors[i], linewidth=1.5, label=plan)
        add_proportionality_guides(ax, max_dev)
        ax.set_xlabel("Deviation from proportion (seat % − vote %)")
        ax.set_ylabel("Frequency")
        ax.set_title(f"Proportionality deviation — {race}\n(statewide Dem vote = {vote_pct:.1f}%)")
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7)
        fig.tight_layout()
        fig.savefig(fig_dir / f"proportion_deviation_hist_{race}.png", bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
        for name in ensemble_names:
            if name not in ensemble_deviations[race]:
                continue
            meta = resolve_ensemble_meta(cfg, name)
            ax.hist((np.array(ensemble_deviations[race][name]) + vote_pct / 100) * 100, bins=12, alpha=0.45, density=True, color=meta["color"], label=meta["label"])
        for i, (plan, dev) in enumerate(sorted(human_devs.items())):
            ax.axvline((dev + vote_pct / 100) * 100 + i * 0.05, color=colors[i], linewidth=1.5, label=plan)
        ax.axvspan(vote_pct - max_dev, vote_pct + max_dev, alpha=0.1, color="green")
        ax.axvline(vote_pct, color="black", linestyle="--", linewidth=1)
        ax.set_xlabel("Democratic seat share (%)")
        ax.set_ylabel("Frequency")
        ax.set_title(f"Democratic seat share — {race}")
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7)
        fig.tight_layout()
        fig.savefig(fig_dir / f"seat_share_hist_{race}.png", bbox_inches="tight")
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 7), dpi=300)
    ax.plot([0, 100], [0, 100], "k--", linewidth=1, label="Perfect proportionality")
    for name in ensemble_names:
        if name not in ensemble_records:
            continue
        meta = resolve_ensemble_meta(cfg, name)
        xs, ys = [], []
        for record in ensemble_records[name]:
            for race in races:
                xs.append(vote_shares[race] * 100)
                ys.append(record["seat_shares"][race] * 100)
        ax.scatter(xs, ys, s=8, alpha=0.08, color=meta["color"], label=meta["label"])
    hx, hy = [], []
    for record in human_records.values():
        for race in races:
            hx.append(vote_shares[race] * 100)
            hy.append(record["seat_shares"][race] * 100)
    ax.scatter(hx, hy, s=90, marker="*", c=districtr(len(hx)), edgecolors="black", linewidths=0.4, zorder=3, label="Human plans")
    ax.set_xlim(0, 100)
    ax.set_ylim(-5, 105)
    ax.set_xlabel("Democratic vote share statewide (%)")
    ax.set_ylabel("Democratic seat share (%)")
    ax.set_title("Seat share vs vote share (all plans × races)")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(fig_dir / "proportion_seats_vs_votes_all_races.png", bbox_inches="tight")
    plt.close(fig)
    print("Wrote proportion figures")


if __name__ == "__main__":
    main()
