"""
knowledgecomplex.schema — SchemaBuilder and vocab/text descriptors.

Public API. Never exposes rdflib, pyshacl, or owlrl objects.

Internal structure mirrors the 2x2 responsibility map:
  {topological, ontological} x {OWL, SHACL}

The core ontology defines KC:Element as the base class for all simplices,
with KC:Vertex (k=0), KC:Edge (k=1), KC:Face (k=2) as subclasses.
add_vertex_type / add_edge_type / add_face_type each declare a user type
as a subclass of the appropriate simplex class and write to both internal
OWL and SHACL graphs.

dump_owl() and dump_shacl() return merged (core + user) Turtle strings.
"""

from __future__ import annotations
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# rdflib is an internal implementation detail.
# Do not re-export any rdflib types through the public API.
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD, BNode
from rdflib.collection import Collection

_RESOURCES = Path(__file__).parent / "resources"
_CORE_OWL = _RESOURCES / "kc_core.ttl"
_CORE_SHAPES = _RESOURCES / "kc_core_shapes.ttl"

# Internal namespace constants
_KC = Namespace("https://example.org/kc#")
_KCS = Namespace("https://example.org/kc/shape#")
_SH = Namespace("http://www.w3.org/ns/shacl#")


@dataclass(frozen=True)
class VocabDescriptor:
    """
    Returned by vocab(). Carries the allowed string values for an attribute.
    Generates both an OWL rdfs:comment annotation and a SHACL sh:in constraint
    when passed to add_*_type().
    """
    values: tuple[str, ...]
    multiple: bool = False

    def __repr__(self) -> str:
        suffix = ", multiple=True" if self.multiple else ""
        return f"vocab({', '.join(repr(v) for v in self.values)}{suffix})"


def vocab(*values: str, multiple: bool = False) -> VocabDescriptor:
    """
    Declare a controlled vocabulary for an attribute.

    Parameters
    ----------
    *values : str
        The allowed string values.
    multiple : bool
        If True, allows multiple values (no sh:maxCount).
        If False (default), generates sh:maxCount 1.

    Returns
    -------
    VocabDescriptor

    Example
    -------
    >>> vocab("adjacent", "opposite")
    vocab('adjacent', 'opposite')
    >>> vocab("a", "b", "c", multiple=True)
    vocab('a', 'b', 'c', multiple=True)
    """
    if not values:
        raise ValueError("vocab() requires at least one value")
    return VocabDescriptor(values=tuple(values), multiple=multiple)


@dataclass(frozen=True)
class TextDescriptor:
    """
    Returned by text(). Marks an attribute as a free-text string (no controlled vocabulary).
    Generates an OWL DatatypeProperty with xsd:string range and a SHACL property shape
    with sh:datatype xsd:string but no sh:in constraint.
    """
    required: bool = True
    multiple: bool = False

    def __repr__(self) -> str:
        parts = []
        if not self.required:
            parts.append("required=False")
        if self.multiple:
            parts.append("multiple=True")
        return f"text({', '.join(parts)})"


def text(*, required: bool = True, multiple: bool = False) -> TextDescriptor:
    """
    Declare a free-text string attribute.

    Parameters
    ----------
    required : bool
        If True (default), generates sh:minCount 1.
    multiple : bool
        If True, allows multiple values (no sh:maxCount).
        If False (default), generates sh:maxCount 1.

    Returns
    -------
    TextDescriptor

    Example
    -------
    >>> text()
    text()
    >>> text(required=False, multiple=True)
    text(required=False, multiple=True)
    """
    return TextDescriptor(required=required, multiple=multiple)


