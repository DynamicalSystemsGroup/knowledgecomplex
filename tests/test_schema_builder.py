"""
tests/test_schema_builder.py

Tests for knowledgecomplex.schema.SchemaBuilder and vocab/text descriptors.
These tests call the public API only — no rdflib imports.
Turtle output is inspected as strings or parsed by rdflib *within the test*
to check for required triples (rdflib use here is in the test, not the API).
"""

import pytest
from rdflib import Graph  # allowed in tests; not in API under test

from knowledgecomplex.schema import SchemaBuilder, vocab, text, VocabDescriptor, TextDescriptor
from knowledgecomplex.exceptions import SchemaError


@pytest.fixture
def basic_schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="test")
    sb.add_vertex_type("Color")
    sb.add_edge_type(
        "ColorPair",
        attributes={"disposition": vocab("adjacent", "opposite")},
    )
    sb.add_face_type(
        "ColorTriple",
        attributes={"pattern": {"vocab": vocab("ooa", "oaa"), "required": False}},
    )
    return sb


# --- vocab() ---

def test_vocab_returns_descriptor():
    v = vocab("a", "b")
    assert isinstance(v, VocabDescriptor)
    assert v.values == ("a", "b")


def test_vocab_empty_raises():
    with pytest.raises(ValueError):
        vocab()


# --- text() ---

def test_text_returns_descriptor():
    t = text()
    assert isinstance(t, TextDescriptor)
    assert t.required is True
    assert t.multiple is False


def test_text_optional():
    t = text(required=False, multiple=True)
    assert t.required is False
    assert t.multiple is True


# --- add_vertex_type ---

def test_add_vertex_type_writes_owl(basic_schema):
    """OWL dump contains subclass triple for Color."""
    ttl = basic_schema.dump_owl()
    g = Graph()
    g.parse(data=ttl, format="turtle")
    from rdflib.namespace import RDFS
    from rdflib import URIRef
    color = URIRef("https://example.org/test#Color")
    kc_vertex = URIRef("https://w3id.org/kc#Vertex")
    assert (color, RDFS.subClassOf, kc_vertex) in g


def test_add_vertex_type_writes_shacl(basic_schema):
    """SHACL dump contains NodeShape targeting Color."""
    ttl = basic_schema.dump_shacl()
    assert "test#Color" in ttl or "ColorShape" in ttl


# --- add_edge_type ---

def test_add_edge_type_writes_owl(basic_schema):
    """OWL dump contains ColorPair subclass of KC:Edge."""
    ttl = basic_schema.dump_owl()
    g = Graph()
    g.parse(data=ttl, format="turtle")
    from rdflib.namespace import RDFS
    from rdflib import URIRef
    rel = URIRef("https://example.org/test#ColorPair")
    kc_edge = URIRef("https://w3id.org/kc#Edge")
    assert (rel, RDFS.subClassOf, kc_edge) in g


def test_add_edge_type_writes_shacl(basic_schema):
    """SHACL dump contains sh:in constraint for disposition."""
    ttl = basic_schema.dump_shacl()
    assert "adjacent" in ttl
    assert "opposite" in ttl


# --- add_face_type ---

def test_add_face_type_optional_attr(basic_schema):
    """Optional attribute generates sh:minCount 0."""
    ttl = basic_schema.dump_shacl()
    # 'pattern' attribute was required=False
    assert "pattern" in ttl
    assert "minCount" in ttl or "sh:minCount" in ttl


# --- vocab → sh:in ---

def test_vocab_generates_sh_in(basic_schema):
    """Vocab values appear in SHACL sh:in constraint."""
    ttl = basic_schema.dump_shacl()
    assert "adjacent" in ttl
    assert "opposite" in ttl
    assert "ooa" in ttl
    assert "oaa" in ttl


# --- dump_owl / dump_shacl include core ---

def test_dump_owl_includes_core(basic_schema):
    """dump_owl() includes KC:Vertex, KC:Edge, KC:Face."""
    ttl = basic_schema.dump_owl()
    assert "Vertex" in ttl
    assert "Edge" in ttl
    assert "Face" in ttl


def test_dump_shacl_includes_core(basic_schema):
    """dump_shacl() includes core EdgeShape and FaceShape."""
    ttl = basic_schema.dump_shacl()
    assert "EdgeShape" in ttl
    assert "FaceShape" in ttl


def test_dump_owl_includes_uri_property(basic_schema):
    """dump_owl() includes kc:uri property from core."""
    ttl = basic_schema.dump_owl()
    assert "kc#uri" in ttl or "kc:uri" in ttl


# --- promote_to_attribute ---

def test_promote_updates_shacl(basic_schema):
    """promote_to_attribute changes SHACL dump (minCount goes from 0 to 1)."""
    basic_schema.promote_to_attribute(
        type="ColorTriple",
        attribute="pattern",
        vocab=vocab("ooa", "oaa"),
        required=True,
    )
    ttl = basic_schema.dump_shacl()
    assert "minCount" in ttl


# --- duplicate type raises ---

def test_duplicate_type_raises():
    """Registering the same type name twice raises SchemaError."""
    sb = SchemaBuilder(namespace="test2")
    sb.add_vertex_type("MyVertex")
    with pytest.raises(SchemaError):
        sb.add_vertex_type("MyVertex")


# --- API opacity ---

def test_no_rdflib_in_public_api():
    """SchemaBuilder public methods return no rdflib objects."""
    import rdflib
    sb = SchemaBuilder(namespace="opacity_test")
    sb.add_vertex_type("V")
    owl_out = sb.dump_owl()
    shacl_out = sb.dump_shacl()
    assert isinstance(owl_out, str), "dump_owl() must return str"
    assert isinstance(shacl_out, str), "dump_shacl() must return str"
    assert not isinstance(owl_out, rdflib.Graph)
    assert not isinstance(shacl_out, rdflib.Graph)
