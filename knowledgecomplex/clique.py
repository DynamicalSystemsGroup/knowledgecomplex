"""knowledgecomplex.clique — Clique complex and flagification methods.

Two workflows for inferring higher-order simplices from the edge graph:

**Generic exploration** (``fill_cliques``)
    Discover what higher-order structure exists before knowing the semantics.
    Fill in generic simplices for all cliques up to a given order.  Inspect
    what shows up, then decide what types to declare.

**Typed inference** (``infer_faces``)
    Once you've declared a face type with semantic meaning, fill in all
    instances of that type from the edge graph.  The face type is required —
    you declare the type, then run inference to populate it.

``find_cliques`` is a pure query that returns vertex cliques without
modifying the complex.

Typical workflow::

    # Phase 1: Explore — what triangles exist?
    sb.add_face_type("_clique")
    kc = KnowledgeComplex(schema=sb)
    # ... add vertices and edges ...
    result = fill_cliques(kc, max_order=2)

    # Phase 2: Inspect
    for fid in result[2]:
        edge_types = {kc.element(e).type for e in kc.boundary(fid)}
        print(f"{fid}: {edge_types}")

    # Phase 3: Typed inference with a real schema
    sb2 = SchemaBuilder(namespace="ex")
    sb2.add_face_type("operation", attributes={...})
    kc2 = KnowledgeComplex(schema=sb2)
    # ... add vertices and edges ...
    infer_faces(kc2, "operation", edge_type="performs")
"""
from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex

from knowledgecomplex.exceptions import SchemaError


# ── Helpers ─────────────────────────────────────────────────────────────────


def _edges_between(
    kc: "KnowledgeComplex",
    v1: str,
    v2: str,
    edge_type: str | None = None,
) -> list[str]:
    """Find KC edges whose boundary is exactly {v1, v2}.

    Parameters
    ----------
    kc : KnowledgeComplex
    v1, v2 : str
        Vertex IDs.
    edge_type : str, optional
        Only return edges of this type.

    Returns
    -------
    list[str]
    """
    # Edges incident to v1 ∩ edges incident to v2
    cb1 = kc.coboundary(v1, type=edge_type)
    cb2 = kc.coboundary(v2, type=edge_type)
    shared = cb1 & cb2

    # Filter to edges (dim=1) whose boundary is exactly {v1, v2}
    result = []
    for eid in shared:
        kind = kc._schema._types.get(kc.element(eid).type, {}).get("kind")
        if kind == "edge" and kc.boundary(eid) == {v1, v2}:
            result.append(eid)
    return result


def _has_face_for_edges(kc: "KnowledgeComplex", edge_ids: frozenset[str]) -> bool:
    """Check if a face already exists whose boundary is exactly edge_ids."""
    # Check coboundary of any edge — faces containing it
    if not edge_ids:
        return False
    first = next(iter(edge_ids))
    candidates = kc.coboundary(first)
    for cid in candidates:
        kind = kc._schema._types.get(kc.element(cid).type, {}).get("kind")
        if kind == "face" and kc.boundary(cid) == set(edge_ids):
            return True
    return False


# ── find_cliques ────────────────────────────────────────────────────────────


