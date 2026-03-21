"""
knowledgecomplex.graph — KnowledgeComplex instance I/O.

Public API. Never exposes rdflib, pyshacl, or owlrl objects.

A KnowledgeComplex corresponds to a kc:Complex individual in the RDF graph.
Each add_vertex / add_edge / add_face call asserts the new element AND its
kc:hasElement membership in the complex. SHACL validation on every write
enforces both per-element constraints (EdgeShape, FaceShape) and
boundary-closure (ComplexShape): if a simplex is in the complex, all its
boundary elements must be too.

This enforces the "slice rule": at every point during construction, the
elements added so far must form a valid complex. Concretely, an element's
boundary elements must already be members before it can be added. This is
a partial ordering — types can be interleaved as long as each element's
boundary predecessors are present (e.g., add v1, v2, edge(v1,v2), v3,
edge(v2,v3), ...). The simplest strategy is to add all vertices, then all
edges, then all faces, but this is not required.

SPARQL queries are encapsulated as named templates. The framework provides
generic queries in knowledgecomplex/queries/; domain models can supply
additional query directories via the query_dirs parameter.

The optional `uri` parameter on add_vertex / add_edge / add_face allows
callers to attach a file URI to any element via the kc:uri property. This
is particularly useful for domain applications where each element corresponds
to an actual document file (e.g. file:///path/to/doc.md).
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from knowledgecomplex.audit import AuditReport

import pandas as pd
import pyshacl
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD

from knowledgecomplex.exceptions import ValidationError, UnknownQueryError, SchemaError
from knowledgecomplex.schema import SchemaBuilder, Codec

_FRAMEWORK_QUERIES_DIR = Path(__file__).parent / "queries"

# Internal namespace constants
_KC = Namespace("https://example.org/kc#")


def _load_query_templates(
    extra_dirs: list[Path] | None = None,
) -> dict[str, str]:
    """Load .sparql files from framework queries dir and any extra directories.

    Extra directories (e.g. from domain models) are loaded after the framework
    queries. If a model provides a query with the same name as a framework query,
    the model's version takes precedence.
    """
    templates: dict[str, str] = {}
    dirs = [_FRAMEWORK_QUERIES_DIR] + (extra_dirs or [])
    for d in dirs:
        for path in d.glob("*.sparql"):
            templates[path.stem] = path.read_text()
    return templates


class _DeferredVerification:
    """Context manager that suppresses per-write SHACL, verifies on exit."""

    def __init__(self, kc: "KnowledgeComplex") -> None:
        self._kc = kc

    def __enter__(self) -> "KnowledgeComplex":
        self._kc._defer_verification = True
        return self._kc

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._kc._defer_verification = False
        if exc_type is None:
            self._kc.verify()
        return None


class Element:
    """
    Lightweight proxy for an element in a KnowledgeComplex.

    Provides read-only access to element properties and compile/decompile
    methods that delegate to the codec registered for this element's type.
    Properties read live from the instance graph on each access.
    """

    def __init__(self, kc: "KnowledgeComplex", id: str) -> None:
        self._kc = kc
        self._id = id
        self._iri = URIRef(f"{kc._schema._base_iri}{id}")

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        ns_str = self._kc._schema._base_iri
        for _, _, o in self._kc._instance_graph.triples((self._iri, RDF.type, None)):
            type_str = str(o)
            if type_str.startswith(ns_str):
                return type_str[len(ns_str):]
        raise ValueError(f"Element '{self._id}' has no user type")

    @property
    def uri(self) -> str | None:
        obj = self._kc._instance_graph.value(self._iri, _KC.uri)
        return str(obj) if obj is not None else None

    @property
    def attrs(self) -> dict[str, Any]:
        ns_str = self._kc._schema._base_iri
        attrs: dict[str, Any] = {}
        for _, p, o in self._kc._instance_graph.triples((self._iri, None, None)):
            p_str = str(p)
            if p_str.startswith(ns_str):
                attr_name = p_str[len(ns_str):]
                attrs[attr_name] = str(o)
        return attrs

    def compile(self) -> None:
        """Write this element's record to the artifact at its URI."""
        codec = self._kc._resolve_codec(self.type)
        uri = self.uri
        if uri is None:
            raise ValueError(f"Element '{self._id}' has no kc:uri — cannot compile")
        element_dict = {"id": self._id, "type": self.type, "uri": uri, **self.attrs}
        codec.compile(element_dict)

    def decompile(self) -> None:
        """Read the artifact at this element's URI and update attributes."""
        codec = self._kc._resolve_codec(self.type)
        uri = self.uri
        if uri is None:
            raise ValueError(f"Element '{self._id}' has no kc:uri — cannot decompile")
        new_attrs = codec.decompile(uri)

        # Remove existing model-namespace attribute triples
        ns_str = self._kc._schema._base_iri
        to_remove = []
        for s, p, o in self._kc._instance_graph.triples((self._iri, None, None)):
            if str(p).startswith(ns_str):
                to_remove.append((s, p, o))
        for triple in to_remove:
            self._kc._instance_graph.remove(triple)

        # Add new attribute triples
        for attr_name, attr_value in new_attrs.items():
            attr_iri = self._kc._ns[attr_name]
            if isinstance(attr_value, (list, tuple)):
                for v in attr_value:
                    self._kc._instance_graph.add((self._iri, attr_iri, Literal(v)))
            else:
                self._kc._instance_graph.add((self._iri, attr_iri, Literal(attr_value)))

        # Re-validate
        self._kc._validate(self._id)


