"""
filtration_evolution.py — Proper filtration: a startup growing over quarters.

A filtration is a strictly growing sequence of subcomplexes. Each quarter
new people join and form collaborations, but nobody leaves. The birth()
index tells us when each element first appeared, enabling persistence
analysis and understanding which structures are foundational vs. late-stage.

Run:
    pip install knowledgecomplex[analysis]
    python examples/filtration_evolution.py
"""

from knowledgecomplex import SchemaBuilder, KnowledgeComplex, Filtration, vocab

# ── Schema ──────────────────────────────────────────────────────────────────

sb = SchemaBuilder(namespace="startup")
sb.add_vertex_type("Person", attributes={"role": vocab("eng", "design", "sales", "founder")})
sb.add_edge_type("Collaborates")
sb.add_face_type("Team")

# ── Build the full complex (all quarters) ───────────────────────────────────

kc = KnowledgeComplex(schema=sb)

# All people
kc.add_vertex("alice", type="Person", role="founder")
kc.add_vertex("bob",   type="Person", role="founder")
kc.add_vertex("carol", type="Person", role="eng")
kc.add_vertex("dave",  type="Person", role="design")
kc.add_vertex("eve",   type="Person", role="sales")

# All collaborations
kc.add_edge("c-ab", type="Collaborates", vertices={"alice", "bob"})
kc.add_edge("c-ac", type="Collaborates", vertices={"alice", "carol"})
kc.add_edge("c-bc", type="Collaborates", vertices={"bob", "carol"})
kc.add_edge("c-ad", type="Collaborates", vertices={"alice", "dave"})
kc.add_edge("c-bd", type="Collaborates", vertices={"bob", "dave"})
kc.add_edge("c-cd", type="Collaborates", vertices={"carol", "dave"})
kc.add_edge("c-ae", type="Collaborates", vertices={"alice", "eve"})
kc.add_edge("c-be", type="Collaborates", vertices={"bob", "eve"})

# Teams (triangles of collaboration)
kc.add_face("eng-team",    type="Team", boundary=["c-ab", "c-ac", "c-bc"])
kc.add_face("design-team", type="Team", boundary=["c-ab", "c-ad", "c-bd"])
kc.add_face("cross-team",  type="Team", boundary=["c-ac", "c-ad", "c-cd"])

# ── Build the filtration (strictly growing) ────────────────────────────────

filt = Filtration(kc)

# Q0: Founders meet and start collaborating
filt.append_closure({"alice", "bob", "c-ab"})

# Q1: First hire (carol) — forms engineering triangle
filt.append_closure({"carol", "c-ac", "c-bc", "eng-team"})

# Q2: Second hire (dave) — design team + cross-functional team
filt.append_closure({"dave", "c-ad", "c-bd", "c-cd", "design-team", "cross-team"})

# Q3: Third hire (eve) — sales edges, no new triangle
filt.append_closure({"eve", "c-ae", "c-be"})

# ── Inspect the filtration ─────────────────────────────────────────────────

print("=== Filtration: Startup Growth ===")
print(f"  {len(filt)} quarters, complete={filt.is_complete}")
print()

for i, step in enumerate(filt):
    print(f"  Q{i}: {len(step)} elements")
    new = filt.new_at(i)
    if new:
        print(f"       new: {sorted(new)}")
print()

# ── Birth tracking ─────────────────────────────────────────────────────────

print("=== When did each element first appear? ===")
for eid in sorted(kc.element_ids()):
    try:
        b = filt.birth(eid)
        print(f"  {eid:15s}  born Q{b}")
    except ValueError:
        print(f"  {eid:15s}  never (not in filtration)")
print()

# ── Topological evolution (Betti numbers at each step) ─────────────────────

try:
    from knowledgecomplex import betti_numbers

    print("=== Betti numbers at each quarter ===")
    print("  (beta_0=components, beta_1=cycles, beta_2=voids)")

    # Build temporary KCs for each step to compute Betti numbers
    for i, step in enumerate(filt):
        # Create a sub-KC with just this step's elements
        sub_kc = KnowledgeComplex(schema=sb)
        # Add elements in dimension order
        for eid in sorted(step):
            elem = kc.element(eid)
            kind = kc._schema._types[elem.type]["kind"]
            if kind == "vertex":
                sub_kc.add_vertex(eid, type=elem.type, **elem.attrs)
        for eid in sorted(step):
            elem = kc.element(eid)
            kind = kc._schema._types[elem.type]["kind"]
            if kind == "edge":
                boundary = sorted(kc.boundary(eid))
                sub_kc.add_edge(eid, type=elem.type, vertices=set(boundary), **elem.attrs)
        for eid in sorted(step):
            elem = kc.element(eid)
            kind = kc._schema._types[elem.type]["kind"]
            if kind == "face":
                boundary = sorted(kc.boundary(eid))
                sub_kc.add_face(eid, type=elem.type, boundary=boundary, **elem.attrs)

        betti = betti_numbers(sub_kc)
        v = len([e for e in step if kc._schema._types[kc.element(e).type]["kind"] == "vertex"])
        e = len([e for e in step if kc._schema._types[kc.element(e).type]["kind"] == "edge"])
        f = len([e for e in step if kc._schema._types[kc.element(e).type]["kind"] == "face"])
        print(f"  Q{i}: V={v} E={e} F={f}  ->  beta={betti}")
    print()
except ImportError:
    print("  (install knowledgecomplex[analysis] for Betti numbers)")
    print()

# ── Filtration from a function ─────────────────────────────────────────────

print("=== Filtration from dimension function ===")
dim_filt = Filtration.from_function(kc, lambda eid: {
    "vertex": 0, "edge": 1, "face": 2,
}[kc._schema._types[kc.element(eid).type]["kind"]])

for i, step in enumerate(dim_filt):
    print(f"  Step {i}: {len(step)} elements (dim <= {i})")
print()
print("Done.")
