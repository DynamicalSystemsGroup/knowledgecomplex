"""
tests/test_codec.py

Tests for codec registration, element.compile(), element.decompile(),
kc.decompile_uri(), and codec inheritance.
"""

import json
import pytest
from pathlib import Path

from knowledgecomplex.schema import SchemaBuilder, Codec, vocab, text
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.exceptions import SchemaError


# ---------------------------------------------------------------------------
# Test codecs
# ---------------------------------------------------------------------------

class MockCodec:
    """Records calls for assertion."""

    def __init__(self):
        self.compile_calls: list[dict] = []
        self.decompile_calls: list[str] = []
        self.decompile_return: dict = {"title": "From Codec"}

    def compile(self, element: dict) -> None:
        self.compile_calls.append(dict(element))

    def decompile(self, uri: str) -> dict:
        self.decompile_calls.append(uri)
        return dict(self.decompile_return)


class JsonFileCodec:
    """Real codec that writes/reads JSON files for round-trip tests."""

    def compile(self, element: dict) -> None:
        uri = element["uri"]
        path = uri.replace("file://", "")
        data = {k: v for k, v in element.items() if k not in ("id", "type", "uri")}
        Path(path).write_text(json.dumps(data))

    def decompile(self, uri: str) -> dict:
        path = uri.replace("file://", "")
        return json.loads(Path(path).read_text())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def qa_kc() -> KnowledgeComplex:
    sb = SchemaBuilder(namespace="qa")
    sb.add_vertex_type("document", attributes={"title": text()})
    sb.add_vertex_type("specification", parent="document", attributes={"format": text()})
    sb.add_vertex_type("guidance", parent="document", attributes={"criteria": text()})
    sb.add_edge_type("verification", attributes={"status": vocab("pass", "fail", "pending")})
    sb.add_face_type("assurance")

    kc = KnowledgeComplex(schema=sb)
    kc.add_vertex("spec-001", type="specification", title="Spec A", format="PDF",
                  uri="file:///tmp/test-spec-001.json")
    kc.add_vertex("guid-001", type="guidance", title="Guide A", criteria="Accuracy",
                  uri="file:///tmp/test-guid-001.json")
    kc.add_vertex("doc-001", type="document", title="Doc A")
    return kc


@pytest.fixture
def deep_kc() -> KnowledgeComplex:
    """Three-deep inheritance for codec inheritance tests."""
    sb = SchemaBuilder(namespace="deep")
    sb.add_vertex_type("document", attributes={"title": text()})
    sb.add_vertex_type("specification", parent="document", attributes={"format": text()})
    sb.add_vertex_type("detailed_spec", parent="specification",
                       attributes={"section": text()})

    kc = KnowledgeComplex(schema=sb)
    kc.add_vertex("ds-001", type="detailed_spec",
                  title="DS", format="PDF", section="S1",
                  uri="file:///tmp/test-ds-001.json")
    kc.add_vertex("spec-001", type="specification",
                  title="Spec", format="PDF",
                  uri="file:///tmp/test-spec-001.json")
    kc.add_vertex("doc-001", type="document", title="Doc",
                  uri="file:///tmp/test-doc-001.json")
    return kc


# ===========================================================================
# Codec registration tests
# ===========================================================================

class TestCodecRegistration:

    def test_register_valid_type(self, qa_kc):
        codec = MockCodec()
        qa_kc.register_codec("specification", codec)

    def test_register_nonexistent_type_raises(self, qa_kc):
        codec = MockCodec()
        with pytest.raises(SchemaError):
            qa_kc.register_codec("nonexistent", codec)

    def test_register_non_codec_raises(self, qa_kc):
        with pytest.raises(TypeError):
            qa_kc.register_codec("specification", "not a codec")

    def test_register_parent_type(self, qa_kc):
        codec = MockCodec()
        qa_kc.register_codec("document", codec)


# ===========================================================================
# element.compile() tests
# ===========================================================================

class TestCompile:

    def test_compile_calls_codec(self, qa_kc):
        codec = MockCodec()
        qa_kc.register_codec("specification", codec)
        elem = qa_kc.element("spec-001")
        elem.compile()
        assert len(codec.compile_calls) == 1
        call = codec.compile_calls[0]
        assert call["id"] == "spec-001"
        assert call["type"] == "specification"
        assert call["uri"] == "file:///tmp/test-spec-001.json"
        assert call["title"] == "Spec A"
        assert call["format"] == "PDF"

    def test_compile_no_uri_raises(self, qa_kc):
        codec = MockCodec()
        qa_kc.register_codec("document", codec)
        elem = qa_kc.element("doc-001")
        with pytest.raises(ValueError):
            elem.compile()

    def test_compile_no_codec_raises(self, qa_kc):
        elem = qa_kc.element("spec-001")
        with pytest.raises(SchemaError):
            elem.compile()


# ===========================================================================
# element.decompile() tests
# ===========================================================================

