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
from scipy.linalg import expm

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
class SweepCut:
    """Result of a vertex sweep cut."""
    vertices: set[str]
    conductance: float
    volume: int
    boundary_edges: int


@dataclass
class EdgeSweepCut:
    """Result of an edge sweep cut."""
    edges: set[str]
    conductance: float
    volume: int


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
# Weight matrices
# ---------------------------------------------------------------------------

def _weight_matrices(
    bm: BoundaryMatrices,
    weights: dict[str, float] | None,
) -> tuple[sp.dia_matrix, sp.dia_matrix, sp.dia_matrix]:
    """Build diagonal weight matrices W₀, W₁, W₂ from a weights dict.

    Returns identity matrices when weights is None. Missing elements
    default to weight 1.0.
    """
    nv = len(bm.vertex_index)
    ne = len(bm.edge_index)
    nf = len(bm.face_index)

    if weights is None:
        return (
            sp.eye(nv, format="dia"),
            sp.eye(ne, format="dia"),
            sp.eye(nf, format="dia"),
        )

    w0 = np.array([weights.get(bm.index_vertex[i], 1.0) for i in range(nv)])
    w1 = np.array([weights.get(bm.index_edge[i], 1.0) for i in range(ne)])
    w2 = np.array([weights.get(bm.index_face[i], 1.0) for i in range(nf)]) if nf > 0 else np.array([])

    return (
        sp.diags(w0, format="dia") if nv > 0 else sp.eye(0, format="dia"),
        sp.diags(w1, format="dia") if ne > 0 else sp.eye(0, format="dia"),
        sp.diags(w2, format="dia") if nf > 0 else sp.eye(0, format="dia"),
    )


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
    weights: dict[str, float] | None = None,
) -> sp.csr_matrix:
    """
    Compute the edge Hodge Laplacian L₁.

    Combinatorial (default):
        L₁ = B1ᵀ W₀ B1 + B2 W₂ B2ᵀ

    where W₀ and W₂ are diagonal simplex weight matrices (identity when
    weights is None).

    Degree-weighted:
        L₁ = B1ᵀ D₀⁻¹ W₀ B1 + D₁⁻¹ B2 W₂ B2ᵀ

    Parameters
    ----------
    kc : KnowledgeComplex
    weighted : bool
        If True, also apply degree normalization.
    weights : dict[str, float], optional
        Map from element IDs to scalar weights. Missing elements default
        to 1.0. Vertex weights enter W₀, face weights enter W₂.

    Returns
    -------
    scipy.sparse.csr_matrix
        (n_edges, n_edges)
    """
    bm = boundary_matrices(kc)
    ne = bm.B1.shape[1]

    if ne == 0:
        return sp.csr_matrix((0, 0), dtype=np.float64)

    W0, _W1, W2 = _weight_matrices(bm, weights)

    if not weighted:
        down = bm.B1.T @ W0 @ bm.B1
        up = bm.B2 @ W2 @ bm.B2.T if bm.B2.shape[1] > 0 else sp.csr_matrix((ne, ne), dtype=np.float64)
        L = (down + up).tocsr()
        return ((L + L.T) / 2).tocsr()
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

        down = bm.B1.T @ D0_inv @ W0 @ bm.B1
        up = D1_inv_sqrt @ bm.B2 @ W2 @ bm.B2.T @ D1_inv_sqrt if bm.B2.shape[1] > 0 else sp.csr_matrix((ne, ne), dtype=np.float64)
        L = (down + up).tocsr()
        return ((L + L.T) / 2).tocsr()


# ---------------------------------------------------------------------------
# Edge PageRank
# ---------------------------------------------------------------------------

