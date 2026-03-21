"""
tests/test_inheritance.py

Tests for user-defined type inheritance, attribute binding, and schema introspection.
Uses a quality-assurance domain as the primary fixture.

All tests call the public API only — no rdflib imports except in tests that
inspect the OWL/SHACL graph output.
"""

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDFS

from knowledgecomplex.schema import SchemaBuilder, vocab, text
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.exceptions import SchemaError, ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def qa_schema() -> SchemaBuilder:
    """QA domain schema with document → specification/guidance inheritance."""
    sb = SchemaBuilder(namespace="qa")
    sb.add_vertex_type("document", attributes={"title": text(), "category": text()})
    sb.add_vertex_type("specification", parent="document",
                       attributes={"format": text()},
                       bind={"category": "structural"})
    sb.add_vertex_type("guidance", parent="document",
                       attributes={"criteria": text()},
                       bind={"category": "quality"})
    sb.add_edge_type("typing",       attributes={"scope": text()})
    sb.add_edge_type("verification", attributes={"status": vocab("pass", "fail", "pending")})
    sb.add_edge_type("validation",   attributes={"status": vocab("pass", "fail", "pending")})
    sb.add_face_type("assurance")
    return sb


@pytest.fixture
def qa_schema_no_bind() -> SchemaBuilder:
    """QA domain schema without bind — for testing inheritance without binding."""
    sb = SchemaBuilder(namespace="qa")
    sb.add_vertex_type("document", attributes={"title": text()})
    sb.add_vertex_type("specification", parent="document", attributes={"format": text()})
    sb.add_vertex_type("guidance", parent="document", attributes={"criteria": text()})
    sb.add_edge_type("typing",       attributes={"scope": text()})
    sb.add_edge_type("verification", attributes={"status": vocab("pass", "fail", "pending")})
    sb.add_edge_type("validation",   attributes={"status": vocab("pass", "fail", "pending")})
    sb.add_face_type("assurance")
    return sb


@pytest.fixture
def deep_schema() -> SchemaBuilder:
    """Three-deep inheritance chain for multi-level tests."""
    sb = SchemaBuilder(namespace="deep")
    sb.add_vertex_type("document", attributes={"title": text()})
    sb.add_vertex_type("specification", parent="document",
                       attributes={"format": text()},
                       bind={"title": "Untitled Spec"})
    sb.add_vertex_type("detailed_specification", parent="specification",
                       attributes={"section": text()})
    return sb


# ===========================================================================
# Schema-level tests (OWL/SHACL graph correctness)
# ===========================================================================

class TestSchemaOWL:

    def test_child_subclass_of_parent(self, qa_schema):
        """specification rdfs:subClassOf document in OWL graph."""
        g = Graph()
        g.parse(data=qa_schema.dump_owl(), format="turtle")
        spec = URIRef("https://example.org/qa#specification")
        doc = URIRef("https://example.org/qa#document")
        assert (spec, RDFS.subClassOf, doc) in g

    def test_parent_subclass_of_kc_vertex(self, qa_schema):
        """document rdfs:subClassOf KC:Vertex in OWL graph."""
        g = Graph()
        g.parse(data=qa_schema.dump_owl(), format="turtle")
        doc = URIRef("https://example.org/qa#document")
        kc_vertex = URIRef("https://w3id.org/kc#Vertex")
        assert (doc, RDFS.subClassOf, kc_vertex) in g

    def test_child_not_direct_subclass_of_kc_vertex(self, qa_schema):
        """specification does NOT have direct rdfs:subClassOf KC:Vertex."""
        g = Graph()
        g.parse(data=qa_schema.dump_owl(), format="turtle")
        spec = URIRef("https://example.org/qa#specification")
        kc_vertex = URIRef("https://w3id.org/kc#Vertex")
        assert (spec, RDFS.subClassOf, kc_vertex) not in g

    def test_guidance_subclass_of_document(self, qa_schema):
        """guidance rdfs:subClassOf document in OWL graph."""
        g = Graph()
        g.parse(data=qa_schema.dump_owl(), format="turtle")
        guidance = URIRef("https://example.org/qa#guidance")
        doc = URIRef("https://example.org/qa#document")
        assert (guidance, RDFS.subClassOf, doc) in g

    def test_child_shape_targets_child(self, qa_schema):
        """Child SHACL shape has sh:targetClass pointing to child IRI."""
        ttl = qa_schema.dump_shacl()
        assert "specificationShape" in ttl
        assert "qa:specification" in ttl or "qa#specification" in ttl

    def test_parent_shape_targets_parent(self, qa_schema):
        """Parent SHACL shape has sh:targetClass pointing to parent IRI."""
        ttl = qa_schema.dump_shacl()
        assert "documentShape" in ttl
        assert "qa:document" in ttl or "qa#document" in ttl

    def test_both_shapes_exist(self, qa_schema):
        """Both parent and child shapes exist in SHACL graph."""
        ttl = qa_schema.dump_shacl()
        assert "documentShape" in ttl
        assert "specificationShape" in ttl
        assert "guidanceShape" in ttl


