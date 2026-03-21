"""
tests/test_clique.py

Tests for knowledgecomplex.clique — clique detection, typed face inference,
and generic flagification.
"""

import pytest

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.clique import find_cliques, infer_faces, fill_cliques, _edges_between
from knowledgecomplex.exceptions import SchemaError


@pytest.fixture
def schema() -> SchemaBuilder:
    """Schema with one vertex type, one edge type, one face type."""
    sb = SchemaBuilder(namespace="cq")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link")
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def schema_multi_edge() -> SchemaBuilder:
    """Schema with two edge types for filtering tests."""
    sb = SchemaBuilder(namespace="cq")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link")
    sb.add_edge_type("Special")
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def triangle(schema) -> KnowledgeComplex:
    """3 vertices, 3 edges forming a single triangle. No face added."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
    return kc


@pytest.fixture
def k4(schema) -> KnowledgeComplex:
    """Complete graph K4: 4 vertices, 6 edges, no faces."""
    kc = KnowledgeComplex(schema=schema)
    for i in range(1, 5):
        kc.add_vertex(f"v{i}", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
    kc.add_edge("e14", type="Link", vertices={"v1", "v4"})
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
    kc.add_edge("e24", type="Link", vertices={"v2", "v4"})
    kc.add_edge("e34", type="Link", vertices={"v3", "v4"})
    return kc


# --- _edges_between ---


class TestEdgesBetween:
    def test_finds_edge(self, triangle):
        edges = _edges_between(triangle, "v1", "v2")
        assert edges == ["e12"]

    def test_no_edge(self, schema):
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("a", type="Node")
        kc.add_vertex("b", type="Node")
        assert _edges_between(kc, "a", "b") == []

    def test_edge_type_filter(self, schema_multi_edge):
        kc = KnowledgeComplex(schema=schema_multi_edge)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")
        kc.add_edge("e1", type="Link", vertices={"v1", "v2"})
        kc.add_edge("e2", type="Special", vertices={"v1", "v2"})
        assert len(_edges_between(kc, "v1", "v2")) == 2
        assert len(_edges_between(kc, "v1", "v2", edge_type="Link")) == 1
        assert len(_edges_between(kc, "v1", "v2", edge_type="Special")) == 1


# --- find_cliques ---


class TestFindCliques:
    def test_triangle_has_one_3clique(self, triangle):
        cliques = find_cliques(triangle, k=3)
        assert len(cliques) == 1
        assert cliques[0] == frozenset(["v1", "v2", "v3"])

    def test_k4_has_four_3cliques(self, k4):
        cliques = find_cliques(k4, k=3)
        assert len(cliques) == 4

    def test_k4_has_one_4clique(self, k4):
        cliques = find_cliques(k4, k=4)
        assert len(cliques) == 1
        assert cliques[0] == frozenset(["v1", "v2", "v3", "v4"])

    def test_no_cliques_in_path(self, schema):
        """A path graph v1-v2-v3 has no triangles."""
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")
        kc.add_vertex("v3", type="Node")
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
        kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
        assert find_cliques(kc, k=3) == []

    def test_edge_type_filter(self, schema_multi_edge):
        """Only edges of specified type form cliques."""
        kc = KnowledgeComplex(schema=schema_multi_edge)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")
        kc.add_vertex("v3", type="Node")
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
        kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
        kc.add_edge("e13", type="Special", vertices={"v1", "v3"})
        # With all edges: 1 triangle
        assert len(find_cliques(kc, k=3)) == 1
        # With only Link edges: no triangle (e13 is Special)
        assert len(find_cliques(kc, k=3, edge_type="Link")) == 0

    def test_k_less_than_2_raises(self, triangle):
        with pytest.raises(ValueError, match="Clique size"):
            find_cliques(triangle, k=1)


# --- infer_faces ---


class TestInferFaces:
    def test_adds_one_face(self, triangle):
        added = infer_faces(triangle, "Triangle")
        assert len(added) == 1
        # Face was actually added
        assert len(triangle.skeleton(2) - triangle.skeleton(1)) == 1

    def test_k4_adds_four_faces(self, k4):
        added = infer_faces(k4, "Triangle")
        assert len(added) == 4

    def test_dry_run_adds_nothing(self, triangle):
        added = infer_faces(triangle, "Triangle", dry_run=True)
        assert len(added) == 1  # one would-be face
        # Nothing actually added
        assert len(triangle.skeleton(2) - triangle.skeleton(1)) == 0

    def test_no_duplicates(self, triangle):
        first = infer_faces(triangle, "Triangle")
        assert len(first) == 1
        second = infer_faces(triangle, "Triangle")
        assert len(second) == 0  # already exists

    def test_edge_type_filter(self, schema_multi_edge):
        kc = KnowledgeComplex(schema=schema_multi_edge)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")
        kc.add_vertex("v3", type="Node")
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
        kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
        kc.add_edge("e13", type="Special", vertices={"v1", "v3"})
        # Filter to Link only — no triangle (e13 is Special)
        added = infer_faces(kc, "Triangle", edge_type="Link")
        assert len(added) == 0
        # No filter — triangle found
        added = infer_faces(kc, "Triangle")
        assert len(added) == 1

    def test_unregistered_type_raises(self, triangle):
        with pytest.raises(SchemaError, match="not registered"):
            infer_faces(triangle, "Bogus")

    def test_non_face_type_raises(self, triangle):
        with pytest.raises(SchemaError, match="not a face type"):
            infer_faces(triangle, "Node")

    def test_custom_id_prefix(self, triangle):
        added = infer_faces(triangle, "Triangle", id_prefix="tri")
        assert added[0].startswith("tri-")

    def test_inferred_face_passes_validation(self, triangle):
        """Inferred face passes SHACL validation (closed triangle)."""
        infer_faces(triangle, "Triangle")
        # If we got here, validation passed during add_face
        face_ids = list(triangle.skeleton(2) - triangle.skeleton(1))
        assert len(face_ids) == 1
        # Boundary should be 3 edges
        assert len(triangle.boundary(face_ids[0])) == 3


# --- fill_cliques ---


class TestFillCliques:
    def test_fills_faces(self, triangle):
        result = fill_cliques(triangle, max_order=2)
        assert 2 in result
        assert len(result[2]) == 1

    def test_k4_fills_four_faces(self, k4):
        result = fill_cliques(k4, max_order=2)
        assert len(result[2]) == 4

    def test_idempotent(self, triangle):
        first = fill_cliques(triangle, max_order=2)
        assert len(first[2]) == 1
        second = fill_cliques(triangle, max_order=2)
        assert len(second[2]) == 0

    def test_no_face_type_raises(self):
        sb = SchemaBuilder(namespace="cq")
        sb.add_vertex_type("Node")
        sb.add_edge_type("Link")
        # No face type declared
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")
        kc.add_vertex("v3", type="Node")
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
        kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
        kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
        with pytest.raises(SchemaError, match="No face types"):
            fill_cliques(kc, max_order=2)

    def test_max_order_too_low_raises(self, triangle):
        with pytest.raises(ValueError, match="max_order"):
            fill_cliques(triangle, max_order=1)
