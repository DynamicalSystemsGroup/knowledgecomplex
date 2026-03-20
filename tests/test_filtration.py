"""
tests/test_filtration.py

Tests for is_subcomplex, Filtration class construction, indexing, iteration,
query methods, and composability with topological queries.

Fixture: double-triangle complex (4 vertices, 5 edges, 2 faces).
"""

import pytest

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.filtration import Filtration
from knowledgecomplex.exceptions import SchemaError


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="topo")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link", attributes={"weight": vocab("light", "heavy")})
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def kc(schema) -> KnowledgeComplex:
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


ALL_ELEMENTS = {
    "v1", "v2", "v3", "v4",
    "e12", "e23", "e13", "e24", "e34",
    "f123", "f234",
}


# ===========================================================================
# is_subcomplex tests
# ===========================================================================

class TestIsSubcomplex:

    def test_single_vertex(self, kc):
        assert kc.is_subcomplex({"v1"}) is True

    def test_edge_with_vertices(self, kc):
        assert kc.is_subcomplex({"v1", "v2", "e12"}) is True

    def test_edge_without_vertices(self, kc):
        assert kc.is_subcomplex({"e12"}) is False

    def test_full_triangle(self, kc):
        assert kc.is_subcomplex(
            {"v1", "v2", "v3", "e12", "e13", "e23", "f123"}
        ) is True

    def test_face_without_edges(self, kc):
        assert kc.is_subcomplex({"f123"}) is False

    def test_empty_set(self, kc):
        assert kc.is_subcomplex(set()) is True

    def test_whole_complex(self, kc):
        assert kc.is_subcomplex(ALL_ELEMENTS) is True

    def test_edges_without_all_vertices(self, kc):
        assert kc.is_subcomplex({"v1", "e12", "e13"}) is False

    def test_two_vertices(self, kc):
        assert kc.is_subcomplex({"v1", "v2"}) is True

    def test_all_vertices(self, kc):
        assert kc.is_subcomplex({"v1", "v2", "v3", "v4"}) is True


# ===========================================================================
# Filtration construction (append)
# ===========================================================================

class TestFiltrationAppend:

    def test_valid_filtration(self, kc):
        filt = Filtration(kc)
        filt.append({"v1"})
        filt.append({"v1", "v2", "e12"})
        filt.append({"v1", "v2", "v3", "e12", "e23", "e13", "f123"})
        assert len(filt) == 3

    def test_non_superset_raises(self, kc):
        filt = Filtration(kc)
        filt.append({"v1", "v2", "e12"})
        with pytest.raises(ValueError, match="monotone"):
            filt.append({"v3"})  # doesn't contain v1, v2, e12

    def test_non_subcomplex_raises(self, kc):
        filt = Filtration(kc)
        with pytest.raises(ValueError, match="subcomplex"):
            filt.append({"e12"})  # missing boundary vertices

    def test_single_step(self, kc):
        filt = Filtration(kc)
        filt.append({"v1"})
        assert len(filt) == 1

    def test_empty_first_step(self, kc):
        filt = Filtration(kc)
        filt.append(set())
        assert len(filt) == 1
        assert filt[0] == set()

    def test_chaining(self, kc):
        filt = Filtration(kc)
        result = filt.append({"v1"}).append({"v1", "v2", "e12"})
        assert result is filt
        assert len(filt) == 2


# ===========================================================================
# Filtration construction (append_closure)
# ===========================================================================

class TestFiltrationAppendClosure:

    def test_single_vertex(self, kc):
        filt = Filtration(kc)
        filt.append_closure({"v1"})
        assert filt[0] == {"v1"}

    def test_edge_auto_closes(self, kc):
        filt = Filtration(kc)
        filt.append_closure({"v1"})
        filt.append_closure({"e12"})
        # closure(e12) = {v1, v2, e12}, union with {v1} = {v1, v2, e12}
        assert filt[1] == {"v1", "v2", "e12"}

    def test_star_closure(self, kc):
        filt = Filtration(kc)
        filt.append_closure(kc.star("v1"))
        # star(v1) includes v1, e12, e13, f123
        # closure of that adds v2, v3, e23
        step = filt[0]
        assert "v1" in step
        assert "f123" in step
        assert "v2" in step  # from closure
        assert "e23" in step  # from closure of f123

    def test_builds_valid_filtration(self, kc):
        filt = Filtration(kc)
        filt.append_closure({"v1"})
        filt.append_closure({"e12"})
        filt.append_closure({"f123"})
        filt.append_closure({"f234"})
        # Each step should be a valid subcomplex
        for i in range(len(filt)):
            assert kc.is_subcomplex(filt[i])
        # Monotone
        for i in range(1, len(filt)):
            assert filt[i - 1] <= filt[i]

    def test_chaining(self, kc):
        filt = Filtration(kc)
        result = filt.append_closure({"v1"}).append_closure({"e12"})
        assert result is filt


# ===========================================================================
# Filtration construction (from_function)
# ===========================================================================

