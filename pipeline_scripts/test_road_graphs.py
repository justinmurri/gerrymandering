"""
test_road_graphs.py
===================
Validates road graph JSON files produced by build_road_graphs.py.

Usage:
    # Test a specific road graph:
    pytest test_road_graphs.py --graph output/UT/road_graph_rook_road_state_UT.json

    # Test a road graph against its contiguity graph (recommended):
    pytest test_road_graphs.py \
        --graph output/UT/road_graph_rook_road_state_UT.json \
        --contiguity output/UT/road_graph_rook_UT.json

    # Test against the original Utah reference file:
    pytest test_road_graphs.py \
        --graph output/UT/road_graph_rook_road_state_UT.json \
        --reference 2020road_graph_rook_w_2025_elections_data_edited.json

    # Run all tests verbosely:
    pytest test_road_graphs.py -v \
        --graph output/UT/road_graph_rook_road_state_UT.json \
        --contiguity output/UT/road_graph_rook_UT.json
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph


# ── CLI options ───────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    parser.addoption("--graph",       required=True,  help="Path to road graph JSON to test")
    parser.addoption("--contiguity",  default=None,   help="Path to contiguity graph JSON (queen or rook)")
    parser.addoption("--reference",   default=None,   help="Path to reference graph JSON to compare structure against")


@pytest.fixture(scope="session")
def graph_path(request) -> Path:
    return Path(request.config.getoption("--graph"))

@pytest.fixture(scope="session")
def contiguity_path(request) -> Path | None:
    p = request.config.getoption("--contiguity")
    return Path(p) if p else None

@pytest.fixture(scope="session")
def reference_path(request) -> Path | None:
    p = request.config.getoption("--reference")
    return Path(p) if p else None

@pytest.fixture(scope="session")
def graph(graph_path) -> nx.Graph:
    with open(graph_path) as f:
        data = json.load(f)
    return json_graph.adjacency_graph(data)

@pytest.fixture(scope="session")
def contiguity_graph(contiguity_path) -> nx.Graph | None:
    if contiguity_path is None:
        return None
    with open(contiguity_path) as f:
        data = json.load(f)
    return json_graph.adjacency_graph(data)

@pytest.fixture(scope="session")
def reference_graph(reference_path) -> nx.Graph | None:
    if reference_path is None:
        return None
    with open(reference_path) as f:
        data = json.load(f)
    return json_graph.adjacency_graph(data)

@pytest.fixture(scope="session")
def raw_data(graph_path) -> dict:
    with open(graph_path) as f:
        return json.load(f)


# ── 1. File structure tests ───────────────────────────────────────────────────

class TestFileStructure:

    def test_required_top_level_keys(self, raw_data):
        """JSON must have the NetworkX adjacency format keys."""
        for key in ("directed", "multigraph", "graph", "nodes", "adjacency"):
            assert key in raw_data, f"Missing top-level key: {key}"

    def test_not_directed(self, raw_data):
        """Graph should be undirected."""
        assert raw_data["directed"] is False

    def test_not_multigraph(self, raw_data):
        """Graph should not be a multigraph."""
        assert raw_data["multigraph"] is False

    def test_crs_present(self, raw_data):
        """CRS should be embedded in graph metadata."""
        graph_meta = dict(raw_data["graph"])
        assert "crs" in graph_meta, "Missing CRS in graph metadata"
        assert "EPSG" in graph_meta["crs"] or "UTM" in graph_meta["crs"], \
            "CRS does not look like a valid projection string"

    def test_nodes_and_adjacency_same_length(self, raw_data):
        """nodes and adjacency arrays must be the same length."""
        assert len(raw_data["nodes"]) == len(raw_data["adjacency"]), \
            "nodes and adjacency arrays have different lengths"

    def test_nodes_not_empty(self, raw_data):
        assert len(raw_data["nodes"]) > 0, "Graph has no nodes"


# ── 2. Node attribute tests ───────────────────────────────────────────────────

class TestNodeAttributes:

    def test_no_geometry_on_nodes(self, raw_data):
        """Geometry should be stripped from node attributes."""
        for node in raw_data["nodes"]:
            assert "geometry" not in node, \
                f"Node {node.get('id')} still has a geometry attribute"

    def test_nodes_have_id(self, raw_data):
        """Every node should have an integer 'id' attribute."""
        for node in raw_data["nodes"]:
            assert "id" in node, f"Node missing 'id': {node}"
            assert isinstance(node["id"], int), \
                f"Node 'id' is not an integer: {node['id']}"

    def test_node_ids_are_contiguous(self, raw_data):
        """Node IDs should be 0..N-1 with no gaps."""
        ids = sorted(n["id"] for n in raw_data["nodes"])
        expected = list(range(len(raw_data["nodes"])))
        assert ids == expected, \
            f"Node IDs are not contiguous 0..N-1. First few: {ids[:10]}"

    def test_nodes_have_census_columns(self, raw_data):
        """Nodes should have basic Census VTD columns."""
        required = ["STATEFP20", "COUNTYFP20", "VTDST20", "GEOID20"]
        for col in required:
            missing = [n["id"] for n in raw_data["nodes"] if col not in n]
            assert not missing, \
                f"Column '{col}' missing from {len(missing)} nodes"


# ── 3. Edge attribute tests ───────────────────────────────────────────────────

class TestEdgeAttributes:

    def test_edges_have_shared_perim(self, raw_data):
        """Every edge should have a shared_perim attribute."""
        for i, neighbors in enumerate(raw_data["adjacency"]):
            for edge in neighbors:
                assert "shared_perim" in edge, \
                    f"Edge from node {i} to {edge.get('id')} missing shared_perim"

    def test_shared_perim_non_negative(self, raw_data):
        """shared_perim should be >= 0."""
        for i, neighbors in enumerate(raw_data["adjacency"]):
            for edge in neighbors:
                val = edge.get("shared_perim", 0)
                assert val >= 0, \
                    f"Negative shared_perim {val} on edge from node {i} to {edge.get('id')}"


# ── 4. Graph topology tests ───────────────────────────────────────────────────

class TestGraphTopology:

    def test_no_self_loops(self, graph):
        """Graph should have no self-loops."""
        loops = list(nx.selfloop_edges(graph))
        assert len(loops) == 0, f"Graph has {len(loops)} self-loops"

    def test_graph_is_connected(self, graph):
        """
        Road graph should be connected (or close to it).
        A small number of isolated nodes is acceptable for islands/enclaves,
        but the largest component should contain >95% of nodes.
        """
        if nx.is_connected(graph):
            return
        components = sorted(nx.connected_components(graph), key=len, reverse=True)
        largest = len(components[0])
        total = graph.number_of_nodes()
        pct = largest / total
        assert pct > 0.95, \
            f"Largest connected component is only {pct:.1%} of nodes ({largest}/{total}). " \
            f"Graph has {len(components)} components."

    def test_reasonable_edge_count(self, graph):
        """
        Each node should have at least 1 neighbor on average.
        A road graph with very few edges likely has a filtering bug.
        """
        avg_degree = sum(d for _, d in graph.degree()) / graph.number_of_nodes()
        assert avg_degree >= 1.0, \
            f"Average degree is only {avg_degree:.2f} — road filtering may be too aggressive"

    def test_no_duplicate_edges(self, graph):
        """Graph should have no duplicate edges (it's not a multigraph)."""
        seen = set()
        for u, v in graph.edges():
            key = (min(u, v), max(u, v))
            assert key not in seen, f"Duplicate edge: {u} — {v}"
            seen.add(key)


# ── 5. Road graph vs contiguity graph tests ───────────────────────────────────

class TestRoadVsContiguity:

    def test_same_node_count(self, graph, contiguity_graph):
        """Road graph and contiguity graph should have the same number of nodes."""
        if contiguity_graph is None:
            pytest.skip("No contiguity graph provided (--contiguity)")
        assert graph.number_of_nodes() == contiguity_graph.number_of_nodes(), (
            f"Node count mismatch: road={graph.number_of_nodes()} "
            f"contiguity={contiguity_graph.number_of_nodes()}"
        )

    def test_road_is_subgraph_of_contiguity(self, graph, contiguity_graph):
        """Every road edge must also exist in the contiguity graph."""
        if contiguity_graph is None:
            pytest.skip("No contiguity graph provided (--contiguity)")
        extra = [(u, v) for u, v in graph.edges()
                 if not contiguity_graph.has_edge(u, v)]
        assert not extra, \
            f"Road graph has {len(extra)} edges not present in contiguity graph: {extra[:5]}"

    def test_road_graph_is_sparser(self, graph, contiguity_graph):
        """Road graph should have fewer edges than contiguity graph."""
        if contiguity_graph is None:
            pytest.skip("No contiguity graph provided (--contiguity)")
        assert graph.number_of_edges() < contiguity_graph.number_of_edges(), (
            f"Road graph has {graph.number_of_edges()} edges but contiguity has "
            f"{contiguity_graph.number_of_edges()} — road filtering had no effect"
        )

    def test_road_retention_rate(self, graph, contiguity_graph):
        """
        Road graph should retain a reasonable fraction of contiguity edges.
        At 'state' level expect 20-80%; at 'all' level expect 60-100%.
        This test uses a wide range to avoid false failures.
        """
        if contiguity_graph is None:
            pytest.skip("No contiguity graph provided (--contiguity)")
        road_edges = graph.number_of_edges()
        cont_edges = contiguity_graph.number_of_edges()
        retention = road_edges / cont_edges
        assert 0.05 < retention < 1.0, \
            f"Road edge retention rate {retention:.1%} is suspicious " \
            f"({road_edges}/{cont_edges} edges kept)"


# ── 6. Reference graph comparison tests ──────────────────────────────────────

class TestReferenceComparison:

    def test_similar_node_count(self, graph, reference_graph):
        """Node count should be within 5% of reference."""
        if reference_graph is None:
            pytest.skip("No reference graph provided (--reference)")
        ref_n = reference_graph.number_of_nodes()
        new_n = graph.number_of_nodes()
        diff = abs(ref_n - new_n) / ref_n
        assert diff < 0.05, \
            f"Node count differs from reference by {diff:.1%} (ref={ref_n}, new={new_n})"

    def test_similar_edge_count(self, graph, reference_graph):
        """Edge count should be within 20% of reference (road levels may differ)."""
        if reference_graph is None:
            pytest.skip("No reference graph provided (--reference)")
        ref_e = reference_graph.number_of_edges()
        new_e = graph.number_of_edges()
        diff = abs(ref_e - new_e) / ref_e
        assert diff < 0.20, \
            f"Edge count differs from reference by {diff:.1%} (ref={ref_e}, new={new_e})"

    def test_same_state_fips(self, raw_data, reference_graph):
        """All nodes should belong to the same state FIPS as the reference."""
        if reference_graph is None:
            pytest.skip("No reference graph provided (--reference)")
        ref_fips = {
            d.get("STATEFP20") for _, d in reference_graph.nodes(data=True)
            if d.get("STATEFP20")
        }
        new_fips = {n.get("STATEFP20") for n in raw_data["nodes"] if n.get("STATEFP20")}
        assert ref_fips == new_fips, \
            f"State FIPS mismatch: reference={ref_fips}, new={new_fips}"