# ===========================================================================
# Schema error tests (bad add_*_type calls)
# ===========================================================================

class TestSchemaErrors:

    def test_parent_nonexistent_raises(self):
        sb = SchemaBuilder(namespace="err")
        with pytest.raises(SchemaError):
            sb.add_vertex_type("child", parent="nonexistent")

    def test_vertex_parent_is_edge_type_raises(self):
        sb = SchemaBuilder(namespace="err")
        sb.add_edge_type("my_edge")
        with pytest.raises(SchemaError):
            sb.add_vertex_type("child", parent="my_edge")

    def test_edge_parent_is_vertex_type_raises(self):
        sb = SchemaBuilder(namespace="err")
        sb.add_vertex_type("my_vertex")
        with pytest.raises(SchemaError):
            sb.add_edge_type("child", parent="my_vertex")

    def test_face_parent_is_vertex_type_raises(self):
        sb = SchemaBuilder(namespace="err")
        sb.add_vertex_type("my_vertex")
        with pytest.raises(SchemaError):
            sb.add_face_type("child", parent="my_vertex")

    def test_duplicate_type_name_raises(self):
        sb = SchemaBuilder(namespace="err")
        sb.add_vertex_type("thing")
        with pytest.raises(SchemaError):
            sb.add_vertex_type("thing")


# ===========================================================================
# Instance success tests (valid constructions)
# ===========================================================================

class TestInstanceSuccess:

    def test_child_vertex_with_inherited_and_own_attrs(self, qa_schema_no_bind):
        """specification vertex with both title (inherited) and format (own) passes."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("spec-001", type="specification", title="My Spec", format="PDF")

    def test_guidance_vertex_with_inherited_and_own_attrs(self, qa_schema_no_bind):
        """guidance vertex with both title (inherited) and criteria (own) passes."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("g-001", type="guidance", title="My Guide", criteria="Accuracy")

    def test_parent_vertex_with_own_attrs(self, qa_schema_no_bind):
        """Plain document vertex with just title passes."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("doc-001", type="document", title="Plain Doc")

    def test_full_qa_triangle(self, qa_schema_no_bind):
        """Build a complete assurance triangle with spec, guidance, edges, face."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("spec-001", type="specification", title="Spec A", format="PDF")
        kc.add_vertex("guid-001", type="guidance", title="Guide A", criteria="Accuracy")
        kc.add_vertex("doc-001", type="document", title="Doc A")

        kc.add_edge("typ-001", type="typing",
                    vertices={"spec-001", "guid-001"}, scope="document type")
        kc.add_edge("ver-001", type="verification",
                    vertices={"doc-001", "spec-001"}, status="pass")
        kc.add_edge("val-001", type="validation",
                    vertices={"doc-001", "guid-001"}, status="pass")

        kc.add_face("assur-001", type="assurance",
                    boundary=["typ-001", "ver-001", "val-001"])

    def test_multiple_triangles_sharing_vertices(self, qa_schema_no_bind):
        """Build two assurance triangles that share vertices."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("spec-001", type="specification", title="Spec A", format="PDF")
        kc.add_vertex("guid-001", type="guidance", title="Guide A", criteria="Accuracy")
        kc.add_vertex("doc-001", type="document", title="Doc A")
        kc.add_vertex("doc-002", type="document", title="Doc B")

        # Triangle 1
        kc.add_edge("typ-001", type="typing",
                    vertices={"spec-001", "guid-001"}, scope="type A")
        kc.add_edge("ver-001", type="verification",
                    vertices={"doc-001", "spec-001"}, status="pass")
        kc.add_edge("val-001", type="validation",
                    vertices={"doc-001", "guid-001"}, status="pass")
        kc.add_face("assur-001", type="assurance",
                    boundary=["typ-001", "ver-001", "val-001"])

        # Triangle 2 shares spec-001 and guid-001
        kc.add_edge("ver-002", type="verification",
                    vertices={"doc-002", "spec-001"}, status="pending")
        kc.add_edge("val-002", type="validation",
                    vertices={"doc-002", "guid-001"}, status="pending")
        kc.add_face("assur-002", type="assurance",
                    boundary=["typ-001", "ver-002", "val-002"])

    def test_child_vertex_in_edge_with_parent_vertex(self, qa_schema_no_bind):
        """Child vertex works in edges alongside parent vertices."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("spec-001", type="specification", title="Spec", format="PDF")
        kc.add_vertex("doc-001", type="document", title="Doc")
        kc.add_edge("ver-001", type="verification",
                    vertices={"doc-001", "spec-001"}, status="pass")


