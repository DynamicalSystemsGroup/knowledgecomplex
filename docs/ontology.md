# Ontology

The topological backbone of knowledgecomplex is defined by two static RDF resources shipped with the package.

## Core OWL — `kc_core.ttl`

The abstract OWL ontology declares the class hierarchy and structural axioms:

- **`kc:Element`** — base class for all simplices
- **`kc:Vertex`** (k=0), **`kc:Edge`** (k=1), **`kc:Face`** (k=2) — subclasses with cardinality axioms on `kc:boundedBy`
- **`kc:Complex`** — a collection of elements linked via `kc:hasElement`

OWL cardinality axioms express boundary counts at the schema level (e.g. an edge is bounded by exactly 2 vertices), but cannot enforce constraints that require co-reference across individuals.

## Core SHACL — `kc_core_shapes.ttl`

The abstract SHACL shapes graph enforces instance-level constraints that exceed OWL-DL expressivity:

- **Boundary distinctness** — the two boundary vertices of an edge must be different individuals
- **Closed triangle** — the three boundary edges of a face must connect its three boundary vertices
- **Boundary closure** — if a simplex is a member of a complex, all its boundary elements must also be members

These constraints use `sh:sparql` validators because they require cross-individual reasoning.

## Interoperability

Because KC stores all data as standard RDF and enforces constraints via W3C SHACL, instance graphs are natively compatible with RDF-based model management systems such as [Flexo MMS](https://github.com/Open-MBEE/flexo-mms-deployment) from the [OpenMBEE](https://www.openmbee.org/) community. JSON-LD export (`dump_graph(format="json-ld")`) provides the primary bridge format. See the [Interoperability section of ARCHITECTURE.md](https://github.com/blockscience/knowledgecomplex/blob/main/ARCHITECTURE.md#interoperability-flexo-mms-and-openmbee) for integration patterns.

## Design rationale

See [ARCHITECTURE.md](https://github.com/blockscience/knowledgecomplex/blob/main/ARCHITECTURE.md) for the full 2x2 responsibility map and design decisions.
