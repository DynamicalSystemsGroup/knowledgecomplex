"""
tests/test_knowledge_complex.py

Tests for knowledgecomplex.graph.KnowledgeComplex.
All tests call the public API only. No rdflib/pyshacl imports.
"""

import pytest
import pandas as pd

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.exceptions import ValidationError, UnknownQueryError


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="demo")
    sb.add_vertex_type("Node")
    sb.add_edge_type(
        "Link",
        attributes={"kind": vocab("directed", "undirected")},
    )
    sb.add_face_type(
        "Triangle",
        attributes={"label": {"vocab": vocab("up", "down"), "required": False}},
    )
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


# --- add_vertex ---

def test_add_vertex_valid(schema):
    """Valid vertex is added without error."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")  # should not raise


def test_add_vertex_invalid_type_fails(schema):
    """Unregistered type raises ValidationError."""
    kc = KnowledgeComplex(schema=schema)
    with pytest.raises(ValidationError):
        kc.add_vertex("v1", type="UnknownType")


# --- add_edge ---

def test_add_edge_valid(schema):
    """Valid edge is added without error."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, kind="undirected")


def test_add_edge_invalid_vocab(schema):
    """Invalid vocab value raises ValidationError."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    with pytest.raises(ValidationError):
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, kind="invalid_value")


# --- add_face ---

def test_add_face_valid(minimal_kc):
    """Valid closed-triangle face already added in fixture — no error."""
    pass  # fixture construction is the test


def test_add_face_open_triangle_fails(schema):
    """Open-triangle face raises ValidationError."""
    kc = KnowledgeComplex(schema=schema)
    for v in ["v1", "v2", "v3", "v4"]:
        kc.add_vertex(v, type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, kind="undirected")
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"}, kind="undirected")
    kc.add_edge("e14", type="Link", vertices={"v1", "v4"}, kind="undirected")
    # e12, e23, e14 do not form a closed triangle
    with pytest.raises(ValidationError):
        kc.add_face("bad", type="Triangle", boundary=["e12", "e23", "e14"])


def test_add_face_wrong_count_raises(schema):
    """boundary list != 3 raises ValueError (not ValidationError)."""
    kc = KnowledgeComplex(schema=schema)
    with pytest.raises(ValueError):
        kc.add_face("f", type="Triangle", boundary=["e1", "e2"])


# --- boundary-closure (ComplexShape) ---

def test_add_edge_before_vertices_fails(schema):
    """Adding an edge before its boundary vertices raises ValidationError."""
    kc = KnowledgeComplex(schema=schema)
    # Do NOT add vertices first
    with pytest.raises(ValidationError):
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, kind="undirected")


# --- ValidationError ---

def test_validation_error_has_report(schema):
    """ValidationError exposes .report as a non-empty string."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    try:
        kc.add_edge("e12", type="Link", vertices={"v1", "v2"}, kind="INVALID")
    except ValidationError as e:
        assert isinstance(e.report, str)
        assert len(e.report) > 0
    else:
        pytest.fail("Expected ValidationError was not raised")


# --- query ---

def test_query_vertices(minimal_kc):
    """Built-in 'vertices' query returns a DataFrame with the 3 added vertices."""
    df = minimal_kc.query("vertices")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3


def test_query_unknown_template_raises(minimal_kc):
    """Unregistered template name raises UnknownQueryError."""
    with pytest.raises(UnknownQueryError):
        minimal_kc.query("no_such_query")


# --- dump_graph ---

def test_dump_graph_is_valid_turtle(minimal_kc):
    """dump_graph() returns parseable Turtle string."""
    from rdflib import Graph  # rdflib allowed in test to verify output
    ttl = minimal_kc.dump_graph()
    assert isinstance(ttl, str)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    assert len(g) > 0


# --- API opacity ---

def test_no_rdflib_in_public_api(minimal_kc):
    """Public methods return no rdflib objects."""
    import rdflib
    ttl = minimal_kc.dump_graph()
    df = minimal_kc.query("vertices")
    assert isinstance(ttl, str)
    assert isinstance(df, pd.DataFrame)
    assert not isinstance(ttl, rdflib.Graph)
