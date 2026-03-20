"""
tests/test_core_owl.py

Tests for knowledgecomplex/resources/kc_core.ttl (abstract OWL ontology).
All tests operate on the raw Turtle file via rdflib — these tests are allowed
to use rdflib directly since they are testing the static resource, not the package API.
"""

import pytest
from pathlib import Path
from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD

KC = Namespace("https://example.org/kc#")
_CORE_OWL = Path(__file__).parent.parent / "knowledgecomplex" / "resources" / "kc_core.ttl"


@pytest.fixture(scope="module")
def core_owl() -> Graph:
    g = Graph()
    g.parse(_CORE_OWL, format="turtle")
    return g


def test_core_owl_is_valid_turtle(core_owl):
    """Core OWL file parses without error."""
    assert len(core_owl) > 0


def test_core_classes_exist(core_owl):
    """KC:Element, KC:Vertex, KC:Edge, KC:Face, KC:Complex are declared as owl:Class."""
    for cls in [KC.Element, KC.Vertex, KC.Edge, KC.Face, KC.Complex]:
        assert (cls, RDF.type, OWL.Class) in core_owl, f"Missing class: {cls}"


def test_simplex_subclass_hierarchy(core_owl):
    """Vertex, Edge, Face are subclasses of Element."""
    for cls in [KC.Vertex, KC.Edge, KC.Face]:
        assert (cls, RDFS.subClassOf, KC.Element) in core_owl, (
            f"{cls} is not declared as rdfs:subClassOf kc:Element"
        )


def test_edge_cardinality_axioms(core_owl):
    """KC:Edge has cardinality restriction on boundedBy (exactly 2 Vertex)."""
    restrictions = set(core_owl.subjects(RDF.type, OWL.Restriction))
    bounded_restricted = any(
        (r, OWL.onProperty, KC.boundedBy) in core_owl
        and (KC.Edge, RDFS.subClassOf, r) in core_owl
        for r in restrictions
    )
    assert bounded_restricted, "No cardinality restriction on kc:boundedBy for Edge"


def test_face_cardinality_axioms(core_owl):
    """KC:Face has cardinality restriction on boundedBy (exactly 3 Edge)."""
    restrictions = set(core_owl.subjects(RDF.type, OWL.Restriction))
    bounded_restricted = any(
        (r, OWL.onProperty, KC.boundedBy) in core_owl
        and (KC.Face, RDFS.subClassOf, r) in core_owl
        for r in restrictions
    )
    assert bounded_restricted, "No cardinality restriction on kc:boundedBy for Face"


def test_bounded_by_domain_range(core_owl):
    """boundedBy has domain kc:Element and range kc:Element."""
    assert (KC.boundedBy, RDFS.domain, KC.Element) in core_owl, (
        "kc:boundedBy missing rdfs:domain kc:Element"
    )
    assert (KC.boundedBy, RDFS.range, KC.Element) in core_owl, (
        "kc:boundedBy missing rdfs:range kc:Element"
    )


def test_has_element_property(core_owl):
    """kc:hasElement property exists with domain Complex and range Element."""
    assert (KC.hasElement, RDF.type, OWL.ObjectProperty) in core_owl
    assert (KC.hasElement, RDFS.domain, KC.Complex) in core_owl
    assert (KC.hasElement, RDFS.range, KC.Element) in core_owl


def test_uri_property_declared(core_owl):
    """kc:uri is declared as an owl:DatatypeProperty with domain kc:Element and range xsd:anyURI."""
    assert (KC.uri, RDF.type, OWL.DatatypeProperty) in core_owl, (
        "kc:uri not declared as owl:DatatypeProperty"
    )
    assert (KC.uri, RDFS.domain, KC.Element) in core_owl, (
        "kc:uri missing rdfs:domain kc:Element"
    )
    assert (KC.uri, RDFS.range, XSD.anyURI) in core_owl, (
        "kc:uri missing rdfs:range xsd:anyURI"
    )