def edge_pagerank(
    kc: "KnowledgeComplex",
    edge_id: str,
    beta: float = 0.1,
    weighted: bool = False,
    weights: dict[str, float] | None = None,
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
    weights : dict[str, float], optional
        Simplex weights (see hodge_laplacian).

    Returns
    -------
    np.ndarray
        (n_edges,)
    """
    bm = boundary_matrices(kc)
    L1 = hodge_laplacian(kc, weighted=weighted, weights=weights)
    ne = L1.shape[0]

    A = beta * sp.eye(ne, format="csr") + L1
    indicator = np.zeros(ne)
    indicator[bm.edge_index[edge_id]] = 1.0

    return _solve_spd(A, indicator)


def edge_pagerank_all(
    kc: "KnowledgeComplex",
    beta: float = 0.1,
    weighted: bool = False,
    weights: dict[str, float] | None = None,
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
    weights : dict[str, float], optional
        Simplex weights (see hodge_laplacian).

    Returns
    -------
    np.ndarray
        (n_edges, n_edges) — column i is the PageRank vector for edge i.
    """
    L1 = hodge_laplacian(kc, weighted=weighted, weights=weights)
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
    weights: dict[str, float] | None = None,
) -> HodgeDecomposition:
    """
    Decompose an edge flow into gradient + curl + harmonic components.

    flow = gradient + curl + harmonic

    where:
    - gradient ∈ im(W₀^{1/2} B1ᵀ) — vertex-driven flow
    - curl ∈ im(W₂^{1/2} B2) — face-driven circulation
    - harmonic ∈ ker(L₁) — topological cycles

    When weights is None, W₀ and W₂ are identity (standard decomposition).

    Parameters
    ----------
    kc : KnowledgeComplex
    flow : np.ndarray
        (n_edges,)
    weights : dict[str, float], optional
        Simplex weights. Affects the inner product used for projection.

    Returns
    -------
    HodgeDecomposition
    """
    bm = boundary_matrices(kc)
    W0, _W1, W2 = _weight_matrices(bm, weights)

    # Weighted projection operators
    # gradient lives in im(B1ᵀ W₀^{1/2}), curl in im(B2 W₂^{1/2})
    # but for the orthogonal decomposition with weighted inner product,
    # we project onto im(B1ᵀ) with W₀-weighted inner product on vertices
    # Practically: project onto im(sqrt(W₀) B1ᵀ) in standard inner product
    if weights is not None:
        w0_sqrt = sp.diags(np.sqrt(np.array(W0.diagonal())), format="csr")
        w2_sqrt = sp.diags(np.sqrt(np.array(W2.diagonal())), format="csr") if W2.shape[0] > 0 else W2
        # B1.T is (ne × nv), W0_sqrt is (nv × nv) → B1.T @ W0_sqrt is (ne × nv)
        grad_op = bm.B1.T @ w0_sqrt if bm.B1.shape[1] > 0 else bm.B1.T
        curl_op = bm.B2 @ w2_sqrt if bm.B2.shape[1] > 0 else bm.B2
    else:
        grad_op = bm.B1.T
        curl_op = bm.B2

    gradient = _project_onto_image(grad_op, flow)
    curl = _project_onto_image(curl_op, flow)
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
    weights: dict[str, float] | None = None,
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
    weights : dict[str, float], optional
        Simplex weights (see hodge_laplacian).

    Returns
    -------
    HodgeAnalysisResults
    """
    bm = boundary_matrices(kc)
    betti = betti_numbers(kc)
    chi = euler_characteristic(kc)
    L1 = hodge_laplacian(kc, weighted=weighted, weights=weights)
    pr = edge_pagerank_all(kc, beta=beta, weighted=weighted, weights=weights)

    decomps: dict[str, HodgeDecomposition] = {}
    infls: dict[str, EdgeInfluence] = {}
    for eid, idx in bm.edge_index.items():
        pr_vec = pr[:, idx]
        decomps[eid] = hodge_decomposition(kc, pr_vec, weights=weights)
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


# ---------------------------------------------------------------------------
# Graph Laplacian (on the 1-skeleton)
# ---------------------------------------------------------------------------

def graph_laplacian(kc: "KnowledgeComplex") -> sp.csr_matrix:
    """
    Compute the normalized graph Laplacian L = I - D⁻¹A on the 1-skeleton.

    Parameters
    ----------
    kc : KnowledgeComplex

    Returns
    -------
    scipy.sparse.csr_matrix
        (n_vertices, n_vertices)
    """
    bm = boundary_matrices(kc)
    nv = len(bm.vertex_index)
    ne = len(bm.edge_index)

    if nv == 0:
        return sp.csr_matrix((0, 0), dtype=np.float64)

    # Build adjacency matrix from B1
    # A = |B1| |B1|ᵀ - D  but simpler: walk the edges directly
    rows, cols, vals = [], [], []
    for e_id, e_idx in bm.edge_index.items():
        bnd = list(kc.boundary(e_id))
        if len(bnd) == 2:
            i = bm.vertex_index[bnd[0]]
            j = bm.vertex_index[bnd[1]]
            rows.extend([i, j])
            cols.extend([j, i])
            vals.extend([1.0, 1.0])

    A = sp.csr_matrix((vals, (rows, cols)), shape=(nv, nv), dtype=np.float64)
    degrees = np.array(A.sum(axis=1)).flatten()
    degrees[degrees == 0] = 1.0
    D_inv = sp.diags(1.0 / degrees, format="csr")

    L = sp.eye(nv, format="csr") - D_inv @ A
    return ((L + L.T) / 2).tocsr()


def _adjacency_and_degrees(kc: "KnowledgeComplex", bm: BoundaryMatrices):
    """Build adjacency matrix and degree dict for the 1-skeleton."""
    nv = len(bm.vertex_index)
    rows, cols, vals = [], [], []
    for e_id in bm.edge_index:
        bnd = list(kc.boundary(e_id))
        if len(bnd) == 2:
            i = bm.vertex_index[bnd[0]]
            j = bm.vertex_index[bnd[1]]
            rows.extend([i, j])
            cols.extend([j, i])
            vals.extend([1.0, 1.0])

    A = sp.csr_matrix((vals, (rows, cols)), shape=(nv, nv), dtype=np.float64)
    degrees = np.array(A.sum(axis=1)).flatten().astype(int)

    # Build id->degree map
    deg_map = {}
    for vid, idx in bm.vertex_index.items():
        deg_map[vid] = int(degrees[idx])

    return A, deg_map


# ---------------------------------------------------------------------------
# Approximate PageRank (Andersen-Chung-Lang push algorithm)
# ---------------------------------------------------------------------------

def approximate_pagerank(
    kc: "KnowledgeComplex",
    seed: str,
    alpha: float = 0.15,
    epsilon: float = 1e-4,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Compute approximate PageRank via the push algorithm.

    Follows Andersen-Chung-Lang (FOCS 2006). Uses lazy random walk
    W = (I + D⁻¹A)/2. Maintains invariant p + pr(α, r) = pr(α, χ_seed).

    Parameters
    ----------
    kc : KnowledgeComplex
    seed : str
        Starting vertex.
    alpha : float
        Teleportation constant (higher = more local).
    epsilon : float
        Convergence threshold: stops when max r(u)/d(u) < epsilon.

    Returns
    -------
    tuple[dict[str, float], dict[str, float]]
        (p, r) — approximate PageRank vector and residual.
    """
    bm = boundary_matrices(kc)
    _, deg_map = _adjacency_and_degrees(kc, bm)

    # Neighbor lookup
    neighbors: dict[str, list[str]] = {v: [] for v in bm.vertex_index}
    for e_id in bm.edge_index:
        bnd = list(kc.boundary(e_id))
        if len(bnd) == 2:
            neighbors[bnd[0]].append(bnd[1])
            neighbors[bnd[1]].append(bnd[0])

    p: dict[str, float] = {}
    r: dict[str, float] = {seed: 1.0}

    # Push loop
    while True:
        # Find vertex with max r(u)/d(u)
        best_u = None
        best_ratio = 0.0
        for u, rv in r.items():
            d = max(deg_map.get(u, 1), 1)
            ratio = rv / d
            if ratio > best_ratio:
                best_ratio = ratio
                best_u = u

        if best_ratio < epsilon or best_u is None:
            break

        # Push operation at best_u
        u = best_u
        ru = r[u]
        d_u = max(deg_map.get(u, 1), 1)

        # Move alpha fraction to p
        p[u] = p.get(u, 0) + alpha * ru

        # Spread (1-alpha) fraction via lazy walk: half stays, half spreads
        r[u] = (1 - alpha) * ru / 2

        spread = (1 - alpha) * ru / (2 * d_u)
        for v in neighbors.get(u, []):
            r[v] = r.get(v, 0) + spread

    return p, r


