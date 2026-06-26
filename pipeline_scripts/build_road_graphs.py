"""
build_road_graphs.py
====================
Builds queen-contiguity and road-filtered adjacency graphs for all 50 US states
in the same NetworkX adjacency-JSON format as the Utah reference files.

Pipeline per state
------------------
1. Download 2020 VTD shapefile from Census TIGER (or use cached copy).
2. Build queen-contiguity graph (GerryChain / libpysal).
3. Download OSM drivable road network for the state (OSMnx / Geofabrik).
4. For every queen edge, test whether a road crosses the shared VTD border.
5. Keep only road-crossing edges → road graph.
6. Attach node attributes (demographics, elections) if a matching CSV is supplied.
7. Serialise both graphs as NetworkX adjacency JSON.

Dependencies
------------
    pip install geopandas gerrychain osmnx shapely networkx pyrosm requests tqdm

Optional (large states — faster than OSMnx streaming):
    pip install pyrosm
    # then set USE_GEOFABRIK_PBF = True below and point GEOFABRIK_DIR at a folder
    # pre-populated with state .osm.pbf files from https://download.geofabrik.de/

Usage
-----
    # All 50 states, queen only (fast — no road download needed):
    python build_road_graphs.py --adjacency queen --no-road

    # Single state, full road graph (all drivable roads):
    python build_road_graphs.py --states UT --adjacency both

    # Single state, state roads and above only (interstate + US + state routes):
    python build_road_graphs.py --states UT --adjacency both --road-level state

    # Single state, county roads and above (adds tertiary / unclassified roads):
    python build_road_graphs.py --states UT --adjacency both --road-level county

    # All states, road graph, 4 parallel workers:
    python build_road_graphs.py --adjacency both --workers 4

    # Use pre-downloaded Geofabrik PBFs instead of OSMnx streaming:
    python build_road_graphs.py --adjacency both --pbf-dir /data/geofabrik/

Road level options
------------------
    all     — every drivable road (default; includes residential streets & tracks)
    county  — county roads and above (tertiary+); good middle ground for VTD analysis
    state   — state routes and above (secondary+); strictest definition

    The road level is embedded in the output filename, e.g.:
        road_graph_queen_road_state_UT.json
        road_graph_queen_road_county_UT.json
        road_graph_queen_road_all_UT.json

Output
------
    output/<STATE>/road_graph_queen_<STATE>.json              (contiguity)
    output/<STATE>/road_graph_queen_road_<LEVEL>_<STATE>.json (road-filtered)
    output/<STATE>/road_graph_rook_<STATE>.json               (if rook or both)
    output/<STATE>/road_graph_rook_road_<LEVEL>_<STATE>.json  (if rook or both)
"""

import argparse
import json
import logging
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import geopandas as gpd
import networkx as nx
import requests
from networkx.readwrite import json_graph
from shapely.ops import unary_union
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Where to write outputs
OUTPUT_DIR = Path("output")

# Where to cache downloaded shapefiles / PBFs
CACHE_DIR = Path(".cache")

# Road buffer in metres — how close a road must come to a shared border
# to count as "crossing" it.  10 m works well for projected CRS.
ROAD_BUFFER_M = 10.0

# Set to True and fill GEOFABRIK_DIR to use local .osm.pbf files
# instead of streaming from OSMnx (much faster for large states).
USE_GEOFABRIK_PBF = False
GEOFABRIK_DIR = Path(".cache/pbf")

# ---------------------------------------------------------------------------
# Road level definitions
# ---------------------------------------------------------------------------
# OSM highway tag values included at each level.
# Each level is a strict superset of the one above it.
#
#   state  — interstate, US highway, state route (motorway / trunk / primary /
#             secondary) + their link ramps.  These are typically state- or
#             federally-maintained roads with route numbers.
#
#   county — adds tertiary roads (county/local routes that often have route
#             numbers) and unclassified roads (OSM catch-all for minor public
#             roads that don't fit other categories). Good default for
#             VTD-level analysis in rural states.
#
#   all    — adds residential streets, living streets, service roads, and
#             tracks.  Captures everything a car can legally drive on.

