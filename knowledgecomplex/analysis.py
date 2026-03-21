"""
knowledgecomplex.analysis — Algebraic topology over knowledge complexes.

Boundary matrices, Betti numbers, Hodge Laplacians, edge PageRank,
and Hodge decomposition of edge flows.

Requires: numpy, scipy (install with ``pip install knowledgecomplex[analysis]``).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg, splu

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BoundaryMatrices:
    """Boundary operators and element-to-index mappings."""
    B1: sp.csr_matrix  # (n_vertices, n_edges)
    B2: sp.csr_matrix  # (n_edges, n_faces)
    vertex_index: dict[str, int]
    edge_index: dict[str, int]
    face_index: dict[str, int]
    index_vertex: dict[int, str]
    index_edge: dict[int, str]
    index_face: dict[int, str]


@dataclass
class HodgeDecomposition:
    """Orthogonal decomposition of an edge flow."""
    gradient: np.ndarray   # im(B1ᵀ) — flows from vertices
    curl: np.ndarray       # im(B2) — flows from faces
    harmonic: np.ndarray   # ker(L₁) — topological cycles


@dataclass
class EdgeInfluence:
    """Influence measures for an edge's PageRank vector."""
    edge_id: str
    spread: float             # ||v||₂ / ||v||₁
    absolute_influence: float  # ||v||₁
    penetration: float        # ||v||₂
    relative_influence: float  # Σv


@dataclass
class HodgeAnalysisResults:
    """Complete Hodge analysis output."""
    betti: list[int]
    euler_characteristic: int
    boundary_matrices: BoundaryMatrices
    laplacian: sp.csr_matrix
    pagerank: np.ndarray  # (n_edges, n_edges)
    decompositions: dict[str, HodgeDecomposition]
    influences: dict[str, EdgeInfluence]


# ---------------------------------------------------------------------------
# Boundary matrices
# ---------------------------------------------------------------------------

def boundary_matrices(kc: "KnowledgeComplex") -> BoundaryMatrices:
    """
    Build the boundary operator matrices B1 (∂₁) and B2 (∂₂).

    B1 is (n_vertices × n_edges) with entries ±1 encoding which vertices
    bound each edge. B2 is (n_edges × n_faces) with entries ±1 encoding
    which edges bound each face.

    Parameters
    ----------
    kc : KnowledgeComplex

    Returns
    -------
    BoundaryMatrices
    """
    # Enumerate elements by dimension
    vertices = sorted(kc.skeleton(0) - kc.skeleton(1))
    # skeleton(0) = vertices, skeleton(1) = vertices + edges
    all_v = set()
    all_e = set()
    all_f = set()
    for eid in kc.element_ids():
        elem = kc.element(eid)
        kind = kc._schema._types.get(elem.type, {}).get("kind")
        if kind == "vertex":
            all_v.add(eid)
        elif kind == "edge":
            all_e.add(eid)
        elif kind == "face":
            all_f.add(eid)

    vertices = sorted(all_v)
    edges = sorted(all_e)
    faces = sorted(all_f)

    vertex_index = {v: i for i, v in enumerate(vertices)}
    edge_index = {e: i for i, e in enumerate(edges)}
    face_index = {f: i for i, f in enumerate(faces)}

    nv, ne, nf = len(vertices), len(edges), len(faces)

    # B1: vertices × edges
    # For each edge, find its 2 boundary vertices.
    # Convention: for edge e = {v_i, v_j} with i < j, B1[i,e] = -1, B1[j,e] = +1
    rows1, cols1, vals1 = [], [], []
    for e_id in edges:
        bnd = sorted(kc.boundary(e_id), key=lambda v: vertex_index.get(v, 0))
        if len(bnd) == 2:
            r0 = vertex_index[bnd[0]]
            r1 = vertex_index[bnd[1]]
            c = edge_index[e_id]
            rows1.extend([r0, r1])
            cols1.extend([c, c])
            vals1.extend([-1.0, 1.0])

    B1 = sp.csr_matrix(
        (vals1, (rows1, cols1)), shape=(nv, ne), dtype=np.float64
    ) if ne > 0 else sp.csr_matrix((nv, 0), dtype=np.float64)

    # B2: edges × faces
    # For each face, find its 3 boundary edges.
    # Orientation: assign signs so that ∂₁∘∂₂ = 0.
    # We pick a consistent orientation per face by walking the vertex cycle.
    rows2, cols2, vals2 = [], [], []
    for f_id in faces:
        bnd_edges = list(kc.boundary(f_id))
        if len(bnd_edges) == 3:
            c = face_index[f_id]
            # Get the vertex sets for each boundary edge
            edge_verts = {}
            for be in bnd_edges:
                edge_verts[be] = kc.boundary(be)

            # Orient: find a vertex ordering (v_a, v_b, v_c) and assign signs
            # to edges based on whether they agree with the cycle orientation
            signs = _orient_face(bnd_edges, edge_verts, vertex_index)
            for be, sign in zip(bnd_edges, signs):
                rows2.append(edge_index[be])
                cols2.append(c)
                vals2.append(sign)

    B2 = sp.csr_matrix(
        (vals2, (rows2, cols2)), shape=(ne, nf), dtype=np.float64
    ) if nf > 0 else sp.csr_matrix((ne, 0), dtype=np.float64)

    return BoundaryMatrices(
        B1=B1, B2=B2,
        vertex_index=vertex_index,
        edge_index=edge_index,
        face_index=face_index,
        index_vertex={v: k for k, v in vertex_index.items()},
        index_edge={v: k for k, v in edge_index.items()},
        index_face={v: k for k, v in face_index.items()},
    )


