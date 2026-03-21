"""
temporal_sweep.py — Parameterized subcomplex sweep over time.

The complex contains ALL elements that ever existed, each with temporal
metadata (active_from, active_until). A parameterized SPARQL query
filters to "active" elements at any given time point. The complex itself
doesn't change — we're just slicing it at different times.

This is NOT a filtration (subcomplexes can shrink when people leave).
It demonstrates query_ids() with parameter substitution.

Run:
    python examples/08_temporal_sweep/temporal_sweep.py
"""

from knowledgecomplex import SchemaBuilder, KnowledgeComplex, vocab, text

# ── Schema with temporal metadata ──────────────────────────────────────────

sb = SchemaBuilder(namespace="proj")
sb.add_vertex_type("Person", attributes={
    "role": vocab("eng", "pm", "qa"),
    "active_from": text(),
    "active_until": text(),  # "9999" means still active
})
sb.add_edge_type("WorksWith", attributes={
    "active_from": text(),
    "active_until": text(),
})
sb.add_face_type("Squad")

# Register a parameterized query: "elements active at time {t}"
# Uses model attributes active_from <= t and active_until > t
sb.add_query("active_vertices", "coboundary")  # placeholder — we'll use a custom template

kc = KnowledgeComplex(schema=sb)

# ── Build the complete timeline ────────────────────────────────────────────

# People with join/leave dates (quarters as integers for simplicity)
people = [
    ("alice", "eng",  "1", "9999"),   # joined Q1, still here
    ("bob",   "eng",  "1", "4"),      # joined Q1, left Q4
    ("carol", "pm",   "2", "9999"),   # joined Q2, still here
    ("dave",  "qa",   "3", "9999"),   # joined Q3, still here
    ("eve",   "eng",  "4", "9999"),   # joined Q4 (replacing bob)
]

for name, role, af, au in people:
    kc.add_vertex(name, type="Person", role=role, active_from=af, active_until=au)

# Collaborations with their own time ranges
collabs = [
    ("w-ab", {"alice", "bob"},   "1", "4"),   # ends when bob leaves
    ("w-ac", {"alice", "carol"}, "2", "9999"),
    ("w-bc", {"bob", "carol"},   "2", "4"),   # ends when bob leaves
    ("w-cd", {"carol", "dave"},  "3", "9999"),
    ("w-ad", {"alice", "dave"},  "3", "9999"),
    ("w-ae", {"alice", "eve"},   "4", "9999"),
    ("w-ce", {"carol", "eve"},   "4", "9999"),
]

for eid, verts, af, au in collabs:
    kc.add_edge(eid, type="WorksWith", vertices=verts, active_from=af, active_until=au)

# Squad alice-carol-dave active from Q3 (uses edges w-ac, w-cd, w-ad)
kc.add_face("squad-1", type="Squad", boundary=["w-ac", "w-cd", "w-ad"])

print(f"Built timeline: {len(kc.element_ids())} total elements across all time")
print()

# ── Parameterized sweep using ParametricSequence ──────────────────────────

from knowledgecomplex import ParametricSequence

def active_filter(elem, t):
    """Element is active at time t if active_from <= t < active_until."""
    af = elem.attrs.get("active_from", "0")
    au = elem.attrs.get("active_until", "9999")
    return af <= t < au

seq = ParametricSequence(kc, values=["1", "2", "3", "4", "5"], filter=active_filter)

print("=== Active subcomplex at each quarter ===")
for t, active in seq:
    print(f"  Q{t}: {len(active)} elements  "
          f"(valid subcomplex: {seq.subcomplex_at(seq.values.index(t))})")
    print(f"       {sorted(active)}")

    i = seq.values.index(t)
    new = seq.new_at(i)
    removed = seq.removed_at(i)
    if new:
        print(f"       joined:  {sorted(new)}")
    if removed:
        print(f"       left:    {sorted(removed)}")
    print()

# ── Lifecycle queries ──────────────────────────────────────────────────────

print("=== Lifecycle ===")
for person in ["alice", "bob", "carol", "dave", "eve"]:
    birth = seq.birth(person)
    death = seq.death(person)
    active = seq.active_at(person)
    print(f"  {person:6s}  birth=Q{birth}  death={'Q'+death if death else 'still active':14s}  active={active}")
print()

# ── Key insight ────────────────────────────────────────────────────────────

print(f"=== Key insight ===")
print(f"  is_monotone: {seq.is_monotone}")
print(f"  This is NOT a filtration — bob leaves at Q3, so Q3 is not a")
print(f"  superset of Q2. But the complex holds the complete history,")
print(f"  and the parameterized filter slices it at any time.")
print()
print(f"  The complex is the territory; the parameterized filter is the map.")
print("Done.")