class SchemaBuilder:
    """
    Author a knowledge complex schema: vertex types, edge types, face types.

    Each add_*_type call declares a new OWL subclass of the appropriate
    KC:Element subclass (Vertex, Edge, or Face) and creates a corresponding
    SHACL node shape. Both OWL and SHACL graphs are maintained internally.
    dump_owl() / dump_shacl() return the full merged Turtle strings.

    Parameters
    ----------
    namespace : str
        Short namespace token for user-defined classes and properties.
        Used to build IRI prefix: https://example.org/{namespace}#

    Example
    -------
    >>> sb = SchemaBuilder(namespace="aaa")
    >>> sb.add_vertex_type("spec")
    >>> sb.add_edge_type("verification",
    ...     attributes={"status": vocab("passing", "failing", "pending")})
    >>> sb.add_face_type("assurance")
    >>> owl_ttl = sb.dump_owl()
    >>> shacl_ttl = sb.dump_shacl()
    """

    def __init__(self, namespace: str) -> None:
        self._namespace = namespace
        self._base_iri = f"https://example.org/{namespace}#"
        # Internal namespace objects
        self._ns = Namespace(self._base_iri)
        self._nss = Namespace(f"https://example.org/{namespace}/shape#")
        # Internal graphs — never exposed publicly
        self._owl_graph: Any = None   # rdflib.Graph, populated in _init_graphs()
        self._shacl_graph: Any = None # rdflib.Graph, populated in _init_graphs()
        self._types: dict[str, dict] = {}  # registry: name -> {kind, attributes}
        self._attr_domains: dict[str, URIRef | None] = {}  # attr name → first domain or None if shared
        self._init_graphs()

    def _init_graphs(self) -> None:
        """Load core OWL and SHACL static resources into internal graphs."""
        self._owl_graph = Graph()
        self._owl_graph.parse(str(_CORE_OWL), format="turtle")

        self._shacl_graph = Graph()
        self._shacl_graph.parse(str(_CORE_SHAPES), format="turtle")

        # Bind prefixes on both graphs
        for g in (self._owl_graph, self._shacl_graph):
            g.bind("kc", _KC)
            g.bind("kcs", _KCS)
            g.bind("sh", _SH)
            g.bind("owl", OWL)
            g.bind("rdfs", RDFS)
            g.bind("rdf", RDF)
            g.bind("xsd", XSD)
            g.bind(self._namespace, self._ns)
            g.bind(f"{self._namespace}s", self._nss)

    def _set_owl_domain(self, attr_iri: URIRef, attr_name: str, type_iri: URIRef) -> None:
        """Set rdfs:domain for a property, removing it if shared across types.

        When a property appears on multiple types, setting multiple rdfs:domain
        values causes RDFS inference to classify any individual with that property
        as a member of ALL domain types — leading to spurious SHACL cross-type
        violations. If the property already has a domain for a different type,
        we remove all domain assertions (SHACL shapes handle per-type enforcement).
        """
        if attr_name not in self._attr_domains:
            # First time seeing this attribute — set domain
            self._attr_domains[attr_name] = type_iri
            self._owl_graph.add((attr_iri, RDFS.domain, type_iri))
        elif self._attr_domains[attr_name] is not None and self._attr_domains[attr_name] != type_iri:
            # Shared across types — remove existing domain
            self._owl_graph.remove((attr_iri, RDFS.domain, None))
            self._attr_domains[attr_name] = None
        # else: already None (shared) or same type — no action needed

    def _add_vocab_attr_to_graphs(
        self,
        type_iri: URIRef,
        shape_iri: URIRef,
        attr_name: str,
        vocab_desc: VocabDescriptor,
        required: bool,
    ) -> None:
        """Add a vocab attribute's OWL property and SHACL property shape (with sh:in)."""
        attr_iri = self._ns[attr_name]

        # OWL: declare data property
        self._owl_graph.add((attr_iri, RDF.type, OWL.DatatypeProperty))
        self._set_owl_domain(attr_iri, attr_name, type_iri)
        self._owl_graph.add((attr_iri, RDFS.range, XSD.string))
        self._owl_graph.add((attr_iri, RDFS.comment,
                             Literal(f"Allowed values: {', '.join(vocab_desc.values)}")))

        # SHACL: create property shape
        prop_shape = BNode()
        self._shacl_graph.add((shape_iri, _SH.property, prop_shape))
        self._shacl_graph.add((prop_shape, _SH.path, attr_iri))
        self._shacl_graph.add((prop_shape, _SH.datatype, XSD.string))
        self._shacl_graph.add((prop_shape, _SH.minCount, Literal(1 if required else 0)))
        if not vocab_desc.multiple:
            self._shacl_graph.add((prop_shape, _SH.maxCount, Literal(1)))

        # sh:in list
        list_node = BNode()
        self._shacl_graph.add((prop_shape, _SH["in"], list_node))
        Collection(self._shacl_graph, list_node,
                   [Literal(v) for v in vocab_desc.values])

    def _add_text_attr_to_graphs(
        self,
        type_iri: URIRef,
        shape_iri: URIRef,
        attr_name: str,
        text_desc: TextDescriptor,
    ) -> None:
        """Add a free-text attribute's OWL property and SHACL property shape (no sh:in)."""
        attr_iri = self._ns[attr_name]

        # OWL: declare data property
        self._owl_graph.add((attr_iri, RDF.type, OWL.DatatypeProperty))
        self._set_owl_domain(attr_iri, attr_name, type_iri)
        self._owl_graph.add((attr_iri, RDFS.range, XSD.string))

        # SHACL: create property shape
        prop_shape = BNode()
        self._shacl_graph.add((shape_iri, _SH.property, prop_shape))
        self._shacl_graph.add((prop_shape, _SH.path, attr_iri))
        self._shacl_graph.add((prop_shape, _SH.datatype, XSD.string))
        self._shacl_graph.add((prop_shape, _SH.minCount,
                               Literal(1 if text_desc.required else 0)))
        if not text_desc.multiple:
            self._shacl_graph.add((prop_shape, _SH.maxCount, Literal(1)))

    def _add_attr_to_graphs(
        self,
        type_iri: URIRef,
        shape_iri: URIRef,
        attr_name: str,
        descriptor: VocabDescriptor | TextDescriptor,
        required: bool | None = None,
    ) -> None:
        """Dispatch to the appropriate attr handler based on descriptor type."""
        if isinstance(descriptor, TextDescriptor):
            self._add_text_attr_to_graphs(type_iri, shape_iri, attr_name, descriptor)
        elif isinstance(descriptor, VocabDescriptor):
            if required is None:
                required = True
            self._add_vocab_attr_to_graphs(type_iri, shape_iri, attr_name, descriptor, required)
        else:
            raise TypeError(f"Unknown attribute descriptor: {type(descriptor)}")

    def _dispatch_attr(
        self,
        type_iri: URIRef,
        shape_iri: URIRef,
        attr_name: str,
        attr_spec: VocabDescriptor | TextDescriptor | dict,
    ) -> None:
        """Route an attribute spec to the correct graph-writing method."""
        if isinstance(attr_spec, (VocabDescriptor, TextDescriptor)):
            self._add_attr_to_graphs(type_iri, shape_iri, attr_name, attr_spec)
        elif isinstance(attr_spec, dict):
            if "vocab" in attr_spec:
                vd = attr_spec["vocab"]
                req = attr_spec.get("required", True)
                self._add_attr_to_graphs(type_iri, shape_iri, attr_name, vd, required=req)
            elif "text" in attr_spec:
                td = attr_spec["text"]
                self._add_attr_to_graphs(type_iri, shape_iri, attr_name, td)
            else:
                raise TypeError(f"Attribute dict must have 'vocab' or 'text' key: {attr_spec}")
        else:
            raise TypeError(f"Unknown attribute spec type: {type(attr_spec)}")

    def add_vertex_type(
        self,
        name: str,
        attributes: dict[str, VocabDescriptor | TextDescriptor | Any] | None = None,
    ) -> "SchemaBuilder":
        """
        Declare a new vertex type (OWL subclass of KC:Vertex + SHACL node shape).

        Parameters
        ----------
        name : str
            Class name within the user namespace.
        attributes : dict, optional
            Mapping of attribute name to descriptor (VocabDescriptor, TextDescriptor,
            or dict with "vocab"/"text" key and optional "required" flag).

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if name in self._types:
            raise SchemaError(f"Type '{name}' is already registered")
        attributes = attributes or {}
        self._types[name] = {"kind": "vertex", "attributes": dict(attributes)}
        type_iri = self._ns[name]
        shape_iri = self._nss[f"{name}Shape"]

        # OWL
        self._owl_graph.add((type_iri, RDF.type, OWL.Class))
        self._owl_graph.add((type_iri, RDFS.subClassOf, _KC.Vertex))

        # SHACL
        self._shacl_graph.add((shape_iri, RDF.type, _SH.NodeShape))
        self._shacl_graph.add((shape_iri, _SH.targetClass, type_iri))

        for attr_name, attr_spec in attributes.items():
            self._dispatch_attr(type_iri, shape_iri, attr_name, attr_spec)

        return self

    def add_edge_type(
        self,
        name: str,
        attributes: dict[str, VocabDescriptor | TextDescriptor | Any] | None = None,
    ) -> "SchemaBuilder":
        """
        Declare a new edge type (OWL subclass of KC:Edge + SHACL property shapes).

        Parameters
        ----------
        name : str
            Class name within the user namespace.
        attributes : dict, optional
            Mapping of attribute name to descriptor (VocabDescriptor, TextDescriptor,
            or dict with "vocab"/"text" key and optional "required" flag).

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if name in self._types:
            raise SchemaError(f"Type '{name}' is already registered")
        attributes = attributes or {}
        self._types[name] = {"kind": "edge", "attributes": dict(attributes)}
        type_iri = self._ns[name]
        shape_iri = self._nss[f"{name}Shape"]

        # OWL
        self._owl_graph.add((type_iri, RDF.type, OWL.Class))
        self._owl_graph.add((type_iri, RDFS.subClassOf, _KC.Edge))

        # SHACL
        self._shacl_graph.add((shape_iri, RDF.type, _SH.NodeShape))
        self._shacl_graph.add((shape_iri, _SH.targetClass, type_iri))

        for attr_name, attr_spec in attributes.items():
            self._dispatch_attr(type_iri, shape_iri, attr_name, attr_spec)

        return self

    def add_face_type(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> "SchemaBuilder":
        """
        Declare a new face type (OWL subclass of KC:Face + SHACL property shapes).

        Attributes with ``required=False`` generate sh:minCount 0 constraints.

        Parameters
        ----------
        name : str
            Class name within the user namespace.
        attributes : dict, optional
            Mapping of attribute name to descriptor (VocabDescriptor, TextDescriptor,
            or dict with "vocab"/"text" key and optional "required" flag).

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if name in self._types:
            raise SchemaError(f"Type '{name}' is already registered")
        attributes = attributes or {}
        self._types[name] = {"kind": "face", "attributes": dict(attributes)}
        type_iri = self._ns[name]
        shape_iri = self._nss[f"{name}Shape"]

        # OWL
        self._owl_graph.add((type_iri, RDF.type, OWL.Class))
        self._owl_graph.add((type_iri, RDFS.subClassOf, _KC.Face))

        # SHACL
        self._shacl_graph.add((shape_iri, RDF.type, _SH.NodeShape))
        self._shacl_graph.add((shape_iri, _SH.targetClass, type_iri))

        for attr_name, attr_spec in attributes.items():
            self._dispatch_attr(type_iri, shape_iri, attr_name, attr_spec)

        return self

    def promote_to_attribute(
        self,
        type: str,
        attribute: str,
        vocab: VocabDescriptor | None = None,
        text: TextDescriptor | None = None,
        required: bool = True,
    ) -> "SchemaBuilder":
        """
        Atomically promote a discovered pattern to a first-class typed attribute.

        Updates both OWL property definition and SHACL shape constraint for the named type.
        After calling this, dump_owl() and dump_shacl() both reflect the updated attribute.

        Parameters
        ----------
        type : str
            The type name (must have been registered via add_*_type).
        attribute : str
            Attribute name to add or upgrade.
        vocab : VocabDescriptor, optional
            Controlled vocabulary for the attribute.
        text : TextDescriptor, optional
            Free-text descriptor for the attribute.
        required : bool
            If True, generates sh:minCount 1. Overrides the descriptor's own required flag.

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if type not in self._types:
            raise SchemaError(f"Type '{type}' is not registered")
        if vocab is None and text is None:
            raise SchemaError("promote_to_attribute requires either vocab or text descriptor")

        type_iri = self._ns[type]
        shape_iri = self._nss[f"{type}Shape"]
        attr_iri = self._ns[attribute]

        # Remove existing OWL triples for this attribute (if upgrading)
        for p in (RDFS.domain, RDFS.range, RDFS.comment):
            self._owl_graph.remove((attr_iri, p, None))
        self._owl_graph.remove((attr_iri, RDF.type, OWL.DatatypeProperty))

        # Remove existing SHACL property shape for this attribute (if upgrading)
        for prop_node in list(self._shacl_graph.objects(shape_iri, _SH.property)):
            if (prop_node, _SH.path, attr_iri) in self._shacl_graph:
                # Remove the sh:in list
                list_head = self._shacl_graph.value(prop_node, _SH["in"])
                if list_head is not None:
                    Collection(self._shacl_graph, list_head).clear()
                    self._shacl_graph.remove((prop_node, _SH["in"], list_head))
                # Remove all triples about this property shape
                for p, o in list(self._shacl_graph.predicate_objects(prop_node)):
                    self._shacl_graph.remove((prop_node, p, o))
                self._shacl_graph.remove((shape_iri, _SH.property, prop_node))

        # Re-add with new settings
        if vocab is not None:
            self._add_attr_to_graphs(type_iri, shape_iri, attribute, vocab, required=required)
        else:
            # Override the text descriptor's required flag with the promote call's value
            effective = TextDescriptor(required=required, multiple=text.multiple)
            self._add_attr_to_graphs(type_iri, shape_iri, attribute, effective)

        # Update type registry
        if "attributes" not in self._types[type]:
            self._types[type]["attributes"] = {}
        if vocab is not None:
            self._types[type]["attributes"][attribute] = {
                "vocab": vocab, "required": required
            }
        else:
            self._types[type]["attributes"][attribute] = text

        return self

    def add_sparql_constraint(
        self,
        type_name: str,
        sparql: str,
        message: str,
    ) -> "SchemaBuilder":
        """
        Attach a sh:sparql constraint to the SHACL shape for type_name.

        The sparql argument must be a SPARQL SELECT query that returns $this
        for each violating focus node. pyshacl evaluates this and reports the
        message for each returned row.

        Parameters
        ----------
        type_name : str
            The type name (must have been registered via add_*_type).
        sparql : str
            SPARQL SELECT query. Must bind $this to each violating node.
        message : str
            Human-readable message reported when the constraint is violated.

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if type_name not in self._types:
            raise SchemaError(f"Type '{type_name}' is not registered")
        shape_iri = self._nss[f"{type_name}Shape"]
        constraint = BNode()
        self._shacl_graph.add((shape_iri, _SH.sparql, constraint))
        self._shacl_graph.add((constraint, RDF.type, _SH.SPARQLConstraint))
        self._shacl_graph.add((constraint, _SH.select, Literal(sparql)))
        self._shacl_graph.add((constraint, _SH.message, Literal(message)))
        return self

    def dump_owl(self) -> str:
        """Return merged OWL graph (core + user schema) as a Turtle string."""
        return self._owl_graph.serialize(format="turtle")

    def dump_shacl(self) -> str:
        """Return merged SHACL graph (core shapes + user shapes) as a Turtle string."""
        return self._shacl_graph.serialize(format="turtle")

    def export(
        self,
        path: str | Path,
        query_dirs: list[Path] | None = None,
    ) -> Path:
        """
        Export the schema to a directory as standard semantic web files.

        Writes ontology.ttl (OWL) and shapes.ttl (SHACL). If query_dirs are
        provided, copies all .sparql files into a queries/ subdirectory.

        Parameters
        ----------
        path : str | Path
            Target directory. Created if it does not exist.
        query_dirs : list[Path], optional
            Directories containing .sparql query templates to include.

        Returns
        -------
        Path
            The export directory.
        """
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        (p / "ontology.ttl").write_text(self.dump_owl())
        (p / "shapes.ttl").write_text(self.dump_shacl())
        if query_dirs:
            qdir = p / "queries"
            qdir.mkdir(exist_ok=True)
            for d in query_dirs:
                for sparql_file in d.glob("*.sparql"):
                    shutil.copy2(sparql_file, qdir / sparql_file.name)
        return p

    @classmethod
    def load(cls, path: str | Path) -> "SchemaBuilder":
        """
        Load a schema from a directory containing ontology.ttl and shapes.ttl.

        Reconstructs the type registry by inspecting OWL subclass triples.

        Parameters
        ----------
        path : str | Path
            Directory containing ontology.ttl and shapes.ttl.

        Returns
        -------
        SchemaBuilder
        """
        p = Path(path)

        owl_graph = Graph()
        owl_graph.parse(str(p / "ontology.ttl"), format="turtle")

        shacl_graph = Graph()
        shacl_graph.parse(str(p / "shapes.ttl"), format="turtle")

        # Discover model namespace: find a namespace binding that is not
        # one of the well-known prefixes (kc, kcs, sh, owl, rdfs, rdf, xsd)
        well_known = {
            str(_KC), str(_KCS), str(_SH),
            str(OWL), str(RDFS), str(RDF), str(XSD),
        }
        namespace = None
        ns_obj = None
        for prefix, uri in owl_graph.namespaces():
            uri_str = str(uri)
            if prefix and uri_str not in well_known and uri_str.startswith("https://example.org/"):
                # Skip shape namespaces (ending with /shape#)
                if "/shape#" in uri_str:
                    continue
                namespace = prefix
                ns_obj = Namespace(uri_str)
                break

        if namespace is None:
            raise ValueError(
                f"Could not detect model namespace in {p / 'ontology.ttl'}. "
                "Expected a namespace binding like 'aaa: <https://example.org/aaa#>'."
            )

        # Build instance without calling __init__
        sb = object.__new__(cls)
        sb._namespace = namespace
        sb._base_iri = str(ns_obj)
        sb._ns = ns_obj
        sb._nss = Namespace(f"https://example.org/{namespace}/shape#")
        sb._owl_graph = owl_graph
        sb._shacl_graph = shacl_graph
        sb._attr_domains = {}

        # Reconstruct _types registry from OWL subclass triples
        sb._types = {}
        kind_map = {
            _KC.Vertex: "vertex",
            _KC.Edge: "edge",
            _KC.Face: "face",
        }
        for kc_class, kind in kind_map.items():
            for type_iri in owl_graph.subjects(RDFS.subClassOf, kc_class):
                # Extract local name from IRI
                local_name = str(type_iri).replace(sb._base_iri, "")
                if local_name:
                    sb._types[local_name] = {"kind": kind}

        return sb
