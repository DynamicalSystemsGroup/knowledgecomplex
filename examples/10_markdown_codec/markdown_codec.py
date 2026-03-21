"""
markdown_codec.py — Round-trip between KC elements and YAML+markdown files.

Models a research literature domain:
  - 3 Concepts (vertices): attention, transformers, scaling
  - 2 Papers (vertices): "Attention Is All You Need", "BERT"
  - 3 edge types covering all vertex-pair combinations:
      * Considers (Paper × Concept): how a paper engages a concept
      * Cites (Paper × Paper): how papers build on each other
      * Relates (Concept × Concept): how concepts connect
  - 2 face types for the rich triangular semantics:
      * Debate (Paper × Paper × Concept): two papers' agreement/disagreement on one concept
      * Comparison (Paper × Concept × Concept): how a paper interrelates two concepts

Demonstrates:
  1. Build KC with elements and URIs pointing to markdown files
  2. Register MarkdownCodec for each type
  3. Compile all elements to markdown files
  4. Simulate an external edit (Obsidian user adds notes)
  5. Decompile: read changes back into the KC
  6. Verify KC ↔ filesystem consistency

Run:
    python examples/10_markdown_codec/markdown_codec.py
"""

import tempfile
from pathlib import Path

from knowledgecomplex import SchemaBuilder, KnowledgeComplex, text, vocab
from knowledgecomplex.codecs import MarkdownCodec, verify_documents

# ── Schema ──────────────────────────────────────────────────────────────────

sb = SchemaBuilder(namespace="lit")

# Vertex types
sb.add_vertex_type("Concept", attributes={
    "name": text(),
    "description": text(),
    "notes": text(required=False),
})
sb.add_vertex_type("Paper", attributes={
    "name": text(),
    "author": text(),
    "abstract": text(),
    "notes": text(required=False),
})

# Edge types — all 3 vertex-pair combinations
sb.add_edge_type("Considers", attributes={
    "context": text(),
    "notes": text(required=False),
})
sb.add_edge_type("Cites", attributes={
    "context": text(),
    "notes": text(required=False),
})
sb.add_edge_type("Relates", attributes={
    "context": text(),
    "notes": text(required=False),
})

# Face types — rich triangular semantics
sb.add_face_type("Debate", attributes={
    "summary": text(),
    "notes": text(required=False),
})
sb.add_face_type("Comparison", attributes={
    "summary": text(),
    "notes": text(required=False),
})