class TestFiltrationFromFunction:

    def test_monotone_function(self, kc):
        # Assign vertices=0, edges=1, faces=2
        def by_dimension(elem_id):
            if elem_id.startswith("v"):
                return 0
            elif elem_id.startswith("e"):
                return 1
            else:
                return 2

        filt = Filtration.from_function(kc, by_dimension)
        assert len(filt) == 3

    def test_each_step_is_subcomplex(self, kc):
        def by_dimension(elem_id):
            if elem_id.startswith("v"):
                return 0
            elif elem_id.startswith("e"):
                return 1
            else:
                return 2

        filt = Filtration.from_function(kc, by_dimension)
        for i in range(len(filt)):
            assert kc.is_subcomplex(filt[i])

    def test_all_elements_in_final_step(self, kc):
        def by_dimension(elem_id):
            if elem_id.startswith("v"):
                return 0
            elif elem_id.startswith("e"):
                return 1
            else:
                return 2

        filt = Filtration.from_function(kc, by_dimension)
        assert filt[-1] == ALL_ELEMENTS

    def test_distinct_values_count(self, kc):
        # All elements get the same value → 1 step
        filt = Filtration.from_function(kc, lambda _: 0)
        assert len(filt) == 1

    def test_monotone_nesting(self, kc):
        def by_dimension(elem_id):
            if elem_id.startswith("v"):
                return 0
            elif elem_id.startswith("e"):
                return 1
            else:
                return 2

        filt = Filtration.from_function(kc, by_dimension)
        for i in range(1, len(filt)):
            assert filt[i - 1] <= filt[i]


# ===========================================================================
# Indexing and iteration
# ===========================================================================

class TestIndexingIteration:

    def _build_filt(self, kc):
        filt = Filtration(kc)
        filt.append({"v1"})
        filt.append({"v1", "v2", "e12"})
        filt.append({"v1", "v2", "v3", "e12", "e23", "e13", "f123"})
        return filt

    def test_getitem_first(self, kc):
        filt = self._build_filt(kc)
        assert filt[0] == {"v1"}

    def test_getitem_last(self, kc):
        filt = self._build_filt(kc)
        assert filt[-1] == {"v1", "v2", "v3", "e12", "e23", "e13", "f123"}

    def test_len(self, kc):
        filt = self._build_filt(kc)
        assert len(filt) == 3

    def test_iteration(self, kc):
        filt = self._build_filt(kc)
        steps = list(filt)
        assert len(steps) == 3
        assert steps[0] == {"v1"}

    def test_out_of_bounds_raises(self, kc):
        filt = self._build_filt(kc)
        with pytest.raises(IndexError):
            filt[10]

    def test_empty_filtration_len(self, kc):
        filt = Filtration(kc)
        assert len(filt) == 0


# ===========================================================================
# Query methods
# ===========================================================================

class TestQueryMethods:

    def _build_filt(self, kc):
        filt = Filtration(kc)
        filt.append({"v1"})
        filt.append({"v1", "v2", "e12"})
        filt.append({"v1", "v2", "v3", "e12", "e23", "e13", "f123"})
        return filt

    def test_birth(self, kc):
        filt = self._build_filt(kc)
        assert filt.birth("v1") == 0
        assert filt.birth("v2") == 1
        assert filt.birth("e12") == 1
        assert filt.birth("f123") == 2

    def test_birth_nonexistent_raises(self, kc):
        filt = self._build_filt(kc)
        with pytest.raises(ValueError):
            filt.birth("nonexistent")

    def test_new_at_first(self, kc):
        filt = self._build_filt(kc)
        assert filt.new_at(0) == {"v1"}

    def test_new_at_middle(self, kc):
        filt = self._build_filt(kc)
        assert filt.new_at(1) == {"v2", "e12"}

    def test_new_at_last(self, kc):
        filt = self._build_filt(kc)
        assert filt.new_at(2) == {"v3", "e23", "e13", "f123"}

    def test_elements_at(self, kc):
        filt = self._build_filt(kc)
        assert filt.elements_at(1) == {"v1", "v2", "e12"}

    def test_is_complete_false(self, kc):
        filt = self._build_filt(kc)
        assert filt.is_complete is False

    def test_is_complete_true(self, kc):
        filt = Filtration(kc)
        filt.append(ALL_ELEMENTS)
        assert filt.is_complete is True

    def test_complex_reference(self, kc):
        filt = Filtration(kc)
        assert filt.complex is kc

    def test_length_property(self, kc):
        filt = self._build_filt(kc)
        assert filt.length == 3


# ===========================================================================
# Composability with topological queries
# ===========================================================================

class TestComposability:

    def test_skeleton_filtration(self, kc):
        """Build filtration from skeleton: sk₀, sk₁, sk₂."""
        filt = Filtration(kc)
        filt.append(kc.skeleton(0))
        filt.append(kc.skeleton(1))
        filt.append(kc.skeleton(2))
        assert len(filt) == 3
        assert filt[0] == {"v1", "v2", "v3", "v4"}
        assert filt[-1] == ALL_ELEMENTS

    def test_star_expansion(self, kc):
        """Build filtration by expanding from a vertex using closures."""
        filt = Filtration(kc)
        filt.append_closure({"v1"})
        filt.append_closure(kc.star("v1"))
        filt.append_closure(kc.star("v2"))
        for i in range(len(filt)):
            assert kc.is_subcomplex(filt[i])

    def test_closure_driven(self, kc):
        """Build filtration using closure of growing element sets."""
        filt = Filtration(kc)
        filt.append_closure({"v1"})
        filt.append_closure({"v2"})
        filt.append_closure({"e12"})
        # After 3 steps, should have at least {v1, v2, e12}
        assert {"v1", "v2", "e12"} <= filt[-1]
