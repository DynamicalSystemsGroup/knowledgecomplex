"""knowledgecomplex.viz — NetworkX export and visualization helpers.

Two complementary views of a knowledge complex are provided:

**Hasse diagram** (``plot_hasse``, ``plot_hasse_star``, ``plot_hasse_skeleton``)
    Every element (vertex, edge, face) becomes a graph node.  Directed edges
    represent the boundary operator, pointing from each element to its boundary
    elements (higher dimension → lower dimension).  Faces have out-degree 3
    and in-degree 0; edges have out-degree 2; vertices have out-degree 0.
    Nodes are colored by type and sized by dimension.

**Geometric realization** (``plot_geometric``, ``plot_geometric_interactive``)
    Only KC vertices become points in 3D space.  KC edges become line segments
    connecting their two boundary vertices.  KC faces become filled,
    semi-transparent triangular patches spanning their three boundary vertices.
    This is the classical geometric realization of the abstract simplicial
    complex — the view a topologist would draw.

``to_networkx`` exports a ``DiGraph`` that backs the Hasse plots.
``verify_networkx`` validates that a DiGraph satisfies simplicial complex
cardinality and closure invariants at runtime.

Requires optional dependencies::

    pip install knowledgecomplex[viz]                # matplotlib + networkx
    pip install knowledgecomplex[viz-interactive]     # + plotly for interactive 3D
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex

_DIM_BY_KIND = {"vertex": 0, "edge": 1, "face": 2}
_SIZE_BY_DIM = {0: 400, 1: 200, 2: 100}

_INSTALL_HINT = (
    "networkx and matplotlib are required for visualization.\n"
    "Install them with:  pip install knowledgecomplex[viz]"
)

_PLOTLY_HINT = (
    "plotly is required for interactive 3D visualization.\n"
    "Install it with:  pip install knowledgecomplex[viz-interactive]"
)


def _require_nx():
    try:
        import networkx as nx
        return nx
    except ImportError:
        raise ImportError(_INSTALL_HINT) from None


def _require_mpl():
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        return matplotlib, plt
    except ImportError:
        raise ImportError(_INSTALL_HINT) from None


def _require_plotly():
    try:
        import plotly.graph_objects as go
        return go
    except ImportError:
        raise ImportError(_PLOTLY_HINT) from None


# ── NetworkX export ─────────────────────────────────────────────────────────


def to_networkx(kc: "KnowledgeComplex") -> Any:
    """Convert a KnowledgeComplex to a directed networkx DiGraph.

    Every element (vertex, edge, face) becomes a node.  Directed edges
    represent the boundary operator ``kc:boundedBy``, pointing **from each
    element to its boundary elements** (higher dimension → lower dimension).

    In the resulting DiGraph:

    - **Face** nodes have out-degree 3 (→ 3 boundary edges) and in-degree 0.
    - **Edge** nodes have out-degree 2 (→ 2 boundary vertices).
    - **Vertex** nodes have out-degree 0 (empty boundary).

    Each node carries attributes:

    - ``type``: element type name (e.g. ``"Node"``, ``"Link"``)
    - ``kind``: ``"vertex"``, ``"edge"``, or ``"face"``
    - ``dim``: 0, 1, or 2
    - ``uri``: file URI if present, else ``None``
    - All model-namespace attributes from the element

    Parameters
    ----------
    kc : KnowledgeComplex

    Returns
    -------
    networkx.DiGraph
    """
    nx = _require_nx()
    G = nx.DiGraph(name=kc._schema._namespace)

    for elem_id in kc.element_ids():
        elem = kc.element(elem_id)
        type_name = elem.type
        kind = kc._schema._types.get(type_name, {}).get("kind", "vertex")
        attrs = {
            "type": type_name,
            "kind": kind,
            "dim": _DIM_BY_KIND.get(kind, 0),
            "uri": elem.uri,
            **elem.attrs,
        }
        G.add_node(elem_id, **attrs)

    # Directed boundary edges: element → boundary element (high dim → low dim)
    for elem_id in kc.element_ids():
        for boundary_id in kc.boundary(elem_id):
            G.add_edge(elem_id, boundary_id)

    return G


# ── Verification ────────────────────────────────────────────────────────────


def verify_networkx(G: Any) -> bool:
    """Validate that a DiGraph satisfies simplicial complex invariants.

    Checks cardinality constraints and boundary closure:

    - Every node has ``kind`` and ``dim`` attributes.
    - **Vertices** (dim=0): out-degree = 0.
    - **Edges** (dim=1): out-degree = 2, both targets are vertices (dim=0).
    - **Faces** (dim=2): out-degree = 3, all targets are edges (dim=1).
    - **Closed-triangle**: for each face, the 3 boundary edges share exactly
      3 distinct vertices (forming a closed triangle, not an open fan).

    Parameters
    ----------
    G : networkx.DiGraph
        A DiGraph produced by :func:`to_networkx`.

    Returns
    -------
    bool
        ``True`` if all invariants hold.

    Raises
    ------
    ValueError
        On the first invariant violation, with a descriptive message.
    TypeError
        If *G* is not a ``DiGraph``.
    """
    nx = _require_nx()
    if not isinstance(G, nx.DiGraph):
        raise TypeError(f"Expected nx.DiGraph, got {type(G).__name__}")

    for node in G.nodes:
        data = G.nodes[node]
        if "kind" not in data or "dim" not in data:
            raise ValueError(f"Node '{node}' missing 'kind' or 'dim' attribute")

        dim = data["dim"]
        out_deg = G.out_degree(node)
        successors = list(G.successors(node))

        if dim == 0:  # vertex
            if out_deg != 0:
                raise ValueError(
                    f"Vertex '{node}' has out-degree {out_deg}, expected 0"
                )

        elif dim == 1:  # edge
            if out_deg != 2:
                raise ValueError(
                    f"Edge '{node}' has out-degree {out_deg}, expected 2"
                )
            for s in successors:
                if G.nodes[s].get("dim") != 0:
                    raise ValueError(
                        f"Edge '{node}' boundary target '{s}' is not a vertex "
                        f"(dim={G.nodes[s].get('dim')})"
                    )

        elif dim == 2:  # face
            if out_deg != 3:
                raise ValueError(
                    f"Face '{node}' has out-degree {out_deg}, expected 3"
                )
            for s in successors:
                if G.nodes[s].get("dim") != 1:
                    raise ValueError(
                        f"Face '{node}' boundary target '{s}' is not an edge "
                        f"(dim={G.nodes[s].get('dim')})"
                    )
            # Closed-triangle: 3 edges must share exactly 3 distinct vertices
            face_vertices = set()
            for edge_node in successors:
                for v in G.successors(edge_node):
                    face_vertices.add(v)
            if len(face_vertices) != 3:
                raise ValueError(
                    f"Face '{node}' boundary edges span {len(face_vertices)} "
                    f"distinct vertices, expected 3 (closed triangle)"
                )

    return True


# ── Color mapping ──────────────────────────────────────────────────────────


def type_color_map(kc: "KnowledgeComplex") -> dict[str, str]:
    """Build a type-name to hex-color mapping from the schema's type registry.

    Uses matplotlib's ``tab10`` colormap (or ``tab20`` if > 10 types)
    for distinct, visually separable colors.

    Parameters
    ----------
    kc : KnowledgeComplex

    Returns
    -------
    dict[str, str]
        Mapping from type name to hex color string.
    """
    _, plt = _require_mpl()
    import matplotlib.colors as mcolors

    type_names = sorted(kc._schema._types.keys())
    cmap_name = "tab10" if len(type_names) <= 10 else "tab20"
    cmap = plt.get_cmap(cmap_name)

    colors = {}
    for i, name in enumerate(type_names):
        colors[name] = mcolors.to_hex(cmap(i % cmap.N))
    return colors


# ── Hasse diagram helpers ──────────────────────────────────────────────────


def _prepare_ax(ax, figsize):
    """Create or reuse a matplotlib Axes."""
    _, plt = _require_mpl()
    if ax is None:
        fig, ax = plt.subplots(1, 1, figsize=figsize)
    else:
        fig = ax.get_figure()
    return fig, ax


def _layout(G):
    """Choose a 2D layout for the graph (converts DiGraph to undirected)."""
    nx = _require_nx()
    if len(G) == 0:
        return {}
    undirected = G.to_undirected() if G.is_directed() else G
    try:
        return nx.kamada_kawai_layout(undirected)
    except Exception:
        return nx.spring_layout(undirected, seed=42)


# ── Hasse diagram plots ───────────────────────────────────────────────────


def plot_hasse(
    kc: "KnowledgeComplex",
    *,
    ax: Any = None,
    figsize: tuple[float, float] = (10, 8),
    with_labels: bool = True,
    node_size_by_dim: bool = True,
) -> tuple[Any, Any]:
    """Plot the Hasse diagram of the complex with type-based color coding.

    Every element (vertex, edge, face) is drawn as a node.  Directed arrows
    represent the boundary operator, pointing from each element to its
    boundary elements (higher dimension → lower dimension).  Nodes are colored
    by type and sized by dimension (vertices largest, faces smallest).

    This is **not** a geometric picture of the complex — it is the partially
    ordered set of simplices.  For a geometric view where vertices are points,
    edges are line segments, and faces are filled triangles, see
    :func:`plot_geometric`.

    Parameters
    ----------
    kc : KnowledgeComplex
    ax : matplotlib Axes, optional
        Axes to draw on. Created if not provided.
    figsize : tuple
        Figure size if creating a new figure.
    with_labels : bool
        Show element ID labels on nodes.
    node_size_by_dim : bool
        Scale node size by dimension (vertex=large, face=small).

    Returns
    -------
    (fig, ax)
        The matplotlib Figure and Axes.
    """
    nx = _require_nx()
    _, plt = _require_mpl()

    G = to_networkx(kc)
    fig, ax = _prepare_ax(ax, figsize)
    pos = _layout(G)
    colors = type_color_map(kc)

    if len(G) == 0:
        ax.set_title("Empty complex")
        ax.axis("off")
        return fig, ax

    node_colors = [colors.get(G.nodes[n].get("type", ""), "#999999") for n in G]
    if node_size_by_dim:
        node_sizes = [_SIZE_BY_DIM.get(G.nodes[n].get("dim", 0), 200) for n in G]
    else:
        node_sizes = 300

    nx.draw_networkx_edges(
        G, pos, ax=ax, edge_color="#cccccc", width=1.5,
        arrows=True, arrowstyle="-|>", arrowsize=12,
        connectionstyle="arc3,rad=0.05",
    )
    nx.draw_networkx_nodes(
        G, pos, ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="#333333",
        linewidths=0.5,
    )
    if with_labels:
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)

    # Legend
    from matplotlib.lines import Line2D
    legend_handles = []
    for type_name in sorted(colors):
        kind = kc._schema._types.get(type_name, {}).get("kind", "?")
        legend_handles.append(
            Line2D([0], [0], marker="o", color="w",
                   markerfacecolor=colors[type_name], markersize=10,
                   label=f"{type_name} ({kind})")
        )
    if legend_handles:
        ax.legend(handles=legend_handles, loc="best", fontsize=8)

    ax.set_title(f"Hasse Diagram: {kc._schema._namespace}")
    ax.axis("off")
    return fig, ax


def plot_hasse_star(
    kc: "KnowledgeComplex",
    id: str,
    *,
    ax: Any = None,
    figsize: tuple[float, float] = (10, 8),
    with_labels: bool = True,
) -> tuple[Any, Any]:
    """Plot the Hasse diagram with the star of an element highlighted.

    Elements in ``St(id)`` are drawn in full color with directed arrows;
    all other elements are dimmed to light gray.  This is the Hasse-diagram
    view — see :func:`plot_hasse` for details on what that means.

    Parameters
    ----------
    kc : KnowledgeComplex
    id : str
        Element whose star to highlight.
    ax : matplotlib Axes, optional
    figsize : tuple
    with_labels : bool

    Returns
    -------
    (fig, ax)
    """
    nx = _require_nx()
    _, plt = _require_mpl()

    G = to_networkx(kc)
    fig, ax = _prepare_ax(ax, figsize)
    pos = _layout(G)
    colors = type_color_map(kc)
    star_ids = kc.star(id)

    highlighted = [n for n in G if n in star_ids]
    dimmed = [n for n in G if n not in star_ids]

    if dimmed:
        nx.draw_networkx_nodes(
            G, pos, nodelist=dimmed, ax=ax,
            node_color="#dddddd", node_size=150,
            edgecolors="#cccccc", linewidths=0.5,
        )

    star_edges = [(u, v) for u, v in G.edges() if u in star_ids and v in star_ids]
    dim_edges = [(u, v) for u, v in G.edges() if (u, v) not in set(star_edges)]
    if dim_edges:
        nx.draw_networkx_edges(
            G, pos, edgelist=dim_edges, ax=ax, edge_color="#eeeeee", width=1.0,
            arrows=True, arrowstyle="-|>", arrowsize=8,
        )
    if star_edges:
        nx.draw_networkx_edges(
            G, pos, edgelist=star_edges, ax=ax, edge_color="#666666", width=2.0,
            arrows=True, arrowstyle="-|>", arrowsize=14,
        )

    if highlighted:
        h_colors = [colors.get(G.nodes[n].get("type", ""), "#999999") for n in highlighted]
        h_sizes = [_SIZE_BY_DIM.get(G.nodes[n].get("dim", 0), 200) for n in highlighted]
        nx.draw_networkx_nodes(
            G, pos, nodelist=highlighted, ax=ax,
            node_color=h_colors, node_size=h_sizes,
            edgecolors="#333333", linewidths=1.0,
        )

    if with_labels:
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)

    ax.set_title(f"Hasse Star({id})")
    ax.axis("off")
    return fig, ax


def plot_hasse_skeleton(
    kc: "KnowledgeComplex",
    k: int,
    *,
    ax: Any = None,
    figsize: tuple[float, float] = (10, 8),
    with_labels: bool = True,
) -> tuple[Any, Any]:
    """Plot the Hasse diagram of the k-skeleton only.

    Shows only elements of dimension ≤ k, with directed boundary arrows.
    This is the Hasse-diagram view — see :func:`plot_hasse` for details.

    k=0: vertices only, k=1: vertices + edges, k=2: everything.

    Parameters
    ----------
    kc : KnowledgeComplex
    k : int
        Maximum dimension (0, 1, or 2).
    ax : matplotlib Axes, optional
    figsize : tuple
    with_labels : bool

    Returns
    -------
    (fig, ax)
    """
    nx = _require_nx()
    _, plt = _require_mpl()

    G = to_networkx(kc)
    skel_ids = kc.skeleton(k)
    subG = G.subgraph(skel_ids).copy()

    fig, ax = _prepare_ax(ax, figsize)
    pos = _layout(subG)
    colors = type_color_map(kc)

    if len(subG) == 0:
        ax.set_title(f"Hasse Skeleton({k}) — empty")
        ax.axis("off")
        return fig, ax

    node_colors = [colors.get(subG.nodes[n].get("type", ""), "#999999") for n in subG]
    node_sizes = [_SIZE_BY_DIM.get(subG.nodes[n].get("dim", 0), 200) for n in subG]

    nx.draw_networkx_edges(
        subG, pos, ax=ax, edge_color="#cccccc", width=1.5,
        arrows=True, arrowstyle="-|>", arrowsize=12,
    )
    nx.draw_networkx_nodes(
        subG, pos, ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="#333333",
        linewidths=0.5,
    )
    if with_labels:
        nx.draw_networkx_labels(subG, pos, ax=ax, font_size=8)

    ax.set_title(f"Hasse Skeleton({k})")
    ax.axis("off")
    return fig, ax


# ── Deprecated aliases ─────────────────────────────────────────────────────


def plot_complex(kc, **kwargs):
    """Deprecated: use :func:`plot_hasse` instead."""
    warnings.warn("plot_complex is deprecated, use plot_hasse", DeprecationWarning, stacklevel=2)
    return plot_hasse(kc, **kwargs)


def plot_star(kc, id, **kwargs):
    """Deprecated: use :func:`plot_hasse_star` instead."""
    warnings.warn("plot_star is deprecated, use plot_hasse_star", DeprecationWarning, stacklevel=2)
    return plot_hasse_star(kc, id, **kwargs)


def plot_skeleton(kc, k, **kwargs):
    """Deprecated: use :func:`plot_hasse_skeleton` instead."""
    warnings.warn("plot_skeleton is deprecated, use plot_hasse_skeleton", DeprecationWarning, stacklevel=2)
    return plot_hasse_skeleton(kc, k, **kwargs)


# ── Geometric realization helpers ──────────────────────────────────────────


def _face_vertices(kc: "KnowledgeComplex", face_id: str) -> list[str]:
    """Get the 3 vertices of a face by walking boundary twice.

    boundary(face) → 3 edges → boundary(each edge) → deduplicate → 3 vertices.
    """
    verts: set[str] = set()
    for edge_id in kc.boundary(face_id):
        verts |= kc.boundary(edge_id)
    return sorted(verts)


def _vertex_positions_3d(
    kc: "KnowledgeComplex",
) -> dict[str, tuple[float, float, float]]:
    """Compute 3D positions for KC vertices using force-directed layout.

    Builds a networkx graph of only KC vertices, with an edge between
    vertices that share a KC edge, then runs spring_layout in 3D.
    """
    nx = _require_nx()
    G = nx.Graph()

    # Add vertex nodes
    vertex_ids = list(kc.skeleton(0))
    for vid in vertex_ids:
        G.add_node(vid)

    # Connect vertices that share a KC edge
    edge_ids = kc.skeleton(1) - kc.skeleton(0)
    for eid in edge_ids:
        boundary = list(kc.boundary(eid))
        if len(boundary) == 2:
            G.add_edge(boundary[0], boundary[1])

    if len(G) == 0:
        return {}

    pos = nx.spring_layout(G, dim=3, seed=42)
    return {vid: tuple(pos[vid]) for vid in pos}


# ── Geometric realization: matplotlib ──────────────────────────────────────


def plot_geometric(
    kc: "KnowledgeComplex",
    *,
    ax: Any = None,
    figsize: tuple[float, float] = (10, 8),
    with_labels: bool = True,
) -> tuple[Any, Any]:
    """Plot the geometric realization of the complex in 3D.

    KC vertices become points in 3D space (positioned by force-directed
    layout).  KC edges become line segments connecting their two boundary
    vertices.  KC faces become filled, semi-transparent triangular patches
    spanning their three boundary vertices.

    This is the classical geometric realization — the view a topologist
    would draw.  For the Hasse diagram where every element is a node and
    boundary relations are directed edges, see :func:`plot_hasse`.

    Parameters
    ----------
    kc : KnowledgeComplex
    ax : matplotlib Axes3D, optional
        A 3D axes to draw on.  Created if not provided.
    figsize : tuple
        Figure size if creating a new figure.
    with_labels : bool
        Show vertex ID labels.

    Returns
    -------
    (fig, ax)
        The matplotlib Figure and Axes3D.
    """
    _, plt = _require_mpl()
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection

    colors = type_color_map(kc)
    pos = _vertex_positions_3d(kc)

    if ax is None:
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111, projection="3d")
    else:
        fig = ax.get_figure()

    if not pos:
        ax.set_title("Empty complex")
        return fig, ax

    # Draw faces as filled triangles
    face_ids = kc.skeleton(2) - kc.skeleton(1)
    for fid in face_ids:
        verts = _face_vertices(kc, fid)
        if len(verts) == 3 and all(v in pos for v in verts):
            tri = [pos[v] for v in verts]
            face_type = kc.element(fid).type
            color = colors.get(face_type, "#999999")
            poly = Poly3DCollection([tri], alpha=0.25, facecolor=color,
                                    edgecolor=color, linewidths=0.5)
            ax.add_collection3d(poly)

    # Draw edges as line segments
    edge_ids = kc.skeleton(1) - kc.skeleton(0)
    for eid in edge_ids:
        boundary = list(kc.boundary(eid))
        if len(boundary) == 2 and all(v in pos for v in boundary):
            p0, p1 = pos[boundary[0]], pos[boundary[1]]
            edge_type = kc.element(eid).type
            color = colors.get(edge_type, "#999999")
            ax.plot3D(
                [p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]],
                color=color, linewidth=2,
            )

    # Draw vertices as scatter points
    vertex_ids = list(kc.skeleton(0))
    for vid in vertex_ids:
        if vid in pos:
            x, y, z = pos[vid]
            vtype = kc.element(vid).type
            color = colors.get(vtype, "#999999")
            ax.scatter3D(x, y, z, color=color, s=80, edgecolors="#333333",
                         linewidths=0.5, zorder=5, depthshade=False)

    # Labels
    if with_labels:
        for vid in vertex_ids:
            if vid in pos:
                x, y, z = pos[vid]
                ax.text(x, y, z, f"  {vid}", fontsize=7)

    # Legend
    from matplotlib.lines import Line2D
    legend_handles = []
    for type_name in sorted(colors):
        kind = kc._schema._types.get(type_name, {}).get("kind", "?")
        legend_handles.append(
            Line2D([0], [0], marker="o", color="w",
                   markerfacecolor=colors[type_name], markersize=8,
                   label=f"{type_name} ({kind})")
        )
    if legend_handles:
        ax.legend(handles=legend_handles, loc="best", fontsize=7)

    ax.set_title(f"Geometric Realization: {kc._schema._namespace}")
    return fig, ax


# ── Geometric realization: plotly ──────────────────────────────────────────


def plot_geometric_interactive(
    kc: "KnowledgeComplex",
) -> Any:
    """Plot an interactive 3D geometric realization of the complex.

    Same geometry as :func:`plot_geometric` — KC vertices are points, KC edges
    are line segments, KC faces are filled triangles — but rendered with
    Plotly for interactive rotation, zoom, and hover inspection.

    Requires plotly::

        pip install knowledgecomplex[viz-interactive]

    Parameters
    ----------
    kc : KnowledgeComplex

    Returns
    -------
    plotly.graph_objects.Figure
        Call ``.show()`` to display or ``.write_html("file.html")`` to save.
    """
    go = _require_plotly()

    colors = type_color_map(kc)
    pos = _vertex_positions_3d(kc)
    fig = go.Figure()

    if not pos:
        fig.update_layout(title="Empty complex")
        return fig

    # Faces as Mesh3d triangles
    face_ids = kc.skeleton(2) - kc.skeleton(1)
    for fid in face_ids:
        verts = _face_vertices(kc, fid)
        if len(verts) == 3 and all(v in pos for v in verts):
            xs = [pos[v][0] for v in verts]
            ys = [pos[v][1] for v in verts]
            zs = [pos[v][2] for v in verts]
            face_type = kc.element(fid).type
            color = colors.get(face_type, "#999999")
            fig.add_trace(go.Mesh3d(
                x=xs, y=ys, z=zs,
                i=[0], j=[1], k=[2],
                color=color, opacity=0.3,
                hoverinfo="text",
                hovertext=f"{fid} ({face_type})",
                showlegend=False,
            ))

    # Edges as line segments
    edge_ids = kc.skeleton(1) - kc.skeleton(0)
    for eid in edge_ids:
        boundary = list(kc.boundary(eid))
        if len(boundary) == 2 and all(v in pos for v in boundary):
            p0, p1 = pos[boundary[0]], pos[boundary[1]]
            edge_type = kc.element(eid).type
            color = colors.get(edge_type, "#999999")
            fig.add_trace(go.Scatter3d(
                x=[p0[0], p1[0]], y=[p0[1], p1[1]], z=[p0[2], p1[2]],
                mode="lines",
                line=dict(color=color, width=4),
                hoverinfo="text",
                hovertext=f"{eid} ({edge_type})",
                showlegend=False,
            ))

    # Vertices as markers
    vertex_ids = [v for v in kc.skeleton(0) if v in pos]
    xs = [pos[v][0] for v in vertex_ids]
    ys = [pos[v][1] for v in vertex_ids]
    zs = [pos[v][2] for v in vertex_ids]
    vtypes = [kc.element(v).type for v in vertex_ids]
    vcolors = [colors.get(t, "#999999") for t in vtypes]
    hover = [f"{vid} ({vt})" for vid, vt in zip(vertex_ids, vtypes)]

    fig.add_trace(go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers+text",
        marker=dict(size=6, color=vcolors, line=dict(width=1, color="#333333")),
        text=vertex_ids,
        textposition="top center",
        textfont=dict(size=8),
        hoverinfo="text",
        hovertext=hover,
        showlegend=False,
    ))

    fig.update_layout(
        title=f"Geometric Realization: {kc._schema._namespace}",
        scene=dict(
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            zaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
        ),
        showlegend=False,
    )
    return fig
