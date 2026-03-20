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

# 4. Inspect the RDF
print(kc.dump_graph())       # Turtle string
```

## The `kc:uri` attribute

Every element (vertex, edge, or face) can carry an optional `kc:uri` property pointing to its source file:

```python
kc.add_vertex("doc-001", type="spec", uri="file:///path/to/doc-001.md")
kc.add_edge("ver-001",   type="verification", vertices={"doc-001", "doc-002"},
            uri="file:///edges/ver-001.md", status="passing")
```

SHACL enforces at-most-one `kc:uri` per element. This is particularly useful for domain applications like AAA where each element corresponds to an actual document file.

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
