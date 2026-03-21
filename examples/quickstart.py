"""
quickstart.py — Load a complex, discover hidden structure, extend it.

This example loads a pre-built data pipeline complex (vertices and edges
only), discovers triangles via clique detection, declares a face type,
fills in the faces, and shows how the topology changes.

Run:
    pip install knowledgecomplex[analysis,viz]
    python examples/quickstart.py
"""

import os
from pathlib import Path

from knowledgecomplex import (
    KnowledgeComplex, find_cliques, infer_faces,
    betti_numbers, euler_characteristic,
    plot_hasse, plot_geometric,
)

# ── 1. Load a pre-built complex ──────────────────────────────────────────

data_dir = Path(__file__).parent / "data" / "pipeline"
kc = KnowledgeComplex.load(data_dir)

print("=== Loaded complex ===")
ids = kc.element_ids()
print(f"{len(ids)} elements: {sorted(ids)}")
print()

# List vertices
print("=== Vertices ===")
print(kc.query("vertices"))
print()

# ── 2. Discover hidden structure ─────────────────────────────────────────

triangles = find_cliques(kc, k=3)
print(f"=== Discovered {len(triangles)} triangles (3-cliques) ===")
for tri in triangles:
    print(f"  vertices: {sorted(tri)}")

    # Show which edges connect them
    for eid in sorted(kc.element_ids()):
        elem = kc.element(eid)
        kind = kc._schema._types.get(elem.type, {}).get("kind")
        if kind == "edge" and kc.boundary(eid) <= tri:
            print(f"    edge {eid} ({elem.type}): {sorted(kc.boundary(eid))}")
print()

# ── 3. Topology before faces ─────────────────────────────────────────────

betti_before = betti_numbers(kc)
print(f"=== Topology (no faces) ===")
print(f"  Betti numbers: {betti_before}")
print(f"  β₁ = {betti_before[1]} independent cycles")
print(f"  Euler characteristic: {euler_characteristic(kc)}")
print()

# ── 4. Declare a face type and fill in faces ─────────────────────────────

# The two triangles have distinct semantics:
#   operation:  actor + activity + input resource  (requires/accesses)
#   production: actor + activity + output resource (produces/responsible)
kc._schema.add_face_type("operation")
kc._schema.add_face_type("production")

# After extending the schema, refresh the internal graphs so the new types
# are visible to SPARQL queries and SHACL validation.
kc._ont_graph.parse(data=kc._schema.dump_owl(), format="turtle")
kc._instance_graph.parse(data=kc._schema.dump_owl(), format="turtle")
kc._shacl_graph.parse(data=kc._schema.dump_shacl(), format="turtle")

# Inspect the triangles to decide which type each gets.
# The input triangle uses "requires" + "accesses" edges → operation
# The output triangle uses "produces" + "responsible" edges → production
for tri in triangles:
    # Find the 3 edges forming this triangle
    edges = {}
    for eid in sorted(kc.element_ids()):
        elem = kc.element(eid)
        kind = kc._schema._types.get(elem.type, {}).get("kind")
        if kind == "edge" and kc.boundary(eid) <= tri:
            edges[eid] = elem.type

    edge_types = set(edges.values())
    boundary = sorted(edges.keys())

    if "requires" in edge_types or "accesses" in edge_types:
        face_type = "operation"
    else:
        face_type = "production"

    face_id = f"{face_type}-{'_'.join(sorted(tri))}"
    kc.add_face(face_id, type=face_type, boundary=boundary)
    print(f"  Added {face_id} ({face_type}): {boundary}")

print()
added = [eid for eid in kc.element_ids()
         if kc._schema._types.get(kc.element(eid).type, {}).get("kind") == "face"]
print(f"=== Added {len(added)} faces ===")
print()

# ── 5. Topology after faces ──────────────────────────────────────────────

betti_after = betti_numbers(kc)
print(f"=== Topology (with faces) ===")
print(f"  Betti numbers: {betti_after}")
print(f"  β₁ = {betti_after[1]} independent cycles (was {betti_before[1]})")
print(f"  Euler characteristic: {euler_characteristic(kc)}")
print()

if betti_before[1] > betti_after[1]:
    print("  Faces filled in cycles — the complex is more connected!")
elif betti_before[1] == betti_after[1]:
    print("  No change in β₁ — cycles were already independent of the faces.")
print()

# ── 6. Visualize ─────────────────────────────────────────────────────────

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

out = Path(__file__).parent

fig, ax = plot_hasse(kc, figsize=(12, 9))
fig.savefig(out / "quickstart_hasse.png", dpi=150, bbox_inches="tight")
print(f"Saved {out / 'quickstart_hasse.png'}")

fig, ax = plot_geometric(kc, figsize=(12, 9))
fig.savefig(out / "quickstart_geometric.png", dpi=150, bbox_inches="tight")
print(f"Saved {out / 'quickstart_geometric.png'}")

plt.close("all")
print("\nDone! See the PNG files in examples/")
