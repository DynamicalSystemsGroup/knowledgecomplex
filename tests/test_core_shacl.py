"""
tests/test_core_shacl.py

Tests for knowledgecomplex/resources/kc_core_shapes.ttl (abstract SHACL shapes).
These tests construct minimal RDF graphs inline and validate against the shapes
directly via pyshacl — testing the static resource, not the package API.
"""

import pytest
from pathlib import Path
from rdflib import Graph, Namespace, RDF, Literal, XSD
import pyshacl

KC = Namespace("https://w3id.org/kc#")
EX = Namespace("https://example.org/test#")

_CORE_OWL    = Path(__file__).parent.parent / "knowledgecomplex" / "resources" / "kc_core.ttl"
_CORE_SHAPES = Path(__file__).parent.parent / "knowledgecomplex" / "resources" / "kc_core_shapes.ttl"


def _load_shapes() -> Graph:
    g = Graph()
    g.parse(_CORE_SHAPES, format="turtle")
    return g


def _load_ontology() -> Graph:
    g = Graph()
    g.parse(_CORE_OWL, format="turtle")
    return g


def _validate(data_graph: Graph) -> tuple[bool, str]:
    """Run pyshacl and return (conforms, report_text)."""
    conforms, _, report_text = pyshacl.validate(
        data_graph,
        shacl_graph=_load_shapes(),
        ont_graph=_load_ontology(),
        inference="rdfs",
        abort_on_first=False,
    )
    return conforms, report_text


def _minimal_valid_edge() -> Graph:
    """Construct a minimal valid KC:Edge individual with 2 boundary vertices."""
    g = Graph()
    g.add((EX.v1, RDF.type, KC.Vertex))
    g.add((EX.v2, RDF.type, KC.Vertex))
    g.add((EX.e1, RDF.type, KC.Edge))
    g.add((EX.e1, KC.boundedBy, EX.v1))
    g.add((EX.e1, KC.boundedBy, EX.v2))
    return g


def test_core_shapes_is_valid_turtle():
    """Shapes file parses without error."""
    g = _load_shapes()
    assert len(g) > 0


def test_valid_edge_passes():
    """A well-formed edge passes SHACL validation."""
    conforms, report = _validate(_minimal_valid_edge())
    assert conforms, f"Expected valid edge to pass.\n{report}"


def test_edge_same_endpoints_fails():
    """Edge with both boundary vertices the same must fail SHACL."""
    g = Graph()
    g.add((EX.v1, RDF.type, KC.Vertex))
    g.add((EX.e1, RDF.type, KC.Edge))
    g.add((EX.e1, KC.boundedBy, EX.v1))
    # Only one distinct vertex — cardinality shape expects 2 distinct triples,
    # but RDF deduplicates identical triples so only 1 boundedBy triple exists.
    conforms, report = _validate(g)
    assert not conforms, "Expected same-endpoint edge to fail SHACL."


def test_valid_face_passes():
    """A well-formed closed-triangle face passes SHACL validation."""
    # Triangle: v1-v2, v2-v3, v3-v1
    g = Graph()
    for v in [EX.v1, EX.v2, EX.v3]:
        g.add((v, RDF.type, KC.Vertex))
    edges = [
        (EX.e12, EX.v1, EX.v2),
        (EX.e23, EX.v2, EX.v3),
        (EX.e31, EX.v3, EX.v1),
    ]
    for e, v_a, v_b in edges:
        g.add((e, RDF.type, KC.Edge))
        g.add((e, KC.boundedBy, v_a))
        g.add((e, KC.boundedBy, v_b))
    g.add((EX.f1, RDF.type, KC.Face))
    for e, _, _ in edges:
        g.add((EX.f1, KC.boundedBy, e))
    conforms, report = _validate(g)
    assert conforms, f"Expected valid face to pass.\n{report}"


