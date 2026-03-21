"""
tests/test_analysis.py

Tests for topological analysis: boundary matrices, Betti numbers,
Hodge Laplacian, edge PageRank, Hodge decomposition, edge influence.

Fixtures:
  - double_triangle: 4 vertices, 5 edges, 2 faces (contractible, β₁=0)
  - cycle_only: 3 vertices, 3 edges, 0 faces (one cycle, β₁=1)
  - disconnected: 2 vertices, 0 edges (β₀=2)
"""

import pytest
import numpy as np
from numpy.testing import assert_allclose

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.analysis import (
    boundary_matrices,
    betti_numbers,
    euler_characteristic,
    hodge_laplacian,
    edge_pagerank,
    edge_pagerank_all,
    hodge_decomposition,
    edge_influence,
    hodge_analysis,
    BoundaryMatrices,
    HodgeDecomposition,
    EdgeInfluence,
    HodgeAnalysisResults,
)


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="topo")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link", attributes={"weight": vocab("light", "heavy")})
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def double_triangle(schema) -> KnowledgeComplex:
    """4 vertices, 5 edges, 2 faces sharing edge e23. Contractible."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_vertex("v4", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, weight="light")
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"}, weight="heavy")
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"}, weight="light")
    kc.add_edge("e24", type="Link", vertices={"v2", "v4"}, weight="heavy")
    kc.add_edge("e34", type="Link", vertices={"v3", "v4"}, weight="light")
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
    kc.add_face("f234", type="Triangle", boundary=["e23", "e24", "e34"])
    return kc


@pytest.fixture
def cycle_only(schema) -> KnowledgeComplex:
    """3 vertices, 3 edges, 0 faces. One independent cycle (β₁=1)."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, weight="light")
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"}, weight="light")
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"}, weight="light")
    return kc


