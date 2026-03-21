"""File-based import/export utilities for KnowledgeComplex.

Functions
---------
save_graph       Serialize the instance graph to a file.
load_graph       Parse a file into the instance graph (additive).
dump_graph       Return the instance graph as a string in a given format.

Design notes
------------
* Turtle (``.ttl``) is the default format — human-readable and consistent
  with the ontology/shapes patterns used throughout the codebase.
* All load functions are **additive**: they call ``graph.parse()`` which
  adds triples to the existing graph.  Load into a fresh
  ``KnowledgeComplex`` for a clean restore.
* No TriG (``.trig``) or N-Quads (``.nq``) — ``KnowledgeComplex`` uses a
  plain ``rdflib.Graph``, not a ``ConjunctiveGraph``.

Adapted from discourse_graph.io (multi-agent-dg).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex

from knowledgecomplex.exceptions import ValidationError

# ── Format registry ─────────────────────────────────────────────────────────

_FORMAT_BY_EXT: dict[str, str] = {
    ".ttl": "turtle",
    ".jsonld": "json-ld",
    ".nt": "ntriples",
    ".n3": "n3",
    ".rdf": "xml",
    ".xml": "xml",
}


def _detect_format(path: Path, given: Optional[str]) -> str:
    """Return the serialization format string.

    Parameters
    ----------
    path :
        File path whose suffix is used for auto-detection.
    given :
        Explicit format override; returned as-is when not ``None``.

    Raises
    ------
    ValueError
        If *given* is ``None`` and the file suffix is not in the registry.
    """
    if given is not None:
        return given
    ext = path.suffix.lower()
    if ext not in _FORMAT_BY_EXT:
        raise ValueError(
            f"Cannot auto-detect RDF format for extension {ext!r}. "
            f"Pass format= explicitly.  Known extensions: "
            f"{', '.join(sorted(_FORMAT_BY_EXT))}."
        )
    return _FORMAT_BY_EXT[ext]


# ── Instance graph I/O ──────────────────────────────────────────────────────


def save_graph(
    kc: "KnowledgeComplex",
    path: "Path | str",
    format: str = "turtle",
) -> None:
    """Serialize ``kc._instance_graph`` to a file.

    Parameters
    ----------
    kc :
        The ``KnowledgeComplex`` whose instance graph is serialized.
    path :
        Destination file path.  The file is created or overwritten.
    format :
        rdflib serialization format string.  Defaults to ``"turtle"``.
        Other useful values: ``"json-ld"``, ``"ntriples"``, ``"n3"``,
        ``"xml"`` (RDF/XML).
    """
    path = Path(path)
    kc._instance_graph.serialize(destination=str(path), format=format)


def load_graph(
    kc: "KnowledgeComplex",
    path: "Path | str",
    format: Optional[str] = None,
    validate: bool = False,
) -> None:
    """Parse a file into ``kc._instance_graph`` (additive).

    Parameters
    ----------
    kc :
        The ``KnowledgeComplex`` whose instance graph receives the
        parsed triples.
    path :
        Source file path.
    format :
        rdflib serialization format string.  When ``None``, auto-detected
        from the file extension using the built-in registry.
    validate :
        If ``True``, run SHACL validation after parsing.  On failure the
        newly added triples are rolled back and ``ValidationError`` is
        raised.  Defaults to ``False`` because the data may have been
        exported from a validated ``KnowledgeComplex`` and re-validating
        is expensive.

    Notes
    -----
    This operation is **additive**: existing triples in the instance graph
    are retained.  For a clean restore, load into a freshly constructed
    ``KnowledgeComplex``.

    The instance graph includes TBox (ontology) triples.  Loading a file
    that was saved from a KC with the same schema is harmless — rdflib
    deduplicates triples.  Loading data from a different schema will merge
    ontologies; the caller is responsible for schema compatibility.
    """
    path = Path(path)
    fmt = _detect_format(path, format)

    if validate:
        before = set(kc._instance_graph)

    kc._instance_graph.parse(source=str(path), format=fmt)

    if validate:
        try:
            kc._validate()
        except ValidationError:
            added = set(kc._instance_graph) - before
            for triple in added:
                kc._instance_graph.remove(triple)
            raise


def dump_graph(
    kc: "KnowledgeComplex",
    format: str = "turtle",
) -> str:
    """Return the instance graph as a string in the requested format.

    Parameters
    ----------
    kc :
        The ``KnowledgeComplex`` whose instance graph is serialized.
    format :
        rdflib serialization format string.  Defaults to ``"turtle"``.

    Returns
    -------
    str
        The serialized graph.
    """
    return kc._instance_graph.serialize(format=format)
