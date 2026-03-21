"""
diff_sequence.py — Diff-based complex sequences with SPARQL export.

Models a project evolving sprint-by-sprint via explicit diffs.
Each sprint's changes are recorded as a ComplexDiff — additions and
removals of elements. The diffs can be exported to SPARQL UPDATE
strings for interoperability with RDF-native systems like flexo MMS,
or imported from remote SPARQL updates.

Run:
    python examples/09_diff_sequence/diff_sequence.py
"""

from knowledgecomplex import (
    SchemaBuilder, KnowledgeComplex, vocab,
    ComplexDiff, ComplexSequence,
)

# ── Schema ──────────────────────────────────────────────────────────────────

sb = SchemaBuilder(namespace="sprint")
sb.add_vertex_type("Feature",  attributes={"status": vocab("planned", "active", "done")})
sb.add_vertex_type("Engineer")
sb.add_edge_type("WorksOn")
sb.add_edge_type("DependsOn")
sb.add_face_type("WorkPackage")

# ── Base state (Sprint 0) ──────────────────────────────────────────────────

kc = KnowledgeComplex(schema=sb)

kc.add_vertex("auth",    type="Feature",  status="active")
kc.add_vertex("api",     type="Feature",  status="planned")
kc.add_vertex("alice",   type="Engineer")
kc.add_vertex("bob",     type="Engineer")
kc.add_edge("alice-auth", type="WorksOn", vertices={"alice", "auth"})
kc.add_edge("bob-auth",   type="WorksOn", vertices={"bob", "auth"})
kc.add_edge("alice-bob",  type="WorksOn", vertices={"alice", "bob"})

print("=== Sprint 0 (base state) ===")
print(f"  Elements: {sorted(kc.element_ids())}")
print()

# ── Sprint 1: API work begins, auth wraps up ──────────────────────────────

sprint1 = (
    ComplexDiff()
    .add_vertex("carol", type="Engineer")
    .add_edge("carol-api", type="WorksOn", vertices={"carol", "api"})
    .add_edge("alice-api", type="WorksOn", vertices={"alice", "api"})
    .add_edge("dep-api-auth", type="DependsOn", vertices={"api", "auth"})
)

# ── Sprint 2: Bob moves to API, triangle forms ────────────────────────────

sprint2 = (
    ComplexDiff()
    .remove("bob-auth")   # Bob stops working on auth
    .add_edge("bob-api", type="WorksOn", vertices={"bob", "api"})
    .add_edge("bob-carol", type="WorksOn", vertices={"bob", "carol"})
    .add_face("wp-api", type="WorkPackage",
              boundary=["alice-api", "bob-api", "alice-bob"])
)

# ── Sprint 3: Auth feature done, alice moves off ──────────────────────────

sprint3 = (
    ComplexDiff()
    .remove("wp-api")       # work package dissolves
    .remove("alice-auth")   # alice leaves auth
)

# ── Build the sequence ─────────────────────────────────────────────────────

seq = ComplexSequence(kc, [sprint1, sprint2, sprint3])

print("=== Complex evolution across sprints ===")
base_ids = set(kc.element_ids())
print(f"  Sprint 0 (base): {len(base_ids)} elements")
for i in range(len(seq)):
    step = seq[i]
    new = seq.new_at(i)
    removed = seq.removed_at(i)
    print(f"  Sprint {i+1}: {len(step)} elements  (+{len(new)} -{len(removed)})")
    if new:
        print(f"    added:   {sorted(new)}")
    if removed:
        print(f"    removed: {sorted(removed)}")
print()

# ── Apply diffs to see the actual complex at each state ────────────────────

print("=== Applying diffs sequentially ===")

# Sprint 1
sprint1.apply(kc)
print(f"  After Sprint 1: {sorted(kc.element_ids())}")

# Sprint 2
sprint2.apply(kc)
print(f"  After Sprint 2: {sorted(kc.element_ids())}")

# Sprint 3
sprint3.apply(kc)
print(f"  After Sprint 3: {sorted(kc.element_ids())}")
print()

# ── SPARQL export (for flexo MMS interoperability) ─────────────────────────

# Re-build to export sprint2's SPARQL from the right state
kc2 = KnowledgeComplex(schema=sb)
kc2.add_vertex("auth",    type="Feature",  status="active")
kc2.add_vertex("api",     type="Feature",  status="planned")
kc2.add_vertex("alice",   type="Engineer")
kc2.add_vertex("bob",     type="Engineer")
kc2.add_vertex("carol",   type="Engineer")
kc2.add_edge("alice-auth", type="WorksOn", vertices={"alice", "auth"})
kc2.add_edge("bob-auth",   type="WorksOn", vertices={"bob", "auth"})
kc2.add_edge("alice-bob",  type="WorksOn", vertices={"alice", "bob"})
kc2.add_edge("carol-api",  type="WorksOn", vertices={"carol", "api"})
kc2.add_edge("alice-api",  type="WorksOn", vertices={"alice", "api"})
kc2.add_edge("dep-api-auth", type="DependsOn", vertices={"api", "auth"})

print("=== SPARQL UPDATE for Sprint 2 ===")
sparql = sprint2.to_sparql(kc2)
print(sparql[:600])
if len(sparql) > 600:
    print("...")
print()

# ── Round-trip: import the SPARQL back ─────────────────────────────────────

print("=== SPARQL round-trip ===")
imported = ComplexDiff.from_sparql(sparql, kc2)
print(f"  Original:  {sprint2}")
print(f"  Imported:  {imported}")
print(f"  Additions match: {len(imported.additions) == len(sprint2.additions)}")
print(f"  Removals match:  {len(imported.removals) >= 1}")
print()

# Apply the imported diff
imported.apply(kc2)
print(f"  After applying imported diff: {len(kc2.element_ids())} elements")
print()

print("Done.")