def _orient_face(
    edges: list[str],
    edge_verts: dict[str, set[str]],
    vertex_index: dict[str, int],
) -> list[float]:
    """Assign ±1 signs to face boundary edges for a consistent orientation.

    Given a triangular face with 3 edges, find a vertex cycle (a, b, c) and
    assign +1 to edges traversed in cycle order, -1 to those against.
    This ensures ∂₁ ∘ ∂₂ = 0.
    """
    # Collect all vertices of the face
    all_verts: set[str] = set()
    for vs in edge_verts.values():
        all_verts |= vs
    verts = sorted(all_verts, key=lambda v: vertex_index.get(v, 0))

    if len(verts) != 3:
        return [1.0] * len(edges)

    a, b, c = verts  # sorted by index

    # Define cycle: a → b → c → a
    # For each edge, check if it goes with or against the cycle
    signs = []
    for e in edges:
        ev = edge_verts[e]
        ev_sorted = sorted(ev, key=lambda v: vertex_index.get(v, 0))
        if len(ev_sorted) != 2:
            signs.append(1.0)
            continue
        v0, v1 = ev_sorted  # v0 has lower index

        # Cycle pairs in order: (a,b), (b,c), (a,c)
        # Edge orientation convention: B1[lower, e] = -1, B1[higher, e] = +1
        # So the edge "points" from lower-index to higher-index vertex.
        # Cycle: a→b→c→a
        # (a,b): cycle goes a→b, edge goes a→b (same) → +1
        # (b,c): cycle goes b→c, edge goes b→c (same) → +1
        # (a,c): cycle goes c→a, edge goes a→c (opposite) → -1
        if (v0, v1) == (a, b):
            signs.append(1.0)
        elif (v0, v1) == (b, c):
            signs.append(1.0)
        elif (v0, v1) == (a, c):
            signs.append(-1.0)
        else:
            signs.append(1.0)

    return signs


# ---------------------------------------------------------------------------
# Betti numbers
# ---------------------------------------------------------------------------

def betti_numbers(kc: "KnowledgeComplex") -> list[int]:
    """
    Compute Betti numbers [β₀, β₁, β₂] of the complex.

    β_k = nullity(∂_k) - rank(∂_{k+1})

    Parameters
    ----------
    kc : KnowledgeComplex

    Returns
    -------
    list[int]
        [β₀, β₁, β₂]
    """
    bm = boundary_matrices(kc)
    nv = bm.B1.shape[0]
    ne = bm.B1.shape[1]
    nf = bm.B2.shape[1]

    rank_B1 = _matrix_rank(bm.B1) if ne > 0 else 0
    rank_B2 = _matrix_rank(bm.B2) if nf > 0 else 0

    # β₀ = nullity(∂₁) at dimension 0
    # ∂₀ doesn't exist (or is zero), so β₀ = n_vertices - rank(∂₁)
    beta0 = nv - rank_B1

    # β₁ = nullity(∂₁) - rank(∂₂) = (n_edges - rank_B1) - rank_B2
    beta1 = (ne - rank_B1) - rank_B2 if ne > 0 else 0

    # β₂ = nullity(∂₂) - rank(∂₃) = (n_faces - rank_B2) - 0
    beta2 = nf - rank_B2 if nf > 0 else 0

    return [beta0, beta1, beta2]


def euler_characteristic(kc: "KnowledgeComplex") -> int:
    """
    Compute the Euler characteristic χ = V - E + F.

    Parameters
    ----------
    kc : KnowledgeComplex

    Returns
    -------
    int
    """
    bm = boundary_matrices(kc)
    return bm.B1.shape[0] - bm.B1.shape[1] + bm.B2.shape[1]


