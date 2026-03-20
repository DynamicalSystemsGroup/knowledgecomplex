"""
tests/test_topology.py

Tests for topological query methods on KnowledgeComplex:
boundary, coboundary, star, closure, closed_star, link, skeleton, degree.

Test fixture: double-triangle complex sharing edge e23.

    v1 --e12-- v2 --e24-- v4
     \        / \        /
     e13    e23  e24   e34
       \  /       \  /
        v3         (v4 reused)

    f123 = (e12, e23, e13)
    f234 = (e23, e24, e34)

4 vertices, 5 edges, 2 faces = 11 elements.
"""

import pytest

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.exceptions import SchemaError


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="topo")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link", attributes={"weight": vocab("light", "heavy")})
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
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, weight="light")
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"}, weight="heavy")
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"}, weight="light")
    kc.add_edge("e24", type="Link", vertices={"v2", "v4"}, weight="heavy")
    kc.add_edge("e34", type="Link", vertices={"v3", "v4"}, weight="light")
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
    kc.add_face("f234", type="Triangle", boundary=["e23", "e24", "e34"])
    return kc


# --- boundary ---

class TestBoundary:
    def test_vertex_boundary_is_empty(self, double_triangle):
        assert double_triangle.boundary("v1") == set()

    def test_edge_boundary(self, double_triangle):
        assert double_triangle.boundary("e12") == {"v1", "v2"}

    def test_face_boundary(self, double_triangle):
        assert double_triangle.boundary("f123") == {"e12", "e23", "e13"}

    def test_boundary_with_type_filter(self, double_triangle):
        # All boundary elements of e12 are Node vertices
        assert double_triangle.boundary("e12", type="Node") == {"v1", "v2"}

    def test_boundary_type_filter_excludes(self, double_triangle):
        # boundary of e12 are vertices, filtering by Link returns empty
        assert double_triangle.boundary("e12", type="Link") == set()


# --- coboundary ---

class TestCoboundary:
    def test_vertex_coboundary(self, double_triangle):
        assert double_triangle.coboundary("v1") == {"e12", "e13"}

    def test_shared_edge_coboundary(self, double_triangle):
        # e23 is shared by both faces
        assert double_triangle.coboundary("e23") == {"f123", "f234"}

    def test_face_coboundary_is_empty(self, double_triangle):
        assert double_triangle.coboundary("f123") == set()

    def test_coboundary_with_type_filter(self, double_triangle):
        # coboundary of v2 filtered to Triangle type
        assert double_triangle.coboundary("v2", type="Triangle") == set()
        # coboundary of v2 filtered to Link type
        assert double_triangle.coboundary("v2", type="Link") == {"e12", "e23", "e24"}


# --- star ---

class TestStar:
    def test_vertex_star(self, double_triangle):
        # v1 is in e12, e13, f123
        assert double_triangle.star("v1") == {"v1", "e12", "e13", "f123"}

    def test_central_vertex_star(self, double_triangle):
        # v2 is in e12, e23, e24, f123, f234
        assert double_triangle.star("v2") == {"v2", "e12", "e23", "e24", "f123", "f234"}

    def test_shared_edge_star(self, double_triangle):
        assert double_triangle.star("e23") == {"e23", "f123", "f234"}

    def test_face_star_is_self(self, double_triangle):
        assert double_triangle.star("f123") == {"f123"}

    def test_star_with_type_filter(self, double_triangle):
        # star of v1 filtered to Link edges only
        assert double_triangle.star("v1", type="Link") == {"e12", "e13"}


# --- closure ---

class TestClosure:
    def test_vertex_closure_is_self(self, double_triangle):
        assert double_triangle.closure("v1") == {"v1"}

    def test_edge_closure(self, double_triangle):
        assert double_triangle.closure("e12") == {"e12", "v1", "v2"}

    def test_face_closure(self, double_triangle):
        assert double_triangle.closure("f123") == {
            "f123", "e12", "e23", "e13", "v1", "v2", "v3"
        }

    def test_closure_set_input(self, double_triangle):
        # closure of {e12, e34} = union of their closures
        assert double_triangle.closure({"e12", "e34"}) == {
            "e12", "v1", "v2", "e34", "v3", "v4"
        }

    def test_closure_with_type_filter(self, double_triangle):
        # closure of f123 filtered to Node vertices only
        assert double_triangle.closure("f123", type="Node") == {"v1", "v2", "v3"}


# --- closed_star ---

class TestClosedStar:
    def test_closed_star_of_central_vertex(self, double_triangle):
        # v2 touches everything — closed star should be the entire complex
        cs = double_triangle.closed_star("v2")
        all_elements = {
            "v1", "v2", "v3", "v4",
            "e12", "e23", "e13", "e24", "e34",
            "f123", "f234",
        }
        assert cs == all_elements

    def test_closed_star_of_peripheral_vertex(self, double_triangle):
        # v1 star = {v1, e12, e13, f123}
        # closure adds boundary of f123: e23, v2, v3
        cs = double_triangle.closed_star("v1")
        assert cs == {"v1", "v2", "v3", "e12", "e13", "e23", "f123"}


