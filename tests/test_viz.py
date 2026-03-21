"""
tests/test_viz.py

Tests for knowledgecomplex.viz — NetworkX export and matplotlib plotting.
Skipped if networkx or matplotlib are not installed.
"""

import pytest

nx = pytest.importorskip("networkx")
mpl = pytest.importorskip("matplotlib")
mpl.use("Agg")  # non-interactive backend for CI

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.viz import (
    to_networkx,
    type_color_map,
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
    def test_node_count(self, kc):
        G = to_networkx(kc)
        assert len(G.nodes) == 7  # 3 vertices + 3 edges + 1 face

    def test_edge_count(self, kc):
        G = to_networkx(kc)
        # boundedBy: 3 edges × 2 vertices + 1 face × 3 edges = 9
        assert len(G.edges) == 9

    def test_node_has_type_kind_dim(self, kc):
        G = to_networkx(kc)
        for n in G.nodes:
            assert "type" in G.nodes[n]
            assert "kind" in G.nodes[n]
            assert "dim" in G.nodes[n]

    def test_vertex_attributes(self, kc):
        G = to_networkx(kc)
        assert G.nodes["v1"]["kind"] == "vertex"
        assert G.nodes["v1"]["dim"] == 0
        assert G.nodes["v1"]["type"] == "Node"

    def test_edge_attributes(self, kc):
        G = to_networkx(kc)
        assert G.nodes["e12"]["kind"] == "edge"
        assert G.nodes["e12"]["dim"] == 1
        assert G.nodes["e12"]["weight"] == "light"

    def test_face_attributes(self, kc):
        G = to_networkx(kc)
        assert G.nodes["f123"]["kind"] == "face"
        assert G.nodes["f123"]["dim"] == 2

    def test_graph_name(self, kc):
        G = to_networkx(kc)
        assert G.graph["name"] == "viz"

    def test_empty_kc(self, empty_kc):
        G = to_networkx(empty_kc)
        assert len(G.nodes) == 0
        assert len(G.edges) == 0


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
            assert len(color) == 7  # #RRGGBB

    def test_distinct_colors(self, kc):
        colors = type_color_map(kc)
        # With 3 types, all should be distinct
        assert len(set(colors.values())) == len(colors)


# --- plot_complex ---


class TestPlotComplex:
    def test_returns_fig_ax(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_complex(kc)
        assert isinstance(fig, plt.Figure)
        assert isinstance(ax, plt.Axes)
        plt.close(fig)

    def test_empty_kc(self, empty_kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_complex(empty_kc)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_custom_ax(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        fig2, ax2 = plot_complex(kc, ax=ax)
        assert ax2 is ax
        plt.close(fig)

    def test_no_labels(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_complex(kc, with_labels=False)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)


# --- plot_star ---


class TestPlotStar:
    def test_returns_fig_ax(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_star(kc, "v1")
        assert isinstance(fig, plt.Figure)
        assert isinstance(ax, plt.Axes)
        plt.close(fig)

    def test_title_contains_id(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_star(kc, "v1")
        assert "v1" in ax.get_title()
        plt.close(fig)


# --- plot_skeleton ---


class TestPlotSkeleton:
    def test_returns_fig_ax(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_skeleton(kc, 1)
        assert isinstance(fig, plt.Figure)
        assert isinstance(ax, plt.Axes)
        plt.close(fig)

    def test_skeleton_0(self, kc):
        import matplotlib.pyplot as plt
        fig, ax = plot_skeleton(kc, 0)
        assert "0" in ax.get_title()
        plt.close(fig)
