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
sb.add_edge_type("responsible", attributes={"level": vocab("owner", "steward")})
sb.add_face_type("operation")

# 2. Build an instance
kc = KnowledgeComplex(schema=sb)
kc.add_vertex("alice",   type="actor",    name="Alice")
kc.add_vertex("etl-run", type="activity", name="Daily ETL")
kc.add_vertex("dataset", type="resource", name="Sales DB")

kc.add_edge("e1", type="performs",    vertices={"alice", "etl-run"},   role="lead")
kc.add_edge("e2", type="requires",   vertices={"etl-run", "dataset"}, mode="write")
kc.add_edge("e3", type="responsible", vertices={"alice", "dataset"},   level="owner")

kc.add_face("op1", type="operation", edges={"e1", "e2", "e3"})

# 3. Query
df = kc.query("vertices")   # built-in SPARQL template
print(df)
```
