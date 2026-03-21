"""
tests/test_audit.py

Tests for verification and audit tooling:
  - kc.verify() — public throwing verification
  - kc.audit() — non-throwing structured report
  - deferred_verification() — context manager for bulk construction
  - audit_file() — static file verification
"""

import pytest
from pathlib import Path

from knowledgecomplex.schema import SchemaBuilder, vocab
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.audit import AuditReport, AuditViolation, audit_file
from knowledgecomplex.exceptions import ValidationError


@pytest.fixture
def schema() -> SchemaBuilder:
    sb = SchemaBuilder(namespace="topo")
    sb.add_vertex_type("Node")
    sb.add_edge_type("Link")
    sb.add_face_type("Triangle")
    return sb


@pytest.fixture
def valid_kc(schema) -> KnowledgeComplex:
    """A valid 3-vertex, 3-edge, 1-face complex."""
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_vertex("v3", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
    kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
    kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
    kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
    return kc


@pytest.fixture
def invalid_kc(schema) -> KnowledgeComplex:
    """A complex with a dangling edge (boundary vertex missing from complex).

    We bypass normal validation by using load_graph to inject bad triples.
    """
    from knowledgecomplex.io import load_graph
    kc = KnowledgeComplex(schema=schema)
    kc.add_vertex("v1", type="Node")
    kc.add_vertex("v2", type="Node")
    kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
    # Manually remove v2 from the complex to create an invalid state
    from rdflib import URIRef
    v2_iri = URIRef(f"{schema._base_iri}v2")
    kc._instance_graph.remove((kc._complex_iri, None, v2_iri))
    return kc


# ===========================================================================
# kc.verify()
# ===========================================================================

class TestVerify:

    def test_valid_no_exception(self, valid_kc):
        valid_kc.verify()  # should not raise

    def test_invalid_raises(self, invalid_kc):
        with pytest.raises(ValidationError):
            invalid_kc.verify()


# ===========================================================================
# kc.audit()
# ===========================================================================

class TestAudit:

    def test_valid_conforms(self, valid_kc):
        report = valid_kc.audit()
        assert isinstance(report, AuditReport)
        assert report.conforms is True
        assert len(report.violations) == 0

    def test_valid_bool(self, valid_kc):
        report = valid_kc.audit()
        assert bool(report) is True

    def test_invalid_does_not_raise(self, invalid_kc):
        report = invalid_kc.audit()  # should NOT raise
        assert isinstance(report, AuditReport)

    def test_invalid_conforms_false(self, invalid_kc):
        report = invalid_kc.audit()
        assert report.conforms is False

    def test_invalid_has_violations(self, invalid_kc):
        report = invalid_kc.audit()
        assert len(report.violations) > 0

    def test_violations_have_message(self, invalid_kc):
        report = invalid_kc.audit()
        for v in report.violations:
            assert isinstance(v, AuditViolation)
            assert isinstance(v.message, str) or isinstance(v.constraint, str)

    def test_report_text(self, invalid_kc):
        report = invalid_kc.audit()
        assert len(report.text) > 0

    def test_report_str(self, valid_kc):
        report = valid_kc.audit()
        s = str(report)
        assert "passed" in s.lower() or "no violation" in s.lower()


# ===========================================================================
# deferred_verification
# ===========================================================================

class TestDeferredVerification:

    def test_valid_bulk_construction(self, schema):
        """Bulk add inside context manager, verifies once at exit."""
        kc = KnowledgeComplex(schema=schema)
        with kc.deferred_verification():
            kc.add_vertex("v1", type="Node")
            kc.add_vertex("v2", type="Node")
            kc.add_vertex("v3", type="Node")
            kc.add_edge("e12", type="Link", vertices={"v1", "v2"})
            kc.add_edge("e23", type="Link", vertices={"v2", "v3"})
            kc.add_edge("e13", type="Link", vertices={"v1", "v3"})
            kc.add_face("f123", type="Triangle", boundary=["e12", "e23", "e13"])
        # If we got here, verification passed on exit

    def test_flag_reset_after_exit(self, schema):
        kc = KnowledgeComplex(schema=schema)
        with kc.deferred_verification():
            kc.add_vertex("v1", type="Node")
        assert kc._defer_verification is False

    def test_flag_reset_on_exception(self, schema):
        kc = KnowledgeComplex(schema=schema)
        try:
            with kc.deferred_verification():
                kc.add_vertex("v1", type="Node")
                raise RuntimeError("simulated error")
        except RuntimeError:
            pass
        assert kc._defer_verification is False

    def test_returns_kc(self, schema):
        """Context manager yields the KC for convenience."""
        kc = KnowledgeComplex(schema=schema)
        with kc.deferred_verification() as ctx:
            assert ctx is kc


# ===========================================================================
# audit_file
# ===========================================================================

class TestAuditFile:

    def test_valid_file(self, valid_kc, tmp_path):
        valid_kc.export(tmp_path / "export")
        report = audit_file(
            tmp_path / "export" / "instance.ttl",
            shapes=tmp_path / "export" / "shapes.ttl",
            ontology=tmp_path / "export" / "ontology.ttl",
        )
        assert isinstance(report, AuditReport)
        assert report.conforms is True

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            audit_file(
                tmp_path / "nonexistent.ttl",
                shapes=tmp_path / "shapes.ttl",
            )

    def test_valid_without_ontology(self, valid_kc, tmp_path):
        """Without ontology, RDFS inference is skipped but basic shapes still work."""
        valid_kc.export(tmp_path / "export")
        report = audit_file(
            tmp_path / "export" / "instance.ttl",
            shapes=tmp_path / "export" / "shapes.ttl",
        )
        assert isinstance(report, AuditReport)
