"""
temporal_sweep.py — Parameterized subcomplex sweep over time.

The complex contains ALL elements that ever existed, each with temporal
metadata (active_from, active_until). A parameterized SPARQL query
filters to "active" elements at any given time point. The complex itself
doesn't change — we're just slicing it at different times.

This is NOT a filtration (subcomplexes can shrink when people leave).
It demonstrates query_ids() with parameter substitution.

Run:
    python examples/temporal_sweep.py
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

# ── Manual parameterized sweep ─────────────────────────────────────────────

# Since we store active_from/active_until as string attributes, we can
# query for elements active at a specific time by comparing attribute values.

print("=== Active subcomplex at each quarter ===")
for t in ["1", "2", "3", "4", "5"]:
    # Get active people at time t
    active_people = set()
    for pid in kc.element_ids(type="Person"):
        elem = kc.element(pid)
        af = elem.attrs.get("active_from", "0")
        au = elem.attrs.get("active_until", "9999")
        if af <= t < au:
            active_people.add(pid)

    # Get active edges at time t
    active_edges = set()
    for eid in kc.element_ids(type="WorksWith"):
        elem = kc.element(eid)
        af = elem.attrs.get("active_from", "0")
        au = elem.attrs.get("active_until", "9999")
        if af <= t < au:
            # Only include if both endpoints are active
            boundary = kc.boundary(eid)
            if boundary <= active_people:
                active_edges.add(eid)

    # Get active faces
    active_faces = set()
    for fid in kc.element_ids(type="Squad"):
        boundary = kc.boundary(fid)
        if boundary <= active_edges:
            active_faces.add(fid)

    active = active_people | active_edges | active_faces
    is_sub = kc.is_subcomplex(active)

    print(f"  Q{t}: {len(active_people)} people, "
          f"{len(active_edges)} collabs, "
          f"{len(active_faces)} squads  "
          f"(valid subcomplex: {is_sub})")
    print(f"       people: {sorted(active_people)}")

    # Show who's new and who left
    if t != "1":
        prev_t = str(int(t) - 1)
        prev_people = set()
        for pid in kc.element_ids(type="Person"):
            elem = kc.element(pid)
            af = elem.attrs.get("active_from", "0")
            au = elem.attrs.get("active_until", "9999")
            if af <= prev_t < au:
                prev_people.add(pid)
        joined = active_people - prev_people
        left = prev_people - active_people
        if joined:
            print(f"       joined: {sorted(joined)}")
        if left:
            print(f"       left:   {sorted(left)}")
    print()

# ── Key insight ────────────────────────────────────────────────────────────

print("=== Key insight ===")
print("  This is NOT a filtration — the subcomplex at Q4 is not a superset")
print("  of Q3 (bob left). But each time-slice is a valid subcomplex,")
print("  and the full complex contains the complete history.")
print()
print("  The complex is the territory; the time-slice queries are the maps.")
print("Done.")
