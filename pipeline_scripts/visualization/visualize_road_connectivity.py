"""Visualize road connectivity breaks for a single districting plan.

Shows road adjacency graph edges with district outlines and non-contiguous
VTDs highlighted. Outputs a side-by-side PNG for queen and rook road graphs.

Usage:
    python visualize_road_connectivity.py --config config_UT.yaml --ensemble districtPairsRA --plan-index 35
    python visualize_road_connectivity.py --config config_UT.yaml --chain data/my_chain.jsonl --sample 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import contextily as ctx
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
from gerrychain import Graph, Partition

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    geoparquet_path,
    load_config,
    load_plan_from_chain,
    project_root,
    resolve_chain_path,
)


def find_broken_vtds(road_graph, assignment: list) -> tuple[set, list]:
    road_nodes = list(road_graph.nodes)
    road_assignment = {n: str(assignment[n]) for n in road_nodes}
    partition = Partition(road_graph, road_assignment)

    broken_vtds: set = set()
    broken_districts: list = []

    for district_id, nodes in partition.parts.items():
        subgraph = road_graph.subgraph(nodes)
        components = list(nx.connected_components(subgraph))
        if len(components) > 1:
            broken_districts.append(district_id)
            largest = max(components, key=len)
            for comp in components:
                if comp != largest:
                    broken_vtds.update(comp)

    return broken_vtds, broken_districts


def draw_tiger_roads(ax, roads_gdf):
    roads_gdf.plot(ax=ax, color="#888888", linewidth=0.4, zorder=2)


def draw_road_edges(ax, road_graph, gdf_proj, broken_vtds):
    centroids = gdf_proj.geometry.centroid
    centroid_map = {i: (centroids.iloc[i].x, centroids.iloc[i].y) for i in range(len(gdf_proj))}

    for u, v in road_graph.edges():
        if u not in centroid_map or v not in centroid_map:
            continue
        u_broken = u in broken_vtds
        v_broken = v in broken_vtds
        color = "orange" if (u_broken or v_broken) else "#aaaaaa"
        lw = 0.8 if (u_broken or v_broken) else 0.3
        ax.plot(
            [centroid_map[u][0], centroid_map[v][0]],
            [centroid_map[u][1], centroid_map[v][1]],
            color=color,
            linewidth=lw,
            zorder=2,
        )


def plot_panel(ax, gdf_proj, districts_gdf, road_graph, broken_vtds, graph_type, vis_cfg, roads_gdf=None):
    basemap = vis_cfg.get("basemap", "roads")
    plan_label = vis_cfg["plan_label"]

    if basemap == "carto":
        gdf_web = gdf_proj.to_crs("EPSG:3857")
        districts_web = districts_gdf.to_crs("EPSG:3857")
        ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=6)
        plot_gdf, plot_districts = gdf_web, districts_web
    elif basemap == "tiger":
        plot_gdf, plot_districts = gdf_proj, districts_gdf
        plot_gdf.plot(ax=ax, color="#f0f0f0", edgecolor="white", linewidth=0.1, zorder=1)
        if roads_gdf is not None:
            draw_tiger_roads(ax, roads_gdf)
    else:
        plot_gdf, plot_districts = gdf_proj, districts_gdf
        plot_gdf.plot(ax=ax, color="#f0f0f0", edgecolor="white", linewidth=0.1, zorder=1)
        if basemap == "roads":
            draw_road_edges(ax, road_graph, plot_gdf, broken_vtds)

    if broken_vtds:
        plot_gdf[plot_gdf.index.isin(broken_vtds)].plot(
            color="yellow", alpha=0.8, edgecolor="orange", linewidth=0.5, ax=ax, zorder=3
        )

    plot_districts.boundary.plot(ax=ax, linewidth=2.5, edgecolor="black", zorder=4)

    for _, row in plot_districts.iterrows():
        centroid_pt = row.geometry.centroid
        ax.annotate(
            f"D{int(row['district'])}",
            xy=(centroid_pt.x, centroid_pt.y),
            ha="center",
            va="center",
            fontsize=12,
            fontweight="bold",
            color="black",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7, ec="none"),
            zorder=5,
        )

    handles = [mpatches.Patch(color="yellow", label="Broken VTDs (not road-contiguous)")]
    if basemap == "roads":
        handles.extend(
            [
                mpatches.Patch(color="#aaaaaa", label="Road connections"),
                mpatches.Patch(color="orange", label="Roads touching broken VTDs"),
            ]
        )
    ax.legend(handles=handles, loc="lower left", fontsize=8)
    ax.set_title(f"Road Connectivity — {graph_type.upper()} ({basemap})\n{plan_label}", fontsize=12)
    ax.axis("off")


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize road connectivity for one plan.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--ensemble", default=None, help="Ensemble name (uses chain from config)")
    parser.add_argument("--chain", default=None, help="Override chain JSONL path")
    parser.add_argument("--derivative", default=None, choices=["raw", "canonical", "winnowed_pb"])
    parser.add_argument("--plan-index", type=int, default=None)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    vis_cfg = cfg["visualizations"]["road_connectivity"]

    cache_dir = top_dir / vis_cfg.get("map_tiles_cache", "data/map_tiles_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    ctx.set_cache_dir(str(cache_dir))

    ensemble_name = args.ensemble or vis_cfg.get("default_ensemble")
    if not ensemble_name and not args.chain:
        raise SystemExit("Provide --ensemble or --chain")

    derivative = args.derivative or vis_cfg.get("default_derivative", "raw")
    chain_path = resolve_chain_path(cfg, top_dir, ensemble_name or "", chain_override=args.chain, derivative=derivative)

    plan_index = args.plan_index if args.plan_index is not None else vis_cfg.get("default_plan_index", 0)
    plan = load_plan_from_chain(chain_path, plan_index=plan_index if args.sample is None else None, sample=args.sample)
    assignment = plan["assignment"]

    plan_label = f"sample {plan['sample']}" if "sample" in plan else f"index {plan_index}"
    vis_cfg = {**vis_cfg, "plan_label": plan_label}

    gdf = gpd.read_parquet(geoparquet_path(cfg, top_dir))
    gdf["district"] = assignment

    basemap = vis_cfg.get("basemap", "roads")
    roads_gdf = None
    if basemap == "tiger":
        fips = cfg["state"]["fips"]
        tiger_template = vis_cfg.get("tiger_roads", "data/tl_2023_{fips}_prisecroads/tl_2023_{fips}_prisecroads.shp")
        tiger_path = top_dir / tiger_template.format(fips=fips)
        roads_gdf = gpd.read_file(tiger_path).to_crs("EPSG:32612")

    road_types = cfg["preprocessing"]["cull"]["road_types"]
    road_graphs = {rt: Graph.from_json(str(top_dir / cfg["inputs"]["road_graphs"][rt])) for rt in road_types}

    basemap_crs = "EPSG:3857" if basemap == "carto" else "EPSG:32612"
    gdf_proj = gdf.to_crs(basemap_crs)
    districts_gdf = gdf_proj.dissolve(by="district", aggfunc="first").reset_index()

    ncols = len(road_types)
    fig, axes = plt.subplots(1, ncols, figsize=(6 * ncols, 7))
    if ncols == 1:
        axes = [axes]

    for ax, road_type in zip(axes, road_types):
        broken_vtds, _ = find_broken_vtds(road_graphs[road_type], assignment)
        plot_panel(ax, gdf_proj, districts_gdf, road_graphs[road_type], broken_vtds, road_type, vis_cfg, roads_gdf)

    fig.suptitle(f"Road Connectivity — {plan_label}", fontsize=14, y=0.985)

    if args.output:
        output_path = Path(args.output)
    else:
        name = ensemble_name or chain_path.stem
        output_path = top_dir / vis_cfg["output"].format(name=name, index=plan_index)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved to: {output_path}")
    if args.show:
        plt.show()
    else:
        plt.close()


if __name__ == "__main__":
    main()