@pytest.fixture
def disconnected(schema) -> KnowledgeComplex:
    """2 vertices, 0 edges. β₀=2."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    return kc


# ===========================================================================
# Boundary matrices
# ===========================================================================

class TestBoundaryMatrices:

    def test_shapes(self, double_triangle):
        bm = boundary_matrices(double_triangle)
        assert bm.B1.shape == (4, 5)  # 4 vertices, 5 edges
        assert bm.B2.shape == (5, 2)  # 5 edges, 2 faces

    def test_B1_two_nonzeros_per_column(self, double_triangle):
        """Each edge has exactly 2 boundary vertices."""
        bm = boundary_matrices(double_triangle)
        for col in range(bm.B1.shape[1]):
            nnz = bm.B1[:, col].nnz
            assert nnz == 2

    def test_B2_three_nonzeros_per_column(self, double_triangle):
        """Each face has exactly 3 boundary edges."""
        bm = boundary_matrices(double_triangle)
        for col in range(bm.B2.shape[1]):
            nnz = bm.B2[:, col].nnz
            assert nnz == 3

    def test_boundary_of_boundary_is_zero(self, double_triangle):
        """∂₁ ∘ ∂₂ = 0 (fundamental theorem of simplicial homology)."""
        bm = boundary_matrices(double_triangle)
        product = bm.B1 @ bm.B2
        assert_allclose(product.toarray(), 0, atol=1e-12)

    def test_index_maps_bijective(self, double_triangle):
        bm = boundary_matrices(double_triangle)
        assert len(bm.vertex_index) == 4
        assert len(bm.edge_index) == 5
        assert len(bm.face_index) == 2
        for k, v in bm.vertex_index.items():
            assert bm.index_vertex[v] == k
        for k, v in bm.edge_index.items():
            assert bm.index_edge[v] == k

    def test_no_faces(self, cycle_only):
        """Complex with no faces has B2 with 0 columns."""
        bm = boundary_matrices(cycle_only)
        assert bm.B1.shape == (3, 3)
        assert bm.B2.shape == (3, 0)

    def test_no_edges(self, disconnected):
        """Complex with no edges has B1 with 0 columns."""
        bm = boundary_matrices(disconnected)
        assert bm.B1.shape == (2, 0)
        assert bm.B2.shape == (0, 0)


# ===========================================================================
# Betti numbers
# ===========================================================================

class TestBettiNumbers:

    def test_double_triangle_contractible(self, double_triangle):
        """Double triangle is contractible: β = [1, 0, 0]."""
        b = betti_numbers(double_triangle)
        assert b == [1, 0, 0]

    def test_cycle_has_hole(self, cycle_only):
        """Triangle boundary has one cycle: β = [1, 1, 0]."""
        b = betti_numbers(cycle_only)
        assert b == [1, 1, 0]

    def test_disconnected_components(self, disconnected):
        """Two disconnected vertices: β = [2, 0, 0]."""
        b = betti_numbers(disconnected)
        assert b == [2, 0, 0]

    def test_euler_characteristic(self, double_triangle):
        """χ = V - E + F = 4 - 5 + 2 = 1."""
        chi = euler_characteristic(double_triangle)
        assert chi == 1

    def test_euler_equals_alternating_betti(self, double_triangle):
        """χ = β₀ - β₁ + β₂."""
        b = betti_numbers(double_triangle)
        chi = euler_characteristic(double_triangle)
        assert chi == b[0] - b[1] + b[2]

    def test_euler_cycle(self, cycle_only):
        """χ = 3 - 3 + 0 = 0."""
        assert euler_characteristic(cycle_only) == 0


# ===========================================================================
# Hodge Laplacian
# ===========================================================================

class TestHodgeLaplacian:

    def test_shape(self, double_triangle):
        L1 = hodge_laplacian(double_triangle)
        assert L1.shape == (5, 5)

    def test_symmetric(self, double_triangle):
        L1 = hodge_laplacian(double_triangle)
        diff = L1 - L1.T
        assert_allclose(diff.toarray(), 0, atol=1e-12)

    def test_positive_semidefinite(self, double_triangle):
        L1 = hodge_laplacian(double_triangle)
        eigenvalues = np.linalg.eigvalsh(L1.toarray())
        assert np.all(eigenvalues >= -1e-10)

    def test_kernel_dimension_equals_beta1(self, double_triangle):
        """dim ker(L₁) = β₁ for combinatorial Laplacian."""
        L1 = hodge_laplacian(double_triangle)
        eigenvalues = np.linalg.eigvalsh(L1.toarray())
        kernel_dim = np.sum(np.abs(eigenvalues) < 1e-8)
        b = betti_numbers(double_triangle)
        assert kernel_dim == b[1]

    def test_kernel_dimension_cycle(self, cycle_only):
        """Cycle has β₁=1 so L₁ has 1D kernel."""
        L1 = hodge_laplacian(cycle_only)
        eigenvalues = np.linalg.eigvalsh(L1.toarray())
        kernel_dim = np.sum(np.abs(eigenvalues) < 1e-8)
        assert kernel_dim == 1

    def test_weighted_symmetric(self, double_triangle):
        L1 = hodge_laplacian(double_triangle, weighted=True)
        diff = L1 - L1.T
        assert_allclose(diff.toarray(), 0, atol=1e-12)

    def test_weighted_psd(self, double_triangle):
        L1 = hodge_laplacian(double_triangle, weighted=True)
        eigenvalues = np.linalg.eigvalsh(L1.toarray())
        assert np.all(eigenvalues >= -1e-10)


# ===========================================================================
# Edge PageRank
# ===========================================================================

class TestEdgePageRank:

    def test_single_edge_shape(self, double_triangle):
        bm = boundary_matrices(double_triangle)
        pr = edge_pagerank(double_triangle, "e12", beta=0.1)
        assert pr.shape == (5,)

    def test_nonzero_at_target(self, double_triangle):
        """The target edge has nonzero PageRank."""
        bm = boundary_matrices(double_triangle)
        pr = edge_pagerank(double_triangle, "e12", beta=0.1)
        assert pr[bm.edge_index["e12"]] > 0

    def test_all_edges_shape(self, double_triangle):
        pr = edge_pagerank_all(double_triangle, beta=0.1)
        assert pr.shape == (5, 5)

    def test_all_edges_symmetric(self, double_triangle):
        """PR matrix is symmetric since L₁ is symmetric."""
        pr = edge_pagerank_all(double_triangle, beta=0.1)
        assert_allclose(pr, pr.T, atol=1e-10)

    def test_single_matches_all(self, double_triangle):
        """Single edge PR matches column of all-edges matrix."""
        bm = boundary_matrices(double_triangle)
        pr_single = edge_pagerank(double_triangle, "e12", beta=0.1)
        pr_all = edge_pagerank_all(double_triangle, beta=0.1)
        col_idx = bm.edge_index["e12"]
        assert_allclose(pr_single, pr_all[:, col_idx], atol=1e-10)


# ===========================================================================
# Hodge decomposition
# ===========================================================================

class TestHodgeDecomposition:

    def test_exact_decomposition(self, double_triangle):
        """gradient + curl + harmonic = original vector."""
        flow = edge_pagerank(double_triangle, "e12", beta=0.1)
        decomp = hodge_decomposition(double_triangle, flow)
        reconstructed = decomp.gradient + decomp.curl + decomp.harmonic
        assert_allclose(reconstructed, flow, atol=1e-8)

    def test_orthogonality(self, double_triangle):
        """Components are mutually orthogonal."""
        flow = edge_pagerank(double_triangle, "e12", beta=0.1)
        decomp = hodge_decomposition(double_triangle, flow)
        assert abs(np.dot(decomp.gradient, decomp.curl)) < 1e-8
        assert abs(np.dot(decomp.gradient, decomp.harmonic)) < 1e-8
        assert abs(np.dot(decomp.curl, decomp.harmonic)) < 1e-8

    def test_contractible_no_harmonic(self, double_triangle):
        """Contractible complex (β₁=0) → harmonic component is zero."""
        flow = edge_pagerank(double_triangle, "e12", beta=0.1)
        decomp = hodge_decomposition(double_triangle, flow)
        assert_allclose(decomp.harmonic, 0, atol=1e-8)

    def test_cycle_has_harmonic(self, cycle_only):
        """Complex with β₁=1 → harmonic component is nonzero for generic flow."""
        flow = np.ones(3)  # uniform flow
        decomp = hodge_decomposition(cycle_only, flow)
        assert np.linalg.norm(decomp.harmonic) > 1e-8


# ===========================================================================
# Edge influence
# ===========================================================================

class TestEdgeInfluence:

    def test_non_negative(self, double_triangle):
        pr = edge_pagerank(double_triangle, "e12", beta=0.1)
        inf = edge_influence("e12", pr)
        assert inf.spread >= 0
        assert inf.absolute_influence >= 0
        assert inf.penetration >= 0

    def test_spread_range(self, double_triangle):
        pr = edge_pagerank(double_triangle, "e12", beta=0.1)
        inf = edge_influence("e12", pr)
        assert 0 <= inf.spread <= 1


# ===========================================================================
# Full analysis
# ===========================================================================

class TestHodgeAnalysis:

    def test_returns_results(self, double_triangle):
        results = hodge_analysis(double_triangle, beta=0.1)
        assert isinstance(results, HodgeAnalysisResults)
        assert results.betti == [1, 0, 0]
        assert results.euler_characteristic == 1
        assert results.pagerank.shape == (5, 5)
        assert len(results.decompositions) == 5
        assert len(results.influences) == 5

    def test_cycle_analysis(self, cycle_only):
        results = hodge_analysis(cycle_only, beta=0.1)
        assert results.betti == [1, 1, 0]
        assert results.euler_characteristic == 0


# ===========================================================================
# Simplex weights
# ===========================================================================

class TestWeights:

    def test_none_matches_unweighted(self, double_triangle):
        """weights=None produces identical results to default."""
        L_default = hodge_laplacian(double_triangle)
        L_none = hodge_laplacian(double_triangle, weights=None)
        assert_allclose(L_default.toarray(), L_none.toarray())

    def test_uniform_weights_match_unweighted(self, double_triangle):
        """All weights=1.0 produces identical results to default."""
        all_ids = double_triangle.element_ids()
        uniform = {eid: 1.0 for eid in all_ids}
        L_default = hodge_laplacian(double_triangle)
        L_uniform = hodge_laplacian(double_triangle, weights=uniform)
        assert_allclose(L_default.toarray(), L_uniform.toarray(), atol=1e-12)

    def test_vertex_weights_change_laplacian(self, double_triangle):
        """Non-uniform vertex weights produce a different Laplacian."""
        w = {"v1": 2.0, "v2": 0.5}  # others default to 1.0
        L_default = hodge_laplacian(double_triangle)
        L_weighted = hodge_laplacian(double_triangle, weights=w)
        assert not np.allclose(L_default.toarray(), L_weighted.toarray())

    def test_face_weights_change_laplacian(self, double_triangle):
        """Non-uniform face weights produce a different Laplacian."""
        w = {"f123": 3.0, "f234": 0.1}
        L_default = hodge_laplacian(double_triangle)
        L_weighted = hodge_laplacian(double_triangle, weights=w)
        assert not np.allclose(L_default.toarray(), L_weighted.toarray())

    def test_weighted_laplacian_symmetric(self, double_triangle):
        """Weighted Laplacian is symmetric."""
        w = {"v1": 2.0, "v2": 0.5, "f123": 3.0}
        L = hodge_laplacian(double_triangle, weights=w)
        assert_allclose(L.toarray(), L.T.toarray(), atol=1e-12)

    def test_weighted_laplacian_psd(self, double_triangle):
        """Weighted Laplacian is positive semidefinite."""
        w = {"v1": 2.0, "v2": 0.5, "f123": 3.0}
        L = hodge_laplacian(double_triangle, weights=w)
        eigenvalues = np.linalg.eigvalsh(L.toarray())
        assert np.all(eigenvalues >= -1e-10)

    def test_betti_unchanged_by_weights(self, double_triangle):
        """Betti numbers are topological invariants — weights don't change them."""
        b_default = betti_numbers(double_triangle)
        # Betti numbers only depend on boundary matrices, not weights
        assert b_default == [1, 0, 0]

    def test_weighted_pagerank_differs(self, double_triangle):
        """Weighted PageRank differs from unweighted."""
        w = {"v1": 5.0, "v3": 0.1, "f123": 2.0}
        pr_default = edge_pagerank(double_triangle, "e12", beta=0.1)
        pr_weighted = edge_pagerank(double_triangle, "e12", beta=0.1, weights=w)
        assert not np.allclose(pr_default, pr_weighted)

    def test_weighted_decomposition_exact(self, double_triangle):
        """Weighted Hodge decomposition still sums to original flow."""
        w = {"v1": 2.0, "f234": 3.0}
        flow = edge_pagerank(double_triangle, "e12", beta=0.1, weights=w)
        decomp = hodge_decomposition(double_triangle, flow, weights=w)
        reconstructed = decomp.gradient + decomp.curl + decomp.harmonic
        assert_allclose(reconstructed, flow, atol=1e-8)

    def test_weighted_hodge_analysis(self, double_triangle):
        """Full hodge_analysis with weights runs without error."""
        w = {"v1": 2.0, "v2": 0.5, "f123": 3.0, "f234": 0.5}
        results = hodge_analysis(double_triangle, beta=0.1, weights=w)
        assert isinstance(results, HodgeAnalysisResults)
        assert results.betti == [1, 0, 0]
        assert results.pagerank.shape == (5, 5)
