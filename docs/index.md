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

Load a pre-built complex, discover hidden structure, and extend it:

```python
from knowledgecomplex import KnowledgeComplex, find_cliques, betti_numbers

# 1. Load a pre-built complex (vertices and edges, no faces yet)
kc = KnowledgeComplex.load("examples/01_quickstart/data/pipeline")

# 2. Discover triangles hiding in the edge graph
triangles = find_cliques(kc, k=3)
print(f"Found {len(triangles)} triangles")       # 2

# 3. Check topology — independent cycles exist
print(betti_numbers(kc))                          # [1, 2, 0] — two cycles

# 4. Declare face types and fill them in
from knowledgecomplex import infer_faces
kc._schema.add_face_type("operation")
infer_faces(kc, "operation")

# 5. Cycles are now filled
print(betti_numbers(kc))                          # [1, 0, 0] — no more cycles

# 6. Visualize
from knowledgecomplex import plot_hasse, plot_geometric
fig, ax = plot_hasse(kc)
fig, ax = plot_geometric(kc)
```

For building schemas from scratch, see [`examples/02_construction/`](https://github.com/blockscience/knowledgecomplex/tree/main/examples/02_construction). Three pre-built ontologies ship with the package:

```python
from knowledgecomplex.ontologies import operations, brand, research
sb = brand.schema()   # audience/theme with resonance, interplay, overlap
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
