"""
tests/test_viz.py

Tests for knowledgecomplex.viz — NetworkX export (DiGraph), Hasse diagram
plots, geometric realization, and verify_networkx.

Skipped if networkx or matplotlib are not installed.
"""

import warnings

import pytest

nx = pytest.importorskip("networkx")
mpl = pytest.importorskip("matplotlib")
mpl.use("Agg")  # non-interactive backend for CI

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.viz import (
    to_networkx,
    verify_networkx,
    type_color_map,
    plot_hasse,
    plot_hasse_star,
    plot_hasse_skeleton,
    plot_geometric,
    plot_complex,
    plot_star,
    plot_skeleton,
)


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="viz")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link", attributes={"weight": vocab("light", "heavy")})
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def kc(schema) -> KnowledgeComplex:
    """3 vertices, 3 edges, 1 face."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, weight="light")
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"}, weight="heavy")
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"}, weight="light")
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
    return kc


@pytest.fixture
def empty_kc(schema) -> KnowledgeComplex:
    return KnowledgeComplex(schema=schema)


# --- to_networkx ---


class TestToNetworkx:
    def test_is_digraph(self, kc):
        G = to_networkx(kc)
        assert isinstance(G, nx.DiGraph)

    def test_node_count(self, kc):
        G = to_networkx(kc)
        assert len(G.nodes) == 7  # 3 vertices + 3 edges + 1 face

    def test_edge_count(self, kc):
        G = to_networkx(kc)
        # boundedBy: 3 edges × 2 vertices + 1 face × 3 edges = 9
        assert len(G.edges) == 9

    def test_edge_direction_high_to_low(self, kc):
        """All edges point from higher dim to lower dim."""
        G = to_networkx(kc)
        for u, v in G.edges():
            assert G.nodes[u]["dim"] > G.nodes[v]["dim"]

    def test_vertex_out_degree_zero(self, kc):
        G = to_networkx(kc)
        for n in G.nodes:
            if G.nodes[n]["dim"] == 0:
                assert G.out_degree(n) == 0, f"Vertex {n} has out-degree {G.out_degree(n)}"

    def test_edge_out_degree_two(self, kc):
        G = to_networkx(kc)
        for n in G.nodes:
            if G.nodes[n]["dim"] == 1:
                assert G.out_degree(n) == 2, f"Edge {n} has out-degree {G.out_degree(n)}"

    def test_face_out_degree_three(self, kc):
        G = to_networkx(kc)
        for n in G.nodes:
            if G.nodes[n]["dim"] == 2:
                assert G.out_degree(n) == 3, f"Face {n} has out-degree {G.out_degree(n)}"

    def test_face_in_degree_zero(self, kc):
        G = to_networkx(kc)
        for n in G.nodes:
            if G.nodes[n]["dim"] == 2:
                assert G.in_degree(n) == 0, f"Face {n} has in-degree {G.in_degree(n)}"

    def test_node_has_type_kind_dim(self, kc):
        G = to_networkx(kc)
        for n in G.nodes:
            assert "type" in G.nodes[n]
            assert "kind" in G.nodes[n]
            assert "dim" in G.nodes[n]

    def test_model_attributes(self, kc):
        G = to_networkx(kc)
        assert G.nodes["e12"]["weight"] == "light"

    def test_graph_name(self, kc):
        G = to_networkx(kc)
        assert G.graph["name"] == "viz"

    def test_empty_kc(self, empty_kc):
        G = to_networkx(empty_kc)
        assert len(G.nodes) == 0
        assert len(G.edges) == 0


# --- verify_networkx ---


class TestVerifyNetworkx:
    def test_valid_complex(self, kc):
        G = to_networkx(kc)
        assert verify_networkx(G) is True

    def test_not_digraph_raises(self):
        G = nx.Graph()
        with pytest.raises(TypeError, match="DiGraph"):
            verify_networkx(G)

    def test_missing_attributes_raises(self):
        G = nx.DiGraph()
        G.add_node("x")
        with pytest.raises(ValueError, match="missing"):
            verify_networkx(G)

    def test_vertex_with_outgoing_edge_raises(self):
        G = nx.DiGraph()
        G.add_node("v1", kind="vertex", dim=0, type="V", uri=None)
        G.add_node("v2", kind="vertex", dim=0, type="V", uri=None)
        G.add_edge("v1", "v2")
        with pytest.raises(ValueError, match="out-degree"):
            verify_networkx(G)

    def test_edge_wrong_out_degree_raises(self):
        G = nx.DiGraph()
        G.add_node("e1", kind="edge", dim=1, type="E", uri=None)
        G.add_node("v1", kind="vertex", dim=0, type="V", uri=None)
        G.add_edge("e1", "v1")
        # out-degree 1 instead of 2
        with pytest.raises(ValueError, match="out-degree 1"):
            verify_networkx(G)

    def test_edge_target_not_vertex_raises(self):
        G = nx.DiGraph()
        G.add_node("e1", kind="edge", dim=1, type="E", uri=None)
        G.add_node("e2", kind="edge", dim=1, type="E", uri=None)
        G.add_node("v1", kind="vertex", dim=0, type="V", uri=None)
        G.add_edge("e1", "v1")
        G.add_edge("e1", "e2")
        with pytest.raises(ValueError, match="not a vertex"):
            verify_networkx(G)

    def test_closed_triangle_invariant(self, kc):
        """The face's 3 boundary edges share exactly 3 distinct vertices."""
        G = to_networkx(kc)
        # This is implicitly tested by verify_networkx succeeding,
        # but let's also check explicitly
        face_nodes = [n for n in G if G.nodes[n]["dim"] == 2]
        for face in face_nodes:
            edges = list(G.successors(face))
            assert len(edges) == 3
            verts = set()
            for e in edges:
                verts |= set(G.successors(e))
            assert len(verts) == 3

    def test_open_triangle_detected(self):
        """A face whose boundary edges don't form a closed triangle fails."""
        G = nx.DiGraph()
        for v in ["v1", "v2", "v3", "v4"]:
            G.add_node(v, kind="vertex", dim=0, type="V", uri=None)
        # e1: v1-v2, e2: v2-v3, e3: v1-v4 (open — v4 instead of v3)
        G.add_node("e1", kind="edge", dim=1, type="E", uri=None)
        G.add_node("e2", kind="edge", dim=1, type="E", uri=None)
        G.add_node("e3", kind="edge", dim=1, type="E", uri=None)
        G.add_edge("e1", "v1"); G.add_edge("e1", "v2")
        G.add_edge("e2", "v2"); G.add_edge("e2", "v3")
        G.add_edge("e3", "v1"); G.add_edge("e3", "v4")
        G.add_node("f", kind="face", dim=2, type="F", uri=None)
        G.add_edge("f", "e1"); G.add_edge("f", "e2"); G.add_edge("f", "e3")
        with pytest.raises(ValueError, match="4 distinct vertices"):
            verify_networkx(G)


