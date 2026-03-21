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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# rdflib is an internal implementation detail.
# Do not re-export any rdflib types through the public API.
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD, BNode
from rdflib.collection import Collection

_RESOURCES = Path(__file__).parent / "resources"
_CORE_OWL = _RESOURCES / "kc_core.ttl"
_CORE_SHAPES = _RESOURCES / "kc_core_shapes.ttl"

# Internal namespace constants
_KC = Namespace("https://w3id.org/kc#")
_KCS = Namespace("https://w3id.org/kc/shape#")
_SH = Namespace("http://www.w3.org/ns/shacl#")


@runtime_checkable
class Codec(Protocol):
    """
    Bidirectional bridge between element records and artifacts at URIs.

    A codec pairs compile (map → territory) and decompile (territory → map)
    for a given element type. Registered on KnowledgeComplex instances via
    register_codec(), and inherited by child types.
    """

    def compile(self, element: dict) -> None:
        """
        Write an element record to the artifact at its URI.

        Parameters
        ----------
        element : dict
            Keys: id, type, uri, plus all attribute key-value pairs.
        """
        ...

    def decompile(self, uri: str) -> dict:
        """
        Read the artifact at a URI and return an attribute dict.

        Parameters
        ----------
        uri : str
            The URI of the artifact to read.

        Returns
        -------
        dict
            Attribute key-value pairs suitable for add_vertex/add_edge/add_face kwargs.
        """
        ...


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
        self._queries: dict[str, str] = {}  # name -> SPARQL template string
        self._init_graphs()

    def __repr__(self) -> str:
        return f"SchemaBuilder(namespace={self._namespace!r}, types={len(self._types)})"

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

    def _validate_parent(self, parent: str | None, expected_kind: str) -> None:
        """Validate parent type exists and has the correct kind."""
        from knowledgecomplex.exceptions import SchemaError
        if parent is None:
            return
        if parent not in self._types:
            raise SchemaError(f"Parent type '{parent}' is not registered")
        if self._types[parent]["kind"] != expected_kind:
            raise SchemaError(
                f"Parent type '{parent}' is kind '{self._types[parent]['kind']}', "
                f"expected '{expected_kind}'"
            )

    def _collect_inherited_attributes(self, type_name: str) -> dict:
        """Walk the parent chain and collect all inherited attributes."""
        inherited = {}
        current = self._types[type_name].get("parent")
        while current is not None:
            parent_attrs = self._types[current].get("attributes", {})
            # Earlier ancestors are overridden by closer ancestors
            for k, v in parent_attrs.items():
                if k not in inherited:
                    inherited[k] = v
            current = self._types[current].get("parent")
        return inherited

    def _validate_bind(
        self,
        bind: dict[str, str],
        all_attributes: dict,
    ) -> None:
        """Validate that bind keys exist in all_attributes and values are legal."""
        from knowledgecomplex.exceptions import SchemaError
        for attr_name, bound_value in bind.items():
            if attr_name not in all_attributes:
                raise SchemaError(
                    f"Cannot bind '{attr_name}': attribute not found on this type or its ancestors"
                )
            descriptor = all_attributes[attr_name]
            # Unwrap dict-style descriptors
            if isinstance(descriptor, dict):
                descriptor = descriptor.get("vocab") or descriptor.get("text")
            if isinstance(descriptor, VocabDescriptor):
                if bound_value not in descriptor.values:
                    raise SchemaError(
                        f"Cannot bind '{attr_name}' to '{bound_value}': "
                        f"not in allowed values {descriptor.values}"
                    )

    def _apply_bind(self, shape_iri: URIRef, bind: dict[str, str]) -> None:
        """Add sh:hasValue + sh:minCount 1 constraints for bound attributes."""
        for attr_name, bound_value in bind.items():
            attr_iri = self._ns[attr_name]
            prop_shape = BNode()
            self._shacl_graph.add((shape_iri, _SH.property, prop_shape))
            self._shacl_graph.add((prop_shape, _SH.path, attr_iri))
            self._shacl_graph.add((prop_shape, _SH.hasValue, Literal(bound_value)))
            self._shacl_graph.add((prop_shape, _SH.minCount, Literal(1)))

    def add_vertex_type(
        self,
        name: str,
        attributes: dict[str, VocabDescriptor | TextDescriptor | Any] | None = None,
        parent: str | None = None,
        bind: dict[str, str] | None = None,
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
        parent : str, optional
            Name of a registered vertex type to inherit from.
        bind : dict, optional
            Mapping of attribute names to fixed string values (sh:hasValue).

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if name in self._types:
            raise SchemaError(f"Type '{name}' is already registered")
        self._validate_parent(parent, "vertex")
        attributes = attributes or {}
        bind = bind or {}

        self._types[name] = {
            "kind": "vertex",
            "attributes": dict(attributes),
            "parent": parent,
            "bind": dict(bind),
        }

        # Validate bind against all attributes (own + inherited)
        if bind:
            inherited = self._collect_inherited_attributes(name)
            all_attrs = {**inherited, **attributes}
            self._validate_bind(bind, all_attrs)

        type_iri = self._ns[name]
        shape_iri = self._nss[f"{name}Shape"]

        # OWL
        superclass = self._ns[parent] if parent else _KC.Vertex
        self._owl_graph.add((type_iri, RDF.type, OWL.Class))
        self._owl_graph.add((type_iri, RDFS.subClassOf, superclass))

        # SHACL
        self._shacl_graph.add((shape_iri, RDF.type, _SH.NodeShape))
        self._shacl_graph.add((shape_iri, _SH.targetClass, type_iri))

        for attr_name, attr_spec in attributes.items():
            self._dispatch_attr(type_iri, shape_iri, attr_name, attr_spec)

        if bind:
            self._apply_bind(shape_iri, bind)

        return self

    def add_edge_type(
        self,
        name: str,
        attributes: dict[str, VocabDescriptor | TextDescriptor | Any] | None = None,
        parent: str | None = None,
        bind: dict[str, str] | None = None,
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
        parent : str, optional
            Name of a registered edge type to inherit from.
        bind : dict, optional
            Mapping of attribute names to fixed string values (sh:hasValue).

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if name in self._types:
            raise SchemaError(f"Type '{name}' is already registered")
        self._validate_parent(parent, "edge")
        attributes = attributes or {}
        bind = bind or {}

        self._types[name] = {
            "kind": "edge",
            "attributes": dict(attributes),
            "parent": parent,
            "bind": dict(bind),
        }

        if bind:
            inherited = self._collect_inherited_attributes(name)
            all_attrs = {**inherited, **attributes}
            self._validate_bind(bind, all_attrs)

        type_iri = self._ns[name]
        shape_iri = self._nss[f"{name}Shape"]

        # OWL
        superclass = self._ns[parent] if parent else _KC.Edge
        self._owl_graph.add((type_iri, RDF.type, OWL.Class))
        self._owl_graph.add((type_iri, RDFS.subClassOf, superclass))

        # SHACL
        self._shacl_graph.add((shape_iri, RDF.type, _SH.NodeShape))
        self._shacl_graph.add((shape_iri, _SH.targetClass, type_iri))

        for attr_name, attr_spec in attributes.items():
            self._dispatch_attr(type_iri, shape_iri, attr_name, attr_spec)

        if bind:
            self._apply_bind(shape_iri, bind)

        return self

    def add_face_type(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        parent: str | None = None,
        bind: dict[str, str] | None = None,
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
        parent : str, optional
            Name of a registered face type to inherit from.
        bind : dict, optional
            Mapping of attribute names to fixed string values (sh:hasValue).

        Returns
        -------
        SchemaBuilder (self, for chaining)
        """
        from knowledgecomplex.exceptions import SchemaError
        if name in self._types:
            raise SchemaError(f"Type '{name}' is already registered")
        self._validate_parent(parent, "face")
        attributes = attributes or {}
        bind = bind or {}

        self._types[name] = {
            "kind": "face",
            "attributes": dict(attributes),
            "parent": parent,
            "bind": dict(bind),
        }

        if bind:
            inherited = self._collect_inherited_attributes(name)
            all_attrs = {**inherited, **attributes}
            self._validate_bind(bind, all_attrs)

        type_iri = self._ns[name]
        shape_iri = self._nss[f"{name}Shape"]

        # OWL
        superclass = self._ns[parent] if parent else _KC.Face
        self._owl_graph.add((type_iri, RDF.type, OWL.Class))
        self._owl_graph.add((type_iri, RDFS.subClassOf, superclass))

        # SHACL
        self._shacl_graph.add((shape_iri, RDF.type, _SH.NodeShape))
        self._shacl_graph.add((shape_iri, _SH.targetClass, type_iri))

        for attr_name, attr_spec in attributes.items():
            self._dispatch_attr(type_iri, shape_iri, attr_name, attr_spec)

        if bind:
            self._apply_bind(shape_iri, bind)

        return self

    def describe_type(self, name: str) -> dict:
        """
        Inspect a registered type's attributes, parent, and bindings.

        Parameters
        ----------
        name : str
            The registered type name.

        Returns
        -------
        dict
            Keys: name, kind, parent, own_attributes, inherited_attributes,
            all_attributes, bound.
        """
        from knowledgecomplex.exceptions import SchemaError
        if name not in self._types:
            raise SchemaError(f"Type '{name}' is not registered")

        info = self._types[name]
        own_attrs = dict(info.get("attributes", {}))
        inherited_attrs = self._collect_inherited_attributes(name)
        # Collect bindings from ancestors
        inherited_bind = {}
        current = info.get("parent")
        while current is not None:
            parent_bind = self._types[current].get("bind", {})
            for k, v in parent_bind.items():
                if k not in inherited_bind:
                    inherited_bind[k] = v
            current = self._types[current].get("parent")
        own_bind = dict(info.get("bind", {}))
        all_bind = {**inherited_bind, **own_bind}

        all_attrs = {**inherited_attrs, **own_attrs}
        return {
            "name": name,
            "kind": info["kind"],
            "parent": info.get("parent"),
            "own_attributes": own_attrs,
            "inherited_attributes": inherited_attrs,
            "all_attributes": all_attrs,
            "bound": all_bind,
        }

    def type_names(self, kind: str | None = None) -> list[str]:
        """
        List registered type names, optionally filtered by kind.

        Parameters
        ----------
        kind : str, optional
            Filter by "vertex", "edge", or "face".

        Returns
        -------
        list[str]
        """
        if kind is None:
            return list(self._types.keys())
        return [n for n, info in self._types.items() if info["kind"] == kind]

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

    # --- Topological query registration and constraint escalation ---

    _TOPO_PATTERNS: dict[str, tuple[str, str]] = {
        # operation -> (graph_pattern_template, result_variable)
        # {simplex_iri} is replaced by the target IRI,
        # {type_filter} by a type constraint or "".
        "boundary": (
            "{simplex_iri} kc:boundedBy ?result . {type_filter}",
            "result",
        ),
        "coboundary": (
            "?result kc:boundedBy {simplex_iri} . {type_filter}",
            "result",
        ),
        "star": (
            "?result kc:boundedBy* {simplex_iri} . {type_filter}",
            "result",
        ),
        "closure": (
            "{simplex_iri} kc:boundedBy* ?result . {type_filter}",
            "result",
        ),
        "link": (
            # closed_star minus star: elements reachable from star's closure
            # but not in the star itself
            "?star_elem kc:boundedBy* {simplex_iri} . "
            "?star_elem kc:boundedBy* ?result . "
            "FILTER NOT EXISTS {{ ?result kc:boundedBy* {simplex_iri} }} "
            "{type_filter}",
            "result",
        ),
        "degree": (
            "?result kc:boundedBy {simplex_iri} .",
            "result",
        ),
    }

    def _build_topo_sparql(
        self,
        operation: str,
        *,
        simplex_iri: str = "{simplex}",
        target_type: str | None = None,
    ) -> str:
        """Build a complete SPARQL SELECT from a topological operation.

        Parameters
        ----------
        operation :
            One of: boundary, coboundary, star, closure, link, degree.
        simplex_iri :
            IRI or placeholder for the focus element.
        target_type :
            Optional type name to filter results.

        Returns
        -------
        str
            A complete SPARQL SELECT query string.
        """
        from knowledgecomplex.exceptions import SchemaError
        if operation not in self._TOPO_PATTERNS:
            raise SchemaError(
                f"Unknown topological operation '{operation}'. "
                f"Valid: {sorted(self._TOPO_PATTERNS)}"
            )
        pattern_tmpl, result_var = self._TOPO_PATTERNS[operation]

        if target_type is not None:
            if target_type not in self._types:
                raise SchemaError(f"Type '{target_type}' is not registered")
            type_iri = self._ns[target_type]
            tf = f"?{result_var} a/rdfs:subClassOf* <{type_iri}> ."
        else:
            tf = ""

        pattern = (
            pattern_tmpl
            .replace("{simplex_iri}", simplex_iri)
            .replace("{type_filter}", tf)
        )

        return (
            f"PREFIX kc: <https://w3id.org/kc#>\n"
            f"PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            f"SELECT ?{result_var} WHERE {{\n"
            f"    {pattern}\n"
            f"}}\n"
        )

    def add_query(
        self,
        name: str,
        operation: str,
        *,
        target_type: str | None = None,
    ) -> "SchemaBuilder":
        """Register a named topological query template on this schema.

        The query is generated from a topological operation and optional type
        filter, then stored internally. It is exported as a ``.sparql`` file
        by :meth:`export` and automatically loaded by
        :class:`~knowledgecomplex.graph.KnowledgeComplex` at runtime.

        Parameters
        ----------
        name : str
            Query template name (becomes the filename stem, e.g. ``"spec_coboundary"``
            exports as ``queries/spec_coboundary.sparql``).
        operation : str
            Topological operation: ``"boundary"``, ``"coboundary"``, ``"star"``,
            ``"closure"``, ``"link"``, or ``"degree"``.
        target_type : str, optional
            Filter results to this type (including subtypes via OWL class hierarchy).

        Returns
        -------
        SchemaBuilder (self, for chaining)

        Example
        -------
        >>> sb.add_query("spec_coboundary", "coboundary", target_type="verification")
        """
        sparql = self._build_topo_sparql(
            operation, simplex_iri="{simplex}", target_type=target_type,
        )
        self._queries[name] = sparql
        return self

    def add_topological_constraint(
        self,
        type_name: str,
        operation: str,
        *,
        target_type: str | None = None,
        predicate: str = "min_count",
        min_count: int = 1,
        max_count: int | None = None,
        message: str | None = None,
    ) -> "SchemaBuilder":
        """Escalate a topological query to a SHACL constraint.

        Generates a ``sh:sparql`` constraint that, for each focus node of
        *type_name*, evaluates a topological operation and checks a cardinality
        predicate. Delegates to :meth:`add_sparql_constraint`.

        Parameters
        ----------
        type_name : str
            The type to constrain (must be registered).
        operation : str
            Topological operation: ``"boundary"``, ``"coboundary"``, ``"star"``,
            ``"closure"``, ``"link"``, or ``"degree"``.
        target_type : str, optional
            Filter the topological result to this type.
        predicate : str
            ``"min_count"`` — at least *min_count* results (default).
            ``"max_count"`` — at most *max_count* results.
            ``"exact_count"`` — exactly *min_count* results.
        min_count : int
            Minimum count (used by ``"min_count"`` and ``"exact_count"``).
        max_count : int, optional
            Maximum count (used by ``"max_count"``).
        message : str, optional
            Custom violation message. Auto-generated if not provided.

        Returns
        -------
        SchemaBuilder (self, for chaining)

        Example
        -------
        >>> sb.add_topological_constraint(
        ...     "spec", "coboundary",
        ...     target_type="verification",
        ...     predicate="min_count", min_count=1,
        ...     message="Every spec must have at least one verification edge",
        ... )
        """
        from knowledgecomplex.exceptions import SchemaError
        if type_name not in self._types:
            raise SchemaError(f"Type '{type_name}' is not registered")
        if operation not in self._TOPO_PATTERNS:
            raise SchemaError(
                f"Unknown topological operation '{operation}'. "
                f"Valid: {sorted(self._TOPO_PATTERNS)}"
            )

        pattern_tmpl, result_var = self._TOPO_PATTERNS[operation]

        if target_type is not None:
            if target_type not in self._types:
                raise SchemaError(f"Type '{target_type}' is not registered")
            type_iri = self._ns[target_type]
            tf = f"?{result_var} a/rdfs:subClassOf* <{type_iri}> ."
        else:
            tf = ""

        pattern = (
            pattern_tmpl
            .replace("{simplex_iri}", "$this")
            .replace("{type_filter}", tf)
        )

        # Build the HAVING clause based on predicate
        if predicate == "min_count":
            having = f"HAVING (COUNT(DISTINCT ?{result_var}) < {min_count})"
        elif predicate == "max_count":
            if max_count is None:
                raise SchemaError("max_count predicate requires max_count parameter")
            having = f"HAVING (COUNT(DISTINCT ?{result_var}) > {max_count})"
        elif predicate == "exact_count":
            having = f"HAVING (COUNT(DISTINCT ?{result_var}) != {min_count})"
        else:
            raise SchemaError(
                f"Unknown predicate '{predicate}'. "
                f"Valid: min_count, max_count, exact_count"
            )

        # Wrap pattern in OPTIONAL so GROUP BY produces a row even when
        # there are zero matches (otherwise HAVING never fires for empty results)
        sparql = (
            f"PREFIX kc: <https://w3id.org/kc#>\n"
            f"PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            f"SELECT $this WHERE {{\n"
            f"    OPTIONAL {{ {pattern} }}\n"
            f"}}\n"
            f"GROUP BY $this\n"
            f"{having}\n"
        )

        if message is None:
            target_desc = f" of type '{target_type}'" if target_type else ""
            message = (
                f"Topological constraint violated: {operation}{target_desc} "
                f"on '{type_name}' failed {predicate} check "
                f"(min={min_count}, max={max_count})"
            )

        return self.add_sparql_constraint(type_name, sparql, message)

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
        # Write schema-generated query templates and copy external query dirs
        if self._queries or query_dirs:
            qdir = p / "queries"
            qdir.mkdir(exist_ok=True)
            for name, sparql_text in self._queries.items():
                (qdir / f"{name}.sparql").write_text(sparql_text)
            if query_dirs:
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
        sb._queries = {}

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
