"""
topology_walkthrough.py — All 8 topological operators with set algebra.

Models a small research collaboration network as a double-triangle complex:
  - 4 researchers (vertices): alice, bob, carol, dave
  - 5 collaborations (edges): linking pairs of researchers
  - 2 papers (faces): each authored by a triangle of collaborators

Run:
    python examples/topology_walkthrough.py
"""

from knowledgecomplex import SchemaBuilder, KnowledgeComplex, vocab

# ── Schema ──────────────────────────────────────────────────────────────────

sb = SchemaBuilder(namespace="research")
sb.add_vertex_type("Researcher", attributes={"field": vocab("ML", "Systems", "Theory")})
sb.add_edge_type("Collaborates")
sb.add_face_type("Paper")

kc = KnowledgeComplex(schema=sb)

# ── Build the complex ───────────────────────────────────────────────────────
# Two triangles sharing the alice-bob edge:
#
#   carol --- alice --- dave
#     \      / \      /
#      \    /   \    /
#       bob      bob  (shared)

kc.add_vertex("alice", type="Researcher", field="ML")
kc.add_vertex("bob",   type="Researcher", field="ML")
kc.add_vertex("carol", type="Researcher", field="Systems")
kc.add_vertex("dave",  type="Researcher", field="Theory")

kc.add_edge("ab", type="Collaborates", vertices={"alice", "bob"})
kc.add_edge("ac", type="Collaborates", vertices={"alice", "carol"})
kc.add_edge("bc", type="Collaborates", vertices={"bob", "carol"})
kc.add_edge("ad", type="Collaborates", vertices={"alice", "dave"})
kc.add_edge("bd", type="Collaborates", vertices={"bob", "dave"})

kc.add_face("paper1", type="Paper", boundary=["ab", "ac", "bc"])
kc.add_face("paper2", type="Paper", boundary=["ab", "ad", "bd"])

# ── Boundary & Coboundary ──────────────────────────────────────────────────

print("=== Boundary (direct faces of a simplex) ===")
print(f"  boundary(alice)  = {kc.boundary('alice')}")      # vertex: empty
print(f"  boundary(ab)     = {kc.boundary('ab')}")          # edge: 2 vertices
print(f"  boundary(paper1) = {kc.boundary('paper1')}")      # face: 3 edges
print()

print("=== Coboundary (simplices that bound this element) ===")
print(f"  coboundary(alice) = {kc.coboundary('alice')}")    # edges incident to alice
print(f"  coboundary(ab)    = {kc.coboundary('ab')}")       # faces containing edge ab
print(f"  coboundary(paper1)= {kc.coboundary('paper1')}")   # nothing (top dim)
print()

# ── Star & Closure ─────────────────────────────────────────────────────────

print("=== Star (all simplices containing this element) ===")
print(f"  star(alice) = {kc.star('alice')}")
print(f"  star(ab)    = {kc.star('ab')}")
print()

print("=== Closure (smallest subcomplex containing these elements) ===")
print(f"  closure(paper1) = {kc.closure('paper1')}")
# Set input: closure of multiple elements
print(f"  closure({{ab, ad}}) = {kc.closure({'ab', 'ad'})}")
print()

# ── Closed Star & Link ─────────────────────────────────────────────────────

print("=== Closed Star = Cl(St(x)) — always a valid subcomplex ===")
cs = kc.closed_star("alice")
print(f"  closed_star(alice) = {cs}")
print(f"  is_subcomplex?     = {kc.is_subcomplex(cs)}")
print()

print("=== Link = Cl(St(x)) \\ St(x) — the 'horizon' around x ===")
print(f"  link(alice) = {kc.link('alice')}")
print(f"  link(bob)   = {kc.link('bob')}")
print(f"  link(ab)    = {kc.link('ab')}")
print()

# ── Skeleton & Degree ──────────────────────────────────────────────────────

print("=== Skeleton (elements up to dimension k) ===")
print(f"  skeleton(0) = {kc.skeleton(0)}  (vertices)")
print(f"  skeleton(1) = {kc.skeleton(1)}  (+ edges)")
print(f"  skeleton(2) = {kc.skeleton(2)}  (+ faces = everything)")
print()

print("=== Degree (incident edges) ===")
print(f"  degree(alice) = {kc.degree('alice')}")  # 3 edges
print(f"  degree(carol) = {kc.degree('carol')}")  # 2 edges
print(f"  degree(dave)  = {kc.degree('dave')}")   # 2 edges
print()

# ── Type-filtered queries ──────────────────────────────────────────────────

print("=== Type-filtered queries ===")
print(f"  star(alice, type='Paper')         = {kc.star('alice', type='Paper')}")
print(f"  star(alice, type='Collaborates')  = {kc.star('alice', type='Collaborates')}")
print(f"  coboundary(alice, type='Collaborates') = {kc.coboundary('alice', type='Collaborates')}")
print()

# ── Set algebra (composition) ──────────────────────────────────────────────

print("=== Set algebra ===")
s_alice = kc.star("alice")
s_carol = kc.star("carol")
s_dave  = kc.star("dave")

print(f"  star(alice) & star(carol) = {s_alice & s_carol}")  # shared
print(f"  star(carol) & star(dave)  = {s_carol & s_dave}")   # disjoint?
print(f"  star(alice) | star(dave)  = {s_alice | s_dave}")   # union
print(f"  star(alice) - star(carol) = {s_alice - s_carol}")  # alice-only
print()

# Compose: closure of the star
composed = kc.closure(kc.star("carol"))
direct   = kc.closed_star("carol")
print(f"  closure(star(carol)) == closed_star(carol)? {composed == direct}")