# ---------------------------------------------------------------------------
# Heat kernel PageRank
# ---------------------------------------------------------------------------

def heat_kernel_pagerank(
    kc: "KnowledgeComplex",
    seed: str,
    t: float = 5.0,
    num_terms: int = 30,
) -> dict[str, float]:
    """
    Compute heat kernel PageRank ρ_{t,seed} on the 1-skeleton.

    ρ_{t,u} = e^{-t} Σ_{k=0}^{N} (t^k / k!) χ_u W^k

    where W = D⁻¹A is the random walk transition matrix.

    Parameters
    ----------
    kc : KnowledgeComplex
    seed : str
        Starting vertex.
    t : float
        Heat parameter (temperature). Small t = local, large t = global.
    num_terms : int
        Number of terms in the Taylor expansion.

    Returns
    -------
    dict[str, float]
        Mapping from vertex IDs to PageRank values.
    """
    bm = boundary_matrices(kc)
    nv = len(bm.vertex_index)

    if nv == 0:
        return {}

    # Build W = D⁻¹A (random walk transition matrix)
    rows, cols, vals = [], [], []
    for e_id in bm.edge_index:
        bnd = list(kc.boundary(e_id))
        if len(bnd) == 2:
            i = bm.vertex_index[bnd[0]]
            j = bm.vertex_index[bnd[1]]
            rows.extend([i, j])
            cols.extend([j, i])
            vals.extend([1.0, 1.0])

    A = sp.csr_matrix((vals, (rows, cols)), shape=(nv, nv), dtype=np.float64)
    degrees = np.array(A.sum(axis=1)).flatten()
    degrees[degrees == 0] = 1.0
    D_inv = sp.diags(1.0 / degrees, format="csr")
    W = D_inv @ A

    # Compute ρ = e^{-t} Σ (t^k / k!) χ_u W^k via Taylor expansion
    seed_idx = bm.vertex_index[seed]
    chi = np.zeros(nv)
    chi[seed_idx] = 1.0

    result = np.zeros(nv)
    current = chi.copy()  # χ_u W^0 = χ_u
    coeff = np.exp(-t)
    factorial = 1.0

    for k in range(num_terms):
        if k > 0:
            factorial *= k
            current = current @ W.toarray()
        result += (t ** k / factorial) * current

    result *= np.exp(-t)

    return {bm.index_vertex[i]: float(result[i]) for i in range(nv)}


