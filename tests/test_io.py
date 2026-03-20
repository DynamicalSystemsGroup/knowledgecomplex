"""
tests/test_io.py

Tests for knowledgecomplex.io — multi-format save/load/dump with additive loading.
"""

import json

import pytest
from rdflib import Graph

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.io import save_graph, load_graph, dump_graph
from knowledgecomplex.exceptions import ValidationError


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="demo")
    sb.add_vertex_type("Node")
    sb.add_edge_type(
        "Link",
        attributes={"kind": vocab("directed", "undirected")},
    )
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def populated_kc(schema) -> KnowledgeComplex:
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


def _triple_count(kc: KnowledgeComplex) -> int:
    return len(kc._instance_graph)


# ── Round-trip tests ────────────────────────────────────────────────────────


def test_save_load_roundtrip_turtle(populated_kc, schema, tmp_path):
    """Turtle round-trip: loaded graph is superset of original (TBox deduplicates,
    but the fresh KC's own kc:Complex individual adds a few extra triples)."""
    path = tmp_path / "instance.ttl"
    save_graph(populated_kc, path)

    fresh = KnowledgeComplex(schema=schema)
    baseline = _triple_count(fresh)
    load_graph(fresh, path)
    # All original triples loaded; fresh may have a few extra from its own kc:Complex
    assert _triple_count(fresh) >= _triple_count(populated_kc)
    # The loaded graph grew beyond the empty-KC baseline
    assert _triple_count(fresh) > baseline


def test_save_load_roundtrip_jsonld(populated_kc, schema, tmp_path):
    """JSON-LD round-trip: loaded graph is superset of original."""
    path = tmp_path / "instance.jsonld"
    save_graph(populated_kc, path, format="json-ld")

    fresh = KnowledgeComplex(schema=schema)
    baseline = _triple_count(fresh)
    load_graph(fresh, path)
    assert _triple_count(fresh) >= _triple_count(populated_kc)
    assert _triple_count(fresh) > baseline


def test_save_load_roundtrip_ntriples(populated_kc, schema, tmp_path):
    """N-Triples round-trip: loaded graph is superset of original."""
    path = tmp_path / "instance.nt"
    save_graph(populated_kc, path, format="ntriples")

    fresh = KnowledgeComplex(schema=schema)
    baseline = _triple_count(fresh)
    load_graph(fresh, path)
    assert _triple_count(fresh) >= _triple_count(populated_kc)
    assert _triple_count(fresh) > baseline


# ── Format auto-detection ──────────────────────────────────────────────────


def test_format_autodetect(populated_kc, schema, tmp_path):
    """.jsonld extension is auto-detected on load."""
    path = tmp_path / "data.jsonld"
    save_graph(populated_kc, path, format="json-ld")

    fresh = KnowledgeComplex(schema=schema)
    load_graph(fresh, path)  # format=None, auto-detected
    assert _triple_count(fresh) >= _triple_count(populated_kc)


def test_format_explicit_override(populated_kc, schema, tmp_path):
    """Explicit format= overrides file extension."""
    path = tmp_path / "data.txt"  # unknown extension
    save_graph(populated_kc, path, format="turtle")

    fresh = KnowledgeComplex(schema=schema)
    load_graph(fresh, path, format="turtle")  # explicit override
    assert _triple_count(fresh) >= _triple_count(populated_kc)


def test_unknown_extension_raises(populated_kc, tmp_path):
    """Unknown extension without explicit format raises ValueError."""
    path = tmp_path / "data.xyz"
    path.write_text("")
    with pytest.raises(ValueError, match="Cannot auto-detect"):
        load_graph(populated_kc, path)


# ── Additive loading ───────────────────────────────────────────────────────


def test_additive_load(schema, tmp_path):
    """Loading a file into an existing KC adds triples (does not replace)."""
    # Build and save KC-A with 2 vertices
    kc_a = KnowledgeComplex(schema=schema)
    kc_a.add_vertex("a1", type="Node")
    kc_a.add_vertex("a2", type="Node")
    save_graph(kc_a, tmp_path / "a.ttl")
    count_a = _triple_count(kc_a)

    # Build KC-B with 2 different vertices
    kc_b = KnowledgeComplex(schema=schema)
    kc_b.add_vertex("b1", type="Node")
    kc_b.add_vertex("b2", type="Node")
    count_b_before = _triple_count(kc_b)

    # Load A into B — triples should grow
    load_graph(kc_b, tmp_path / "a.ttl")
    assert _triple_count(kc_b) > count_b_before


# ── Validation on load ─────────────────────────────────────────────────────


def test_load_validate_pass(populated_kc, schema, tmp_path):
    """validate=True with valid data succeeds."""
    path = tmp_path / "valid.ttl"
    save_graph(populated_kc, path)

    fresh = KnowledgeComplex(schema=schema)
    load_graph(fresh, path, validate=True)  # should not raise
    assert _triple_count(fresh) >= _triple_count(populated_kc)


def test_load_validate_fail_rollback(schema, tmp_path):
    """Invalid data with validate=True raises ValidationError, graph unchanged."""
    # Create a file with a dangling edge (no boundary vertices in complex)
    bad_ttl = tmp_path / "bad.ttl"
    bad_ttl.write_text("""\
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix kc: <https://example.org/kc#> .
@prefix demo: <https://example.org/demo#> .

<https://example.org/demo#dangling_edge> rdf:type demo:Link ;
    kc:boundedBy <https://example.org/demo#phantom_v1> ,
                 <https://example.org/demo#phantom_v2> .

<https://example.org/demo#_complex> kc:hasElement
    <https://example.org/demo#dangling_edge> .
""")

    kc = KnowledgeComplex(schema=schema)
    count_before = _triple_count(kc)

    with pytest.raises(ValidationError):
        load_graph(kc, bad_ttl, validate=True)

    # Graph should be unchanged after rollback
    assert _triple_count(kc) == count_before


# ── dump_graph ──────────────────────────────────────────────────────────────


def test_dump_graph_jsonld(populated_kc):
    """dump_graph with json-ld returns parseable JSON-LD."""
    output = dump_graph(populated_kc, format="json-ld")
    assert isinstance(output, str)
    parsed = json.loads(output)  # valid JSON
    assert isinstance(parsed, (list, dict))

    # Parseable by rdflib
    g = Graph()
    g.parse(data=output, format="json-ld")
    assert len(g) > 0


def test_dump_graph_turtle_default(populated_kc):
    """dump_graph defaults to Turtle."""
    output = dump_graph(populated_kc)
    g = Graph()
    g.parse(data=output, format="turtle")
    assert len(g) == _triple_count(populated_kc)