ROAD_LEVELS: dict[str, list[str]] = {
    "state": [
        "motorway",       "motorway_link",
        "trunk",          "trunk_link",
        "primary",        "primary_link",
        "secondary",      "secondary_link",
    ],
    "county": [
        "motorway",       "motorway_link",
        "trunk",          "trunk_link",
        "primary",        "primary_link",
        "secondary",      "secondary_link",
        "tertiary",       "tertiary_link",
        "unclassified",
    ],
    "all": [
        "motorway",       "motorway_link",
        "trunk",          "trunk_link",
        "primary",        "primary_link",
        "secondary",      "secondary_link",
        "tertiary",       "tertiary_link",
        "unclassified",
        "residential",
        "living_street",
        "service",
        "track",
    ],
}

# ---------------------------------------------------------------------------
# State metadata
# ---------------------------------------------------------------------------

# (name, fips, UTM EPSG, OSM place name for osmnx query)
# UTM zones chosen to minimise distortion for each state.
# For whole-CONUS consistency you can replace the EPSG with 5070 (Albers).
STATE_INFO = {
    "AL": ("Alabama",         "01", 32616, "Alabama, USA"),
    "AK": ("Alaska",          "02", 32604, "Alaska, USA"),
    "AZ": ("Arizona",         "04", 32612, "Arizona, USA"),
    "AR": ("Arkansas",        "05", 32615, "Arkansas, USA"),
    "CA": ("California",      "06", 32610, "California, USA"),
    "CO": ("Colorado",        "08", 32613, "Colorado, USA"),
    "CT": ("Connecticut",     "09", 32618, "Connecticut, USA"),
    "DE": ("Delaware",        "10", 32618, "Delaware, USA"),
    "FL": ("Florida",         "12", 32617, "Florida, USA"),
    "GA": ("Georgia",         "13", 32617, "Georgia, USA"),
    "HI": ("Hawaii",          "15", 32604, "Hawaii, USA"),
    "ID": ("Idaho",           "16", 32611, "Idaho, USA"),
    "IL": ("Illinois",        "17", 32616, "Illinois, USA"),
    "IN": ("Indiana",         "18", 32616, "Indiana, USA"),
    "IA": ("Iowa",            "19", 32615, "Iowa, USA"),
    "KS": ("Kansas",          "20", 32614, "Kansas, USA"),
    "KY": ("Kentucky",        "21", 32617, "Kentucky, USA"),
    "LA": ("Louisiana",       "22", 32615, "Louisiana, USA"),
    "ME": ("Maine",           "23", 32619, "Maine, USA"),
    "MD": ("Maryland",        "24", 32618, "Maryland, USA"),
    "MA": ("Massachusetts",   "25", 32619, "Massachusetts, USA"),
    "MI": ("Michigan",        "26", 32617, "Michigan, USA"),
    "MN": ("Minnesota",       "27", 32615, "Minnesota, USA"),
    "MS": ("Mississippi",     "28", 32616, "Mississippi, USA"),
    "MO": ("Missouri",        "29", 32615, "Missouri, USA"),
    "MT": ("Montana",         "30", 32612, "Montana, USA"),
    "NE": ("Nebraska",        "31", 32614, "Nebraska, USA"),
    "NV": ("Nevada",          "32", 32611, "Nevada, USA"),
    "NH": ("New Hampshire",   "33", 32619, "New Hampshire, USA"),
    "NJ": ("New Jersey",      "34", 32618, "New Jersey, USA"),
    "NM": ("New Mexico",      "35", 32613, "New Mexico, USA"),
    "NY": ("New York",        "36", 32618, "New York, USA"),
    "NC": ("North Carolina",  "37", 32617, "North Carolina, USA"),
    "ND": ("North Dakota",    "38", 32614, "North Dakota, USA"),
    "OH": ("Ohio",            "39", 32617, "Ohio, USA"),
    "OK": ("Oklahoma",        "40", 32614, "Oklahoma, USA"),
    "OR": ("Oregon",          "41", 32610, "Oregon, USA"),
    "PA": ("Pennsylvania",    "42", 32617, "Pennsylvania, USA"),
    "RI": ("Rhode Island",    "44", 32619, "Rhode Island, USA"),
    "SC": ("South Carolina",  "45", 32617, "South Carolina, USA"),
    "SD": ("South Dakota",    "46", 32614, "South Dakota, USA"),
    "TN": ("Tennessee",       "47", 32616, "Tennessee, USA"),
    "TX": ("Texas",           "48", 32614, "Texas, USA"),
    "UT": ("Utah",            "49", 32612, "Utah, USA"),
    "VT": ("Vermont",         "50", 32618, "Vermont, USA"),
    "VA": ("Virginia",        "51", 32617, "Virginia, USA"),
    "WA": ("Washington",      "53", 32610, "Washington, USA"),
    "WV": ("West Virginia",   "54", 32617, "West Virginia, USA"),
    "WI": ("Wisconsin",       "55", 32616, "Wisconsin, USA"),
    "WY": ("Wyoming",         "56", 32612, "Wyoming, USA"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1 — Download & cache Census VTD shapefile
# ---------------------------------------------------------------------------

TIGER_BASE = "https://www2.census.gov/geo/tiger/TIGER2020PL/LAYER/VTD/2020/"


def vtd_shapefile_path(abbr: str, fips: str) -> Path:
    """Return local path to extracted shapefile, downloading if needed."""
    dest = CACHE_DIR / "vtd" / abbr
    shp = dest / f"tl_2020_{fips}_vtd20.shp"
    if shp.exists():
        return shp

    dest.mkdir(parents=True, exist_ok=True)
    url = f"{TIGER_BASE}tl_2020_{fips}_vtd20.zip"
    log.info(f"[{abbr}] Downloading VTD shapefile from {url}")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with zipfile.ZipFile(BytesIO(r.content)) as z:
        z.extractall(dest)
    log.info(f"[{abbr}] VTD shapefile cached at {dest}")
    return shp


# ---------------------------------------------------------------------------
# Step 2 — Build contiguity graph
# ---------------------------------------------------------------------------

def build_contiguity_graph(
    gdf: gpd.GeoDataFrame,
    adjacency: str = "queen",
) -> nx.Graph:
    """
    Build a queen or rook contiguity graph from a GeoDataFrame using GerryChain.

    GerryChain returns a NetworkX graph directly. We add a 'shared_perim'
    attribute to each edge (metres, requires projected CRS) and ensure nodes
    are indexed by integer position to match the rest of the pipeline.
    """
    from gerrychain import Graph as GerryGraph

    if adjacency not in ("queen", "rook"):
        raise ValueError(f"adjacency must be 'queen' or 'rook', got {adjacency!r}")

    # GerryChain builds the graph and attaches all GeoDataFrame columns as
    # node attributes automatically.
    gc_graph = GerryGraph.from_geodataframe(gdf, adjacency=adjacency)

    # GerryChain uses the GeoDataFrame index as node keys; re-map to
    # contiguous integers so the rest of the pipeline stays consistent.
    gc_graph = nx.convert_node_labels_to_integers(gc_graph)

    # Add 'id' attribute, strip geometry, and compute shared_perim for every edge.
    for node in gc_graph.nodes:
        gc_graph.nodes[node]["id"] = node
        gc_graph.nodes[node].pop("geometry", None)

    for u, v in gc_graph.edges():
        geom_u = gdf.geometry.iloc[u]
        geom_v = gdf.geometry.iloc[v]
        shared = geom_u.intersection(geom_v)
        shared_perim = shared.length if not shared.is_empty else 0.0
        gc_graph[u][v]["shared_perim"] = shared_perim

    return gc_graph


# ---------------------------------------------------------------------------
# Step 3 — Download road network
# ---------------------------------------------------------------------------

def load_road_edges(
    abbr: str,
    state_name: str,
    osm_place: str,
    epsg: int,
    road_level: str = "all",
    pbf_dir: Path | None = None,
) -> gpd.GeoDataFrame:
    """
    Return a GeoDataFrame of road LineStrings filtered to `road_level`,
    in the state's projected CRS.

    road_level must be one of: "state", "county", "all"  (see ROAD_LEVELS).

    The raw drivable network is downloaded once per state and cached;
    level filtering is applied on load so you can switch levels without
    re-downloading.

    If pbf_dir is set and a matching .osm.pbf exists there, use pyrosm (fast).
    Otherwise stream from OSMnx (slower but requires no pre-download).
    """
    import osmnx as ox

    # Raw (unfiltered) cache — download once, filter per level
    raw_cache = CACHE_DIR / "roads" / f"{abbr}_roads_raw.parquet"

    if not raw_cache.exists():
        raw_cache.parent.mkdir(parents=True, exist_ok=True)
        if pbf_dir:
            pbf_candidates = (
                list(pbf_dir.glob(f"{abbr.lower()}*.osm.pbf"))
                + list(pbf_dir.glob(f"*{state_name.lower().replace(' ', '-')}*.osm.pbf"))
            )
            if pbf_candidates:
                _download_roads_pbf(abbr, pbf_candidates[0], epsg, raw_cache)
            else:
                _download_roads_osmnx(abbr, osm_place, epsg, raw_cache)
        else:
            _download_roads_osmnx(abbr, osm_place, epsg, raw_cache)

    log.info(f"[{abbr}] Loading road edges (level={road_level})")
    edges_gdf = gpd.read_parquet(raw_cache)
    edges_gdf = _filter_by_road_level(edges_gdf, road_level)
    log.info(f"[{abbr}] {len(edges_gdf):,} road segments after level filter")
    return edges_gdf


def _filter_by_road_level(
    edges_gdf: gpd.GeoDataFrame,
    road_level: str,
) -> gpd.GeoDataFrame:
    """
    Filter a road GeoDataFrame to only the highway types in ROAD_LEVELS[road_level].

    The 'highway' column may contain a string or a list of strings (OSMnx
    sometimes returns lists for ways with multiple tags), so we handle both.
    """
    if road_level not in ROAD_LEVELS:
        raise ValueError(
            f"road_level must be one of {list(ROAD_LEVELS)}, got {road_level!r}"
        )
    if "highway" not in edges_gdf.columns:
        log.warning("No 'highway' column found — returning all edges unfiltered")
        return edges_gdf

    allowed = set(ROAD_LEVELS[road_level])

    def _matches(val) -> bool:
        if isinstance(val, list):
            return bool(allowed.intersection(val))
        return val in allowed

    mask = edges_gdf["highway"].apply(_matches)
    return edges_gdf[mask].copy()


def _download_roads_osmnx(
    abbr: str,
    osm_place: str,
    epsg: int,
    cache_path: Path,
) -> None:
    """Download full drivable network via OSMnx and cache as parquet."""
    import osmnx as ox

    log.info(f"[{abbr}] Streaming road network from OSMnx for '{osm_place}'")
    ox.settings.useful_tags_way = ["highway", "name", "oneway", "maxspeed", "lanes"]
    G_road = ox.graph_from_place(osm_place, network_type="drive", simplify=True, retain_all=False)
    edges_gdf = ox.graph_to_gdfs(G_road, nodes=False)[["geometry", "highway"]]
    edges_gdf = edges_gdf.to_crs(epsg=epsg)
    edges_gdf.to_parquet(cache_path)
    log.info(f"[{abbr}] Raw road edges cached ({len(edges_gdf):,} segments) → {cache_path}")


def _download_roads_pbf(
    abbr: str,
    pbf_path: Path,
    epsg: int,
    cache_path: Path,
) -> None:
    """Load full drivable network from a Geofabrik .osm.pbf and cache as parquet."""
    try:
        from pyrosm import OSM
    except ImportError:
        raise ImportError("Install pyrosm: pip install pyrosm")

    log.info(f"[{abbr}] Loading roads from PBF {pbf_path}")
    osm = OSM(str(pbf_path))
    edges_gdf = osm.get_network(network_type="driving")[["geometry", "highway"]]
    edges_gdf = edges_gdf.to_crs(epsg=epsg)
    edges_gdf.to_parquet(cache_path)
    log.info(f"[{abbr}] Raw road edges cached ({len(edges_gdf):,} segments) → {cache_path}")


# Back-compat aliases (kept so external code that imported these still works)
_roads_from_osmnx = _download_roads_osmnx
_roads_from_pbf   = _download_roads_pbf


# ---------------------------------------------------------------------------
# Step 4 — Filter queen edges by road crossing
# ---------------------------------------------------------------------------

def build_road_graph(
    queen_graph: nx.Graph,
    gdf: gpd.GeoDataFrame,
    road_edges: gpd.GeoDataFrame,
    buffer_m: float = ROAD_BUFFER_M,
) -> nx.Graph:
    """
    Return a subgraph of queen_graph containing only edges where a road
    crosses (or passes very close to) the shared VTD border.

    Strategy
    --------
    1. For each queen edge (u, v), compute the shared border geometry.
    2. Buffer it by `buffer_m` metres.
    3. Spatial-index query: any road segment intersects the buffer? → keep edge.

    The spatial index (STRtree) is built once and reused for all edges.
    """
    # Pre-index road geometries
    road_geoms = list(road_edges.geometry)
    road_idx = road_edges.sindex  # geopandas wraps STRtree automatically

    road_graph = nx.Graph()
    road_graph.add_nodes_from(queen_graph.nodes(data=True))

    edges = list(queen_graph.edges(data=True))
    kept = 0

    for u, v, data in tqdm(edges, desc="  Filtering edges", leave=False):
        geom_u = gdf.geometry.iloc[u]
        geom_v = gdf.geometry.iloc[v]
        shared_border = geom_u.intersection(geom_v)
        if shared_border.is_empty:
            continue
        buf = shared_border.buffer(buffer_m)

        # Candidate road segments via spatial index
        candidate_idxs = list(road_idx.intersection(buf.bounds))
        for ci in candidate_idxs:
            if road_geoms[ci].intersects(buf):
                road_graph.add_edge(u, v, **data)
                kept += 1
                break

    log.info(f"  Road graph: {kept}/{len(edges)} queen edges kept")
    return road_graph


# ---------------------------------------------------------------------------
# Step 5 — Serialise to NetworkX adjacency JSON
# ---------------------------------------------------------------------------

def save_graph(G: nx.Graph, path: Path, crs_wkt: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json_graph.adjacency_data(G)
    # Embed CRS in graph metadata (matches Utah reference format)
    if crs_wkt:
        data["graph"] = [["crs", crs_wkt]]
    with open(path, "w") as f:
        json.dump(data, f)
    log.info(f"  Saved → {path}  ({path.stat().st_size / 1e6:.1f} MB)")


# ---------------------------------------------------------------------------
# Per-state driver
# ---------------------------------------------------------------------------

def process_state(
    abbr: str,
    build_adjacency: str,  # "queen", "rook", or "both"
    build_road: bool,
    road_level: str,       # "state", "county", or "all"
    pbf_dir: Path | None,
) -> str:
    """Full pipeline for a single state. Returns abbr on success."""
    name, fips, epsg, osm_place = STATE_INFO[abbr]
    log.info(f"[{abbr}] === Starting {name} ===")
    t0 = time.time()

    # --- 1. Shapefile ---
    shp_path = vtd_shapefile_path(abbr, fips)
    gdf = gpd.read_file(shp_path)
    gdf = gdf.to_crs(epsg=epsg)
    gdf = gdf.reset_index(drop=True)
    crs_wkt = gdf.crs.to_wkt()
    log.info(f"[{abbr}] {len(gdf):,} VTDs loaded, CRS EPSG:{epsg}")

    adjacency_types = (
        ["queen", "rook"] if build_adjacency == "both"
        else [build_adjacency]
    )

    for adj_type in adjacency_types:
        out_contiguity = OUTPUT_DIR / abbr / f"road_graph_{adj_type}_{abbr}.json"
        out_road = OUTPUT_DIR / abbr / f"road_graph_{adj_type}_road_{road_level}_{abbr}.json"

        # Skip if already done
        if out_contiguity.exists() and (not build_road or out_road.exists()):
            log.info(f"[{abbr}] {adj_type} outputs already exist, skipping")
            continue

        # --- 2. Contiguity graph ---
        log.info(f"[{abbr}] Building {adj_type} contiguity graph …")
        cont_graph = build_contiguity_graph(gdf, adjacency=adj_type)
        save_graph(cont_graph, out_contiguity, crs_wkt)

        # --- 3–4. Road graph ---
        if build_road:
            road_edges = load_road_edges(abbr, name, osm_place, epsg, road_level, pbf_dir)
            if road_edges.crs.to_epsg() != epsg:
                road_edges = road_edges.to_crs(epsg=epsg)
            log.info(f"[{abbr}] Building {adj_type} road graph (level={road_level}) …")
            rg = build_road_graph(cont_graph, gdf, road_edges)
            save_graph(rg, out_road, crs_wkt)

    elapsed = time.time() - t0
    log.info(f"[{abbr}] Done in {elapsed:.0f}s")
    return abbr


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--states", nargs="+", default=list(STATE_INFO.keys()),
        metavar="XX",
        help="2-letter state abbreviations (default: all 50)",
    )
    p.add_argument(
        "--adjacency", choices=["queen", "rook", "both"], default="both",
        help="Which contiguity type(s) to build (default: both)",
    )
    p.add_argument(
        "--no-road", dest="build_road", action="store_false",
        help="Skip road-graph step (build contiguity only)",
    )
    p.add_argument(
        "--road-level",
        choices=["state", "county", "all"],
        default="all",
        help=(
            "Which roads count as a crossing between two VTDs (default: all). "
            "'state' = state routes and above (motorway/trunk/primary/secondary). "
            "'county' = county roads and above (adds tertiary + unclassified). "
            "'all' = every drivable road (adds residential, service, tracks)."
        ),
    )
    p.add_argument(
        "--workers", type=int, default=1,
        help="Number of parallel workers (default: 1; use 2–4 for large runs)",
    )
    p.add_argument(
        "--pbf-dir", type=Path, default=None,
        metavar="DIR",
        help=(
            "Directory containing Geofabrik .osm.pbf files "
            "(e.g. us-latest.osm.pbf or utah-latest.osm.pbf). "
            "Falls back to OSMnx streaming if not supplied."
        ),
    )
    p.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR,
        help="Root output directory (default: ./output)",
    )
    p.add_argument(
        "--cache-dir", type=Path, default=CACHE_DIR,
        help="Root cache directory (default: ./.cache)",
    )
    return p.parse_args()


def main():
    args = parse_args()

    global OUTPUT_DIR, CACHE_DIR
    OUTPUT_DIR = args.output_dir
    CACHE_DIR  = args.cache_dir

    states = [s.upper() for s in args.states]
    unknown = [s for s in states if s not in STATE_INFO]
    if unknown:
        log.error(f"Unknown state abbreviation(s): {unknown}")
        sys.exit(1)

    log.info(
        f"Processing {len(states)} state(s): {', '.join(states)}\n"
        f"  adjacency={args.adjacency}  road={args.build_road}  "
        f"road_level={args.road_level}  workers={args.workers}"
    )

    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    process_state,
                    abbr,
                    args.adjacency,
                    args.build_road,
                    args.road_level,
                    args.pbf_dir,
                ): abbr
                for abbr in states
            }
            for fut in as_completed(futures):
                abbr = futures[fut]
                try:
                    fut.result()
                except Exception as exc:
                    log.error(f"[{abbr}] FAILED: {exc}")
    else:
        for abbr in states:
            try:
                process_state(abbr, args.adjacency, args.build_road, args.road_level, args.pbf_dir)
            except Exception as exc:
                log.error(f"[{abbr}] FAILED: {exc}", exc_info=True)

    log.info("All done.")


if __name__ == "__main__":
    main()