# ── Build KC in a temp directory ────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    root = Path(tmpdir)

    kc = KnowledgeComplex(schema=sb)

    # Helper to build file URIs
    def uri(name: str) -> str:
        return f"file://{root / name}.md"

    # --- Vertices ---

    kc.add_vertex("attention", type="Concept", uri=uri("concept-attention"),
                  name="Attention Mechanisms",
                  description="Weighted aggregation of sequence elements",
                  notes="")

    kc.add_vertex("transformers", type="Concept", uri=uri("concept-transformers"),
                  name="Transformer Architecture",
                  description="Self-attention based sequence model",
                  notes="")

    kc.add_vertex("scaling", type="Concept", uri=uri("concept-scaling"),
                  name="Scaling Laws",
                  description="Performance as a function of model and data size",
                  notes="")

    kc.add_vertex("vaswani", type="Paper", uri=uri("paper-vaswani"),
                  name="Attention Is All You Need",
                  author="Vaswani et al.",
                  abstract="Proposes the Transformer, dispensing with recurrence entirely",
                  notes="")

    kc.add_vertex("devlin", type="Paper", uri=uri("paper-devlin"),
                  name="BERT: Pre-training of Deep Bidirectional Transformers",
                  author="Devlin et al.",
                  abstract="Bidirectional pre-training via masked language modeling",
                  notes="")

    # --- Edges (all 3 pairings) ---

    # Paper × Concept
    kc.add_edge("vaswani-attention", type="Considers",
                vertices={"vaswani", "attention"}, uri=uri("considers-vaswani-attention"),
                context="Introduces multi-head attention as the core mechanism",
                notes="")

    kc.add_edge("vaswani-transformers", type="Considers",
                vertices={"vaswani", "transformers"}, uri=uri("considers-vaswani-transformers"),
                context="Defines the Transformer architecture",
                notes="")

    kc.add_edge("devlin-attention", type="Considers",
                vertices={"devlin", "attention"}, uri=uri("considers-devlin-attention"),
                context="Extends attention to bidirectional context",
                notes="")

    # Paper × Paper
    kc.add_edge("devlin-cites-vaswani", type="Cites",
                vertices={"devlin", "vaswani"}, uri=uri("cites-devlin-vaswani"),
                context="BERT builds directly on the Transformer architecture",
                notes="")

    # Concept × Concept
    kc.add_edge("attention-transformers", type="Relates",
                vertices={"attention", "transformers"}, uri=uri("relates-attention-transformers"),
                context="Attention is the fundamental building block of transformers",
                notes="")

    # --- Faces ---

    # Debate: Paper × Paper × Concept (two papers on one concept)
    kc.add_face("debate-attention", type="Debate",
                boundary=["vaswani-attention", "devlin-attention", "devlin-cites-vaswani"],
                uri=uri("debate-attention"),
                summary="Vaswani introduces attention; Devlin extends it bidirectionally. "
                        "The debate: is unidirectional attention sufficient?",
                notes="")

    # Comparison: Paper × Concept × Concept (one paper, two concepts)
    kc.add_face("comparison-vaswani", type="Comparison",
                boundary=["vaswani-attention", "vaswani-transformers", "attention-transformers"],
                uri=uri("comparison-vaswani"),
                summary="Vaswani bridges attention and transformers — showing that "
                        "attention alone is sufficient for state-of-the-art sequence modeling",
                notes="")

    print(f"Built KC: {len(kc.element_ids())} elements")
    print()

    # ── Register codecs ────────────────────────────────────────────────────

    concept_codec = MarkdownCodec(
        frontmatter_attrs=["name", "description"],
        section_attrs=["notes"],
    )
    paper_codec = MarkdownCodec(
        frontmatter_attrs=["name", "author", "abstract"],
        section_attrs=["notes"],
    )
    edge_codec = MarkdownCodec(
        frontmatter_attrs=["context"],
        section_attrs=["notes"],
    )
    face_codec = MarkdownCodec(
        frontmatter_attrs=["summary"],
        section_attrs=["notes"],
    )

    kc.register_codec("Concept", concept_codec)
    kc.register_codec("Paper", paper_codec)
    kc.register_codec("Considers", edge_codec)
    kc.register_codec("Cites", edge_codec)
    kc.register_codec("Relates", edge_codec)
    kc.register_codec("Debate", face_codec)
    kc.register_codec("Comparison", face_codec)

    # ── Compile: KC → markdown files ───────────────────────────────────────

    print("=== Compiling all elements to markdown ===")
    for eid in sorted(kc.element_ids()):
        elem = kc.element(eid)
        if elem.uri:
            elem.compile()

    # Show what was written
    for f in sorted(root.glob("*.md")):
        print(f"  {f.name}  ({f.stat().st_size} bytes)")
    print()

    # Show one file's content
    sample = root / "paper-vaswani.md"
    print(f"=== Content of {sample.name} ===")
    print(sample.read_text())

    # ── Verify: KC ↔ filesystem ────────────────────────────────────────────

    print("=== Verify (should be clean) ===")
    issues = verify_documents(kc, root)
    if not issues:
        print("  All elements match their files.")
    else:
        for issue in issues:
            print(f"  {issue}")
    print()

    # ── Simulate external edit (Obsidian user adds notes) ──────────────────

    print("=== Simulating external edit ===")
    vaswani_file = root / "paper-vaswani.md"
    original = vaswani_file.read_text()
    modified = original.replace(
        "## Notes\n\n(empty)",
        "## Notes\n\nSeminal paper — introduced positional encoding and "
        "multi-head attention. Key insight: parallelizable training."
    )
    vaswani_file.write_text(modified)
    print(f"  Modified {vaswani_file.name} — added notes")
    print()

    # ── Verify: detects the mismatch ───────────────────────────────────────

    print("=== Verify (should detect mismatch) ===")
    issues = verify_documents(kc, root)
    for issue in issues:
        print(f"  {issue}")
    print()

    # ── Decompile: read changes back into KC ───────────────────────────────

    print("=== Decompile: reading changes back ===")
    before = kc.element("vaswani").attrs.get("notes", "(none)")
    print(f"  Before decompile: notes = '{before}'")

    kc.element("vaswani").decompile()

    after = kc.element("vaswani").attrs.get("notes", "(none)")
    print(f"  After decompile:  notes = '{after}'")
    print()

    # ── Verify again: should be clean ──────────────────────────────────────

    print("=== Verify (should be clean again) ===")
    issues = verify_documents(kc, root)
    if not issues:
        print("  All elements match their files.")
    else:
        for issue in issues:
            print(f"  {issue}")
    print()

    print("Done.")
