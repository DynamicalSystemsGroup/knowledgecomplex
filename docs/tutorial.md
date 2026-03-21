# Tutorial

A progressive walkthrough of knowledgecomplex, from schema definition through algebraic topology.

## 1. Define a schema

A schema declares vertex, edge, and face types with attributes. The `SchemaBuilder` generates OWL and SHACL automatically.

```python
from knowledgecomplex import SchemaBuilder, vocab, text

sb = SchemaBuilder(namespace="vv")

# Vertex types (subclass of kc:Vertex)
sb.add_vertex_type("requirement", attributes={"title": text()})
sb.add_vertex_type("test_case",   attributes={"title": text()})

# Edge type with controlled vocabulary (enforced via sh:in)
sb.add_edge_type("verifies", attributes={
    "status": vocab("passing", "failing", "pending"),
})

# Face type
sb.add_face_type("coverage")
```

### Attribute descriptors

| Descriptor | What it generates | Example |
|---|---|---|
| `text()` | `xsd:string`, required, single-valued | `title: text()` |
| `text(required=False)` | `xsd:string`, optional | `notes: text(required=False)` |
| `text(multiple=True)` | `xsd:string`, required, multi-valued | `tags: text(multiple=True)` |
| `vocab("a", "b")` | `sh:in ("a" "b")`, required, single-valued | `status: vocab("pass", "fail")` |

### Type inheritance and binding

Types can inherit from other user-defined types. Child types can bind inherited attributes to fixed values:

```python
sb.add_vertex_type("document", attributes={"title": text(), "category": text()})
sb.add_vertex_type("specification", parent="document",
                   attributes={"format": text()},
                   bind={"category": "structural"})
```

### Introspection

```python
sb.describe_type("specification")
# {'name': 'specification', 'kind': 'vertex', 'parent': 'document',
#  'own_attributes': {'format': text()},
#  'inherited_attributes': {'title': text(), 'category': text()},
#  'all_attributes': {'title': text(), 'category': text(), 'format': text()},
#  'bound': {'category': 'structural'}}

sb.type_names(kind="vertex")   # ['document', 'specification']
```

## 2. Build a complex

A `KnowledgeComplex` manages instances. Every write triggers SHACL verification — the graph is always in a valid state.

```python
from knowledgecomplex import KnowledgeComplex

kc = KnowledgeComplex(schema=sb)

# Vertices have no boundary — always valid
kc.add_vertex("req-001", type="requirement", title="Boot time < 5s")
kc.add_vertex("tc-001",  type="test_case",   title="Boot smoke test")
kc.add_vertex("tc-002",  type="test_case",   title="Boot regression")

# Edges need their boundary vertices to already exist (slice rule)
kc.add_edge("ver-001", type="verifies",
            vertices={"req-001", "tc-001"}, status="passing")
kc.add_edge("ver-002", type="verifies",
            vertices={"req-001", "tc-002"}, status="pending")
kc.add_edge("ver-003", type="verifies",
            vertices={"tc-001", "tc-002"}, status="passing")

# Faces need 3 boundary edges forming a closed triangle
kc.add_face("cov-001", type="coverage",
            boundary=["ver-001", "ver-002", "ver-003"])
```

### What gets enforced

| Constraint | When | What happens |
|---|---|---|
| Type must be registered | Before RDF assertions | `ValidationError` |
| Boundary cardinality (2 for edges, 3 for faces) | Before SHACL | `ValueError` |
| Boundary elements must exist in complex (slice rule) | SHACL on write | `ValidationError` + rollback |
| Vocab values must be in allowed set | SHACL on write | `ValidationError` + rollback |
| Face boundary edges must form closed triangle | SHACL on write | `ValidationError` + rollback |

### Element handles

```python
elem = kc.element("req-001")
elem.id      # "req-001"
elem.type    # "requirement"
elem.attrs   # {"title": "Boot time < 5s"}

kc.element_ids(type="test_case")   # ["tc-001", "tc-002"]
kc.elements(type="test_case")      # [Element('tc-001', ...), Element('tc-002', ...)]
```

## 3. Topological queries

Every query returns `set[str]` for natural set algebra. All accept an optional `type=` filter.

