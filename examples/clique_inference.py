"""
clique_inference.py — Flagification and typed face inference.

Demonstrates the explore → inspect → type workflow:
  1. Build a social network with only vertices and edges
  2. Discover what triangles (3-cliques) exist
  3. Fill them generically to explore the structure
  4. Re-build with typed face inference for semantic meaning

Run:
    pip install knowledgecomplex[viz]
    python examples/clique_inference.py
"""

from knowledgecomplex import (
    SchemaBuilder, KnowledgeComplex, vocab,
    find_cliques, infer_faces, fill_cliques,
    plot_hasse, plot_geometric,
)
import matplotlib.pyplot as plt

# ── Phase 1: Build a social network (vertices + edges only) ────────────────

sb = SchemaBuilder(namespace="social")
sb.add_vertex_type("Person")
sb.add_edge_type("Collaborates")
sb.add_edge_type("Mentors")
sb.add_face_type("Team")  # declared but not yet populated

kc = KnowledgeComplex(schema=sb)

# 5 people
for name in ["alice", "bob", "carol", "dave", "eve"]:
    kc.add_vertex(name, type="Person")

# Collaboration edges (form several triangles)
kc.add_edge("c-ab", type="Collaborates", vertices={"alice", "bob"})
kc.add_edge("c-ac", type="Collaborates", vertices={"alice", "carol"})
kc.add_edge("c-bc", type="Collaborates", vertices={"bob", "carol"})
kc.add_edge("c-bd", type="Collaborates", vertices={"bob", "dave"})
kc.add_edge("c-cd", type="Collaborates", vertices={"carol", "dave"})
kc.add_edge("c-de", type="Collaborates", vertices={"dave", "eve"})

# A mentoring edge (different type — won't form team triangles)
kc.add_edge("m-ae", type="Mentors", vertices={"alice", "eve"})

print("=== Network built ===")
print(f"  {len(kc.skeleton(0))} people, {len(kc.skeleton(1) - kc.skeleton(0))} relationships")
print()

# ── Phase 2: Discover cliques ──────────────────────────────────────────────

print("=== find_cliques: what triangles exist? ===")
all_triangles = find_cliques(kc, k=3)
print(f"  All 3-cliques (any edge type): {len(all_triangles)}")
for tri in all_triangles:
    print(f"    {sorted(tri)}")
print()

# Filter to collaboration-only triangles
collab_triangles = find_cliques(kc, k=3, edge_type="Collaborates")
print(f"  Collaboration-only 3-cliques: {len(collab_triangles)}")
for tri in collab_triangles:
    print(f"    {sorted(tri)}")
print()

# ── Phase 3: Dry run — preview what would be added ─────────────────────────

print("=== infer_faces dry run ===")
preview = infer_faces(kc, "Team", edge_type="Collaborates", dry_run=True)
print(f"  Would add {len(preview)} Team faces: {preview}")
print(f"  Current face count: {len(kc.skeleton(2) - kc.skeleton(1))}")
print()

# ── Phase 4: Typed inference — fill Team faces ─────────────────────────────

print("=== infer_faces: filling Team faces ===")
added = infer_faces(kc, "Team", edge_type="Collaborates", id_prefix="team")
print(f"  Added {len(added)} faces: {added}")
print()

# Inspect what was created
for fid in added:
    edges = kc.boundary(fid)
    edge_types = {kc.element(e).type for e in edges}
    vertices = set()
    for e in edges:
        vertices |= kc.boundary(e)
    print(f"  {fid}: members={sorted(vertices)}, edge_types={edge_types}")
print()

# Idempotent — running again adds nothing
second_run = infer_faces(kc, "Team", edge_type="Collaborates")
print(f"  Second run added {len(second_run)} faces (idempotent)")
print()

# ── Phase 5: Visualize ─────────────────────────────────────────────────────

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))

# Hasse diagram — shows all elements as nodes with directed boundary arrows
plot_hasse(kc, ax=ax1)
ax1.set_title("Hasse Diagram (after inference)")

# We need a separate figure for 3D
plt.tight_layout()
fig.savefig("examples/clique_hasse.png", dpi=150, bbox_inches="tight")
print("Saved examples/clique_hasse.png")
plt.close(fig)

# Geometric realization — vertices as 3D points, edges as lines, faces as triangles
fig, ax = plot_geometric(kc, figsize=(10, 8))
fig.savefig("examples/clique_geometric.png", dpi=150, bbox_inches="tight")
print("Saved examples/clique_geometric.png")
plt.close(fig)
