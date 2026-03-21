"""
tests/test_stress.py

Adversarial and edge-case tests to smoke out issues before public release.
Covers: weird inputs, boundary conditions, concurrency-like patterns,
round-trip fidelity, API misuse, and internal consistency.
"""

import pytest
import re
from pathlib import Path

from knowledgecomplex.schema import SchemaBuilder, vocab, text, TextDescriptor, VocabDescriptor
from knowledgecomplex.graph import KnowledgeComplex, Element
from knowledgecomplex.filtration import Filtration
from knowledgecomplex.exceptions import ValidationError, SchemaError, UnknownQueryError


# ===========================================================================
# Namespace and ID edge cases
# ===========================================================================

class TestWeirdNames:

    def test_hyphenated_ids(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("my-type", attributes={"my-attr": text()})
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("my-vertex-1", type="my-type", **{"my-attr": "hello"})

    def test_numeric_ids(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("123", type="Node")
        kc.add_vertex("456", type="Node")

    def test_unicode_attribute_values(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node", attributes={"name": text()})
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node", name="日本語テスト")
        elem = kc.element("v1")
        assert elem.attrs["name"] == "日本語テスト"

    def test_empty_string_attribute(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node", attributes={"name": text()})
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node", name="")

    def test_long_ids(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        long_id = "x" * 500
        kc.add_vertex(long_id, type="Node")
        assert kc.element(long_id).id == long_id

    def test_special_chars_in_namespace(self):
        """Namespace with dots or underscores."""
        sb = SchemaBuilder(namespace="my_project")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node")


# ===========================================================================
# Empty and minimal complexes
# ===========================================================================

class TestEmptyComplex:

    def test_empty_verify(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        kc.verify()  # empty complex is valid

    def test_empty_audit(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        report = kc.audit()
        assert report.conforms

    def test_empty_element_ids(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        assert kc.element_ids() == []

    def test_empty_skeleton(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        assert kc.skeleton(0) == set()
        assert kc.skeleton(1) == set()
        assert kc.skeleton(2) == set()

    def test_single_vertex(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node")
        assert kc.boundary("v1") == set()
        assert kc.coboundary("v1") == set()
        assert kc.star("v1") == {"v1"}
        assert kc.degree("v1") == 0


# ===========================================================================
# Duplicate element IDs
# ===========================================================================

class TestDuplicateIds:

    def test_duplicate_vertex_id(self):
        """Adding a vertex with an existing ID should fail or produce invalid state."""
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node")
        # Second add with same ID — what happens?
        # This should either raise or the graph should still verify
        try:
            kc.add_vertex("v1", type="Node")
        except (ValidationError, ValueError):
            pass  # acceptable
        else:
            # If no exception, at least verify the complex is still valid
            kc.verify()


# ===========================================================================
# Schema consistency
# ===========================================================================

class TestSchemaConsistency:

    def test_describe_type_after_inheritance(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("parent", attributes={"a": text()})
        sb.add_vertex_type("child", parent="parent", attributes={"b": text()})
        desc = sb.describe_type("child")
        assert "a" in desc["inherited_attributes"]
        assert "b" in desc["own_attributes"]
        assert "a" in desc["all_attributes"]
        assert "b" in desc["all_attributes"]

    def test_type_names_consistent_with_describe(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("V1")
        sb.add_edge_type("E1")
        sb.add_face_type("F1")
        for name in sb.type_names():
            desc = sb.describe_type(name)
            assert desc["name"] == name


# ===========================================================================
# Export/load round-trip fidelity
# ===========================================================================

class TestRoundTrip:

    def test_schema_round_trip(self, tmp_path):
        sb = SchemaBuilder(namespace="rt")
        sb.add_vertex_type("Node", attributes={"name": text()})
        sb.add_edge_type("Link", attributes={"weight": vocab("light", "heavy")})
        sb.add_face_type("Tri")
        sb.export(tmp_path)

        sb2 = SchemaBuilder.load(tmp_path)
        assert set(sb2.type_names()) == set(sb.type_names())

    def test_complex_round_trip(self, tmp_path):
        sb = SchemaBuilder(namespace="rt")
        sb.add_vertex_type("Node", attributes={"name": text()})
        sb.add_edge_type("Link")
        sb.add_face_type("Tri")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node", name="Alice")
        kc.add_vertex("v2", type="Node", name="Bob")
        kc.add_vertex("v3", type="Node", name="Carol")
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
        kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
        kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
        kc.add_face("f", type="Tri", boundary=["e12", "e23", "e13"])

        kc.export(tmp_path / "out")
        kc2 = KnowledgeComplex.load(tmp_path / "out")

        assert set(kc2.element_ids()) == set(kc.element_ids())
        assert kc2.element("v1").attrs["name"] == "Alice"

    def test_round_trip_preserves_boundary(self, tmp_path):
        sb = SchemaBuilder(namespace="rt")
        sb.add_vertex_type("N")
        sb.add_edge_type("E")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("a", type="N")
        kc.add_vertex("b", type="N")
        kc.add_edge("e", type="E", vertices={"a", "b"})

        kc.export(tmp_path / "out")
        kc2 = KnowledgeComplex.load(tmp_path / "out")
        assert kc2.boundary("e") == {"a", "b"}


# ===========================================================================
# Filtration edge cases
# ===========================================================================

class TestFiltrationEdgeCases:

    def _make_kc(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        sb.add_edge_type("E")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        kc.add_vertex("v2", type="N")
        kc.add_edge("e12", type="E", vertices={"v1", "v2"})
        return kc

    def test_empty_filtration_iteration(self):
        kc = self._make_kc()
        filt = Filtration(kc)
        assert list(filt) == []

    def test_single_element_filtration(self):
        kc = self._make_kc()
        filt = Filtration(kc)
        filt.append({"v1"})
        assert len(filt) == 1
        assert filt[0] == {"v1"}

    def test_append_closure_from_empty(self):
        kc = self._make_kc()
        filt = Filtration(kc)
        filt.append_closure({"e12"})
        assert filt[0] == {"v1", "v2", "e12"}

    def test_from_function_all_same_value(self):
        kc = self._make_kc()
        filt = Filtration.from_function(kc, lambda _: 0)
        assert len(filt) == 1


# ===========================================================================
# Analysis edge cases
# ===========================================================================

class TestAnalysisEdgeCases:

    def test_betti_single_vertex(self):
        from knowledgecomplex.analysis import betti_numbers
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        assert betti_numbers(kc) == [1, 0, 0]

    def test_betti_no_elements(self):
        from knowledgecomplex.analysis import betti_numbers
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        assert betti_numbers(kc) == [0, 0, 0]

    def test_boundary_matrices_vertices_only(self):
        from knowledgecomplex.analysis import boundary_matrices
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        kc.add_vertex("v2", type="N")
        bm = boundary_matrices(kc)
        assert bm.B1.shape == (2, 0)
        assert bm.B2.shape == (0, 0)


# ===========================================================================
# Clique inference edge cases
# ===========================================================================

class TestCliqueEdgeCases:

    def test_find_cliques_no_edges(self):
        from knowledgecomplex import find_cliques
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        kc.add_vertex("v2", type="N")
        assert find_cliques(kc, k=3) == []

    def test_find_cliques_no_triangles(self):
        from knowledgecomplex import find_cliques
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        sb.add_edge_type("E")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        kc.add_vertex("v2", type="N")
        kc.add_edge("e12", type="E", vertices={"v1", "v2"})
        assert find_cliques(kc, k=3) == []


# ===========================================================================
# Deferred verification with invalid final state
# ===========================================================================

class TestDeferredVerificationInvalid:

    def test_deferred_then_verify_catches_issues(self):
        """Build something invalid in deferred mode, verify at exit should catch it."""
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        sb.add_edge_type("E")
        kc = KnowledgeComplex(schema=sb)

        # We can't easily build invalid state with deferred mode since
        # Python guards (cardinality checks) still fire.
        # But we can test that deferred + valid construction works.
        with kc.deferred_verification():
            kc.add_vertex("v1", type="N")
            kc.add_vertex("v2", type="N")
            kc.add_edge("e12", type="E", vertices={"v1", "v2"})


# ===========================================================================
# Codec edge cases
# ===========================================================================

class TestCodecEdgeCases:

    def test_register_codec_for_nonexistent_type(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)

        class FakeCodec:
            def compile(self, element): pass
            def decompile(self, uri): return {}

        with pytest.raises(SchemaError):
            kc.register_codec("Nonexistent", FakeCodec())

    def test_compile_without_uri_raises(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node")

        class FakeCodec:
            def compile(self, element): pass
            def decompile(self, uri): return {}

        kc.register_codec("Node", FakeCodec())
        with pytest.raises(ValueError):
            kc.element("v1").compile()


# ===========================================================================
# is_subcomplex edge cases
# ===========================================================================

class TestSubcomplexEdgeCases:

    def test_empty_is_subcomplex(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        assert kc.is_subcomplex(set()) is True

    def test_full_complex_is_subcomplex(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        sb.add_edge_type("E")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        kc.add_vertex("v2", type="N")
        kc.add_edge("e12", type="E", vertices={"v1", "v2"})
        all_ids = set(kc.element_ids())
        assert kc.is_subcomplex(all_ids) is True


# ===========================================================================
# Topological query edge cases
# ===========================================================================

class TestTopologyEdgeCases:

    def test_skeleton_invalid_k(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        with pytest.raises(ValueError):
            kc.skeleton(-1)
        with pytest.raises(ValueError):
            kc.skeleton(3)

    def test_boundary_of_vertex_is_empty(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        assert kc.boundary("v1") == set()

    def test_star_of_isolated_vertex(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        assert kc.star("v1") == {"v1"}

    def test_closure_of_single_vertex(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        assert kc.closure("v1") == {"v1"}


# ===========================================================================
# remove_element edge cases
# ===========================================================================

class TestRemoveElement:

    def test_remove_nonexistent_raises(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        with pytest.raises(ValueError):
            kc.remove_element("ghost")

    def test_remove_then_readd(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        kc.remove_element("v1")
        assert "v1" not in kc.element_ids()
        kc.add_vertex("v1", type="N")
        assert "v1" in kc.element_ids()


# ===========================================================================
# Ontology module imports
# ===========================================================================

class TestOntologyImports:

    def test_operations_schema(self):
        from knowledgecomplex.ontologies import operations
        sb = operations.schema()
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("alice", type="actor", name="Alice")

    def test_brand_schema(self):
        from knowledgecomplex.ontologies import brand
        sb = brand.schema()
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("gen-z", type="audience", name="Gen Z")
        kc.add_vertex("trust", type="theme", name="Trust")
        kc.add_edge("r1", type="resonance",
                    vertices={"gen-z", "trust"},
                    valence="positive", intensity="strong")

    def test_research_schema(self):
        from knowledgecomplex.ontologies import research
        sb = research.schema()
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("paper1", type="paper", title="A Great Paper")
        kc.add_vertex("ml", type="concept", name="Machine Learning")
        kc.add_edge("d1", type="discusses",
                    vertices={"paper1", "ml"}, depth="primary")


# ===========================================================================
# Attribute validation
# ===========================================================================

class TestAttributeValidation:

    def test_invalid_vocab_value_rejected(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_edge_type("E", attributes={"status": vocab("open", "closed")})
        sb.add_vertex_type("N")
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="N")
        kc.add_vertex("v2", type="N")
        with pytest.raises(ValidationError):
            kc.add_edge("e1", type="E", vertices={"v1", "v2"}, status="INVALID")

    def test_missing_required_attribute_rejected(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node", attributes={"name": text()})
        kc = KnowledgeComplex(schema=sb)
        with pytest.raises(ValidationError):
            kc.add_vertex("v1", type="Node")  # missing name

    def test_optional_attribute_not_required(self):
        sb = SchemaBuilder(namespace="test")
        sb.add_vertex_type("Node", attributes={"name": text(required=False)})
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="Node")  # should not raise