```python
# Boundary operator ∂
kc.boundary("ver-001")     # {'req-001', 'tc-001'}  (edge → vertices)
kc.boundary("cov-001")     # {'ver-001', 'ver-002', 'ver-003'}  (face → edges)
kc.boundary("req-001")     # set()  (vertex → empty)

# Coboundary (inverse boundary)
kc.coboundary("req-001")   # {'ver-001', 'ver-002'}  (vertex → incident edges)

# Star: all simplices containing σ as a face
kc.star("req-001")         # req-001 + incident edges + incident faces

# Closure: smallest subcomplex containing σ
kc.closure("cov-001")      # cov-001 + 3 edges + 3 vertices

# Link: Cl(St(σ)) \ St(σ)
kc.link("req-001")

# Skeleton: elements up to dimension k
kc.skeleton(0)   # vertices only
kc.skeleton(1)   # vertices + edges

# Degree
kc.degree("req-001")   # 2

# Subcomplex check
kc.is_subcomplex({"req-001", "tc-001", "ver-001"})   # True
kc.is_subcomplex({"ver-001"})                         # False (missing vertices)

# Set algebra composes naturally
shared = kc.star("req-001") & kc.star("tc-001")
```

## 4. Local partitioning

The topological queries above use combinatorial adjacency — boundary, star, and closure walk the simplicial structure directly. Local partitioning uses **diffusion** instead: spread probability from a seed and sweep the result to find a natural cluster boundary. This finds structure that combinatorial queries miss.

Requires `pip install knowledgecomplex[analysis]`.

### Graph partitioning (vertex clusters)

Diffuse from a seed vertex using personalized PageRank or the heat kernel, then sweep the resulting distribution to find a cut with low conductance:

```python
from knowledgecomplex.analysis import (
    approximate_pagerank, heat_kernel_pagerank,
    sweep_cut, local_partition,
)

# Approximate PageRank: push-based diffusion (Andersen-Chung-Lang)
p, r = approximate_pagerank(kc, seed="req-001", alpha=0.15)
# p is a sparse dict of vertex → probability; more mass near seed

# Heat kernel PageRank: exponential diffusion (Fan Chung)
rho = heat_kernel_pagerank(kc, seed="req-001", t=5.0)
# t controls locality: small t = tight cluster, large t = broad spread

# Sweep either distribution to find a low-conductance cut
cut = sweep_cut(kc, p)
cut.vertices      # set of vertex IDs on the small side
cut.conductance   # Cheeger ratio — lower means cleaner partition

# Or use local_partition for the full pipeline in one call
cut = local_partition(kc, seed="req-001", method="pagerank")
cut = local_partition(kc, seed="req-001", method="heat_kernel")
```

### Edge partitioning (simplicial clusters)

The simplicial version replaces the graph Laplacian with the **Hodge Laplacian** on edges. Instead of partitioning vertices, it partitions edges — finding clusters of relationships:

```python
from knowledgecomplex.analysis import edge_local_partition

# Hodge PageRank: (βI + L₁)⁻¹ χ_e — diffusion on the edge space
cut = edge_local_partition(kc, seed_edge="ver-001", method="hodge_pagerank")

# Hodge heat kernel: e^{-tL₁} χ_e — exponential diffusion on edges
cut = edge_local_partition(kc, seed_edge="ver-001", method="hodge_heat", t=5.0)

cut.edges         # set of edge IDs in the cluster
cut.conductance   # edge conductance
```

The key difference: graph partitioning asks "which vertices are near this vertex?" while edge partitioning asks "which relationships are near this relationship?" — a question that only makes sense in a simplicial complex, not in a plain graph.

## 5. Algebraic topology

Requires `pip install knowledgecomplex[analysis]`.

```python
from knowledgecomplex.analysis import (
    boundary_matrices, betti_numbers, euler_characteristic,
    hodge_laplacian, edge_pagerank, hodge_decomposition, hodge_analysis,
)

# Boundary matrices (sparse)
bm = boundary_matrices(kc)
# bm.B1: (n_vertices × n_edges), bm.B2: (n_edges × n_faces)
# Invariant: B1 @ B2 = 0 (∂₁ ∘ ∂₂ = 0)

# Betti numbers
betti = betti_numbers(kc)     # [β₀, β₁, β₂]
chi = euler_characteristic(kc) # V - E + F = β₀ - β₁ + β₂

# Hodge Laplacian
L1 = hodge_laplacian(kc)      # B1ᵀB1 + B2B2ᵀ (symmetric PSD)
# dim(ker L₁) = β₁

# Edge PageRank
pr = edge_pagerank(kc, "ver-001", beta=0.1)   # (βI + L₁)⁻¹ χ_e

# Hodge decomposition: flow = gradient + curl + harmonic
decomp = hodge_decomposition(kc, pr)
# decomp.gradient  — im(B1ᵀ), vertex-driven flow
# decomp.curl      — im(B2), face-driven circulation
# decomp.harmonic  — ker(L₁), topological cycles

# Full analysis in one call
results = hodge_analysis(kc, beta=0.1)
```

All analysis functions accept an optional `weights` dict mapping element IDs to scalar weights, which factor into the Laplacian as diagonal weight matrices.

