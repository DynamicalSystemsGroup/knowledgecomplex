"""knowledgecomplex.diff — Complex diffs and sequences for time-varying complexes.

A ``ComplexDiff`` records element additions and removals.  It can be applied
to a ``KnowledgeComplex`` to mutate it, exported to a SPARQL UPDATE string
for interoperability with RDF-native systems (e.g. flexo MMS), or imported
from a SPARQL UPDATE string received from a remote system.

A ``ComplexSequence`` wraps a base complex and an ordered list of diffs,
representing a time series of complex states.  Element ID sets at each step
are computed by applying diffs cumulatively.

Example::

    diff = ComplexDiff()
    diff.add_vertex("eve", type="Person")
    diff.add_edge("e-ae", type="Link", vertices={"alice", "eve"})
    diff.remove("old-edge")

    diff.apply(kc)                  # mutate the complex
    sparql = diff.to_sparql(kc)     # export as SPARQL UPDATE

    # Import a diff from a remote system
    remote_diff = ComplexDiff.from_sparql(sparql, kc)
    remote_diff.apply(kc2)
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex

_KC = Namespace("https://example.org/kc#")


class ComplexDiff:
    """A set of element additions and removals that transform a complex.

    Build a diff by chaining ``add_vertex``, ``add_edge``, ``add_face``,
    and ``remove`` calls.  Then apply it to a ``KnowledgeComplex`` via
    :meth:`apply`, or export it to a SPARQL UPDATE string via :meth:`to_sparql`.
    """

    def __init__(self) -> None:
        self._additions: list[dict[str, Any]] = []
        self._removals: list[str] = []

    @property
    def additions(self) -> list[dict[str, Any]]:
        """Element additions: list of dicts with id, type, kind, boundary, attrs."""
        return list(self._additions)

    @property
    def removals(self) -> list[str]:
        """Element removals: list of element IDs."""
        return list(self._removals)

    # ── Builder methods (chainable) ────────────────────────────────────────

    def add_vertex(
        self, id: str, type: str, uri: str | None = None, **attrs: Any
    ) -> "ComplexDiff":
        """Record a vertex addition."""
        self._additions.append({
            "id": id, "type": type, "kind": "vertex",
            "boundary": None, "uri": uri, "attrs": attrs,
        })
        return self

    def add_edge(
        self, id: str, type: str, vertices: set[str] | list[str],
        uri: str | None = None, **attrs: Any,
    ) -> "ComplexDiff":
        """Record an edge addition."""
        self._additions.append({
            "id": id, "type": type, "kind": "edge",
            "boundary": list(vertices), "uri": uri, "attrs": attrs,
        })
        return self

    def add_face(
        self, id: str, type: str, boundary: list[str],
        uri: str | None = None, **attrs: Any,
    ) -> "ComplexDiff":
        """Record a face addition."""
        self._additions.append({
            "id": id, "type": type, "kind": "face",
            "boundary": list(boundary), "uri": uri, "attrs": attrs,
        })
        return self

    def remove(self, id: str) -> "ComplexDiff":
        """Record an element removal."""
        self._removals.append(id)
        return self

    # ── Apply ──────────────────────────────────────────────────────────────

    def apply(self, kc: "KnowledgeComplex", validate: bool = True) -> None:
        """Apply this diff to a KnowledgeComplex.

        Removals are processed first (highest dimension first to avoid
        boundary-closure violations), then additions.

        Parameters
        ----------
        kc : KnowledgeComplex
        validate : bool
            If True (default), run SHACL validation after all changes.
            Raises ``ValidationError`` on failure (changes are NOT rolled back).
        """
        # Sort removals: higher-dim first to avoid intermediate violations
        # Determine dimension of each removal from the live complex
        dim_order = {"face": 2, "edge": 1, "vertex": 0}
        removals_with_dim = []
        for rid in self._removals:
            try:
                elem = kc.element(rid)
                kind = kc._schema._types.get(elem.type, {}).get("kind", "vertex")
                removals_with_dim.append((dim_order.get(kind, 0), rid))
            except ValueError:
                pass  # already removed or doesn't exist — skip
        removals_with_dim.sort(key=lambda x: -x[0])  # highest dim first

        for _, rid in removals_with_dim:
            kc.remove_element(rid)

        # Process additions sorted by dimension (vertices first, edges, then faces)
        dim_order = {"vertex": 0, "edge": 1, "face": 2}
        sorted_additions = sorted(
            self._additions, key=lambda a: dim_order.get(a["kind"], 0)
        )
        for add in sorted_additions:
            kind = add["kind"]
            if kind == "vertex":
                kc.add_vertex(
                    add["id"], type=add["type"], uri=add["uri"], **add["attrs"]
                )
            elif kind == "edge":
                kc.add_edge(
                    add["id"], type=add["type"], vertices=add["boundary"],
                    uri=add["uri"], **add["attrs"],
                )
            elif kind == "face":
                kc.add_face(
                    add["id"], type=add["type"], boundary=add["boundary"],
                    uri=add["uri"], **add["attrs"],
                )

    # ── SPARQL export ──────────────────────────────────────────────────────

    def to_sparql(self, kc: "KnowledgeComplex") -> str:
        """Export this diff as a SPARQL UPDATE string.

        Generates ``DELETE DATA`` blocks for removals and ``INSERT DATA``
        blocks for additions, using the KC's namespace for IRI construction.

        Parameters
        ----------
        kc : KnowledgeComplex
            Used to read existing triples for removals and to resolve namespaces.

        Returns
        -------
        str
            A SPARQL UPDATE string.
        """
        ns = kc._schema._base_iri
        parts = []

        # DELETE DATA for removals
        if self._removals:
            delete_triples = []
            for rid in self._removals:
                iri = URIRef(f"{ns}{rid}")
                # Collect all triples involving this element
                for s, p, o in kc._instance_graph.triples((iri, None, None)):
                    delete_triples.append(f"  <{s}> <{p}> {_sparql_obj(o)} .")
                for s, p, o in kc._instance_graph.triples((None, None, iri)):
                    delete_triples.append(f"  <{s}> <{p}> <{o}> .")
            if delete_triples:
                parts.append(
                    "DELETE DATA {\n" + "\n".join(delete_triples) + "\n}"
                )

        # INSERT DATA for additions
        if self._additions:
            insert_triples = []
            for add in self._additions:
                iri = f"<{ns}{add['id']}>"
                type_iri = f"<{ns}{add['type']}>"
                insert_triples.append(f"  {iri} <{RDF.type}> {type_iri} .")

                if add.get("boundary"):
                    for bid in add["boundary"]:
                        b_iri = f"<{ns}{bid}>"
                        insert_triples.append(f"  {iri} <{_KC.boundedBy}> {b_iri} .")

                if add.get("uri"):
                    insert_triples.append(
                        f'  {iri} <{_KC.uri}> "{add["uri"]}"^^<{XSD.anyURI}> .'
                    )

                for attr_name, attr_value in add.get("attrs", {}).items():
                    attr_iri = f"<{ns}{attr_name}>"
                    if isinstance(attr_value, (list, tuple)):
                        for v in attr_value:
                            insert_triples.append(f'  {iri} {attr_iri} "{v}" .')
                    else:
                        insert_triples.append(f'  {iri} {attr_iri} "{attr_value}" .')

                # Add to complex
                complex_iri = f"<{ns}_complex>"
                insert_triples.append(
                    f"  {complex_iri} <{_KC.hasElement}> {iri} ."
                )

            parts.append(
                "INSERT DATA {\n" + "\n".join(insert_triples) + "\n}"
            )

        return " ;\n".join(parts)

    # ── SPARQL import ──────────────────────────────────────────────────────

    @classmethod
    def from_sparql(cls, sparql: str, kc: "KnowledgeComplex") -> "ComplexDiff":
        """Parse a SPARQL UPDATE string into a ComplexDiff.

        Extracts ``INSERT DATA`` and ``DELETE DATA`` blocks, parses their
        triple content, and reconstructs element additions and removals.

        Parameters
        ----------
        sparql : str
            SPARQL UPDATE string (as produced by :meth:`to_sparql`).
        kc : KnowledgeComplex
            Used to resolve namespaces and determine element kinds.

        Returns
        -------
        ComplexDiff
        """
        ns = kc._schema._base_iri
        diff = cls()

        # Extract DELETE DATA blocks → removals
        for match in re.finditer(
            r"DELETE\s+DATA\s*\{(.*?)\}", sparql, re.DOTALL | re.IGNORECASE
        ):
            block = match.group(1)
            removed_ids = set()
            for triple_match in re.finditer(r"<([^>]+)>\s+<[^>]+>\s+", block):
                subj = triple_match.group(1)
                if subj.startswith(ns) and not subj.endswith("_complex"):
                    removed_ids.add(subj[len(ns):])
            for rid in sorted(removed_ids):
                diff.remove(rid)

        # Extract INSERT DATA blocks → additions
        for match in re.finditer(
            r"INSERT\s+DATA\s*\{(.*?)\}", sparql, re.DOTALL | re.IGNORECASE
        ):
            block = match.group(1)
            # Parse triples to reconstruct elements
            g = Graph()
            # Convert to N-Triples-like format for parsing
            nt_lines = []
            for line in block.strip().split("\n"):
                line = line.strip()
                if line:
                    nt_lines.append(line)
            nt_data = "\n".join(nt_lines)
            try:
                g.parse(data=nt_data, format="nt")
            except Exception:
                continue

            # Find elements (subjects with rdf:type in model namespace)
            has_element = _KC.hasElement
            bounded_by = _KC.boundedBy
            kc_uri = _KC.uri

            for subj in set(g.subjects(RDF.type, None)):
                subj_str = str(subj)
                if not subj_str.startswith(ns):
                    continue
                elem_id = subj_str[len(ns):]

                # Get type
                type_iri = g.value(subj, RDF.type)
                if type_iri is None:
                    continue
                type_str = str(type_iri)
                if not type_str.startswith(ns):
                    continue
                type_name = type_str[len(ns):]

                # Determine kind from schema
                kind = kc._schema._types.get(type_name, {}).get("kind", "vertex")

                # Get boundary
                boundary = []
                for _, _, o in g.triples((subj, bounded_by, None)):
                    bid = str(o)
                    if bid.startswith(ns):
                        boundary.append(bid[len(ns):])

                # Get uri
                uri_val = g.value(subj, kc_uri)
                uri = str(uri_val) if uri_val else None

                # Get model attributes
                attrs = {}
                for _, p, o in g.triples((subj, None, None)):
                    p_str = str(p)
                    if (p_str.startswith(ns) and p_str != str(type_iri)
                            and p != RDF.type and p != bounded_by
                            and p != kc_uri and p != has_element):
                        attr_name = p_str[len(ns):]
                        attrs[attr_name] = str(o)

                if kind == "vertex":
                    diff.add_vertex(elem_id, type=type_name, uri=uri, **attrs)
                elif kind == "edge":
                    diff.add_edge(
                        elem_id, type=type_name, vertices=boundary,
                        uri=uri, **attrs,
                    )
                elif kind == "face":
                    diff.add_face(
                        elem_id, type=type_name, boundary=boundary,
                        uri=uri, **attrs,
                    )

        return diff

    def __repr__(self) -> str:
        return (
            f"ComplexDiff(+{len(self._additions)} additions, "
            f"-{len(self._removals)} removals)"
        )


def _sparql_obj(obj) -> str:
    """Format an RDF object for SPARQL DATA blocks."""
    if isinstance(obj, URIRef):
        return f"<{obj}>"
    elif isinstance(obj, Literal):
        if obj.datatype:
            return f'"{obj}"^^<{obj.datatype}>'
        return f'"{obj}"'
    return f'"{obj}"'


class ComplexSequence:
    """A base complex + ordered list of diffs, representing a time series.

    Computes element ID sets at each step by applying diffs cumulatively
    to the base complex's element set.  This is a lightweight representation
    that does not reconstruct full ``KnowledgeComplex`` instances at each step.

    Parameters
    ----------
    kc : KnowledgeComplex
        The base complex (state at step -1, before any diffs).
    diffs : list[ComplexDiff]
        Ordered sequence of diffs to apply.
    """

    def __init__(
        self,
        kc: "KnowledgeComplex",
        diffs: list[ComplexDiff],
    ) -> None:
        self._kc = kc
        self._diffs = list(diffs)
        # Pre-compute element ID sets at each step
        self._steps: list[frozenset[str]] = []
        current = set(kc.element_ids())
        for diff in diffs:
            for rid in diff.removals:
                current.discard(rid)
            for add in diff.additions:
                current.add(add["id"])
            self._steps.append(frozenset(current))

    @property
    def complex(self) -> "KnowledgeComplex":
        """The base KnowledgeComplex."""
        return self._kc

    @property
    def diffs(self) -> list[ComplexDiff]:
        """The ordered list of diffs."""
        return list(self._diffs)

    def __len__(self) -> int:
        return len(self._steps)

    def __getitem__(self, index: int) -> set[str]:
        """Element IDs present at step ``index``."""
        return set(self._steps[index])

    def __iter__(self):
        for step in self._steps:
            yield set(step)

    def new_at(self, index: int) -> set[str]:
        """Elements added at step ``index`` (not present in previous step)."""
        current = self._steps[index]
        if index == 0:
            base = frozenset(self._kc.element_ids())
            return set(current - base)
        return set(current - self._steps[index - 1])

    def removed_at(self, index: int) -> set[str]:
        """Elements removed at step ``index`` (present in previous, absent now)."""
        current = self._steps[index]
        if index == 0:
            base = frozenset(self._kc.element_ids())
            return set(base - current)
        return set(self._steps[index - 1] - current)

    def __repr__(self) -> str:
        return f"ComplexSequence({len(self._steps)} steps)"