# --- link ---

class TestLink:
    def test_link_of_central_vertex(self, double_triangle):
        # Lk(v2) = Cl(St(v2)) \ St(v2)
        # St(v2) = {v2, e12, e23, e24, f123, f234}
        # Cl(St(v2)) = entire complex
        # Link = {v1, v3, v4, e13, e34}
        assert double_triangle.link("v2") == {"v1", "v3", "v4", "e13", "e34"}

    def test_link_of_peripheral_vertex(self, double_triangle):
        # St(v1) = {v1, e12, e13, f123}
        # Cl(St(v1)) = {v1, v2, v3, e12, e13, e23, f123}
        # Link = {v2, v3, e23}
        assert double_triangle.link("v1") == {"v2", "v3", "e23"}

    def test_link_of_shared_edge(self, double_triangle):
        # St(e23) = {e23, f123, f234}
        # Cl(St(e23)) = {e23, v2, v3, f123, e12, e13, v1, f234, e24, e34, v4}
        # Link = Cl(St) - St = {v2, v3, e12, e13, v1, e24, e34, v4}
        expected = {"v1", "v2", "v3", "v4", "e12", "e13", "e24", "e34"}
        assert double_triangle.link("e23") == expected

    def test_link_of_face(self, double_triangle):
        # St(f123) = {f123}
        # Cl(St(f123)) = {f123, e12, e23, e13, v1, v2, v3}
        # Link = {e12, e23, e13, v1, v2, v3}
        assert double_triangle.link("f123") == {"e12", "e23", "e13", "v1", "v2", "v3"}

    def test_link_with_type_filter(self, double_triangle):
        # link of v2 filtered to Node only
        assert double_triangle.link("v2", type="Node") == {"v1", "v3", "v4"}


# --- skeleton ---

class TestSkeleton:
    def test_skeleton_0(self, double_triangle):
        assert double_triangle.skeleton(0) == {"v1", "v2", "v3", "v4"}

    def test_skeleton_1(self, double_triangle):
        assert double_triangle.skeleton(1) == {
            "v1", "v2", "v3", "v4",
            "e12", "e23", "e13", "e24", "e34",
        }

    def test_skeleton_2(self, double_triangle):
        assert double_triangle.skeleton(2) == {
            "v1", "v2", "v3", "v4",
            "e12", "e23", "e13", "e24", "e34",
            "f123", "f234",
        }

    def test_skeleton_negative_raises(self, double_triangle):
        with pytest.raises(ValueError, match="skeleton dimension"):
            double_triangle.skeleton(-1)

    def test_skeleton_too_high_raises(self, double_triangle):
        with pytest.raises(ValueError, match="skeleton dimension"):
            double_triangle.skeleton(3)


# --- degree ---

class TestDegree:
    def test_degree_peripheral_vertex(self, double_triangle):
        assert double_triangle.degree("v1") == 2  # e12, e13

    def test_degree_central_vertex(self, double_triangle):
        assert double_triangle.degree("v2") == 3  # e12, e23, e24

    def test_degree_v3(self, double_triangle):
        assert double_triangle.degree("v3") == 3  # e23, e13, e34

    def test_degree_v4(self, double_triangle):
        assert double_triangle.degree("v4") == 2  # e24, e34


# --- composability ---

class TestComposability:
    def test_closure_of_star(self, double_triangle):
        """closure(star(id)) == closed_star(id)."""
        cs = double_triangle.closed_star("v1")
        composed = double_triangle.closure(double_triangle.star("v1"))
        assert cs == composed

    def test_set_intersection(self, double_triangle):
        """Star intersection finds shared elements."""
        s1 = double_triangle.star("v1")
        s2 = double_triangle.star("v3")
        # v1 and v3 share e13 and f123
        shared = s1 & s2
        assert "e13" in shared
        assert "f123" in shared

    def test_set_union(self, double_triangle):
        """Star union combines neighborhoods."""
        s1 = double_triangle.star("v1")
        s4 = double_triangle.star("v4")
        combined = s1 | s4
        assert "v1" in combined
        assert "v4" in combined

    def test_set_difference(self, double_triangle):
        """Set difference works for custom link-like operations."""
        st = double_triangle.star("v1")
        bd = double_triangle.boundary("e12")
        # Remove v1's star boundary vertices
        result = st - bd
        assert "v1" not in result or "v2" not in result


# --- type filter edge cases ---

class TestTypeFilterEdgeCases:
    def test_invalid_type_raises(self, double_triangle):
        with pytest.raises(SchemaError):
            double_triangle.star("v1", type="NonexistentType")

    def test_star_filter_to_triangle(self, double_triangle):
        assert double_triangle.star("v1", type="Triangle") == {"f123"}

    def test_coboundary_filter_empty_result(self, double_triangle):
        # v1 has no Triangle in its direct coboundary (coboundary is edges)
        # but coboundary means direct containment only
        assert double_triangle.coboundary("v1", type="Triangle") == set()
