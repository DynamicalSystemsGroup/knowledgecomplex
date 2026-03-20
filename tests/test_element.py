"""
tests/test_element.py

Tests for Element handles (kc.element()) and element listing
(kc.element_ids(), kc.elements()).

Uses the QA domain schema with inheritance.
"""

import pytest

from knowledgecomplex.schema import SchemaBuilder, vocab, text
from knowledgecomplex.graph import KnowledgeComplex, Element
from knowledgecomplex.exceptions import SchemaError


@pytest.fixture
def qa_kc() -> KnowledgeComplex:
    """QA domain with a few elements added."""
    sb = SchemaBuilder(namespace="qa")
    sb.add_vertex_type("document", attributes={"title": text()})
    sb.add_vertex_type("specification", parent="document", attributes={"format": text()})
    sb.add_vertex_type("guidance", parent="document", attributes={"criteria": text()})
    sb.add_edge_type("typing", attributes={"scope": text()})
    sb.add_edge_type("verification", attributes={"status": vocab("pass", "fail", "pending")})
    sb.add_edge_type("validation", attributes={"status": vocab("pass", "fail", "pending")})
    sb.add_face_type("assurance")

    kc = KnowledgeComplex(schema=sb)
    kc.add_vertex("spec-001", type="specification", title="Spec A", format="PDF")
    kc.add_vertex("guid-001", type="guidance", title="Guide A", criteria="Accuracy")
    kc.add_vertex("doc-001", type="document", title="Doc A")
    kc.add_edge("typ-001", type="typing",
                vertices={"spec-001", "guid-001"}, scope="type A")
    kc.add_edge("ver-001", type="verification",
                vertices={"doc-001", "spec-001"}, status="pass")
    kc.add_edge("val-001", type="validation",
                vertices={"doc-001", "guid-001"}, status="pass")
    kc.add_face("assur-001", type="assurance",
                boundary=["typ-001", "ver-001", "val-001"])
    return kc


@pytest.fixture
def qa_kc_with_uri() -> KnowledgeComplex:
    """QA domain with a vertex that has a URI."""
    sb = SchemaBuilder(namespace="qa")
    sb.add_vertex_type("document", attributes={"title": text()})
    sb.add_vertex_type("specification", parent="document", attributes={"format": text()})

    kc = KnowledgeComplex(schema=sb)
    kc.add_vertex("spec-001", type="specification", title="Spec A", format="PDF",
                  uri="file:///docs/spec-001.md")
    kc.add_vertex("doc-001", type="document", title="Doc A")
    return kc


@pytest.fixture
def empty_kc() -> KnowledgeComplex:
    """Empty KC with schema but no elements."""
    sb = SchemaBuilder(namespace="qa")
    sb.add_vertex_type("document", attributes={"title": text()})
    return KnowledgeComplex(schema=sb)


# ===========================================================================
# Element handle tests
# ===========================================================================

class TestElementHandle:

    def test_element_id(self, qa_kc):
        elem = qa_kc.element("spec-001")
        assert elem.id == "spec-001"

    def test_element_type(self, qa_kc):
        elem = qa_kc.element("spec-001")
        assert elem.type == "specification"

    def test_element_type_parent(self, qa_kc):
        elem = qa_kc.element("doc-001")
        assert elem.type == "document"

    def test_element_uri_present(self, qa_kc_with_uri):
        elem = qa_kc_with_uri.element("spec-001")
        assert elem.uri == "file:///docs/spec-001.md"

    def test_element_uri_absent(self, qa_kc):
        elem = qa_kc.element("spec-001")
        assert elem.uri is None

    def test_element_attrs(self, qa_kc):
        elem = qa_kc.element("spec-001")
        attrs = elem.attrs
        assert attrs["title"] == "Spec A"
        assert attrs["format"] == "PDF"

    def test_element_attrs_inherited(self, qa_kc):
        """Child element attrs include inherited attributes."""
        elem = qa_kc.element("spec-001")
        assert "title" in elem.attrs  # inherited from document

    def test_element_attrs_parent_only(self, qa_kc):
        """Parent element has only its own attrs."""
        elem = qa_kc.element("doc-001")
        assert "title" in elem.attrs
        assert "format" not in elem.attrs

    def test_element_nonexistent_raises(self, qa_kc):
        with pytest.raises(ValueError):
            qa_kc.element("nonexistent")

    def test_element_is_element_type(self, qa_kc):
        elem = qa_kc.element("spec-001")
        assert isinstance(elem, Element)

    def test_edge_element(self, qa_kc):
        elem = qa_kc.element("typ-001")
        assert elem.type == "typing"
        assert elem.attrs["scope"] == "type A"

    def test_face_element(self, qa_kc):
        elem = qa_kc.element("assur-001")
        assert elem.type == "assurance"


# ===========================================================================
# element_ids() tests
# ===========================================================================

class TestElementIds:

    def test_all_ids(self, qa_kc):
        ids = qa_kc.element_ids()
        assert "spec-001" in ids
        assert "guid-001" in ids
        assert "doc-001" in ids
        assert "typ-001" in ids
        assert "ver-001" in ids
        assert "val-001" in ids
        assert "assur-001" in ids
        assert len(ids) == 7

    def test_filter_by_type(self, qa_kc):
        ids = qa_kc.element_ids(type="specification")
        assert ids == ["spec-001"]

    def test_filter_by_parent_includes_children(self, qa_kc):
        """Filtering by 'document' includes specification and guidance."""
        ids = qa_kc.element_ids(type="document")
        assert "doc-001" in ids
        assert "spec-001" in ids
        assert "guid-001" in ids
        assert len(ids) == 3

    def test_filter_nonexistent_type_raises(self, qa_kc):
        with pytest.raises(SchemaError):
            qa_kc.element_ids(type="nonexistent")

    def test_empty_complex(self, empty_kc):
        assert empty_kc.element_ids() == []

    def test_filter_edge_type(self, qa_kc):
        ids = qa_kc.element_ids(type="typing")
        assert ids == ["typ-001"]

    def test_filter_face_type(self, qa_kc):
        ids = qa_kc.element_ids(type="assurance")
        assert ids == ["assur-001"]


# ===========================================================================
# elements() tests
# ===========================================================================

class TestElements:

    def test_all_elements(self, qa_kc):
        elems = qa_kc.elements()
        assert len(elems) == 7
        assert all(isinstance(e, Element) for e in elems)

    def test_filter_by_type(self, qa_kc):
        elems = qa_kc.elements(type="specification")
        assert len(elems) == 1
        assert elems[0].id == "spec-001"
        assert elems[0].type == "specification"

    def test_filter_by_parent_includes_children(self, qa_kc):
        elems = qa_kc.elements(type="document")
        ids = {e.id for e in elems}
        assert ids == {"doc-001", "spec-001", "guid-001"}

    def test_element_attrs_correct(self, qa_kc):
        elems = qa_kc.elements(type="guidance")
        assert len(elems) == 1
        assert elems[0].attrs["criteria"] == "Accuracy"
        assert elems[0].attrs["title"] == "Guide A"
