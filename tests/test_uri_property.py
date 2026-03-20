"""
tests/test_uri_property.py

Tests for the kc:uri superstructure attribute.
Verifies that kc:uri can be set on any element type (vertex, edge, face)
and that SHACL enforces at-most-one per element.
"""

import pytest
from pathlib import Path
from rdflib import Graph, Namespace, RDF, XSD
import pyshacl

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.exceptions import ValidationError

KC = Namespace("https://example.org/kc#")
EX = Namespace("https://example.org/test#")

_CORE_OWL    = Path(__file__).parent.parent / "knowledgecomplex" / "resources" / "kc_core.ttl"
_CORE_SHAPES = Path(__file__).parent.parent / "knowledgecomplex" / "resources" / "kc_core_shapes.ttl"


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="demo")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link", attributes={"kind": vocab("directed", "undirected")})
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def minimal_kc(schema) -> KnowledgeComplex:
    """3-vertex, 3-edge, 1-face valid closed triangle."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, kind="undirected")
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"}, kind="undirected")
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"}, kind="undirected")
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
    return kc


# ---------------------------------------------------------------------------
# URI on vertex
# ---------------------------------------------------------------------------

def test_vertex_with_uri(schema):
    """add_vertex accepts a uri kwarg and stores it in the graph."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node", uri="file:///docs/v1.md")
    ttl = kc.dump_graph()
    assert "file:///docs/v1.md" in ttl


def test_vertex_without_uri(schema):
    """add_vertex without uri still works (uri is optional)."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")  # should not raise


def test_vertex_uri_round_trips(schema):
    """kc:uri asserted on vertex is retrievable via SPARQL."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("spec-001", type="Node", uri="file:///path/to/spec-001.md")
    ttl = kc.dump_graph()
    from rdflib import Graph as G
    g = G()
    g.parse(data=ttl, format="turtle")
    # Check that the uri triple is present
    uri_values = list(g.objects(None, KC.uri))
    assert len(uri_values) == 1
    assert str(uri_values[0]) == "file:///path/to/spec-001.md"


# ---------------------------------------------------------------------------
# URI on edge
# ---------------------------------------------------------------------------

def test_edge_with_uri(schema):
    """add_edge accepts a uri kwarg."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"},
                uri="file:///edges/e12.md", kind="undirected")
    ttl = kc.dump_graph()
    assert "file:///edges/e12.md" in ttl


# ---------------------------------------------------------------------------
# URI on face
# ---------------------------------------------------------------------------

def test_face_with_uri(minimal_kc):
    """The face in minimal_kc can also carry a uri (added separately here)."""
    schema = SchemaBuilder(namespace="demo2")
    schema.add_vertex_type("Node")
    schema.add_edge_type("Link", attributes={"kind": vocab("undirected")})
    schema.add_face_type("Triangle")
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, kind="undirected")
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"}, kind="undirected")
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"}, kind="undirected")
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"],
                uri="file:///faces/f123.md")
    ttl = kc.dump_graph()
    assert "file:///faces/f123.md" in ttl


# ---------------------------------------------------------------------------
# SHACL enforcement: at-most-one kc:uri per element (via shapes directly)
# ---------------------------------------------------------------------------

def test_uri_at_most_one_shacl():
    """SHACL ElementShape rejects an element with two kc:uri values."""
    from rdflib import Literal

    g = Graph()
    g.add((EX.v1, RDF.type, KC.Vertex))
    # Deliberately assert two different kc:uri values
    g.add((EX.v1, KC.uri, Literal("file:///a.md", datatype=XSD.anyURI)))
    g.add((EX.v1, KC.uri, Literal("file:///b.md", datatype=XSD.anyURI)))

    shapes = Graph()
    shapes.parse(_CORE_SHAPES, format="turtle")
    ont = Graph()
    ont.parse(_CORE_OWL, format="turtle")

    conforms, _, report = pyshacl.validate(
        g,
        shacl_graph=shapes,
        ont_graph=ont,
        inference="rdfs",
        abort_on_first=False,
    )
    assert not conforms, "Expected two kc:uri values to fail SHACL sh:maxCount 1."


def test_uri_single_value_shacl_passes():
    """SHACL ElementShape accepts an element with exactly one kc:uri value."""
    from rdflib import Literal

    g = Graph()
    g.add((EX.v1, RDF.type, KC.Vertex))
    g.add((EX.v1, KC.uri, Literal("file:///a.md", datatype=XSD.anyURI)))

    shapes = Graph()
    shapes.parse(_CORE_SHAPES, format="turtle")
    ont = Graph()
    ont.parse(_CORE_OWL, format="turtle")

    conforms, _, report = pyshacl.validate(
        g,
        shacl_graph=shapes,
        ont_graph=ont,
        inference="rdfs",
        abort_on_first=False,
    )
    assert conforms, f"Expected single kc:uri value to pass SHACL.\n{report}"