# ---------------------------------------------------------------------------
# Sweep cut (graph version)
# ---------------------------------------------------------------------------

def sweep_cut(
    kc: "KnowledgeComplex",
    distribution: dict[str, float],
    max_volume: int | None = None,
) -> SweepCut:
    """
    Sweep a vertex distribution to find a cut with minimum conductance.

    Sorts vertices by p(v)/d(v) descending, computes conductance of each
    prefix set, returns the cut with minimum conductance.

    Parameters
    ----------
    kc : KnowledgeComplex
    distribution : dict[str, float]
        Vertex distribution (e.g., from approximate_pagerank).
    max_volume : int, optional
        Maximum volume for the small side of the cut.

    Returns
    -------
    SweepCut
    """
    bm = boundary_matrices(kc)
    _, deg_map = _adjacency_and_degrees(kc, bm)

    # Neighbor lookup
    neighbors: dict[str, set[str]] = {v: set() for v in bm.vertex_index}
    for e_id in bm.edge_index:
        bnd = list(kc.boundary(e_id))
        if len(bnd) == 2:
            neighbors[bnd[0]].add(bnd[1])
            neighbors[bnd[1]].add(bnd[0])

    total_volume = sum(deg_map.values())

    # Sort vertices by p(v)/d(v) descending
    scored = []
    for vid in bm.vertex_index:
        pv = distribution.get(vid, 0.0)
        dv = max(deg_map.get(vid, 1), 1)
        scored.append((vid, pv / dv))
    scored.sort(key=lambda x: -x[1])

    # Sweep: incrementally build S, track boundary edges and volume
    best_cut = SweepCut(vertices=set(), conductance=float("inf"), volume=0, boundary_edges=0)
    S: set[str] = set()
    vol_S = 0
    boundary = 0

    for vid, _ in scored:
        d_v = deg_map.get(vid, 0)
        # Update boundary: edges from vid to S decrease boundary,
        # edges from vid to outside S increase boundary
        edges_to_S = len(neighbors[vid] & S)
        edges_to_outside = d_v - edges_to_S
        boundary = boundary - edges_to_S + edges_to_outside

        S.add(vid)
        vol_S += d_v

        if vol_S == 0 or vol_S >= total_volume:
            continue

        if max_volume is not None and vol_S > max_volume:
            break

        denom = min(vol_S, total_volume - vol_S)
        cond = boundary / denom if denom > 0 else float("inf")

        if cond < best_cut.conductance:
            best_cut = SweepCut(
                vertices=set(S),
                conductance=cond,
                volume=vol_S,
                boundary_edges=boundary,
            )

    return best_cut


