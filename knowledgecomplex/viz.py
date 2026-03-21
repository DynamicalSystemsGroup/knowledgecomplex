"""knowledgecomplex.viz — NetworkX export and matplotlib visualization helpers.

Quality-of-life inspection tools for visualizing knowledge complexes.
Type-based color coding makes it easy to spot structural patterns at a glance.

Requires optional dependencies::

    pip install knowledgecomplex[viz]

Functions
---------
to_networkx       Convert a KnowledgeComplex to a networkx Graph.
type_color_map    Build a type-name → hex-color mapping.
plot_complex      Plot the full complex with type-based coloring.
plot_star         Plot with a specific element's star highlighted.
plot_skeleton     Plot only the k-skeleton.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex

_DIM_BY_KIND = {"vertex": 0, "edge": 1, "face": 2}
_SIZE_BY_DIM = {0: 400, 1: 200, 2: 100}

_INSTALL_HINT = (
    "networkx and matplotlib are required for visualization.\n"
    "Install them with:  pip install knowledgecomplex[viz]"
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


# ── NetworkX export ─────────────────────────────────────────────────────────


def to_networkx(kc: "KnowledgeComplex") -> Any:
    """Convert a KnowledgeComplex to a networkx Graph.

    Nodes represent elements (vertices, edges, faces). NetworkX edges
    represent ``kc:boundedBy`` relations (e.g. an KC edge node connects
    to its two KC vertex nodes).

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
    networkx.Graph
    """
    nx = _require_nx()
    G = nx.Graph(name=kc._schema._namespace)

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

    # Add boundary edges
    for elem_id in kc.element_ids():
        for boundary_id in kc.boundary(elem_id):
            G.add_edge(elem_id, boundary_id)

    return G


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


# ── Plot helpers ────────────────────────────────────────────────────────────


def _prepare_ax(ax, figsize):
    """Create or reuse a matplotlib Axes."""
    _, plt = _require_mpl()
    if ax is None:
        fig, ax = plt.subplots(1, 1, figsize=figsize)
    else:
        fig = ax.get_figure()
    return fig, ax


def _layout(G):
    """Choose a layout for the graph."""
    nx = _require_nx()
    if len(G) == 0:
        return {}
    try:
        return nx.kamada_kawai_layout(G)
    except Exception:
        return nx.spring_layout(G, seed=42)


def plot_complex(
    kc: "KnowledgeComplex",
    *,
    ax: Any = None,
    figsize: tuple[float, float] = (10, 8),
    with_labels: bool = True,
    node_size_by_dim: bool = True,
) -> tuple[Any, Any]:
    """Plot the full complex with type-based color coding.

    Nodes are colored by type and sized by dimension (vertices largest,
    faces smallest). A legend maps colors to type names.

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

    nx.draw_networkx_edges(G, pos, ax=ax, edge_color="#cccccc", width=1.5)
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

    ax.set_title(f"Knowledge Complex: {kc._schema._namespace}")
    ax.axis("off")
    return fig, ax


def plot_star(
    kc: "KnowledgeComplex",
    id: str,
    *,
    ax: Any = None,
    figsize: tuple[float, float] = (10, 8),
    with_labels: bool = True,
) -> tuple[Any, Any]:
    """Plot the complex with the star of an element highlighted.

    Elements in ``St(id)`` are drawn in full color; all other elements
    are dimmed to light gray.

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

    # Split nodes into highlighted and dimmed
    highlighted = [n for n in G if n in star_ids]
    dimmed = [n for n in G if n not in star_ids]

    # Draw dimmed first
    if dimmed:
        nx.draw_networkx_nodes(
            G, pos, nodelist=dimmed, ax=ax,
            node_color="#dddddd", node_size=150,
            edgecolors="#cccccc", linewidths=0.5,
        )

    # Draw edges: highlighted if both endpoints in star, else dimmed
    star_edges = [(u, v) for u, v in G.edges() if u in star_ids and v in star_ids]
    dim_edges = [(u, v) for u, v in G.edges() if (u, v) not in star_edges]
    if dim_edges:
        nx.draw_networkx_edges(G, pos, edgelist=dim_edges, ax=ax, edge_color="#eeeeee", width=1.0)
    if star_edges:
        nx.draw_networkx_edges(G, pos, edgelist=star_edges, ax=ax, edge_color="#666666", width=2.0)

    # Draw highlighted nodes
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

    ax.set_title(f"Star({id})")
    ax.axis("off")
    return fig, ax


def plot_skeleton(
    kc: "KnowledgeComplex",
    k: int,
    *,
    ax: Any = None,
    figsize: tuple[float, float] = (10, 8),
    with_labels: bool = True,
) -> tuple[Any, Any]:
    """Plot only the k-skeleton of the complex.

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
        ax.set_title(f"Skeleton({k}) — empty")
        ax.axis("off")
        return fig, ax

    node_colors = [colors.get(subG.nodes[n].get("type", ""), "#999999") for n in subG]
    node_sizes = [_SIZE_BY_DIM.get(subG.nodes[n].get("dim", 0), 200) for n in subG]

    nx.draw_networkx_edges(subG, pos, ax=ax, edge_color="#cccccc", width=1.5)
    nx.draw_networkx_nodes(
        subG, pos, ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="#333333",
        linewidths=0.5,
    )
    if with_labels:
        nx.draw_networkx_labels(subG, pos, ax=ax, font_size=8)

    ax.set_title(f"Skeleton({k})")
    ax.axis("off")
    return fig, ax