class KnowledgeComplex:
    """
    Manage a knowledge complex instance: add elements, validate, query.

    Maps to a kc:Complex individual in the RDF graph. Each element added
    via add_vertex / add_edge / add_face becomes a kc:hasElement member of
    this complex. Boundary-closure is enforced by ComplexShape on every write
    (the "slice rule": every prefix of the insertion sequence is a valid complex).
    An element's boundary elements must be added before the element itself.

    Parameters
    ----------
    schema : SchemaBuilder
        A fully configured schema. The merged OWL + SHACL is loaded into
        the internal graph at construction time.
    query_dirs : list[Path], optional
        Additional directories containing .sparql query templates
        (e.g. from domain models). Merged with the framework's built-in queries.

    Example
    -------
    >>> from knowledgecomplex import SchemaBuilder, KnowledgeComplex, vocab
    >>> sb = SchemaBuilder(namespace="aaa")
    >>> sb.add_vertex_type("spec")
    >>> sb.add_vertex_type("guidance")
    >>> sb.add_edge_type("verification",
    ...     attributes={"status": vocab("passing", "failing", "pending")})
    >>> kc = KnowledgeComplex(schema=sb)
    >>> kc.add_vertex("spec-001", type="spec", uri="file:///docs/spec-001.md")
    >>> kc.add_vertex("guidance-001", type="guidance")
    >>> kc.add_edge("ver-001", type="verification",
    ...             vertices={"spec-001", "guidance-001"}, status="passing")
    """

    def __init__(
        self,
        schema: SchemaBuilder,
        query_dirs: list[Path] | None = None,
    ) -> None:
        self._schema = schema
        self._query_dirs_raw = query_dirs or []
        self._query_templates = _load_query_templates(extra_dirs=query_dirs)
        self._instance_graph: Any = None  # rdflib.Graph, populated in _init_graph()
        self._complex_iri: Any = None     # URIRef for the kc:Complex individual
        self._ns = schema._ns
        self._codecs: dict[str, Codec] = {}
        self._defer_verification = False
        self._init_graph()

    def _init_graph(self) -> None:
        """
        Initialize the instance graph and create the kc:Complex individual.

        Parses the merged OWL from schema into the instance graph.
        Creates a kc:Complex individual to serve as the container for all
        elements added via add_vertex / add_edge / add_face.
        Stores the ontology + shapes graphs separately for pyshacl calls.
        """
        # Parse merged OWL into instance graph (TBox + ABox in one graph)
        self._instance_graph = Graph()
        self._instance_graph.parse(data=self._schema.dump_owl(), format="turtle")

        # Separate graphs for pyshacl validation
        self._ont_graph = Graph()
        self._ont_graph.parse(data=self._schema.dump_owl(), format="turtle")
        self._shacl_graph = Graph()
        self._shacl_graph.parse(data=self._schema.dump_shacl(), format="turtle")

        # Create kc:Complex individual
        self._complex_iri = URIRef(f"{self._schema._base_iri}_complex")
        self._instance_graph.add((self._complex_iri, RDF.type, _KC.Complex))

        # Bind prefixes for SPARQL queries and serialization
        self._instance_graph.bind("kc", _KC)
        self._instance_graph.bind(self._schema._namespace, self._ns)
        self._instance_graph.bind("rdfs", RDFS)
        self._instance_graph.bind("rdf", RDF)
        self._instance_graph.bind("owl", OWL)
        self._instance_graph.bind("xsd", XSD)

    def _validate(self, focus_node_id: str | None = None) -> None:
        """
        Run pyshacl against the current instance graph.

        Skipped when deferred_verification() context manager is active.

        Parameters
        ----------
        focus_node_id : str, optional
            If provided, used in the error message to identify which element
            triggered the failure.

        Raises
        ------
        ValidationError
            If verification fails. report attribute contains human-readable text.
        """
        if self._defer_verification:
            return

        conforms, _, results_text = pyshacl.validate(
            data_graph=self._instance_graph,
            shacl_graph=self._shacl_graph,
            ont_graph=self._ont_graph,
            inference="rdfs",
            abort_on_first=False,
        )
        if not conforms:
            msg = "SHACL validation failed"
            if focus_node_id:
                msg += f" (after adding '{focus_node_id}')"
            raise ValidationError(msg, report=results_text)

    def verify(self) -> None:
        """
        Run SHACL verification on the current instance graph.

        Checks all topological and ontological constraints. Raises on failure.
        Use :meth:`audit` for a non-throwing alternative.

        Raises
        ------
        ValidationError
            If any SHACL constraint is violated.
        """
        # Bypass the deferral flag — verify() is an explicit user request
        conforms, _, results_text = pyshacl.validate(
            data_graph=self._instance_graph,
            shacl_graph=self._shacl_graph,
            ont_graph=self._ont_graph,
            inference="rdfs",
            abort_on_first=False,
        )
        if not conforms:
            raise ValidationError("SHACL verification failed", report=results_text)

    def audit(self) -> "AuditReport":
        """
        Run SHACL verification and return a structured report.

        Unlike :meth:`verify`, this never raises — it returns an
        :class:`~knowledgecomplex.audit.AuditReport` with ``conforms``,
        ``violations``, and ``text`` fields.

        Returns
        -------
        AuditReport
        """
        from knowledgecomplex.audit import _build_report
        conforms, _, results_text = pyshacl.validate(
            data_graph=self._instance_graph,
            shacl_graph=self._shacl_graph,
            ont_graph=self._ont_graph,
            inference="rdfs",
            abort_on_first=False,
        )
        return _build_report(conforms, results_text, self._schema._namespace)

    def deferred_verification(self) -> "_DeferredVerification":
        """
        Context manager that suppresses per-write SHACL verification.

        Inside the context, ``add_vertex``, ``add_edge``, and ``add_face``
        skip SHACL checks. On exit, a single verification pass runs over
        the entire graph. If verification fails, ``ValidationError`` is raised.

        This is much faster for bulk construction — one SHACL pass instead
        of one per element.

        Example
        -------
        >>> with kc.deferred_verification():
        ...     kc.add_vertex("v1", type="Node")
        ...     kc.add_vertex("v2", type="Node")
        ...     kc.add_edge("e1", type="Link", vertices={"v1", "v2"})
        """
        return _DeferredVerification(self)

    def _assert_element(
        self,
        id: str,
        type: str,
        boundary_ids: list[str] | None,
        attributes: dict[str, Any],
        uri: str | None = None,
    ) -> None:
        """Common logic for add_vertex, add_edge, add_face."""
        # Step 0: Python-side type guard
        if type not in self._schema._types:
            raise ValidationError(
                f"Unregistered type: '{type}'",
                report=f"Type '{type}' is not registered in the schema. "
                       f"Registered types: {sorted(self._schema._types.keys())}",
            )

        type_iri = self._ns[type]
        id_iri = URIRef(f"{self._schema._base_iri}{id}")

        # Track triples added for rollback on validation failure
        added_triples = []

        def add(s, p, o):
            self._instance_graph.add((s, p, o))
            added_triples.append((s, p, o))

        # Assert type
        add(id_iri, RDF.type, type_iri)

        # Assert boundary relations
        if boundary_ids:
            for bid in boundary_ids:
                b_iri = URIRef(f"{self._schema._base_iri}{bid}")
                add(id_iri, _KC.boundedBy, b_iri)

        # Assert kc:uri (superstructure attribute — uses kc: namespace, not model namespace)
        if uri is not None:
            add(id_iri, _KC.uri, Literal(uri, datatype=XSD.anyURI))

        # Assert attributes (in model namespace)
        for attr_name, attr_value in attributes.items():
            if isinstance(attr_value, (list, tuple)):
                for v in attr_value:
                    add(id_iri, self._ns[attr_name], Literal(v))
            else:
                add(id_iri, self._ns[attr_name], Literal(attr_value))

        # Add to complex
        add(self._complex_iri, _KC.hasElement, id_iri)

        # Validate — rollback on failure
        try:
            self._validate(id)
        except ValidationError:
            for s, p, o in added_triples:
                self._instance_graph.remove((s, p, o))
            raise

    def add_vertex(
        self,
        id: str,
        type: str,
        uri: str | None = None,
        **attributes: Any,
    ) -> None:
        """
        Assert a vertex individual and add it to the complex.

        Asserts the vertex as an individual of the given type (subclass of
        KC:Vertex), then asserts kc:hasElement on the complex. Validates via
        SHACL. Vertices have empty boundary (k=0), so boundary-closure is
        trivially satisfied.

        Parameters
        ----------
        id : str
            Local identifier for the vertex.
        type : str
            Vertex type name (must be a registered subclass of KC:Vertex).
        uri : str, optional
            Source file URI for this element (e.g. "file:///path/to/doc.md").
            Stored as kc:uri (xsd:anyURI). At-most-one per element.
        **attributes : Any
            Additional attribute values for the vertex.

        Raises
        ------
        ValidationError
            If SHACL validation fails after assertion.
        """
        self._assert_element(id, type, boundary_ids=None, attributes=attributes, uri=uri)

    def add_edge(
        self,
        id: str,
        type: str,
        vertices: set[str] | list[str],
        uri: str | None = None,
        **attributes: Any,
    ) -> None:
        """
        Assert an edge individual, link to boundary vertices, and add to complex.

        Asserts the edge as an individual of the given type (subclass of
        KC:Edge), links it to exactly 2 boundary vertices via kc:boundedBy,
        then asserts kc:hasElement on the complex. Validates via SHACL including:
        - EdgeShape: exactly 2 distinct boundary vertices
        - ComplexShape: boundary vertices must already be members of the complex

        Parameters
        ----------
        id : str
            Local identifier for the edge.
        type : str
            Edge type name (must be a registered subclass of KC:Edge).
        vertices : set[str] | list[str]
            Exactly 2 vertex IDs forming the boundary of this edge.
            Unordered (edges are unoriented).
        uri : str, optional
            Source file URI for this element.
        **attributes : Any
            Attribute values (e.g. status="passing").

        Raises
        ------
        ValueError
            If len(vertices) != 2.
        ValidationError
            If SHACL validation fails after assertion.
        """
        if len(vertices) != 2:
            raise ValueError(f"add_edge requires exactly 2 vertices; got {len(vertices)}")
        self._assert_element(id, type, boundary_ids=list(vertices), attributes=attributes, uri=uri)

    def add_face(
        self,
        id: str,
        type: str,
        boundary: list[str],
        uri: str | None = None,
        **attributes: Any,
    ) -> None:
        """
        Assert a face individual, link to boundary edges, and add to complex.

        Asserts the face as an individual of the given type (subclass of
        KC:Face), links it to exactly 3 boundary edges via kc:boundedBy,
        then asserts kc:hasElement on the complex. Validates via SHACL including:
        - FaceShape: exactly 3 boundary edges forming a closed triangle
        - ComplexShape: boundary edges must already be members of the complex

        Parameters
        ----------
        id : str
            Local identifier for the face.
        type : str
            Face type name (must be a registered subclass of KC:Face).
        boundary : list[str]
            Exactly 3 edge IDs forming the boundary of this face.
        uri : str, optional
            Source file URI for this element.
        **attributes : Any
            Attribute values.

        Raises
        ------
        ValueError
            If len(boundary) != 3.
        ValidationError
            If SHACL validation fails after assertion.
        """
        if len(boundary) != 3:
            raise ValueError(f"add_face requires exactly 3 boundary edges; got {len(boundary)}")
        self._assert_element(id, type, boundary_ids=boundary, attributes=attributes, uri=uri)

    def remove_element(self, id: str) -> None:
        """Remove an element and all its triples from the complex.

        Removes the element's type assertion, boundary relations (both
        directions), attributes, kc:uri, and kc:hasElement membership.

        No validation is performed after removal — the caller is responsible
        for ensuring the resulting complex is valid (e.g. removing faces
        before their boundary edges).

        Parameters
        ----------
        id : str
            Element identifier to remove.

        Raises
        ------
        ValueError
            If no element with that ID exists.
        """
        iri = URIRef(f"{self._schema._base_iri}{id}")
        if (iri, RDF.type, None) not in self._instance_graph:
            raise ValueError(f"No element with id '{id}' in the complex")

        # Remove all triples where element is subject
        for s, p, o in list(self._instance_graph.triples((iri, None, None))):
            self._instance_graph.remove((s, p, o))

        # Remove all triples where element is object (coboundary, hasElement)
        for s, p, o in list(self._instance_graph.triples((None, None, iri))):
            self._instance_graph.remove((s, p, o))

    def query(self, template_name: str, **kwargs: Any) -> pd.DataFrame:
        """
        Execute a named SPARQL template and return results as a DataFrame.

        Parameters
        ----------
        template_name : str
            Name of a registered query template (filename stem from
            framework or model query directories).
        **kwargs : Any
            Substitution values for {placeholder} tokens in the template.

        Returns
        -------
        pd.DataFrame
            One row per SPARQL result binding.

        Raises
        ------
        UnknownQueryError
            If template_name is not registered.
        """
        if template_name not in self._query_templates:
            raise UnknownQueryError(
                f"No query template named '{template_name}'. "
                f"Available: {sorted(self._query_templates)}"
            )
        sparql = self._query_templates[template_name]

        # Substitute {placeholder} tokens with kwargs values
        for key, value in kwargs.items():
            sparql = sparql.replace(f"{{{key}}}", str(value))

        # Provide namespace bindings for queries that may not declare all prefixes
        init_ns = {
            "kc": _KC,
            "rdf": RDF,
            "rdfs": RDFS,
            "owl": OWL,
            "xsd": XSD,
            self._schema._namespace: self._ns,
        }
        results = self._instance_graph.query(sparql, initNs=init_ns)

        columns = [str(v) for v in results.vars]
        rows = []
        for row in results:
            rows.append([str(val) if val is not None else None for val in row])
        return pd.DataFrame(rows, columns=columns)

    def query_ids(self, template_name: str, **kwargs: Any) -> set[str]:
        """Execute a named SPARQL template and return the first column as element IDs.

        Like :meth:`query` but returns a ``set[str]`` of element IDs
        (namespace prefix stripped) instead of a DataFrame.  Useful for
        obtaining subcomplexes from parameterized queries.

        Parameters
        ----------
        template_name : str
            Name of a registered query template.
        **kwargs : Any
            Substitution values for ``{placeholder}`` tokens in the template.

        Returns
        -------
        set[str]

        Raises
        ------
        UnknownQueryError
            If template_name is not registered.
        """
        if template_name not in self._query_templates:
            raise UnknownQueryError(
                f"No query template named '{template_name}'. "
                f"Available: {sorted(self._query_templates)}"
            )
        sparql = self._query_templates[template_name]
        for key, value in kwargs.items():
            sparql = sparql.replace(f"{{{key}}}", str(value))
        return self._ids_from_query(sparql)

    def dump_graph(self) -> str:
        """Return the instance graph as a Turtle string."""
        return self._instance_graph.serialize(format="turtle")

    def export(self, path: str | Path) -> Path:
        """
        Export the schema, queries, and instance graph to a directory.

        Writes ontology.ttl, shapes.ttl, queries/*.sparql, and instance.ttl.

        Parameters
        ----------
        path : str | Path
            Target directory. Created if it does not exist.

        Returns
        -------
        Path
            The export directory.
        """
        p = Path(path)
        self._schema.export(p, query_dirs=self._query_dirs_raw)
        (p / "instance.ttl").write_text(self.dump_graph())
        return p

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeComplex":
        """
        Load a knowledge complex from a directory.

        Reads ontology.ttl and shapes.ttl to reconstruct the schema,
        queries/*.sparql for query templates, and instance.ttl (if present)
        for the instance graph.

        Parameters
        ----------
        path : str | Path
            Directory containing at minimum ontology.ttl and shapes.ttl.

        Returns
        -------
        KnowledgeComplex
        """
        p = Path(path)
        schema = SchemaBuilder.load(p)
        query_dir = p / "queries"
        query_dirs = [query_dir] if query_dir.exists() else []
        kc = cls(schema=schema, query_dirs=query_dirs)
        instance_file = p / "instance.ttl"
        if instance_file.exists():
            kc._instance_graph.parse(str(instance_file), format="turtle")
        return kc

    # --- Element handles and listing ---

    def element(self, id: str) -> Element:
        """
        Get an Element handle for the given element ID.

        Parameters
        ----------
        id : str
            Local identifier of the element.

        Returns
        -------
        Element

        Raises
        ------
        ValueError
            If no element with that ID exists in the graph.
        """
        iri = URIRef(f"{self._schema._base_iri}{id}")
        if (iri, RDF.type, None) not in self._instance_graph:
            raise ValueError(f"No element with id '{id}' in the complex")
        return Element(self, id)

    def element_ids(self, type: str | None = None) -> list[str]:
        """
        List element IDs, optionally filtered by type (includes subtypes).

        Parameters
        ----------
        type : str, optional
            Filter to elements of this type or any subtype.

        Returns
        -------
        list[str]
        """
        ns_str = self._schema._base_iri
        if type is not None:
            if type not in self._schema._types:
                raise SchemaError(f"Type '{type}' is not registered")
            type_iri = self._ns[type]
            # Use SPARQL with subClassOf* to include subtypes
            sparql = f"""
            SELECT ?elem WHERE {{
                ?elem a/rdfs:subClassOf* <{type_iri}> .
                <{self._complex_iri}> <https://example.org/kc#hasElement> ?elem .
            }}
            """
            results = self._instance_graph.query(
                sparql, initNs={"rdfs": RDFS, "rdf": RDF}
            )
            ids = []
            for row in results:
                elem_str = str(row[0])
                if elem_str.startswith(ns_str):
                    ids.append(elem_str[len(ns_str):])
            return sorted(ids)
        else:
            # All elements in the complex
            ids = []
            for _, _, o in self._instance_graph.triples(
                (self._complex_iri, _KC.hasElement, None)
            ):
                elem_str = str(o)
                if elem_str.startswith(ns_str):
                    ids.append(elem_str[len(ns_str):])
            return sorted(ids)

    def elements(self, type: str | None = None) -> list[Element]:
        """
        List Element handles, optionally filtered by type (includes subtypes).

        Parameters
        ----------
        type : str, optional
            Filter to elements of this type or any subtype.

        Returns
        -------
        list[Element]
        """
        return [Element(self, id) for id in self.element_ids(type=type)]

    def is_subcomplex(self, ids: set[str]) -> bool:
        """
        Check whether a set of element IDs forms a valid subcomplex.

        A set is a valid subcomplex iff it is closed under the boundary
        operator: for every element in the set, all its boundary elements
        are also in the set.

        Parameters
        ----------
        ids : set[str]
            Element identifiers to check.

        Returns
        -------
        bool
        """
        if not ids:
            return True
        return set(ids) == self.closure(ids)

    # --- Topological query helpers ---

    def _iri(self, id: str) -> str:
        """Return the full IRI string for an element ID."""
        return f"{self._schema._base_iri}{id}"

    def _type_filter_clause(self, var: str, type: str | None) -> str:
        """Return a SPARQL clause filtering ?var by type, or empty string."""
        if type is None:
            return ""
        if type not in self._schema._types:
            raise SchemaError(f"Type '{type}' is not registered")
        type_iri = self._ns[type]
        return f"?{var} a/rdfs:subClassOf* <{type_iri}> ."

    def _ids_from_query(self, sparql: str) -> set[str]:
        """Execute SPARQL and return the first column as a set of element IDs."""
        ns_str = self._schema._base_iri
        init_ns = {
            "kc": _KC, "rdf": RDF, "rdfs": RDFS,
            "owl": OWL, "xsd": XSD,
            self._schema._namespace: self._ns,
        }
        results = self._instance_graph.query(sparql, initNs=init_ns)
        ids: set[str] = set()
        for row in results:
            val = str(row[0])
            if val.startswith(ns_str):
                ids.add(val[len(ns_str):])
        return ids

    # --- Topological query methods ---

    def boundary(self, id: str, *, type: str | None = None) -> set[str]:
        """Return ∂(id): the direct faces of element id via kc:boundedBy.

        For a vertex, returns the empty set.
        For an edge, returns its 2 boundary vertices.
        For a face, returns its 3 boundary edges.

        Parameters
        ----------
        id : str
            Element identifier.
        type : str, optional
            Filter results to this type (including subtypes).

        Returns
        -------
        set[str]
        """
        sparql = (
            self._query_templates["boundary"]
            .replace("{simplex}", f"<{self._iri(id)}>")
            .replace("{type_filter}", self._type_filter_clause("boundary", type))
        )
        return self._ids_from_query(sparql)

    def coboundary(self, id: str, *, type: str | None = None) -> set[str]:
        """Return δ(id): all simplices whose boundary contains id.

        Parameters
        ----------
        id : str
            Element identifier.
        type : str, optional
            Filter results to this type (including subtypes).

        Returns
        -------
        set[str]
        """
        tf = self._type_filter_clause("coboundary", type)
        sparql = f"""\
PREFIX kc: <https://example.org/kc#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?coboundary WHERE {{
    ?coboundary kc:boundedBy <{self._iri(id)}> .
    {tf}
}}"""
        return self._ids_from_query(sparql)

    def star(self, id: str, *, type: str | None = None) -> set[str]:
        """Return St(id): all simplices containing id as a face (transitive coboundary + self).

        Parameters
        ----------
        id : str
            Element identifier.
        type : str, optional
            Filter results to this type (including subtypes).

        Returns
        -------
        set[str]
        """
        sparql = (
            self._query_templates["star"]
            .replace("{simplex}", f"<{self._iri(id)}>")
            .replace("{type_filter}", self._type_filter_clause("star", type))
        )
        return self._ids_from_query(sparql)

    def closure(self, ids: str | set[str], *, type: str | None = None) -> set[str]:
        """Return Cl(ids): the smallest subcomplex containing ids.

        Accepts a single ID or a set of IDs. When given a set, returns the
        union of closures.

        Parameters
        ----------
        ids : str or set[str]
            Element identifier(s).
        type : str, optional
            Filter results to this type (including subtypes).

        Returns
        -------
        set[str]
        """
        if isinstance(ids, str):
            sparql = (
                self._query_templates["closure"]
                .replace("{simplex}", f"<{self._iri(ids)}>")
                .replace("{type_filter}", self._type_filter_clause("closure", type))
            )
            return self._ids_from_query(sparql)
        # Set input: use VALUES clause
        values = " ".join(f"(<{self._iri(i)}>)" for i in ids)
        tf = self._type_filter_clause("closure", type)
        sparql = f"""\
PREFIX kc: <https://example.org/kc#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?closure WHERE {{
    VALUES (?sigma) {{ {values} }}
    ?sigma kc:boundedBy* ?closure .
    {tf}
}}"""
        return self._ids_from_query(sparql)

    def closed_star(self, id: str, *, type: str | None = None) -> set[str]:
        """Return Cl(St(id)): the closure of the star.

        Always a valid subcomplex.

        Parameters
        ----------
        id : str
            Element identifier.
        type : str, optional
            Filter results to this type (including subtypes).

        Returns
        -------
        set[str]
        """
        return self.closure(self.star(id), type=type)

    def link(self, id: str, *, type: str | None = None) -> set[str]:
        """Return Lk(id): Cl(St(id)) \\ St(id).

        The link is the set of simplices in the closed star that do not
        themselves contain id as a face.

        Parameters
        ----------
        id : str
            Element identifier.
        type : str, optional
            Filter results to this type (including subtypes).

        Returns
        -------
        set[str]
        """
        result = self.closed_star(id) - self.star(id)
        if type is not None:
            typed = set(self.element_ids(type=type))
            result &= typed
        return result

    def skeleton(self, k: int) -> set[str]:
        """Return sk_k(K): all elements of dimension <= k.

        k=0: vertices only
        k=1: vertices and edges
        k=2: vertices, edges, and faces (everything)

        Parameters
        ----------
        k : int
            Maximum dimension (0, 1, or 2).

        Returns
        -------
        set[str]

        Raises
        ------
        ValueError
            If k < 0 or k > 2.
        """
        if k < 0 or k > 2:
            raise ValueError(f"skeleton dimension must be 0, 1, or 2; got {k}")
        dim_classes_map = {
            0: [_KC.Vertex],
            1: [_KC.Vertex, _KC.Edge],
            2: [_KC.Vertex, _KC.Edge, _KC.Face],
        }
        classes = dim_classes_map[k]
        unions = " UNION ".join(
            f"{{ ?elem a/rdfs:subClassOf* <{c}> }}" for c in classes
        )
        sparql = (
            self._query_templates["skeleton"]
            .replace("{complex}", f"<{self._complex_iri}>")
            .replace("{dim_classes}", unions)
        )
        return self._ids_from_query(sparql)

    def degree(self, id: str) -> int:
        """Return deg(id): the number of edges incident to vertex id.

        Parameters
        ----------
        id : str
            Vertex identifier.

        Returns
        -------
        int
        """
        sparql = (
            self._query_templates["degree"]
            .replace("{simplex}", f"<{self._iri(id)}>")
        )
        init_ns = {
            "kc": _KC, "rdf": RDF, "rdfs": RDFS,
            "owl": OWL, "xsd": XSD,
            self._schema._namespace: self._ns,
        }
        results = self._instance_graph.query(sparql, initNs=init_ns)
        for row in results:
            return int(row[0])
        return 0

    # --- Codec registration and resolution ---

    def register_codec(self, type_name: str, codec: Codec) -> None:
        """
        Register a codec for the given type.

        Parameters
        ----------
        type_name : str
            Must be a registered type in the schema.
        codec : Codec
            Object implementing compile() and decompile().
        """
        if type_name not in self._schema._types:
            raise SchemaError(f"Type '{type_name}' is not registered")
        if not isinstance(codec, Codec):
            raise TypeError(
                f"Expected a Codec instance, got {type(codec).__name__}"
            )
        self._codecs[type_name] = codec

    def _resolve_codec(self, type_name: str) -> Codec:
        """Walk type hierarchy to find the nearest registered codec."""
        current: str | None = type_name
        while current is not None:
            if current in self._codecs:
                return self._codecs[current]
            current = self._schema._types.get(current, {}).get("parent")
        raise SchemaError(
            f"No codec registered for type '{type_name}' or any of its ancestors"
        )

    def decompile_uri(self, type_name: str, uri: str) -> dict:
        """
        Decompile an artifact at a URI without adding it to the graph.

        Parameters
        ----------
        type_name : str
            The element type (used to resolve the codec).
        uri : str
            URI of the artifact to read.

        Returns
        -------
        dict
            Attribute key-value pairs.
        """
        if type_name not in self._schema._types:
            raise SchemaError(f"Type '{type_name}' is not registered")
        codec = self._resolve_codec(type_name)
        return codec.decompile(uri)