# ===========================================================================
# Instance failure tests (validation rejections)
# ===========================================================================

class TestInstanceFailure:

    def test_child_missing_inherited_attr_fails(self, qa_schema_no_bind):
        """specification vertex missing inherited title fails validation."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        with pytest.raises(ValidationError):
            kc.add_vertex("spec-001", type="specification", format="PDF")

    def test_child_missing_own_attr_fails(self, qa_schema_no_bind):
        """specification vertex missing own format fails validation."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        with pytest.raises(ValidationError):
            kc.add_vertex("spec-001", type="specification", title="My Spec")

    def test_guidance_missing_inherited_attr_fails(self, qa_schema_no_bind):
        """guidance vertex missing inherited title fails validation."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        with pytest.raises(ValidationError):
            kc.add_vertex("g-001", type="guidance", criteria="Accuracy")

    def test_invalid_vocab_on_edge_fails(self, qa_schema_no_bind):
        """Edge with invalid vocab value fails validation."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("spec-001", type="specification", title="Spec", format="PDF")
        kc.add_vertex("doc-001", type="document", title="Doc")
        with pytest.raises(ValidationError):
            kc.add_edge("ver-001", type="verification",
                        vertices={"doc-001", "spec-001"}, status="INVALID")

    def test_edge_missing_boundary_vertex_fails(self, qa_schema_no_bind):
        """Edge referencing a vertex not in the complex fails."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        with pytest.raises(ValidationError):
            kc.add_edge("ver-001", type="verification",
                        vertices={"ghost-001", "ghost-002"}, status="pass")

    def test_open_triangle_face_fails(self, qa_schema_no_bind):
        """Face with edges that don't form a closed triangle fails."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        kc.add_vertex("v1", type="document", title="A")
        kc.add_vertex("v2", type="specification", title="B", format="PDF")
        kc.add_vertex("v3", type="guidance", title="C", criteria="X")
        kc.add_vertex("v4", type="document", title="D")

        kc.add_edge("e1", type="typing", vertices={"v1", "v2"}, scope="s")
        kc.add_edge("e2", type="verification", vertices={"v2", "v3"}, status="pass")
        kc.add_edge("e3", type="validation", vertices={"v3", "v4"}, status="pass")

        with pytest.raises(ValidationError):
            kc.add_face("bad", type="assurance", boundary=["e1", "e2", "e3"])

    def test_unregistered_type_fails(self, qa_schema_no_bind):
        """Adding an element with an unregistered type fails."""
        kc = KnowledgeComplex(schema=qa_schema_no_bind)
        with pytest.raises(ValidationError):
            kc.add_vertex("x", type="nonexistent_type")


# ===========================================================================
# Bind tests (sh:hasValue)
# ===========================================================================