def test_open_triangle_face_fails():
    """Face with non-closed edges must fail SHACL sh:sparql constraint."""
    # Edges: v1-v2, v2-v3, v1-v4 (not a closed triangle — introduces v4)
    g = Graph()
    for v in [EX.v1, EX.v2, EX.v3, EX.v4]:
        g.add((v, RDF.type, KC.Vertex))
    edges = [
        (EX.e12, EX.v1, EX.v2),
        (EX.e23, EX.v2, EX.v3),
        (EX.e14, EX.v1, EX.v4),  # broken — introduces v4, breaks cycle
    ]
    for e, v_a, v_b in edges:
        g.add((e, RDF.type, KC.Edge))
        g.add((e, KC.boundedBy, v_a))
        g.add((e, KC.boundedBy, v_b))
    g.add((EX.f1, RDF.type, KC.Face))
    for e, _, _ in edges:
        g.add((EX.f1, KC.boundedBy, e))
    conforms, report = _validate(g)
    assert not conforms, "Expected open-triangle face to fail SHACL."


def test_fan_triangle_face_fails():
    """Face with 3 edges sharing a hub vertex but not forming a cycle must fail.

    Fan pattern: v1-v2, v1-v3, v1-v4 — all 3 edges share v1 but the other
    endpoints (v2, v3, v4) are all distinct and unconnected. 4 distinct vertices,
    not 3 — cannot form a closed triangle.
    """
    g = Graph()
    for v in [EX.v1, EX.v2, EX.v3, EX.v4]:
        g.add((v, RDF.type, KC.Vertex))
    edges = [
        (EX.e12, EX.v1, EX.v2),
        (EX.e13, EX.v1, EX.v3),
        (EX.e14, EX.v1, EX.v4),
    ]
    for e, v_a, v_b in edges:
        g.add((e, RDF.type, KC.Edge))
        g.add((e, KC.boundedBy, v_a))
        g.add((e, KC.boundedBy, v_b))
    g.add((EX.f1, RDF.type, KC.Face))
    for e, _, _ in edges:
        g.add((EX.f1, KC.boundedBy, e))
    conforms, report = _validate(g)
    assert not conforms, "Expected fan-pattern face to fail SHACL."


def test_face_wrong_edge_count_fails():
    """Face with 2 edges must fail SHACL."""
    g = _minimal_valid_edge()
    g.add((EX.v3, RDF.type, KC.Vertex))
    g.add((EX.e2, RDF.type, KC.Edge))
    g.add((EX.e2, KC.boundedBy, EX.v2))
    g.add((EX.e2, KC.boundedBy, EX.v3))
    g.add((EX.f1, RDF.type, KC.Face))
    g.add((EX.f1, KC.boundedBy, EX.e1))
    g.add((EX.f1, KC.boundedBy, EX.e2))  # only 2 edges
    conforms, report = _validate(g)
    assert not conforms, "Expected 2-edge face to fail SHACL."


# ---------------------------------------------------------------------------
# ComplexShape — boundary-closure tests
# ---------------------------------------------------------------------------

def _minimal_valid_complex() -> Graph:
    """Construct a minimal valid Complex containing one edge and its two vertices."""
    g = Graph()
    g.add((EX.v1, RDF.type, KC.Vertex))
    g.add((EX.v2, RDF.type, KC.Vertex))
    g.add((EX.e1, RDF.type, KC.Edge))
    g.add((EX.e1, KC.boundedBy, EX.v1))
    g.add((EX.e1, KC.boundedBy, EX.v2))
    g.add((EX.cx, RDF.type, KC.Complex))
    g.add((EX.cx, KC.hasElement, EX.v1))
    g.add((EX.cx, KC.hasElement, EX.v2))
    g.add((EX.cx, KC.hasElement, EX.e1))
    return g


def test_valid_complex_passes():
    """A complex containing an edge and both its boundary vertices passes SHACL."""
    conforms, report = _validate(_minimal_valid_complex())
    assert conforms, f"Expected valid complex to pass.\n{report}"


def test_complex_missing_boundary_vertex_fails():
    """A complex containing an edge but missing one boundary vertex must fail SHACL."""
    g = Graph()
    g.add((EX.v1, RDF.type, KC.Vertex))
    g.add((EX.v2, RDF.type, KC.Vertex))
    g.add((EX.e1, RDF.type, KC.Edge))
    g.add((EX.e1, KC.boundedBy, EX.v1))
    g.add((EX.e1, KC.boundedBy, EX.v2))
    # Complex has the edge and v1, but NOT v2
    g.add((EX.cx, RDF.type, KC.Complex))
    g.add((EX.cx, KC.hasElement, EX.v1))
    g.add((EX.cx, KC.hasElement, EX.e1))
    conforms, report = _validate(g)
    assert not conforms, "Expected complex missing a boundary vertex to fail SHACL."
