"""
local_partition.py — Find clusters using diffusion, not just adjacency.

Builds a "barbell" complex: two triangles joined by a single bridge edge.
Uses graph partitioning (PageRank and heat kernel) to find the two clusters,
then uses edge partitioning (Hodge Laplacian) to cluster the relationships.

The key insight: topological queries (boundary, star, closure) walk the
combinatorial structure directly. Partitioning uses *diffusion* — spreading
probability from a seed and sweeping the result to find where the flow
bottlenecks. This finds natural cluster boundaries that adjacency alone
can't identify.

Run:
    pip install knowledgecomplex[analysis]
    python examples/11_local_partition/local_partition.py
"""

from knowledgecomplex import SchemaBuilder, KnowledgeComplex
from knowledgecomplex.analysis import (
    approximate_pagerank,
    heat_kernel_pagerank,
    sweep_cut,
    local_partition,
    edge_local_partition,
    betti_numbers,
)

# ── Build a barbell: two triangles joined by a bridge ────────────────────

sb = SchemaBuilder(namespace="net")
sb.add_vertex_type("Node")
sb.add_edge_type("Link")
sb.add_face_type("Cell")

kc = KnowledgeComplex(schema=sb)

# Left triangle
kc.add_vertex("L1", type="Node")
kc.add_vertex("L2", type="Node")
kc.add_vertex("L3", type="Node")
kc.add_edge("eL12", type="Link", vertices={"L1", "L2"})
kc.add_edge("eL23", type="Link", vertices={"L2", "L3"})
kc.add_edge("eL13", type="Link", vertices={"L1", "L3"})
kc.add_face("fL", type="Cell", boundary=["eL12", "eL23", "eL13"])

# Bridge
kc.add_vertex("B", type="Node")
kc.add_edge("bridge", type="Link", vertices={"L2", "B"})

# Right triangle
kc.add_vertex("R1", type="Node")
kc.add_vertex("R2", type="Node")
kc.add_edge("eR1B", type="Link", vertices={"B", "R1"})
kc.add_edge("eR12", type="Link", vertices={"R1", "R2"})
kc.add_edge("eRB2", type="Link", vertices={"B", "R2"})
kc.add_face("fR", type="Cell", boundary=["eR1B", "eR12", "eRB2"])

print(f"Complex: {len(kc.element_ids())} elements")
print(f"Betti numbers: {betti_numbers(kc)}")
print()

# ── Graph partitioning: vertex clusters via PageRank ─────────────────────

print("=== Approximate PageRank from L1 ===")
p, r = approximate_pagerank(kc, seed="L1", alpha=0.15)
for v in sorted(p, key=lambda v: -p[v]):
    print(f"  {v:4s}  {p[v]:.4f}")
print()

cut = sweep_cut(kc, p)
print(f"Best sweep cut: {sorted(cut.vertices)}")
print(f"  conductance: {cut.conductance:.4f}")
print()

# ── Heat kernel: different diffusion profile ─────────────────────────────

print("=== Heat Kernel PageRank from L1 (t=3) ===")
rho = heat_kernel_pagerank(kc, seed="L1", t=3.0)
for v in sorted(rho, key=lambda v: -rho[v]):
    print(f"  {v:4s}  {rho[v]:.4f}")
print()

cut_hk = sweep_cut(kc, rho)
print(f"Heat kernel cut: {sorted(cut_hk.vertices)}")
print(f"  conductance: {cut_hk.conductance:.4f}")
print()

# ── local_partition: one-call convenience ────────────────────────────────

print("=== local_partition (one call) ===")
cut_pr = local_partition(kc, seed="L1", method="pagerank")
cut_hk2 = local_partition(kc, seed="L1", method="heat_kernel")
print(f"PageRank method:    {sorted(cut_pr.vertices)}, conductance={cut_pr.conductance:.4f}")
print(f"Heat kernel method: {sorted(cut_hk2.vertices)}, conductance={cut_hk2.conductance:.4f}")
print()

# ── Edge partitioning: relationship clusters via Hodge Laplacian ─────────

print("=== Edge local partition (Hodge) ===")
print("Starting from edge eL12 (inside left triangle):")
edge_cut_pr = edge_local_partition(kc, seed_edge="eL12", method="hodge_pagerank")
print(f"  Hodge PageRank: {sorted(edge_cut_pr.edges)}, conductance={edge_cut_pr.conductance:.4f}")

edge_cut_hk = edge_local_partition(kc, seed_edge="eL12", method="hodge_heat", t=3.0)
print(f"  Hodge heat:     {sorted(edge_cut_hk.edges)}, conductance={edge_cut_hk.conductance:.4f}")
print()

# ── Compare: combinatorial vs diffusion ──────────────────────────────────

print("=== Combinatorial star vs diffusion partition ===")
star_L1 = kc.star("L1")
print(f"Star(L1):      {sorted(star_L1)}")
print(f"  → includes everything L1 touches, regardless of cluster structure")
print()
print(f"Partition(L1): {sorted(cut_pr.vertices)}")
print(f"  → finds the natural cluster boundary via diffusion bottleneck")