def _matrix_rank(M: sp.csr_matrix, tol: float = 1e-10) -> int:
    """Compute rank of a sparse matrix via SVD."""
    if M.shape[0] == 0 or M.shape[1] == 0:
        return 0
    dense = M.toarray()
    s = np.linalg.svd(dense, compute_uv=False)
    return int(np.sum(s > tol))


# ---------------------------------------------------------------------------
# Hodge Laplacian
# ---------------------------------------------------------------------------

def hodge_laplacian(
    kc: "KnowledgeComplex",
    weighted: bool = False,
) -> sp.csr_matrix:
    """
    Compute the edge Hodge Laplacian L₁.

    Combinatorial (default):
        L₁ = B1ᵀ B1 + B2 B2ᵀ

    Degree-weighted:
        L₁ = B1ᵀ D₀⁻¹ B1 + D₁⁻¹ B2 B2ᵀ

    Parameters
    ----------
    kc : KnowledgeComplex
    weighted : bool
        If True, use degree-weighted Laplacian.

    Returns
    -------
    scipy.sparse.csr_matrix
        (n_edges, n_edges)
    """
    bm = boundary_matrices(kc)
    ne = bm.B1.shape[1]

    if ne == 0:
        return sp.csr_matrix((0, 0), dtype=np.float64)

    if not weighted:
        down = bm.B1.T @ bm.B1
        up = bm.B2 @ bm.B2.T if bm.B2.shape[1] > 0 else sp.csr_matrix((ne, ne), dtype=np.float64)
        return (down + up).tocsr()
    else:
        # D₀: diagonal vertex degrees
        nv = bm.B1.shape[0]
        vertex_degrees = np.array(np.abs(bm.B1).sum(axis=1)).flatten()
        vertex_degrees[vertex_degrees == 0] = 1.0
        D0_inv = sp.diags(1.0 / vertex_degrees, format="csr")

        # D₁: diagonal edge face-degrees
        if bm.B2.shape[1] > 0:
            edge_face_degrees = np.array(np.abs(bm.B2).sum(axis=1)).flatten()
        else:
            edge_face_degrees = np.zeros(ne)
        edge_face_degrees[edge_face_degrees == 0] = 1.0
        D1_inv_sqrt = sp.diags(1.0 / np.sqrt(edge_face_degrees), format="csr")
        D0_inv_sqrt = sp.diags(1.0 / np.sqrt(vertex_degrees), format="csr")

        # Symmetric form: D₀^{-1/2} B1ᵀ ... uses symmetric normalization
        down = bm.B1.T @ D0_inv @ bm.B1
        up = D1_inv_sqrt @ bm.B2 @ bm.B2.T @ D1_inv_sqrt if bm.B2.shape[1] > 0 else sp.csr_matrix((ne, ne), dtype=np.float64)
        L = (down + up).tocsr()
        # Symmetrize to eliminate floating-point asymmetry
        return ((L + L.T) / 2).tocsr()


# ---------------------------------------------------------------------------
# Edge PageRank
# ---------------------------------------------------------------------------

def edge_pagerank(
    kc: "KnowledgeComplex",
    edge_id: str,
    beta: float = 0.1,
    weighted: bool = False,
) -> np.ndarray:
    """
    Compute personalized edge PageRank for a single edge.

    PR_e = (βI + L₁)⁻¹ χ_e

    Parameters
    ----------
    kc : KnowledgeComplex
    edge_id : str
    beta : float
    weighted : bool

    Returns
    -------
    np.ndarray
        (n_edges,)
    """
    bm = boundary_matrices(kc)
    L1 = hodge_laplacian(kc, weighted=weighted)
    ne = L1.shape[0]

    A = beta * sp.eye(ne, format="csr") + L1
    indicator = np.zeros(ne)
    indicator[bm.edge_index[edge_id]] = 1.0

    return _solve_spd(A, indicator)


def edge_pagerank_all(
    kc: "KnowledgeComplex",
    beta: float = 0.1,
    weighted: bool = False,
) -> np.ndarray:
    """
    Compute edge PageRank for all edges via matrix factorization.

    Factorizes (βI + L₁) once, then solves for each column of the identity.
    Equivalent to computing (βI + L₁)⁻¹.

    Parameters
    ----------
    kc : KnowledgeComplex
    beta : float
    weighted : bool

    Returns
    -------
    np.ndarray
        (n_edges, n_edges) — column i is the PageRank vector for edge i.
    """
    L1 = hodge_laplacian(kc, weighted=weighted)
    ne = L1.shape[0]

    if ne == 0:
        return np.empty((0, 0))

    A = beta * sp.eye(ne, format="csc") + L1.tocsc()

    # Factor once (SPD → LU on sparse, or Cholesky)
    factor = splu(A)
    result = np.zeros((ne, ne))
    for i in range(ne):
        rhs = np.zeros(ne)
        rhs[i] = 1.0
        result[:, i] = factor.solve(rhs)

    return result


