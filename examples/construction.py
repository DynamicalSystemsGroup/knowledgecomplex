"""
quickstart.py — Runnable version of the README quick-start example.

Models a data pipeline as a typed simplicial complex:
  - 4 vertices: an actor, an activity, and two resources
  - 5 edges: performs, requires, produces, accesses, responsible
  - 2 faces: an operation triangle and a production triangle

Run:
    pip install knowledgecomplex[viz,analysis]
    python examples/quickstart.py
"""

from knowledgecomplex import SchemaBuilder, KnowledgeComplex, vocab, text

# 1. Define a schema
sb = SchemaBuilder(namespace="ex")
sb.add_vertex_type("actor",    attributes={"name": text()})
sb.add_vertex_type("activity", attributes={"name": text()})
sb.add_vertex_type("resource", attributes={"name": text()})
sb.add_edge_type("performs",     attributes={"role": vocab("lead", "support")})
sb.add_edge_type("requires",    attributes={"mode": vocab("read", "write")})
sb.add_edge_type("produces",    attributes={"mode": vocab("read", "write")})
sb.add_edge_type("accesses",    attributes={"mode": vocab("read", "write")})
sb.add_edge_type("responsible", attributes={"level": vocab("owner", "steward")})
sb.add_face_type("operation")
sb.add_face_type("production")

# 2. Build an instance
kc = KnowledgeComplex(schema=sb)
kc.add_vertex("alice",    type="actor",    name="Alice")
kc.add_vertex("etl-run",  type="activity", name="Daily ETL")
kc.add_vertex("dataset1", type="resource", name="JSON Records")
kc.add_vertex("dataset2", type="resource", name="Sales DB")

kc.add_edge("e1", type="performs",    vertices={"alice", "etl-run"},    role="lead")
kc.add_edge("e2", type="requires",   vertices={"etl-run", "dataset1"}, mode="read")
kc.add_edge("e3", type="produces",   vertices={"etl-run", "dataset2"}, mode="write")
kc.add_edge("e4", type="accesses",   vertices={"alice", "dataset1"},   mode="read")
kc.add_edge("e5", type="responsible", vertices={"alice", "dataset2"},  level="owner")

kc.add_face("op1",   type="operation",  boundary=["e1", "e2", "e4"])
kc.add_face("prod1", type="production", boundary=["e1", "e3", "e5"])

# 3. Query
print("=== Vertices ===")
df = kc.query("vertices")
print(df)
print()

# 4. Topological queries
print("=== Boundary of face op1 ===")
print(kc.boundary("op1"))
print()

print("=== Star of alice (all simplices containing alice) ===")
print(kc.star("alice"))
print()

print("=== Skeleton k=1 (vertices + edges only) ===")
print(kc.skeleton(1))
print()

# 5. Algebraic topology
from knowledgecomplex import betti_numbers, euler_characteristic, edge_pagerank, edge_influence

betti = betti_numbers(kc)
chi = euler_characteristic(kc)
print(f"=== Betti numbers: {betti} ===")
print(f"  beta_0 = {betti[0]}  (connected components)")
print(f"  beta_1 = {betti[1]}  (independent cycles)")
print(f"  beta_2 = {betti[2]}  (enclosed voids)")
print(f"  Euler characteristic chi = {chi}  (V - E + F = {len(kc.skeleton(0))} - {len(kc.skeleton(1) - kc.skeleton(0))} + {len(kc.skeleton(2) - kc.skeleton(1))})")
print()

# Edge PageRank — measure influence of each edge on the complex
from knowledgecomplex import boundary_matrices
bm = boundary_matrices(kc)
print("=== Edge PageRank (influence ranking) ===")
for eid in sorted(bm.edge_index):
    pr = edge_pagerank(kc, eid)
    infl = edge_influence(eid, pr)
    print(f"  {eid:12s}  spread={infl.spread:.3f}  influence={infl.absolute_influence:.3f}")
print()

# 6. Inspect the RDF
print("=== Turtle dump ===")
print(kc.dump_graph())

# 6. Visualize — Hasse diagrams (elements as nodes, boundary as directed arrows)
from knowledgecomplex import (
    to_networkx, verify_networkx,
    plot_hasse, plot_hasse_star, plot_geometric,
)
import matplotlib.pyplot as plt

# Export to directed networkx graph and verify invariants
G = to_networkx(kc)
verify_networkx(G)
print(f"DiGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} directed edges")
print()

# Hasse diagram — arrows point from faces→edges→vertices (high→low dim)
fig, ax = plot_hasse(kc, figsize=(12, 9))
fig.savefig("examples/hasse.png", dpi=150, bbox_inches="tight")
print("Saved examples/hasse.png")
plt.close(fig)

# Hasse star of alice — her neighborhood highlighted
fig, ax = plot_hasse_star(kc, "alice", figsize=(12, 9))
fig.savefig("examples/hasse_star_alice.png", dpi=150, bbox_inches="tight")
print("Saved examples/hasse_star_alice.png")
plt.close(fig)

# 7. Geometric realization — vertices as 3D points, edges as lines, faces as triangles
fig, ax = plot_geometric(kc, figsize=(12, 9))
fig.savefig("examples/geometric.png", dpi=150, bbox_inches="tight")
print("Saved examples/geometric.png")
plt.close(fig)