def find_cliques(
    kc: "KnowledgeComplex",
    k: int = 3,
    *,
    edge_type: str | None = None,
) -> list[frozenset[str]]:
    """Find all k-cliques of KC vertices in the edge graph.

    A k-clique is a set of k vertices where every pair is connected by
    an edge.  This is a pure query — it does not modify the complex.

    Parameters
    ----------
    kc : KnowledgeComplex
    k : int
        Clique size (default 3 for triangles).
    edge_type : str, optional
        Only consider edges of this type when building the adjacency graph.

    Returns
    -------
    list[frozenset[str]]
        Each element is a frozenset of k vertex IDs.
    """
    if k < 2:
        raise ValueError(f"Clique size must be >= 2, got {k}")

    # Build adjacency from vertex-edge structure
    vertices = sorted(kc.skeleton(0))
    adj: dict[str, set[str]] = {v: set() for v in vertices}

    edge_ids = kc.skeleton(1) - kc.skeleton(0)
    for eid in edge_ids:
        if edge_type is not None and kc.element(eid).type != edge_type:
            continue
        boundary = kc.boundary(eid)
        if len(boundary) == 2:
            v1, v2 = sorted(boundary)
            adj[v1].add(v2)
            adj[v2].add(v1)

    # Enumerate cliques via Bron-Kerbosch or brute-force for small k
    cliques: list[frozenset[str]] = []
    sorted_verts = sorted(vertices)

    if k == 2:
        # k=2 cliques are just edges
        for i, v1 in enumerate(sorted_verts):
            for v2 in sorted_verts[i + 1:]:
                if v2 in adj[v1]:
                    cliques.append(frozenset([v1, v2]))
    else:
        # General: enumerate (k-1)-subsets and check
        for combo in combinations(sorted_verts, k):
            if all(combo[j] in adj[combo[i]]
                   for i in range(k) for j in range(i + 1, k)):
                cliques.append(frozenset(combo))

    return cliques


# ── infer_faces ─────────────────────────────────────────────────────────────


def infer_faces(
    kc: "KnowledgeComplex",
    face_type: str,
    *,
    edge_type: str | None = None,
    id_prefix: str = "face",
    dry_run: bool = False,
) -> list[str]:
    """Infer and add faces of a declared type from 3-cliques in the edge graph.

    Finds all triangles (3-cliques of KC vertices), resolves the 3 boundary
    edges for each, and calls ``kc.add_face()`` with the specified type.
    Skips triangles that already have a face.

    Parameters
    ----------
    kc : KnowledgeComplex
    face_type : str
        A registered face type to assign to inferred faces.
    edge_type : str, optional
        Only consider edges of this type when finding triangles.
    id_prefix : str
        Prefix for auto-generated face IDs (e.g. ``"face-0"``).
    dry_run : bool
        If ``True``, return the list of would-be face IDs and their
        boundaries without adding them to the complex.

    Returns
    -------
    list[str]
        IDs of newly added (or would-be) faces.

    Raises
    ------
    SchemaError
        If *face_type* is not a registered face type.
    """
    if face_type not in kc._schema._types:
        raise SchemaError(f"Type '{face_type}' is not registered")
    if kc._schema._types[face_type].get("kind") != "face":
        raise SchemaError(f"Type '{face_type}' is not a face type")

    triangles = find_cliques(kc, k=3, edge_type=edge_type)
    added: list[str] = []
    counter = 0

    for tri in triangles:
        verts = sorted(tri)
        # Find edges for each pair
        edges = []
        valid = True
        for i in range(3):
            for j in range(i + 1, 3):
                e = _edges_between(kc, verts[i], verts[j], edge_type=edge_type)
                if not e:
                    valid = False
                    break
                edges.append(e[0])  # take first matching edge
            if not valid:
                break

        if not valid or len(edges) != 3:
            continue

        # Skip if face already exists for these edges
        if _has_face_for_edges(kc, frozenset(edges)):
            continue

        face_id = f"{id_prefix}-{counter}"
        counter += 1

        if not dry_run:
            kc.add_face(face_id, type=face_type, boundary=edges)
        added.append(face_id)

    return added


# ── fill_cliques ────────────────────────────────────────────────────────────