## 6. Filtrations

A filtration is a nested sequence of valid subcomplexes: C₀ ⊆ C₁ ⊆ ... ⊆ Cₘ.

```python
from knowledgecomplex import Filtration

filt = Filtration(kc)
filt.append({"req-001"})                              # must be valid subcomplex
filt.append_closure({"ver-001"})                       # auto-closes + unions with previous
filt.append_closure({"cov-001"})                       # adds face + all boundary

filt.birth("cov-001")   # index where element first appears
filt.new_at(2)          # elements added at step 2 (Cₚ \ Cₚ₋₁)
filt[1]                 # set of element IDs at step 1

# Build from a scoring function
filt2 = Filtration.from_function(kc, lambda eid: some_score(eid))
```

## 7. Parametric sequences

A `ParametricSequence` views a single complex through a parameterized filter. The complex holds all elements across all parameter values; the filter selects which are "active" at each value. Unlike a Filtration, subcomplexes can shrink — elements can appear and disappear.

```python
from knowledgecomplex import ParametricSequence

# Complex has people with active_from/active_until attributes
seq = ParametricSequence(
    kc,
    values=["Q1", "Q2", "Q3", "Q4"],
    filter=lambda elem, t: elem.attrs.get("active_from", "0") <= t < elem.attrs.get("active_until", "9999"),
)

seq["Q2"]                   # set of element IDs active at Q2
seq.birth("carol")          # "Q2" — first value where carol appears
seq.death("bob")            # "Q3" — first value where bob disappears
seq.active_at("bob")        # ["Q1", "Q2"]
seq.new_at(1)               # elements appearing at Q2
seq.removed_at(2)           # elements disappearing at Q3 (bob left)
seq.is_monotone             # False — people can leave
seq.subcomplex_at(0)        # is the Q1 slice boundary-closed?

for value, ids in seq:
    print(f"{value}: {len(ids)} elements")
```

The complex is the territory; the parameterized filter is the map.

## 8. Clique inference

Discover higher-order structure hiding in the edge graph:

```python
from knowledgecomplex import find_cliques, infer_faces

# Pure query — what triangles exist?
triangles = find_cliques(kc, k=3)

# Fill in all triangles as typed faces
added = infer_faces(kc, "coverage")

# Preview without modifying
preview = infer_faces(kc, "coverage", dry_run=True)
```

## 9. Export and load

```python
# Export schema + instance to a directory
kc.export("output/my_complex")
# Creates: ontology.ttl, shapes.ttl, instance.ttl, queries/*.sparql

# Reconstruct from exported files
kc2 = KnowledgeComplex.load("output/my_complex")
kc2.audit().conforms   # True
```

Multi-format serialization:

```python
from knowledgecomplex import save_graph, load_graph

save_graph(kc, "data.jsonld", format="json-ld")
load_graph(kc, "data.ttl")   # additive loading
```

## 10. Verification and audit

```python
# Throwing verification
kc.verify()   # raises ValidationError on failure

# Non-throwing audit
report = kc.audit()
report.conforms       # bool
report.violations     # list[AuditViolation]
print(report)         # human-readable summary

# Deferred verification for bulk construction
with kc.deferred_verification():
    for item in big_dataset:
        kc.add_vertex(item.id, type=item.type, **item.attrs)
    # ... add edges, faces ...
# Single SHACL pass runs on exit

# Static file verification (no Python objects needed)
from knowledgecomplex import audit_file
report = audit_file("data/instance.ttl", shapes="data/shapes.ttl",
                    ontology="data/ontology.ttl")
```

## 11. Pre-built ontologies

Three ontologies ship with the package:

```python
from knowledgecomplex.ontologies import operations, brand, research

sb = operations.schema()   # actor, activity, resource
sb = brand.schema()        # audience, theme
sb = research.schema()     # paper, concept, note
```

## Gotchas

| Issue | Detail |
|---|---|
| **Slice rule** | Boundary elements must exist before the element that references them. Add vertices → edges → faces. |
| **Closed triangle** | A face's 3 edges must span exactly 3 vertices in a cycle. An open fan or 4-vertex path will fail. |
| **`remove_element`** | No post-removal verification. Remove faces before their edges, edges before their vertices. |
| **Schema after `load()`** | `load()` recovers type names, kinds, attributes, and parent relationships from OWL + SHACL. Full `describe_type()` introspection works after loading. |
| **Deferred verification** | Inside the context manager, intermediate states need not be valid. Verification runs once on exit. |
| **Face orientation** | Boundary matrix signs are computed internally to guarantee ∂₁∘∂₂ = 0. The orientation is consistent but not guaranteed to match external conventions. |