def _solve_spd(A: sp.csr_matrix, b: np.ndarray) -> np.ndarray:
    """Solve Ax = b for SPD matrix A. Try CG, fall back to dense."""
    x, info = cg(A, b, atol=1e-12, maxiter=1000)
    if info != 0:
        x = np.linalg.solve(A.toarray(), b)
    return x


# ---------------------------------------------------------------------------
# Hodge decomposition
# ---------------------------------------------------------------------------

def hodge_decomposition(
    kc: "KnowledgeComplex",
    flow: np.ndarray,
) -> HodgeDecomposition:
    """
    Decompose an edge flow into gradient + curl + harmonic components.

    flow = gradient + curl + harmonic

    where:
    - gradient ∈ im(B1ᵀ) — vertex-driven flow
    - curl ∈ im(B2) — face-driven circulation
    - harmonic ∈ ker(L₁) — topological cycles

    Parameters
    ----------
    kc : KnowledgeComplex
    flow : np.ndarray
        (n_edges,)

    Returns
    -------
    HodgeDecomposition
    """
    bm = boundary_matrices(kc)

    gradient = _project_onto_image(bm.B1.T, flow)
    curl = _project_onto_image(bm.B2, flow)
    harmonic = flow - gradient - curl

    return HodgeDecomposition(
        gradient=gradient,
        curl=curl,
        harmonic=harmonic,
    )


def _project_onto_image(
    A: sp.csr_matrix,
    v: np.ndarray,
    regularization: float = 1e-10,
) -> np.ndarray:
    """Project v onto im(A): proj = A (AᵀA + λI)⁻¹ Aᵀ v."""
    if A.shape[1] == 0:
        return np.zeros_like(v)

    ATA = A.T @ A
    ATA_reg = ATA + regularization * sp.eye(ATA.shape[0], format="csr")
    ATv = A.T @ v

    x, info = cg(ATA_reg, ATv, atol=1e-12, maxiter=1000)
    if info != 0:
        x = np.linalg.lstsq(ATA_reg.toarray(), ATv, rcond=None)[0]

    return A @ x


# ---------------------------------------------------------------------------
# Edge influence
# ---------------------------------------------------------------------------

def edge_influence(edge_id: str, pr_vector: np.ndarray) -> EdgeInfluence:
    """
    Compute influence measures from a PageRank vector.

    Parameters
    ----------
    edge_id : str
    pr_vector : np.ndarray

    Returns
    -------
    EdgeInfluence
    """
    l1 = float(np.sum(np.abs(pr_vector)))
    l2 = float(np.linalg.norm(pr_vector))
    spread = l2 / l1 if l1 > 0 else 0.0
    return EdgeInfluence(
        edge_id=edge_id,
        spread=spread,
        absolute_influence=l1,
        penetration=l2,
        relative_influence=float(np.sum(pr_vector)),
    )


# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------

def hodge_analysis(
    kc: "KnowledgeComplex",
    beta: float = 0.1,
    weighted: bool = False,
) -> HodgeAnalysisResults:
    """
    Run complete Hodge analysis on a knowledge complex.

    Computes boundary matrices, Betti numbers, Hodge Laplacian,
    edge PageRank for all edges, Hodge decomposition, and influence measures.

    Parameters
    ----------
    kc : KnowledgeComplex
    beta : float
    weighted : bool

    Returns
    -------
    HodgeAnalysisResults
    """
    bm = boundary_matrices(kc)
    betti = betti_numbers(kc)
    chi = euler_characteristic(kc)
    L1 = hodge_laplacian(kc, weighted=weighted)
    pr = edge_pagerank_all(kc, beta=beta, weighted=weighted)

    decomps: dict[str, HodgeDecomposition] = {}
    infls: dict[str, EdgeInfluence] = {}
    for eid, idx in bm.edge_index.items():
        pr_vec = pr[:, idx]
        decomps[eid] = hodge_decomposition(kc, pr_vec)
        infls[eid] = edge_influence(eid, pr_vec)

    return HodgeAnalysisResults(
        betti=betti,
        euler_characteristic=chi,
        boundary_matrices=bm,
        laplacian=L1,
        pagerank=pr,
        decompositions=decomps,
        influences=infls,
    )