def fill_cliques(
    kc: "KnowledgeComplex",
    max_order: int = 2,
    *,
    edge_type: str | None = None,
    id_prefix: str = "clique",
) -> dict[int, list[str]]:
    """Fill generic simplices for all cliques up to max_order.

    Discovers what higher-order structure exists without requiring semantic
    type declarations.  For k=2 (faces), uses the first declared face type.
    For k>2, uses ``_assert_element`` directly with the base ``kc:Element``
    type — these are generic, untyped simplices.

    This is an exploration tool.  Once you've inspected the structure,
    declare typed face types and use :func:`infer_faces` for semantic
    inference.

    Parameters
    ----------
    kc : KnowledgeComplex
    max_order : int
        Maximum simplex dimension to fill (default 2 = faces).
    edge_type : str, optional
        Only consider edges of this type when finding cliques.
    id_prefix : str
        Prefix for auto-generated IDs.

    Returns
    -------
    dict[int, list[str]]
        Mapping from dimension to list of newly added element IDs.
        E.g. ``{2: ["clique-0", "clique-1"], 3: ["clique-4"]}``.
    """
    if max_order < 2:
        raise ValueError(f"max_order must be >= 2, got {max_order}")

    result: dict[int, list[str]] = {}

    # k=2: faces — use first declared face type
    if max_order >= 2:
        face_types = kc._schema.type_names(kind="face")
        if not face_types:
            raise SchemaError(
                "No face types declared. Add at least one face type "
                "(e.g. sb.add_face_type('_clique')) before calling fill_cliques."
            )
        face_type = face_types[0]
        result[2] = infer_faces(
            kc, face_type, edge_type=edge_type, id_prefix=id_prefix,
        )

    # k>2: higher-order generic simplices
    if max_order >= 3:
        from rdflib import URIRef, RDF
        _KC_NS = kc._instance_graph.namespace_manager.store

        for dim in range(3, max_order + 1):
            cliques = find_cliques(kc, k=dim + 1, edge_type=edge_type)
            added: list[str] = []
            counter = 0

            for clique in cliques:
                # Find the k boundary (dim-1)-simplices
                # For a (dim)-simplex, boundary is (dim+1 choose dim) = dim+1
                # (dim-1)-simplices from subsets of size dim
                boundary_ids = []
                valid = True

                for sub in combinations(sorted(clique), dim):
                    # Find the (dim-1)-simplex with these vertices in its closure
                    sub_set = frozenset(sub)
                    # For dim=3: find face whose closure vertices = sub (3 vertices)
                    found = _find_simplex_with_vertices(kc, sub_set, dim - 1)
                    if found is None:
                        valid = False
                        break
                    boundary_ids.append(found)

                if not valid:
                    continue

                # Check no duplicate
                elem_id = f"{id_prefix}-{dim}d-{counter}"

                if not dry_run_check(kc, boundary_ids):
                    counter += 1
                    # Use _assert_element directly for generic higher-order
                    kc._assert_element(
                        elem_id,
                        face_types[0],  # reuse face type as best available
                        boundary_ids=boundary_ids,
                        attributes={},
                    )
                    added.append(elem_id)

            result[dim] = added

    return result


def _find_simplex_with_vertices(
    kc: "KnowledgeComplex",
    vertices: frozenset[str],
    dim: int,
) -> str | None:
    """Find a simplex of given dimension whose closure contains exactly these vertices."""
    if dim == 1:
        # Find edge between 2 vertices
        verts = sorted(vertices)
        if len(verts) != 2:
            return None
        edges = _edges_between(kc, verts[0], verts[1])
        return edges[0] if edges else None
    elif dim == 2:
        # Find face whose 3 vertices match
        verts = sorted(vertices)
        if len(verts) != 3:
            return None
        # Check edges between each pair
        for i in range(3):
            for j in range(i + 1, 3):
                edges = _edges_between(kc, verts[i], verts[j])
                if not edges:
                    return None
        # Find face containing all three edges
        edge_sets = []
        for i in range(3):
            for j in range(i + 1, 3):
                edge_sets.append(set(_edges_between(kc, verts[i], verts[j])))
        # Check coboundary of first edge for faces
        if edge_sets:
            for e in edge_sets[0]:
                for cand in kc.coboundary(e):
                    kind = kc._schema._types.get(kc.element(cand).type, {}).get("kind")
                    if kind == "face":
                        face_boundary = kc.boundary(cand)
                        # Check if boundary edges connect these vertices
                        face_verts = set()
                        for be in face_boundary:
                            face_verts |= kc.boundary(be)
                        if face_verts == set(verts):
                            return cand
    return None


def dry_run_check(kc, boundary_ids):
    """Check if an element with this boundary already exists."""
    if not boundary_ids:
        return False
    first = boundary_ids[0]
    for cand in kc.coboundary(first):
        if set(kc.boundary(cand)) == set(boundary_ids):
            return True
    return False