class TestBind:

    def test_bind_correct_value_passes(self, qa_schema):
        """specification with category=structural passes (matches bind)."""
        kc = KnowledgeComplex(schema=qa_schema)
        kc.add_vertex("spec-001", type="specification",
                      title="Spec", format="PDF", category="structural")

    def test_bind_wrong_value_fails(self, qa_schema):
        """specification with category=quality fails (sh:hasValue violation)."""
        kc = KnowledgeComplex(schema=qa_schema)
        with pytest.raises(ValidationError):
            kc.add_vertex("spec-001", type="specification",
                          title="Spec", format="PDF", category="quality")

    def test_bind_omitted_fails(self, qa_schema):
        """specification omitting category fails (bound implies required)."""
        kc = KnowledgeComplex(schema=qa_schema)
        with pytest.raises(ValidationError):
            kc.add_vertex("spec-001", type="specification",
                          title="Spec", format="PDF")

    def test_parent_not_bound(self, qa_schema):
        """Plain document with any category still passes (bind only constrains child)."""
        kc = KnowledgeComplex(schema=qa_schema)
        kc.add_vertex("doc-001", type="document",
                      title="Doc", category="anything")

    def test_bind_vocab_valid_value_schema_ok(self):
        """Binding a vocab attribute to a value in the allowed set succeeds."""
        sb = SchemaBuilder(namespace="bv")
        sb.add_vertex_type("base", attributes={
            "status": vocab("active", "inactive")
        })
        sb.add_vertex_type("always_active", parent="base",
                           bind={"status": "active"})

    def test_bind_vocab_invalid_value_raises(self):
        """Binding a vocab attribute to a value not in the allowed set raises SchemaError."""
        sb = SchemaBuilder(namespace="bv")
        sb.add_vertex_type("base", attributes={
            "status": vocab("active", "inactive")
        })
        with pytest.raises(SchemaError):
            sb.add_vertex_type("broken", parent="base",
                               bind={"status": "deleted"})

    def test_bind_nonexistent_attr_raises(self):
        """Binding an attribute not in the type's ancestry raises SchemaError."""
        sb = SchemaBuilder(namespace="bv")
        sb.add_vertex_type("base", attributes={"title": text()})
        with pytest.raises(SchemaError):
            sb.add_vertex_type("child", parent="base",
                               bind={"nonexistent": "value"})

    def test_guidance_bind_correct_value_passes(self, qa_schema):
        """guidance with category=quality passes (matches bind)."""
        kc = KnowledgeComplex(schema=qa_schema)
        kc.add_vertex("g-001", type="guidance",
                      title="Guide", criteria="Accuracy", category="quality")

    def test_guidance_bind_wrong_value_fails(self, qa_schema):
        """guidance with category=structural fails."""
        kc = KnowledgeComplex(schema=qa_schema)
        with pytest.raises(ValidationError):
            kc.add_vertex("g-001", type="guidance",
                          title="Guide", criteria="Accuracy", category="structural")


# ===========================================================================
# Introspection tests (describe_type / type_names)
# ===========================================================================

