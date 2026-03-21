# Prebuilt Ontologies

This directory contains ready-to-use domain ontologies that ship with the package.
Each module exposes a `schema()` function returning a configured `SchemaBuilder`.

## Available ontologies

| Module | Domain | Vertex types | Edge types | Face types |
|--------|--------|-------------|------------|------------|
| `operations` | Actor/activity/resource workflows | actor, activity, resource | performs, requires, produces, accesses, responsible | operation, production |
| `brand` | Audience/theme brand strategy | audience, theme | resonance, interplay, overlap | thematic_alignment, audience_bridge |
| `research` | Paper/concept literature review | paper, concept, note | discusses, cites, connects, references | synthesis, annotation |

## Usage

```python
from knowledgecomplex import KnowledgeComplex
from knowledgecomplex.ontologies import operations

sb = operations.schema(namespace="my_project")
kc = KnowledgeComplex(schema=sb)

kc.add_vertex("alice", type="actor", name="Alice")
kc.add_vertex("etl",   type="activity", name="Daily ETL")
kc.add_edge("e1", type="performs", vertices={"alice", "etl"}, role="lead")
```

Each ontology is a thin Python module — typically under 30 lines. They exist as
convenience starting points, not as comprehensive domain models. Extend them by
calling additional `add_*_type()` methods on the returned `SchemaBuilder`.

## Philosophy: don't hoard ontologies

This package deliberately ships very few ontologies. Domain ontologies belong
to their domain communities, not to a framework package. The prebuilt ontologies
here are examples and starting points — they demonstrate the API patterns and
give new users something to run immediately.

For production use, we recommend:

1. **Define your ontology in Python** using `SchemaBuilder`
2. **Export it** as standard OWL + SHACL Turtle files
3. **Publish it** at a persistent URI following semantic web best practices
4. **Share the Python module** alongside the Turtle files for programmatic use

## Creating and exporting ontologies

### Define in Python

```python
from knowledgecomplex import SchemaBuilder, vocab, text

sb = SchemaBuilder(namespace="mydom")
sb.add_vertex_type("Document", attributes={"title": text(), "status": vocab("draft", "final")})
sb.add_edge_type("References")
sb.add_face_type("Collection")
```

### Export as Turtle

```python
# Export to a directory
sb.export("my_ontology/")
#   my_ontology/ontology.ttl   — OWL classes, properties, axioms
#   my_ontology/shapes.ttl     — SHACL validation shapes
#   my_ontology/queries/       — SPARQL templates (if any registered)

# Or get the raw Turtle strings
owl_turtle = sb.dump_owl()
shacl_turtle = sb.dump_shacl()
```

### Load from Turtle

```python
from knowledgecomplex import SchemaBuilder

sb = SchemaBuilder.load("my_ontology/")  # reads ontology.ttl + shapes.ttl
```

This makes ontologies portable — they can be shared as a directory of `.ttl`
files, version-controlled, and loaded by any `knowledgecomplex` user.

## Publishing ontologies on the semantic web

The standard approach for making ontologies discoverable and citable:

### 1. Choose a persistent URI

Use a redirect service that outlives any single hosting provider:

- **[w3id.org](https://w3id.org/)** — community-maintained persistent identifiers.
  Register by submitting a PR to [perma-id/w3id.org](https://github.com/perma-id/w3id.org)
  with an `.htaccess` file for content negotiation.
- **[purl.org](https://purl.archive.org/)** — Internet Archive's persistent URL service.

Example: `https://w3id.org/myorg/myontology/` resolves to your Turtle file
when requested with `Accept: text/turtle`, or to HTML documentation otherwise.

### 2. Host the Turtle files

The simplest approach: host on GitHub and point the persistent URI at the raw file.

```
# .htaccess for w3id.org
RewriteEngine On
RewriteCond %{HTTP_ACCEPT} text/turtle
RewriteRule ^$ https://raw.githubusercontent.com/myorg/myrepo/main/ontology.ttl [R=303,L]
RewriteRule ^$ https://myorg.github.io/myrepo/ [R=303,L]
```

### 3. Use dereferenceable URIs in your schema

Once your persistent URI is live, use it as your namespace:

```python
sb = SchemaBuilder(namespace="mydom")
# Currently generates: https://example.org/mydom#
# For production: update _base_iri to your w3id.org URI
```

Note: the current framework uses `https://example.org/{namespace}#` as the
default base IRI. For production deployments, this should be replaced with
your registered persistent URI. This is tracked as a pre-release task.

## Existing ontologies as design references

Standard semantic web ontologies (Dublin Core, SKOS, PROV-O, schema.org, etc.)
are **not directly compatible** with knowledge complex ontologies. They define
flat class hierarchies and properties — they don't inherit from `kc:Vertex`,
`kc:Edge`, or `kc:Face`, and they have no concept of boundary operators or
simplicial structure.

That said, they are valuable as **design references** when deciding what types
and attributes your KC ontology should have:

- **[Linked Open Vocabularies (LOV)](https://lov.linkeddata.es/)** — searchable
  index of RDF vocabularies. Useful for finding standard property names and
  attribute patterns before defining your own.
- **[schema.org](https://schema.org/)** — web-scale vocabulary. Good reference
  for entity types (Person, Organization, CreativeWork) when modeling actors.
- **[SKOS](https://www.w3.org/2004/02/skos/)** — knowledge organization.
  Relevant when your vertices represent concepts in a taxonomy.
- **[PROV-O](https://www.w3.org/TR/prov-o/)** — provenance. Useful patterns
  for activity/agent/entity relationships that map naturally to KC edges.

The workflow: browse existing ontologies for naming conventions and attribute
patterns, then declare your KC types using `SchemaBuilder`. The KC types
carry the simplicial structure that flat ontologies lack.

## The KC ontology registry (future)

Since KC ontologies extend `kc:Element` with typed simplices, they form their
own ecosystem distinct from the broader semantic web. A KC ontology authored
by one team can be loaded by another via `SchemaBuilder.load()`, but only if
it was exported by `SchemaBuilder.export()`.

We plan to host a public registry of KC-compatible ontologies at
**knowledgecomplex.org**. The registry will serve as the canonical place to:

- Discover published KC ontologies by domain
- Resolve persistent URIs for KC ontology namespaces
- Host documentation and SHACL shape files for registered ontologies
- Provide content negotiation (Turtle vs. HTML) following semantic web conventions

This is not yet live. For now, share ontologies as Git repositories containing
the exported `ontology.ttl` + `shapes.ttl` files and the Python module that
generates them. Community contributions of domain ontologies are welcome —
when the registry launches, published ontologies will be the first entries.

## Loading KC ontologies from Turtle

If you have a KC ontology exported by `SchemaBuilder.export()`:

```python
sb = SchemaBuilder.load("path/to/ontology_dir/")
# Reads ontology.ttl + shapes.ttl, reconstructs the type registry
```

This only works for KC-native ontologies (those extending `kc:Vertex`,
`kc:Edge`, `kc:Face`). Arbitrary OWL ontologies from external sources
cannot be loaded this way — they would need to be re-authored as KC types.