# ---------------------------------------------------------------------------
# Local partition (graph version)
# ---------------------------------------------------------------------------

def local_partition(
    kc: "KnowledgeComplex",
    seed: str,
    target_conductance: float = 0.5,
    target_volume: int | None = None,
    method: str = "pagerank",
) -> SweepCut:
    """
    Find a local partition near a seed vertex.

    Parameters
    ----------
    kc : KnowledgeComplex
    seed : str
        Starting vertex.
    target_conductance : float
        Target conductance for setting alpha/t.
    target_volume : int, optional
        Maximum volume for the small side.
    method : str
        "pagerank" — approximate PageRank (Andersen-Chung-Lang).
        "heat_kernel" — heat kernel PageRank (Chung).

    Returns
    -------
    SweepCut
    """
    if method == "pagerank":
        alpha = target_conductance ** 2 / (16 * np.log(sum(
            max(kc.degree(v), 1) for v in kc.element_ids(type=None)
            if kc._schema._types.get(kc.element(v).type, {}).get("kind") == "vertex"
        ) + 1))
        alpha = max(min(alpha, 0.5), 0.01)
        p, r = approximate_pagerank(kc, seed, alpha=alpha)
        return sweep_cut(kc, p, max_volume=target_volume)

    elif method == "heat_kernel":
        t = max(1.0, 4.0 / (target_conductance ** 2))
        rho = heat_kernel_pagerank(kc, seed, t=t)
        return sweep_cut(kc, rho, max_volume=target_volume)

    else:
        raise ValueError(f"Unknown method '{method}'. Use 'pagerank' or 'heat_kernel'.")


# ---------------------------------------------------------------------------
# Edge sweep cut (simplicial version)
# ---------------------------------------------------------------------------

