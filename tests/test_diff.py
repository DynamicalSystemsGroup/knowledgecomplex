"""
tests/test_diff.py

Tests for knowledgecomplex.diff — ComplexDiff and ComplexSequence.
"""

import pytest

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.diff import ComplexDiff, ComplexSequence
from knowledgecomplex.exceptions import ValidationError


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="df")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link")
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def base_kc(schema) -> KnowledgeComplex:
    """Triangle: v1-v2-v3, edges e12/e23/e13, face f123."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
    return kc


# --- ComplexDiff.apply ---


class TestComplexDiffApply:
    def test_add_vertex(self, schema):
        kc = KnowledgeComplex(schema=schema)
        diff = ComplexDiff().add_vertex("v1", type="Node")
        diff.apply(kc)
        assert "v1" in kc.element_ids()

    def test_add_edge(self, schema):
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")
        diff = ComplexDiff().add_edge("e12", type="Link", vertices={"v1", "v2"})
        diff.apply(kc)
        assert "e12" in kc.element_ids()

    def test_remove_element(self, base_kc):
        # Remove face first, then can remove edges
        diff = ComplexDiff().remove("f123")
        diff.apply(base_kc)
        assert "f123" not in base_kc.element_ids()
        assert "e12" in base_kc.element_ids()  # edges still there

    def test_remove_orders_by_dimension(self, base_kc):
        """Removing face + edge in one diff: face removed first (higher dim)."""
        diff = ComplexDiff().remove("e12").remove("f123")
        diff.apply(base_kc)
        assert "f123" not in base_kc.element_ids()
        assert "e12" not in base_kc.element_ids()

    def test_add_and_remove(self, base_kc):
        diff = (
            ComplexDiff()
            .remove("f123")
            .add_vertex("v4", type="Node")
        )
        diff.apply(base_kc)
        assert "f123" not in base_kc.element_ids()
        assert "v4" in base_kc.element_ids()

    def test_chaining(self):
        diff = (
            ComplexDiff()
            .add_vertex("a", type="Node")
            .add_vertex("b", type="Node")
            .remove("c")
        )
        assert len(diff.additions) == 2
        assert len(diff.removals) == 1


# --- remove_element on KnowledgeComplex ---


class TestRemoveElement:
    def test_remove_vertex(self, schema):
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("v1", type="Node")
        kc.remove_element("v1")
        assert "v1" not in kc.element_ids()

    def test_remove_nonexistent_raises(self, schema):
        kc = KnowledgeComplex(schema=schema)
        with pytest.raises(ValueError, match="No element"):
            kc.remove_element("nope")

    def test_remove_face_preserves_edges(self, base_kc):
        base_kc.remove_element("f123")
        assert "e12" in base_kc.element_ids()
        assert "e23" in base_kc.element_ids()


# --- ComplexDiff.to_sparql ---


class TestToSparql:
    def test_insert_only(self, schema):
        kc = KnowledgeComplex(schema=schema)
        diff = ComplexDiff().add_vertex("v1", type="Node")
        sparql = diff.to_sparql(kc)
        assert "INSERT DATA" in sparql
        assert "DELETE DATA" not in sparql
        assert "df#v1" in sparql

    def test_delete_only(self, base_kc):
        diff = ComplexDiff().remove("f123")
        sparql = diff.to_sparql(base_kc)
        assert "DELETE DATA" in sparql
        assert "df#f123" in sparql

    def test_both_insert_and_delete(self, base_kc):
        diff = ComplexDiff().remove("f123").add_vertex("v4", type="Node")
        sparql = diff.to_sparql(base_kc)
        assert "DELETE DATA" in sparql
        assert "INSERT DATA" in sparql


# --- ComplexDiff.from_sparql round-trip ---


class TestFromSparql:
    def test_roundtrip_additions(self, schema):
        kc = KnowledgeComplex(schema=schema)
        original = (
            ComplexDiff()
            .add_vertex("v1", type="Node")
            .add_vertex("v2", type="Node")
        )
        sparql = original.to_sparql(kc)
        restored = ComplexDiff.from_sparql(sparql, kc)
        assert len(restored.additions) == len(original.additions)

    def test_roundtrip_removals(self, base_kc):
        original = ComplexDiff().remove("f123")
        sparql = original.to_sparql(base_kc)
        restored = ComplexDiff.from_sparql(sparql, base_kc)
        assert len(restored.removals) >= 1
        # f123 should appear in removals
        assert "f123" in restored.removals

    def test_roundtrip_apply_equivalence(self, schema):
        """Applying original and roundtripped diff produces same result."""
        kc1 = KnowledgeComplex(schema=schema)
        kc2 = KnowledgeComplex(schema=schema)

        diff = (
            ComplexDiff()
            .add_vertex("a", type="Node")
            .add_vertex("b", type="Node")
            .add_edge("ab", type="Link", vertices={"a", "b"})
        )

        # Apply original
        diff.apply(kc1)

        # Roundtrip through SPARQL
        sparql = diff.to_sparql(kc2)
        restored = ComplexDiff.from_sparql(sparql, kc2)
        restored.apply(kc2)

        assert set(kc1.element_ids()) == set(kc2.element_ids())


# --- query() substitution fix ---


class TestQuerySubstitution:
    def test_query_substitutes_placeholders(self, base_kc):
        """query() now performs {placeholder} substitution."""
        # The coboundary template uses {simplex}
        iri = f"<{base_kc._schema._base_iri}v1>"
        df = base_kc.query("coboundary", simplex=iri)
        assert len(df) > 0  # v1 has coboundary edges

    def test_query_ids_returns_set(self, base_kc):
        """query_ids() returns set[str] of element IDs."""
        iri = f"<{base_kc._schema._base_iri}v1>"
        ids = base_kc.query_ids("coboundary", simplex=iri)
        assert isinstance(ids, set)
        assert len(ids) > 0
        # Should contain edges incident to v1
        for eid in ids:
            assert isinstance(eid, str)


# --- ComplexSequence ---


class TestComplexSequence:
    def test_basic_sequence(self, schema):
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")

        d1 = ComplexDiff().add_vertex("v3", type="Node")
        d2 = ComplexDiff().add_edge("e12", type="Link", vertices={"v1", "v2"})

        seq = ComplexSequence(kc, [d1, d2])
        assert len(seq) == 2
        assert "v3" in seq[0]
        assert "e12" in seq[1]

    def test_new_at(self, schema):
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("v1", type="Node")

        d1 = ComplexDiff().add_vertex("v2", type="Node")
        d2 = ComplexDiff().add_vertex("v3", type="Node")

        seq = ComplexSequence(kc, [d1, d2])
        assert seq.new_at(0) == {"v2"}
        assert seq.new_at(1) == {"v3"}

    def test_removed_at(self, schema):
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("v1", type="Node")
        kc.add_vertex("v2", type="Node")

        d1 = ComplexDiff().remove("v2")
        seq = ComplexSequence(kc, [d1])
        assert seq.removed_at(0) == {"v2"}

    def test_iteration(self, schema):
        kc = KnowledgeComplex(schema=schema)
        kc.add_vertex("v1", type="Node")

        d1 = ComplexDiff().add_vertex("v2", type="Node")
        d2 = ComplexDiff().add_vertex("v3", type="Node")

        seq = ComplexSequence(kc, [d1, d2])
        steps = list(seq)
        assert len(steps) == 2
        assert "v2" in steps[0]
        assert "v3" in steps[1]

    def test_repr(self, schema):
        kc = KnowledgeComplex(schema=schema)
        seq = ComplexSequence(kc, [ComplexDiff(), ComplexDiff()])
        assert "2 steps" in repr(seq)
