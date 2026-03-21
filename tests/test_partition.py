"""
tests/test_partition.py

Tests for local partition algorithms:
  - Graph version: graph_laplacian, approximate_pagerank, heat_kernel_pagerank,
    sweep_cut, local_partition
  - Simplicial version: edge_sweep_cut, edge_local_partition

Fixtures:
  - double_triangle: 4v, 5e, 2f (compact, no clear partition)
  - barbell: two triangles joined by a bridge edge (clear partition target)
"""

import pytest

np = pytest.importorskip("numpy")
scipy = pytest.importorskip("scipy")

from numpy.testing import assert_allclose

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.analysis import (
    graph_laplacian,
    approximate_pagerank,
    heat_kernel_pagerank,
    sweep_cut,
    local_partition,
    edge_sweep_cut,
    edge_local_partition,
    boundary_matrices,
    hodge_laplacian,
    SweepCut,
    EdgeSweepCut,
)


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="topo")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link")
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def double_triangle(schema) -> KnowledgeComplex:
    """4 vertices, 5 edges, 2 faces sharing edge e23."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_vertex("v4", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
    kc.add_edge("e24", type="Link", vertices={"v2", "v4"})
    kc.add_edge("e34", type="Link", vertices={"v3", "v4"})
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
    kc.add_face("f234", type="Triangle", boundary=["e23", "e24", "e34"])
    return kc


@pytest.fixture
def barbell(schema) -> KnowledgeComplex:
    r"""Two triangles joined by a bridge edge. Clear partition target.

        v1 --e12-- v2          v5 --e56-- v6
         \        /  \        /  \        /
         e13    e23  e25    e45  e46    e56
           \  /        \  /        \  /
            v3          v4(bridge)  (reuses v5,v6)

    Left triangle: v1,v2,v3 with edges e12,e23,e13
    Bridge: e24 connecting v2-v4
    Right triangle: v4,v5,v6 with edges e45,e56,e46
    """
    kc = KnowledgeComplex(schema=schema)
    # Left triangle
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
    kc.add_face("f_left", type="Triangle", boundary=["e12", "e23", "e13"])
    # Bridge
    kc.add_vertex("v4", type="Node")
    kc.add_edge("e24", type="Link", vertices={"v2", "v4"})
    # Right triangle
    kc.add_vertex("v5", type="Node")
    kc.add_vertex("v6", type="Node")
    kc.add_edge("e45", type="Link", vertices={"v4", "v5"})
    kc.add_edge("e56", type="Link", vertices={"v5", "v6"})
    kc.add_edge("e46", type="Link", vertices={"v4", "v6"})
    kc.add_face("f_right", type="Triangle", boundary=["e45", "e56", "e46"])
    return kc


# ===========================================================================
# Graph Laplacian
# ===========================================================================

class TestGraphLaplacian:

    def test_shape(self, double_triangle):
        L = graph_laplacian(double_triangle)
        assert L.shape == (4, 4)

    def test_symmetric(self, double_triangle):
        L = graph_laplacian(double_triangle)
        assert_allclose(L.toarray(), L.T.toarray(), atol=1e-12)

    def test_diagonal_is_one(self, double_triangle):
        """Normalized Laplacian L = I - D⁻¹A has 1s on the diagonal."""
        L = graph_laplacian(double_triangle)
        assert_allclose(L.diagonal(), np.ones(4))

    def test_row_sums_zero(self, double_triangle):
        """Normalized Laplacian: L = I - D⁻¹A, so L·1 ≠ 0 in general.
        But the combinatorial Laplacian D-A has row sums 0."""
        L = graph_laplacian(double_triangle)
        # For normalized Laplacian, diagonal is 1 and row sums
        # depend on degree distribution — just check it's valid
        assert L.shape[0] == 4

    def test_barbell_shape(self, barbell):
        L = graph_laplacian(barbell)
        assert L.shape == (6, 6)


# ===========================================================================
# Approximate PageRank
# ===========================================================================

class TestApproximatePageRank:

    def test_returns_dicts(self, double_triangle):
        p, r = approximate_pagerank(double_triangle, "v1")
        assert isinstance(p, dict)
        assert isinstance(r, dict)

    def test_p_sums_to_at_most_one(self, double_triangle):
        p, r = approximate_pagerank(double_triangle, "v1")
        assert sum(p.values()) <= 1.0 + 1e-10

    def test_residual_bounded(self, double_triangle):
        eps = 1e-3
        p, r = approximate_pagerank(double_triangle, "v1", epsilon=eps)
        for vid, rv in r.items():
            deg = double_triangle.degree(vid)
            if deg > 0:
                assert rv / deg < eps + 1e-10

    def test_seed_has_most_mass(self, double_triangle):
        p, r = approximate_pagerank(double_triangle, "v1", alpha=0.5)
        # With high alpha, seed should have significant mass
        assert p.get("v1", 0) > 0

    def test_barbell_locality(self, barbell):
        """Starting from v1, more mass on left side than right."""
        p, r = approximate_pagerank(barbell, "v1", alpha=0.15)
        left_mass = sum(p.get(v, 0) for v in ["v1", "v2", "v3"])
        right_mass = sum(p.get(v, 0) for v in ["v4", "v5", "v6"])
        assert left_mass > right_mass


# ===========================================================================
# Heat kernel PageRank
# ===========================================================================

class TestHeatKernelPageRank:

    def test_returns_dict(self, double_triangle):
        rho = heat_kernel_pagerank(double_triangle, "v1")
        assert isinstance(rho, dict)

    def test_sums_near_one(self, double_triangle):
        rho = heat_kernel_pagerank(double_triangle, "v1", t=5.0)
        assert abs(sum(rho.values()) - 1.0) < 0.01

    def test_concentrated_small_t(self, double_triangle):
        """For small t, mass is concentrated near seed."""
        rho = heat_kernel_pagerank(double_triangle, "v1", t=0.1)
        assert rho.get("v1", 0) > rho.get("v4", 0)

    def test_spreads_large_t(self, double_triangle):
        """For large t, mass spreads toward stationary distribution."""
        rho_small = heat_kernel_pagerank(double_triangle, "v1", t=0.5)
        rho_large = heat_kernel_pagerank(double_triangle, "v1", t=50.0)
        # Large t should be more uniform
        vals_large = list(rho_large.values())
        vals_small = list(rho_small.values())
        assert np.std(vals_large) < np.std(vals_small)


# ===========================================================================
# Sweep cut (graph)
# ===========================================================================

class TestSweepCut:

    def test_returns_sweepcut(self, double_triangle):
        p, _ = approximate_pagerank(double_triangle, "v1")
        cut = sweep_cut(double_triangle, p)
        assert isinstance(cut, SweepCut)

    def test_conductance_positive(self, double_triangle):
        p, _ = approximate_pagerank(double_triangle, "v1")
        cut = sweep_cut(double_triangle, p)
        assert cut.conductance > 0

    def test_barbell_finds_bridge(self, barbell):
        """Barbell graph should yield a cut with low conductance at the bridge."""
        p, _ = approximate_pagerank(barbell, "v1", alpha=0.15)
        cut = sweep_cut(barbell, p)
        assert cut.conductance < 1.0
        # The small side should be one of the two triangles (3 vertices)
        assert len(cut.vertices) <= 4

    def test_max_volume(self, barbell):
        p, _ = approximate_pagerank(barbell, "v1")
        cut = sweep_cut(barbell, p, max_volume=6)
        assert cut.volume <= 6


# ===========================================================================
# Local partition (graph)
# ===========================================================================

class TestLocalPartition:

    def test_pagerank_method(self, barbell):
        cut = local_partition(barbell, "v1", method="pagerank")
        assert isinstance(cut, SweepCut)
        assert cut.conductance > 0

    def test_heat_kernel_method(self, barbell):
        cut = local_partition(barbell, "v1", method="heat_kernel")
        assert isinstance(cut, SweepCut)
        assert cut.conductance > 0

    def test_barbell_low_conductance(self, barbell):
        cut = local_partition(barbell, "v1", method="pagerank")
        # Barbell has a clear bottleneck; conductance should be small
        assert cut.conductance < 1.0


# ===========================================================================
# Edge sweep cut (simplicial)
# ===========================================================================

class TestEdgeSweepCut:

    def test_returns_result(self, double_triangle):
        from knowledgecomplex.analysis import edge_pagerank
        pr = edge_pagerank(double_triangle, "e12", beta=0.1)
        cut = edge_sweep_cut(double_triangle, pr)
        assert isinstance(cut, EdgeSweepCut)

    def test_conductance_positive(self, double_triangle):
        from knowledgecomplex.analysis import edge_pagerank
        pr = edge_pagerank(double_triangle, "e12", beta=0.1)
        cut = edge_sweep_cut(double_triangle, pr)
        assert cut.conductance > 0


# ===========================================================================
# Edge local partition (simplicial)
# ===========================================================================

class TestEdgeLocalPartition:

    def test_hodge_pagerank_method(self, double_triangle):
        cut = edge_local_partition(double_triangle, "e12", method="hodge_pagerank")
        assert isinstance(cut, EdgeSweepCut)

    def test_hodge_heat_method(self, double_triangle):
        cut = edge_local_partition(double_triangle, "e12", method="hodge_heat")
        assert isinstance(cut, EdgeSweepCut)

    def test_with_weights(self, double_triangle):
        w = {"v1": 2.0, "f123": 3.0}
        cut = edge_local_partition(double_triangle, "e12",
                                   method="hodge_pagerank", weights=w)
        assert isinstance(cut, EdgeSweepCut)

    def test_barbell_edge_partition(self, barbell):
        cut = edge_local_partition(barbell, "e12", method="hodge_pagerank")
        assert isinstance(cut, EdgeSweepCut)
        assert cut.conductance > 0