class TestDecompile:

    def test_decompile_calls_codec(self, qa_kc):
        codec = MockCodec()
        codec.decompile_return = {"title": "Updated Title", "format": "DOCX"}
        qa_kc.register_codec("specification", codec)
        elem = qa_kc.element("spec-001")
        elem.decompile()
        assert len(codec.decompile_calls) == 1
        assert codec.decompile_calls[0] == "file:///tmp/test-spec-001.json"

    def test_decompile_updates_attrs(self, qa_kc):
        codec = MockCodec()
        codec.decompile_return = {"title": "Updated Title", "format": "DOCX"}
        qa_kc.register_codec("specification", codec)
        elem = qa_kc.element("spec-001")
        elem.decompile()
        assert elem.attrs["title"] == "Updated Title"
        assert elem.attrs["format"] == "DOCX"

    def test_decompile_no_uri_raises(self, qa_kc):
        codec = MockCodec()
        qa_kc.register_codec("document", codec)
        elem = qa_kc.element("doc-001")
        with pytest.raises(ValueError):
            elem.decompile()

    def test_decompile_no_codec_raises(self, qa_kc):
        elem = qa_kc.element("spec-001")
        with pytest.raises(SchemaError):
            elem.decompile()


# ===========================================================================
# decompile_uri() tests (standalone)
# ===========================================================================

class TestDecompileUri:

    def test_returns_attr_dict(self, qa_kc):
        codec = MockCodec()
        codec.decompile_return = {"title": "From URI", "format": "HTML"}
        qa_kc.register_codec("specification", codec)
        result = qa_kc.decompile_uri("specification", "file:///some/path.json")
        assert result == {"title": "From URI", "format": "HTML"}
        assert codec.decompile_calls == ["file:///some/path.json"]

    def test_nonexistent_type_raises(self, qa_kc):
        with pytest.raises(SchemaError):
            qa_kc.decompile_uri("nonexistent", "file:///x")

    def test_no_codec_raises(self, qa_kc):
        with pytest.raises(SchemaError):
            qa_kc.decompile_uri("specification", "file:///x")


# ===========================================================================
# Codec inheritance tests
# ===========================================================================

class TestCodecInheritance:

    def test_child_inherits_parent_codec(self, qa_kc):
        """Register on document, compile on specification — uses document's codec."""
        codec = MockCodec()
        qa_kc.register_codec("document", codec)
        elem = qa_kc.element("spec-001")
        elem.compile()
        assert len(codec.compile_calls) == 1
        assert codec.compile_calls[0]["type"] == "specification"

    def test_child_override(self, qa_kc):
        """Register on both — specification uses its own."""
        parent_codec = MockCodec()
        child_codec = MockCodec()
        qa_kc.register_codec("document", parent_codec)
        qa_kc.register_codec("specification", child_codec)
        elem = qa_kc.element("spec-001")
        elem.compile()
        assert len(child_codec.compile_calls) == 1
        assert len(parent_codec.compile_calls) == 0

    def test_grandchild_inherits_from_root(self, deep_kc):
        """Only root has codec — grandchild uses it."""
        codec = MockCodec()
        deep_kc.register_codec("document", codec)
        elem = deep_kc.element("ds-001")
        elem.compile()
        assert len(codec.compile_calls) == 1
        assert codec.compile_calls[0]["type"] == "detailed_spec"

    def test_grandchild_uses_middle_override(self, deep_kc):
        """Register on root and middle — grandchild uses middle's."""
        root_codec = MockCodec()
        mid_codec = MockCodec()
        deep_kc.register_codec("document", root_codec)
        deep_kc.register_codec("specification", mid_codec)
        elem = deep_kc.element("ds-001")
        elem.compile()
        assert len(mid_codec.compile_calls) == 1
        assert len(root_codec.compile_calls) == 0

    def test_decompile_inherits(self, qa_kc):
        """Decompile also inherits codecs."""
        codec = MockCodec()
        codec.decompile_return = {"title": "Inherited", "format": "TXT"}
        qa_kc.register_codec("document", codec)
        elem = qa_kc.element("spec-001")
        elem.decompile()
        assert elem.attrs["title"] == "Inherited"

    def test_decompile_uri_inherits(self, qa_kc):
        """decompile_uri also inherits codecs."""
        codec = MockCodec()
        codec.decompile_return = {"title": "Via Parent"}
        qa_kc.register_codec("document", codec)
        result = qa_kc.decompile_uri("specification", "file:///x")
        assert result == {"title": "Via Parent"}


# ===========================================================================
# Round-trip test
# ===========================================================================

class TestRoundTrip:

    def test_compile_then_decompile(self, qa_kc, tmp_path):
        """Write to file via compile, read back via decompile, attrs match."""
        uri = f"file://{tmp_path / 'spec.json'}"

        # Re-create with temp URI
        sb = SchemaBuilder(namespace="qa")
        sb.add_vertex_type("document", attributes={"title": text()})
        sb.add_vertex_type("specification", parent="document",
                           attributes={"format": text()})
        kc = KnowledgeComplex(schema=sb)
        kc.add_vertex("spec-001", type="specification",
                      title="Round Trip Spec", format="PDF", uri=uri)

        codec = JsonFileCodec()
        kc.register_codec("specification", codec)

        # Compile: write to file
        elem = kc.element("spec-001")
        elem.compile()
        written = json.loads(Path(tmp_path / "spec.json").read_text())
        assert written["title"] == "Round Trip Spec"
        assert written["format"] == "PDF"

        # Modify the file externally
        written["title"] = "Modified Externally"
        Path(tmp_path / "spec.json").write_text(json.dumps(written))

        # Decompile: read back
        elem.decompile()
        assert elem.attrs["title"] == "Modified Externally"
        assert elem.attrs["format"] == "PDF"
