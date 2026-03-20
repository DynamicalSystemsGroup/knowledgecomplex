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
sb = SchemaBuilder(namespace="aaa")
sb.add_vertex_type("spec",     attributes={"title": text(), "domain": text()})
sb.add_vertex_type("guidance", attributes={"title": text(), "domain": text()})
sb.add_edge_type("verification",
    attributes={"status": vocab("passing", "failing", "pending")})
sb.add_face_type("assurance")

# 2. Build an instance
kc = KnowledgeComplex(schema=sb)
kc.add_vertex("spec-001",     type="spec",     uri="file:///docs/spec-001.md",
              title="Spec for Verification", domain="aaa")
kc.add_vertex("guidance-001", type="guidance", uri="file:///docs/guidance-001.md",
              title="Guidance for Verification", domain="aaa")
kc.add_edge("ver-001", type="verification",
            vertices={"spec-001", "guidance-001"}, status="passing")

# 3. Query
df = kc.query("vertices")   # built-in SPARQL template
print(df)
```
