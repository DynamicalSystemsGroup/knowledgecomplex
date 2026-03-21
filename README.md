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

See [`examples/quickstart.py`](examples/quickstart.py) to load a pre-built complex, discover triangles via clique detection, and extend it with faces. See [`examples/construction.py`](examples/construction.py) for a runnable version of the schema construction above.

## The `kc:uri` attribute

Every element (vertex, edge, or face) can carry an optional `kc:uri` property pointing to its source file:

```python
kc.add_vertex("alice", type="actor", name="Alice",
            uri="file:///actors/alice.md")
kc.add_edge("e1", type="performs", vertices={"alice", "etl-run"},
            role="lead", uri="file:///edges/e1.md")
```

SHACL enforces at-most-one `kc:uri` per element. This is useful for domain applications where each element corresponds to an actual document or record.

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