class TestIntrospection:

    def test_describe_child_parent_and_kind(self, qa_schema):
        """describe_type returns correct parent and kind."""
        desc = qa_schema.describe_type("specification")
        assert desc["parent"] == "document"
        assert desc["kind"] == "vertex"
        assert desc["name"] == "specification"

    def test_describe_own_attributes(self, qa_schema):
        """own_attributes contains format but not title."""
        desc = qa_schema.describe_type("specification")
        assert "format" in desc["own_attributes"]
        assert "title" not in desc["own_attributes"]

    def test_describe_inherited_attributes(self, qa_schema):
        """inherited_attributes contains title but not format."""
        desc = qa_schema.describe_type("specification")
        assert "title" in desc["inherited_attributes"]
        assert "format" not in desc["inherited_attributes"]

    def test_describe_all_attributes(self, qa_schema):
        """all_attributes contains both inherited and own."""
        desc = qa_schema.describe_type("specification")
        assert "title" in desc["all_attributes"]
        assert "category" in desc["all_attributes"]
        assert "format" in desc["all_attributes"]

    def test_describe_bound(self, qa_schema):
        """bound returns the bound values."""
        desc = qa_schema.describe_type("specification")
        assert desc["bound"] == {"category": "structural"}

    def test_describe_parent_has_no_parent(self, qa_schema):
        """describe_type for root type returns parent=None."""
        desc = qa_schema.describe_type("document")
        assert desc["parent"] is None
        assert desc["inherited_attributes"] == {}

    def test_describe_nonexistent_raises(self, qa_schema):
        """describe_type for nonexistent type raises SchemaError."""
        with pytest.raises(SchemaError):
            qa_schema.describe_type("nonexistent")

    def test_type_names_all(self, qa_schema):
        """type_names() returns all registered types."""
        names = qa_schema.type_names()
        expected = {"document", "specification", "guidance",
                    "typing", "verification", "validation", "assurance"}
        assert set(names) == expected

    def test_type_names_vertex(self, qa_schema):
        """type_names(kind='vertex') returns only vertex types."""
        names = qa_schema.type_names(kind="vertex")
        assert set(names) == {"document", "specification", "guidance"}

    def test_type_names_edge(self, qa_schema):
        """type_names(kind='edge') returns only edge types."""
        names = qa_schema.type_names(kind="edge")
        assert set(names) == {"typing", "verification", "validation"}

    def test_type_names_face(self, qa_schema):
        """type_names(kind='face') returns only face types."""
        names = qa_schema.type_names(kind="face")
        assert set(names) == {"assurance"}


# ===========================================================================
# Multi-level inheritance tests
# ===========================================================================

class TestMultiLevel:

    def test_three_deep_chain_owl(self, deep_schema):
        """detailed_specification subClassOf specification subClassOf document."""
        g = Graph()
        g.parse(data=deep_schema.dump_owl(), format="turtle")
        ds = URIRef("https://example.org/deep#detailed_specification")
        spec = URIRef("https://example.org/deep#specification")
        doc = URIRef("https://example.org/deep#document")
        kc_vertex = URIRef("https://w3id.org/kc#Vertex")

        assert (ds, RDFS.subClassOf, spec) in g
        assert (spec, RDFS.subClassOf, doc) in g
        assert (doc, RDFS.subClassOf, kc_vertex) in g

    def test_three_deep_inherited_attributes(self, deep_schema):
        """detailed_specification inherits from both ancestors."""
        desc = deep_schema.describe_type("detailed_specification")
        assert "title" in desc["inherited_attributes"]
        assert "format" in desc["inherited_attributes"]
        assert "section" in desc["own_attributes"]
        assert "section" not in desc["inherited_attributes"]

    def test_three_deep_all_attributes(self, deep_schema):
        """all_attributes includes attrs from the entire chain."""
        desc = deep_schema.describe_type("detailed_specification")
        assert "title" in desc["all_attributes"]
        assert "format" in desc["all_attributes"]
        assert "section" in desc["all_attributes"]

    def test_three_deep_instance_valid(self, deep_schema):
        """Instance of detailed_specification must satisfy all ancestor constraints."""
        kc = KnowledgeComplex(schema=deep_schema)
        kc.add_vertex("ds-001", type="detailed_specification",
                      title="Untitled Spec", format="PDF", section="Section 1")

    def test_three_deep_instance_missing_grandparent_attr_fails(self, deep_schema):
        """Instance missing grandparent's required title fails."""
        kc = KnowledgeComplex(schema=deep_schema)
        with pytest.raises(ValidationError):
            kc.add_vertex("ds-001", type="detailed_specification",
                          format="PDF", section="Section 1")

    def test_three_deep_instance_missing_parent_attr_fails(self, deep_schema):
        """Instance missing parent's required format fails."""
        kc = KnowledgeComplex(schema=deep_schema)
        with pytest.raises(ValidationError):
            kc.add_vertex("ds-001", type="detailed_specification",
                          title="Untitled Spec", section="Section 1")

    def test_three_deep_instance_missing_own_attr_fails(self, deep_schema):
        """Instance missing own required section fails."""
        kc = KnowledgeComplex(schema=deep_schema)
        with pytest.raises(ValidationError):
            kc.add_vertex("ds-001", type="detailed_specification",
                          title="Untitled Spec", format="PDF")

    def test_middle_bind_propagates_to_grandchild(self, deep_schema):
        """Bind at specification level constrains detailed_specification instances."""
        desc = deep_schema.describe_type("detailed_specification")
        # The grandchild should see the bind from its parent
        assert "title" in desc["inherited_attributes"]

        # Instance must use the bound value
        kc = KnowledgeComplex(schema=deep_schema)
        kc.add_vertex("ds-001", type="detailed_specification",
                      title="Untitled Spec", format="PDF", section="S1")

    def test_middle_bind_wrong_value_fails_on_grandchild(self, deep_schema):
        """Grandchild instance with wrong bound value fails."""
        kc = KnowledgeComplex(schema=deep_schema)
        with pytest.raises(ValidationError):
            kc.add_vertex("ds-001", type="detailed_specification",
                          title="Wrong Title", format="PDF", section="S1")