# --- type_color_map ---


class TestTypeColorMap:
    def test_covers_all_types(self, kc):
        colors = type_color_map(kc)
        for type_name in kc._schema._types:
            assert type_name in colors

    def test_returns_hex_strings(self, kc):
        colors = type_color_map(kc)
        for color in colors.values():
            assert color.startswith("#")
            assert len(color) == 7

    def test_distinct_colors(self, kc):
        colors = type_color_map(kc)
        assert len(set(colors.values())) == len(colors)


# --- plot_hasse ---


class TestPlotHasse:
    def test_returns_fig_ax(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_hasse(kc)
        assert isinstance(fig, plt.Figure)
        assert isinstance(ax, plt.Axes)
        plt.close(fig)

    def test_empty_kc(self, empty_kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_hasse(empty_kc)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_title_contains_hasse(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_hasse(kc)
        assert "Hasse" in ax.get_title()
        plt.close(fig)

    def test_star_returns_fig_ax(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_hasse_star(kc, "v1")
        assert isinstance(fig, plt.Figure)
        assert "Star" in ax.get_title()
        plt.close(fig)

    def test_skeleton_returns_fig_ax(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_hasse_skeleton(kc, 1)
        assert isinstance(fig, plt.Figure)
        assert "Skeleton" in ax.get_title()
        plt.close(fig)


# --- plot_geometric ---


class TestPlotGeometric:
    def test_returns_fig_and_3d_ax(self, kc):
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        fig, ax = plot_geometric(kc)
        assert isinstance(fig, plt.Figure)
        # Axes3D is a subclass of Axes
        assert hasattr(ax, "zaxis") or isinstance(ax, Axes3D)
        plt.close(fig)

    def test_empty_kc(self, empty_kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_geometric(empty_kc)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_title_contains_geometric(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_geometric(kc)
        assert "Geometric" in ax.get_title()
        plt.close(fig)


# --- plot_geometric_interactive ---


class TestPlotGeometricInteractive:
    def test_returns_plotly_figure(self, kc):
        plotly = pytest.importorskip("plotly")
        from knowledgecomplex.viz import plot_geometric_interactive
        fig = plot_geometric_interactive(kc)
        assert isinstance(fig, plotly.graph_objects.Figure)

    def test_empty_kc(self, empty_kc):
        plotly = pytest.importorskip("plotly")
        from knowledgecomplex.viz import plot_geometric_interactive
        fig = plot_geometric_interactive(empty_kc)
        assert isinstance(fig, plotly.graph_objects.Figure)


# --- deprecated aliases ---


class TestDeprecatedAliases:
    def test_plot_complex_warns(self, kc):
        import matplotlib.pyplot as plt
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fig, ax = plot_complex(kc)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "plot_hasse" in str(w[0].message)
            plt.close(fig)

    def test_plot_star_warns(self, kc):
        import matplotlib.pyplot as plt
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fig, ax = plot_star(kc, "v1")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "plot_hasse_star" in str(w[0].message)
            plt.close(fig)

    def test_plot_skeleton_warns(self, kc):
        import matplotlib.pyplot as plt
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fig, ax = plot_skeleton(kc, 1)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "plot_hasse_skeleton" in str(w[0].message)
            plt.close(fig)
