"""Visualize weighted average Democratic vote share by district for one plan.

Outputs a PNG map colored red→white→blue by margin over 50%.

Usage:
    python visualize_plan_dem_share.py --config config_UT.yaml --ensemble districtPairsRA --plan-index 100
    python visualize_plan_dem_share.py --config config_UT.yaml --chain data/my_chain.jsonl --sample 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from shapely.affinity import rotate

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    geoparquet_path,
    load_config,
    load_plan_from_chain,
    project_root,
    resolve_chain_path,
)


def compute_district_margins(gdf, races, dem_suffix, gop_suffix):
    all_dem_cols = [f"{r}{dem_suffix}" for r in races]
    all_rep_cols = [f"{r}{gop_suffix}" for r in races]

    district_groups = gdf.groupby("district")[all_dem_cols + all_rep_cols].sum()
    total_dem = district_groups[all_dem_cols].values
    total_rep = district_groups[all_rep_cols].values
    total_votes = total_dem + total_rep

    weighted_dem_share = total_dem.sum(axis=1) / total_votes.sum(axis=1)
    district_stats = district_groups[[]].copy()
    district_stats["dem_share"] = weighted_dem_share
    district_stats["margin"] = (district_stats["dem_share"] - 0.5) * 100
    return district_stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize plan dem vote share by district.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--ensemble", default=None)
    parser.add_argument("--chain", default=None)
    parser.add_argument("--derivative", default=None, choices=["raw", "canonical", "winnowed_pb"])
    parser.add_argument("--plan-index", type=int, default=None)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    vis_cfg = cfg["visualizations"]["plan_dem_share"]

    ensemble_name = args.ensemble or vis_cfg.get("default_ensemble")
    if not ensemble_name and not args.chain:
        raise SystemExit("Provide --ensemble or --chain")

    derivative = args.derivative or vis_cfg.get("default_derivative", "raw")
    chain_path = resolve_chain_path(cfg, top_dir, ensemble_name or "", chain_override=args.chain, derivative=derivative)

    plan_index = args.plan_index if args.plan_index is not None else vis_cfg.get("default_plan_index", 0)
    plan = load_plan_from_chain(chain_path, plan_index=plan_index if args.sample is None else None, sample=args.sample)
    assignment = plan["assignment"]
    plan_label = f"sample {plan['sample']}" if "sample" in plan else f"index {plan_index}"

    races = cfg["elections"]["races"]
    dem_suffix = cfg["columns"]["party_dem_suffix"]
    gop_suffix = cfg["columns"]["party_gop_suffix"]

    gdf = gpd.read_parquet(geoparquet_path(cfg, top_dir))
    gdf["district"] = assignment
    district_stats = compute_district_margins(gdf, races, dem_suffix, gop_suffix)
    gdf = gdf.merge(district_stats[["dem_share", "margin"]], on="district")

    districts_gdf = gdf.dissolve(by="district", aggfunc="first").reset_index()
    districts_gdf = districts_gdf.to_crs("EPSG:32612")

    rotate_deg = vis_cfg.get("rotate_degrees", 0)
    if rotate_deg:
        centroid = districts_gdf.geometry.unary_union.centroid
        districts_gdf["geometry"] = districts_gdf.geometry.apply(
            lambda geom: rotate(geom, rotate_deg, origin=centroid)
        )

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    max_margin = districts_gdf["margin"].abs().max()
    cmap = mcolors.LinearSegmentedColormap.from_list("rwb", ["#af0900", "#ffffff", "#02469e"])

    districts_gdf.plot(
        column="margin",
        cmap=cmap,
        vmin=-max_margin,
        vmax=max_margin,
        linewidth=0.8,
        edgecolor="black",
        legend=True,
        legend_kwds={"label": "Points above 50% (+ = Dem, − = Rep)", "shrink": 0.5},
        ax=ax,
    )

    for _, row in districts_gdf.iterrows():
        centroid_pt = row.geometry.centroid
        margin = row["margin"]
        direction = "D" if margin > 0 else "R"
        ax.annotate(
            f"D{int(row['district'])}\n{direction}+{abs(margin):.1f}",
            xy=(centroid_pt.x, centroid_pt.y),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color="black",
        )

    abbrev = cfg["state"]["abbrev"]
    ax.set_title(
        f"Weighted Avg Margin by District — All Elections\n({abbrev}, {plan_label})",
        fontsize=13,
    )
    ax.axis("off")

    if args.output:
        output_path = Path(args.output)
    else:
        name = ensemble_name or chain_path.stem
        output_path = top_dir / vis_cfg["output"].format(name=name, index=plan_index)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved to: {output_path}")
    if args.show:
        plt.show()
    else:
        plt.close()


if __name__ == "__main__":
    main()