# ===========================================================================
# Edge and face type inheritance
# ===========================================================================

class TestEdgeFaceInheritance:

    def test_edge_type_inheritance(self):
        """Edge types support parent parameter."""
        sb = SchemaBuilder(namespace="ef")
        sb.add_vertex_type("node")
        sb.add_edge_type("relation", attributes={"weight": text()})
        sb.add_edge_type("strong_relation", parent="relation",
                         attributes={"confidence": text()})

        g = Graph()
        g.parse(data=sb.dump_owl(), format="turtle")
        strong = URIRef("https://example.org/ef#strong_relation")
        rel = URIRef("https://example.org/ef#relation")
        assert (strong, RDFS.subClassOf, rel) in g

    def test_edge_type_inheritance_instance(self):
        """Instance of child edge type inherits parent attributes."""
        sb = SchemaBuilder(namespace="ef")
        sb.add_vertex_type("node")
        sb.add_edge_type("relation", attributes={"weight": text()})
        sb.add_edge_type("strong_relation", parent="relation",
                         attributes={"confidence": text()})

        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="node")
        kc.add_vertex("v2", type="node")
        kc.add_edge("e1", type="strong_relation",
                    vertices={"v1", "v2"}, weight="high", confidence="0.95")

    def test_edge_child_missing_inherited_attr_fails(self):
        """Child edge missing inherited weight fails."""
        sb = SchemaBuilder(namespace="ef")
        sb.add_vertex_type("node")
        sb.add_edge_type("relation", attributes={"weight": text()})
        sb.add_edge_type("strong_relation", parent="relation",
                         attributes={"confidence": text()})

        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="node")
        kc.add_vertex("v2", type="node")
        with pytest.raises(ValidationError):
            kc.add_edge("e1", type="strong_relation",
                        vertices={"v1", "v2"}, confidence="0.95")

    def test_face_type_inheritance(self):
        """Face types support parent parameter."""
        sb = SchemaBuilder(namespace="ef")
        sb.add_vertex_type("node")
        sb.add_edge_type("link")
        sb.add_face_type("region", attributes={"label": text()})
        sb.add_face_type("special_region", parent="region",
                         attributes={"priority": text()})

        g = Graph()
        g.parse(data=sb.dump_owl(), format="turtle")
        special = URIRef("https://example.org/ef#special_region")
        region = URIRef("https://example.org/ef#region")
        assert (special, RDFS.subClassOf, region) in g

    def test_face_type_inheritance_instance(self):
        """Instance of child face type inherits parent attributes."""
        sb = SchemaBuilder(namespace="ef")
        sb.add_vertex_type("node")
        sb.add_edge_type("link")
        sb.add_face_type("region", attributes={"label": text()})
        sb.add_face_type("special_region", parent="region",
                         attributes={"priority": text()})

        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("v1", type="node")
        kc.add_vertex("v2", type="node")
        kc.add_vertex("v3", type="node")
        kc.add_edge("e1", type="link", vertices={"v1", "v2"})
        kc.add_edge("e2", type="link", vertices={"v2", "v3"})
        kc.add_edge("e3", type="link", vertices={"v1", "v3"})
        kc.add_face("f1", type="special_region",
                    boundary=["e1", "e2", "e3"],
                    label="Zone A", priority="high")
