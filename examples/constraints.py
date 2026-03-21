"""
constraints.py — Topological constraint escalation and schema-level queries.

Models a V&V (verification & validation) system where:
  - Requirements (vertices) must each have at least one verification edge
  - Edges connect requirements to test artifacts

Demonstrates how topological queries can be escalated to SHACL constraints
that are enforced at write time, and how named queries can be registered
on the schema for reuse.

Run:
    python examples/constraints.py
"""

from knowledgecomplex import SchemaBuilder, KnowledgeComplex, vocab, ValidationError

# ── Schema with topological constraints ────────────────────────────────────

sb = SchemaBuilder(namespace="vv")

sb.add_vertex_type("Requirement", attributes={"priority": vocab("high", "medium", "low")})
sb.add_vertex_type("TestCase",    attributes={"status": vocab("pass", "fail", "pending")})
sb.add_edge_type("Verifies")
sb.add_face_type("Coverage")

# Register a named query: "for a given requirement, find all verification edges"
sb.add_query("req_verifications", "coboundary", target_type="Verifies")
print("=== Registered named query: req_verifications ===")
print()

# Export schema to see generated SPARQL
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    sb.export(tmpdir)
    sparql_file = Path(tmpdir) / "queries" / "req_verifications.sparql"
    if sparql_file.exists():
        print("=== Generated SPARQL template ===")
        print(sparql_file.read_text())

# ── Build a valid complex (no constraints yet) ─────────────────────────────

print("=== Building complex WITHOUT constraints ===")
kc = KnowledgeComplex(schema=sb)
kc.add_vertex("req-1", type="Requirement", priority="high")
kc.add_vertex("req-2", type="Requirement", priority="medium")
kc.add_vertex("test-a", type="TestCase", status="pass")
kc.add_vertex("test-b", type="TestCase", status="pending")

kc.add_edge("v1", type="Verifies", vertices={"req-1", "test-a"})
kc.add_edge("v2", type="Verifies", vertices={"req-1", "test-b"})
kc.add_edge("v3", type="Verifies", vertices={"req-2", "test-a"})

print(f"  Added {len(kc.skeleton(0))} vertices, {len(kc.skeleton(1) - kc.skeleton(0))} edges")
print(f"  req-1 verifications: {kc.coboundary('req-1', type='Verifies')}")
print(f"  req-2 verifications: {kc.coboundary('req-2', type='Verifies')}")
print()

# ── Now add a max_count constraint ─────────────────────────────────────────

print("=== Schema with max_count constraint ===")
sb2 = SchemaBuilder(namespace="vv")
sb2.add_vertex_type("Requirement", attributes={"priority": vocab("high", "medium", "low")})
sb2.add_vertex_type("TestCase",    attributes={"status": vocab("pass", "fail", "pending")})
sb2.add_edge_type("Verifies")

# Each TestCase can verify at most 2 requirements
sb2.add_topological_constraint(
    "TestCase", "coboundary",
    target_type="Verifies",
    predicate="max_count", max_count=2,
    message="A test case can verify at most 2 requirements",
)

kc2 = KnowledgeComplex(schema=sb2)
kc2.add_vertex("req-1", type="Requirement", priority="high")
kc2.add_vertex("req-2", type="Requirement", priority="medium")
kc2.add_vertex("req-3", type="Requirement", priority="low")
kc2.add_vertex("test-a", type="TestCase", status="pass")

kc2.add_edge("v1", type="Verifies", vertices={"req-1", "test-a"})
kc2.add_edge("v2", type="Verifies", vertices={"req-2", "test-a"})
print("  Added 2 verification edges to test-a (within limit)")

# Third edge would exceed max_count=2
try:
    kc2.add_edge("v3", type="Verifies", vertices={"req-3", "test-a"})
    print("  ERROR: should have raised!")
except ValidationError as e:
    print(f"  Third edge correctly rejected: {e}")
print()

# ── Inspect generated SHACL ────────────────────────────────────────────────

print("=== Generated SHACL (excerpt) ===")
shacl = sb2.dump_shacl()
# Show just the constraint-related lines
for line in shacl.split("\n"):
    if "Topological" in line or "max_count" in line or "coboundary" in line:
        print(f"  {line.strip()}")
print()

print("Done.")
