# knowledgecomplex

A Python library for defining and instantiating **typed simplicial complexes** backed by OWL, SHACL, and SPARQL.

## What it is

A **knowledge complex** is a simplicial complex (vertices, edges, faces) where each element has a type governed by a formal ontology. The library provides:

- **`SchemaBuilder`** — a DSL for declaring vertex/edge/face types, attributes, and vocabularies. Generates OWL and SHACL automatically.
- **`KnowledgeComplex`** — an instance manager that adds elements, validates them against SHACL on every write, and executes named SPARQL queries.
- **Core OWL + SHACL** — a static topological backbone: the `Element → Vertex/Edge/Face` hierarchy, boundary-cardinality axioms, and closed-triangle/boundary-closure constraints.

All semantic web machinery (rdflib, pyshacl, owlrl) stays internal. The public API is pure Python.

## Install

```bash
pip install knowledgecomplex
```

Or from source:

```bash
git clone https://github.com/BlockScience/knowledgecomplex.git
cd knowledgecomplex
pip install -e ".[dev]"
```

## Quick start

```python
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
df = kc.query("vertices")   # built-in SPARQL template
print(df)

# 4. Inspect the RDF
print(kc.dump_graph())       # Turtle string
```

See [`examples/`](examples/) for 11 runnable examples covering all features below.

## Topological queries

Every `KnowledgeComplex` has methods for the standard simplicial complex operations.
All return `set[str]` for natural set algebra:

```python
kc.boundary("face-1")            # {e1, e2, e3} — direct boundary
kc.star("alice")                  # all simplices containing alice
kc.link("alice")                  # Cl(St) \ St — the horizon around alice
kc.closure({"e1", "e2"})          # smallest subcomplex containing these edges
kc.degree("alice")                # number of incident edges

# Set algebra composes naturally
shared = kc.star("alice") & kc.star("bob")
```

All operators accept an optional `type=` filter for OWL-subclass-aware filtering.

## Clique inference

Discover higher-order structure from the edge graph:

```python
from knowledgecomplex import find_cliques, infer_faces

triangles = find_cliques(kc, k=3)          # pure query — what triangles exist?
infer_faces(kc, "operation")               # fill in all triangles as typed faces
infer_faces(kc, "team", edge_type="collab") # restrict to specific edge types
```

## Visualization

Two complementary views — Hasse diagrams (all elements as nodes, boundary as directed arrows) and geometric realization (vertices as 3D points, edges as lines, faces as filled triangles):

```python
from knowledgecomplex import plot_hasse, plot_geometric

fig, ax = plot_hasse(kc)          # directed boundary graph, type-colored
fig, ax = plot_geometric(kc)      # 3D triangulation with matplotlib
```

Export to NetworkX for further analysis:

```python
from knowledgecomplex import to_networkx, verify_networkx

G = to_networkx(kc)     # nx.DiGraph with exact degree invariants
verify_networkx(G)       # validate cardinality + closed-triangle constraints
```

## Algebraic topology

Betti numbers, Euler characteristic, Hodge Laplacian, and edge PageRank (requires `pip install knowledgecomplex[analysis]`):

```python
from knowledgecomplex import betti_numbers, euler_characteristic, edge_pagerank

betti = betti_numbers(kc)          # [beta_0, beta_1, beta_2]
chi = euler_characteristic(kc)     # V - E + F
pr = edge_pagerank(kc, "e1")       # personalized edge PageRank vector
```

## Local partitioning

Find clusters via diffusion — spread probability from a seed and sweep to find natural bottlenecks:

```python
from knowledgecomplex.analysis import local_partition, edge_local_partition

# Vertex clusters via PageRank or heat kernel diffusion
cut = local_partition(kc, seed="alice", method="pagerank")
cut.vertices       # vertex IDs on the small side
cut.conductance    # lower = cleaner partition

# Edge clusters via Hodge Laplacian diffusion
edge_cut = edge_local_partition(kc, seed_edge="e1", method="hodge_pagerank")
edge_cut.edges     # relationship cluster around e1
```

## Filtrations and time-varying complexes

Filtrations model strictly growing subcomplexes. Diffs model arbitrary add/remove sequences:

```python
from knowledgecomplex import Filtration, ComplexDiff, ComplexSequence

filt = Filtration(kc)
filt.append_closure({"v1", "v2", "e12"})    # Q0: founders
filt.append_closure({"v3", "e23", "face1"}) # Q1: first triangle
print(filt.birth("face1"))                  # 1

diff = ComplexDiff().add_vertex("eve", type="Person").remove("old-edge")
diff.apply(kc)                              # mutate the complex
print(diff.to_sparql(kc))                   # export as SPARQL UPDATE
```

## I/O and codecs

Multi-format serialization and round-trip with external files:

```python
from knowledgecomplex import save_graph, load_graph, MarkdownCodec

save_graph(kc, "data.jsonld", format="json-ld")
load_graph(kc, "data.ttl")                  # additive loading

codec = MarkdownCodec(frontmatter_attrs=["name"], section_attrs=["notes"])
kc.register_codec("Paper", codec)
kc.element("paper-1").compile()             # KC -> markdown file
kc.element("paper-1").decompile()           # markdown file -> KC
```

## Constraint escalation

Escalate topological queries to SHACL constraints enforced on every write:

```python
sb.add_topological_constraint(
    "requirement", "coboundary",
    target_type="verification",
    predicate="min_count", min_count=1,
    message="Every requirement must have at least one verification edge",
)
```

## The `kc:uri` attribute

Every element can carry an optional `kc:uri` property pointing to its source file.
SHACL enforces at-most-one `kc:uri` per element.

## Architecture

The library is organised around a 2×2 responsibility map. Every rule belongs to exactly one cell:

|                 | **OWL**                                                   | **SHACL**                                                         |
|-----------------|-----------------------------------------------------------|-------------------------------------------------------------------|
| **Topological** | `kc:Element`, `kc:Vertex`, `kc:Edge`, `kc:Face` hierarchy; cardinality axioms on `kc:boundedBy`; `kc:Complex` via `kc:hasElement` | Boundary vertices are distinct; boundary edges form a closed triangle; boundary-closure of a complex (all require `sh:sparql`) |
| **Ontological** | Concrete subclasses and their properties; domain/range declarations | Controlled vocabulary (`sh:in`); attribute presence rules; co-occurrence constraints |

### Why both OWL and SHACL at each layer

**Topological layer:** OWL cardinality axioms express structural counts at the schema level. SHACL is required for the closed-triangle constraint because OWL cannot express co-reference across three property assertions on different individuals — a known expressivity boundary of OWL-DL.

**Ontological layer:** OWL defines what attributes a type *has* (property declarations, subclass hierarchy). SHACL defines what values those attributes *must have* at the instance level. OWL cannot enforce controlled vocabularies on string-valued data properties.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design rationale.

## Domain model example

This package is used by [mtg-kc](https://github.com/BlockScience/mtg-kc) as a demonstration application, and by [assurances-audits-accountability](https://github.com/BlockScience/assurances-audits-accountability) as a domain-specific knowledge complex for typed document assurance.

## License

Apache 2.0 — see [LICENSE](LICENSE).
