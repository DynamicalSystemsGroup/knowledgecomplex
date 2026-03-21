"""
io_roundtrip.py — Multi-format I/O and additive loading.

Demonstrates:
  - Saving instance graphs in Turtle, JSON-LD, and N-Triples
  - Loading data additively into an existing complex
  - Directory-based export/load for full round-trips
  - String serialization with dump_graph()

Run:
    python examples/io_roundtrip.py
"""

import tempfile
from pathlib import Path

from knowledgecomplex import (
    SchemaBuilder, KnowledgeComplex, vocab,
    save_graph, load_graph, dump_graph,
)

# ── Build a simple complex ─────────────────────────────────────────────────

sb = SchemaBuilder(namespace="io")
sb.add_vertex_type("Node")
sb.add_edge_type("Link", attributes={"weight": vocab("light", "heavy")})
sb.add_face_type("Triangle")

kc = KnowledgeComplex(schema=sb)
kc.add_vertex("a", type="Node")
kc.add_vertex("b", type="Node")
kc.add_vertex("c", type="Node")
kc.add_edge("ab", type="Link", vertices={"a", "b"}, weight="heavy")
kc.add_edge("bc", type="Link", vertices={"b", "c"}, weight="light")
kc.add_edge("ac", type="Link", vertices={"a", "c"}, weight="light")
kc.add_face("f1", type="Triangle", boundary=["ab", "bc", "ac"])

print(f"Built complex: {len(kc.element_ids())} elements")
print()

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)

    # ── Multi-format export ────────────────────────────────────────────────

    print("=== Saving in multiple formats ===")
    save_graph(kc, tmp / "data.ttl")
    save_graph(kc, tmp / "data.jsonld", format="json-ld")
    save_graph(kc, tmp / "data.nt", format="ntriples")

    for f in sorted(tmp.glob("data.*")):
        size = f.stat().st_size
        print(f"  {f.name:15s}  {size:>6} bytes")
    print()

    # ── JSON-LD string output ──────────────────────────────────────────────

    print("=== JSON-LD string (first 500 chars) ===")
    jsonld = dump_graph(kc, format="json-ld")
    print(jsonld[:500])
    print("...")
    print()

    # ── Load into a fresh KC ───────────────────────────────────────────────

    print("=== Loading from JSON-LD into fresh KC ===")
    fresh = KnowledgeComplex(schema=sb)
    print(f"  Fresh KC before load: {len(fresh.element_ids())} elements")
    load_graph(fresh, tmp / "data.jsonld")
    print(f"  Fresh KC after load:  {len(fresh.element_ids())} elements")
    print()

    # ── Additive loading (merge two datasets) ──────────────────────────────

    print("=== Additive loading: merging two datasets ===")

    # Build a second dataset with different elements
    kc2 = KnowledgeComplex(schema=sb)
    kc2.add_vertex("d", type="Node")
    kc2.add_vertex("e", type="Node")
    kc2.add_edge("de", type="Link", vertices={"d", "e"}, weight="heavy")
    save_graph(kc2, tmp / "dataset2.ttl")

    # Load both into one KC
    merged = KnowledgeComplex(schema=sb)
    load_graph(merged, tmp / "data.ttl")
    count_after_first = len(merged.element_ids())
    load_graph(merged, tmp / "dataset2.ttl")
    count_after_second = len(merged.element_ids())

    print(f"  After loading dataset 1: {count_after_first} elements")
    print(f"  After loading dataset 2: {count_after_second} elements (additive)")
    print()

    # ── Directory-based export/load ────────────────────────────────────────

    print("=== Directory export/load (full round-trip) ===")
    export_dir = tmp / "exported"
    kc.export(export_dir)
    print(f"  Exported to {export_dir}:")
    for f in sorted(export_dir.rglob("*")):
        if f.is_file():
            print(f"    {f.relative_to(export_dir)}")

    loaded = KnowledgeComplex.load(export_dir)
    print(f"  Loaded back: {len(loaded.element_ids())} elements")
    print()

print("Done.")