def edge_sweep_cut(
    kc: "KnowledgeComplex",
    edge_distribution: np.ndarray,
    bm: BoundaryMatrices | None = None,
) -> EdgeSweepCut:
    """
    Sweep an edge distribution to find an edge partition with minimum conductance.

    Sorts edges by |distribution(e)|/degree(e) descending, computes edge
    conductance of each prefix. Edge conductance measures how many
    vertex-boundary connections cross the partition.

    Parameters
    ----------
    kc : KnowledgeComplex
    edge_distribution : np.ndarray
        (n_edges,) vector of edge values.
    bm : BoundaryMatrices, optional
        Pre-computed boundary matrices.

    Returns
    -------
    EdgeSweepCut
    """
    if bm is None:
        bm = boundary_matrices(kc)

    ne = len(bm.edge_index)
    if ne == 0:
        return EdgeSweepCut(edges=set(), conductance=float("inf"), volume=0)

    # Edge degree: number of faces incident to each edge + number of vertices
    # Use coboundary size as a measure of "degree" for edges
    edge_degrees = np.array(np.abs(bm.B2).sum(axis=1)).flatten() + 2  # +2 for boundary vertices

    # Sort edges by |distribution(e)| / degree(e) descending
    scored = []
    for eid, idx in bm.edge_index.items():
        val = abs(edge_distribution[idx])
        deg = max(edge_degrees[idx], 1)
        scored.append((eid, idx, val / deg))
    scored.sort(key=lambda x: -x[2])

    # Edge adjacency: two edges are adjacent if they share a vertex
    # Build edge adjacency from B1
    edge_adj: dict[str, set[str]] = {e: set() for e in bm.edge_index}
    # For each vertex, collect incident edges
    vertex_edges: dict[int, list[str]] = {}
    for eid, eidx in bm.edge_index.items():
        col = bm.B1[:, eidx]
        for vidx in col.nonzero()[0]:
            vertex_edges.setdefault(vidx, []).append(eid)

    for vidx, eids in vertex_edges.items():
        for i, e1 in enumerate(eids):
            for e2 in eids[i + 1:]:
                edge_adj[e1].add(e2)
                edge_adj[e2].add(e1)

    total_edge_vol = int(sum(edge_degrees))
    S: set[str] = set()
    vol_S = 0
    boundary = 0

    best = EdgeSweepCut(edges=set(), conductance=float("inf"), volume=0)

    for eid, eidx, _ in scored:
        d_e = int(edge_degrees[eidx])
        adj_in_S = len(edge_adj[eid] & S)
        adj_outside = len(edge_adj[eid]) - adj_in_S
        boundary = boundary - adj_in_S + adj_outside

        S.add(eid)
        vol_S += d_e

        if vol_S == 0 or vol_S >= total_edge_vol:
            continue

        denom = min(vol_S, total_edge_vol - vol_S)
        cond = boundary / denom if denom > 0 else float("inf")

        if cond < best.conductance:
            best = EdgeSweepCut(edges=set(S), conductance=cond, volume=vol_S)

    return best


# ---------------------------------------------------------------------------
# Edge local partition (simplicial version)
# ---------------------------------------------------------------------------

def edge_local_partition(
    kc: "KnowledgeComplex",
    seed_edge: str,
    t: float = 5.0,
    beta: float = 0.1,
    method: str = "hodge_heat",
    weights: dict[str, float] | None = None,
) -> EdgeSweepCut:
    """
    Find a local edge partition using the Hodge Laplacian.

    Parameters
    ----------
    kc : KnowledgeComplex
    seed_edge : str
        Starting edge.
    t : float
        Heat parameter (for hodge_heat method).
    beta : float
        Regularization (for hodge_pagerank method).
    method : str
        "hodge_heat" — e^{-tL₁} χ_e (heat kernel on edges).
        "hodge_pagerank" — (βI + L₁)⁻¹ χ_e (existing edge PageRank).
    weights : dict[str, float], optional
        Simplex weights.

    Returns
    -------
    EdgeSweepCut
    """
    bm = boundary_matrices(kc)
    ne = len(bm.edge_index)

    if ne == 0:
        return EdgeSweepCut(edges=set(), conductance=float("inf"), volume=0)

    L1 = hodge_laplacian(kc, weights=weights)

    if method == "hodge_pagerank":
        dist = edge_pagerank(kc, seed_edge, beta=beta, weights=weights)
    elif method == "hodge_heat":
        # Compute e^{-tL₁} χ_e via dense matrix exponential
        L1_dense = L1.toarray()
        heat = expm(-t * L1_dense)
        seed_idx = bm.edge_index[seed_edge]
        dist = heat[:, seed_idx]
    else:
        raise ValueError(f"Unknown method '{method}'. Use 'hodge_heat' or 'hodge_pagerank'.")

    return edge_sweep_cut(kc, dist, bm=bm)
