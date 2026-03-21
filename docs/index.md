# knowledgecomplex

A Python library for defining and instantiating **typed simplicial complexes** backed by OWL, SHACL, and SPARQL.

## Overview

A **knowledge complex** is a simplicial complex (vertices, edges, faces) where each element has a type governed by a formal ontology. The library provides:

- **`SchemaBuilder`** — a DSL for declaring vertex/edge/face types, attributes, and vocabularies. Generates OWL and SHACL automatically.
- **`KnowledgeComplex`** — an instance manager that adds elements, validates them against SHACL on every write, and executes named SPARQL queries.
- **Core OWL + SHACL** — a static topological backbone: the `Element > Vertex/Edge/Face` hierarchy, boundary-cardinality axioms, and closed-triangle/boundary-closure constraints.

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
```

See the [examples/](https://github.com/blockscience/knowledgecomplex/tree/main/examples) directory for 10 runnable examples.

## API Reference

- [Schema authoring](api/schema.md) — `SchemaBuilder`, `vocab`, `text`, type inheritance, constraint escalation
- [Instance management](api/graph.md) — `KnowledgeComplex`, `Element`, topological queries, SPARQL templates
- [Visualization](api/viz.md) — Hasse diagrams, geometric realization, NetworkX export
- [Algebraic topology](api/analysis.md) — Betti numbers, Hodge Laplacian, edge PageRank
- [Clique inference](api/clique.md) — `find_cliques`, `infer_faces`, `fill_cliques`
- [Filtrations](api/filtration.md) — nested subcomplex sequences, birth tracking
- [Diffs and sequences](api/diff.md) — `ComplexDiff`, `ComplexSequence`, SPARQL UPDATE export/import
- [File I/O](api/io.md) — multi-format save/load (Turtle, JSON-LD, N-Triples)
- [Codecs](api/codecs.md) — `MarkdownCodec` for YAML+markdown round-trip
- [Exceptions](api/exceptions.md) — `ValidationError`, `SchemaError`, `UnknownQueryError`
