"""
knowledgecomplex.parametric — Parametric sequences over knowledge complexes.

A ParametricSequence represents a single complex viewed through a
parameterized filter. Each parameter value selects a subcomplex —
the sequence of subcomplexes can grow, shrink, or change arbitrarily
as the parameter varies.

Unlike :class:`~knowledgecomplex.filtration.Filtration`, which enforces
monotone nesting, a ParametricSequence is observational — it computes
slices lazily from a filter function.
"""

from __future__ import annotations
from typing import Any, Callable, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex, Element


class ParametricSequence:
    """
    A complex viewed through a parameterized filter.

    One complex holds all elements. A filter function decides which
    elements are active at each parameter value. The result is a
    sequence of subcomplexes indexed by parameter values.

    Parameters
    ----------
    kc : KnowledgeComplex
        The complex containing all elements.
    values : list
        Ordered parameter values (e.g. ``["Q1", "Q2", "Q3", "Q4"]``).
    filter : Callable[[Element, value], bool]
        Returns True if the element is active at the given parameter value.

    Example
    -------
    >>> seq = ParametricSequence(kc, values=["1","2","3","4"],
    ...     filter=lambda elem, t: elem.attrs.get("active_from","0") <= t)
    >>> seq[0]              # element IDs active at "1"
    >>> seq.birth("carol")  # first value where carol appears
    """

    def __init__(
        self,
        kc: "KnowledgeComplex",
        values: list,
        filter: Callable[["Element", Any], bool],
    ) -> None:
        self._kc = kc
        self._values = list(values)
        self._filter = filter
        self._cache: dict[int, frozenset[str]] = {}

    def _compute(self, index: int) -> frozenset[str]:
        """Compute and cache the element set at a given index."""
        if index not in self._cache:
            value = self._values[index]
            ids = frozenset(
                eid for eid in self._kc.element_ids()
                if self._filter(self._kc.element(eid), value)
            )
            self._cache[index] = ids
        return self._cache[index]

    def __repr__(self) -> str:
        return f"ParametricSequence(steps={len(self._values)}, monotone={self.is_monotone})"

    # --- Indexing ---

    def __getitem__(self, key: int | Any) -> set[str]:
        if isinstance(key, int):
            return set(self._compute(key))
        # Try to look up by parameter value
        try:
            index = self._values.index(key)
        except ValueError:
            raise KeyError(f"Parameter value {key!r} not in values list")
        return set(self._compute(index))

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[tuple[Any, set[str]]]:
        for i, value in enumerate(self._values):
            yield value, set(self._compute(i))

    # --- Properties ---

    @property
    def complex(self) -> "KnowledgeComplex":
        """The parent KnowledgeComplex."""
        return self._kc

    @property
    def values(self) -> list:
        """The ordered parameter values."""
        return list(self._values)

    @property
    def is_monotone(self) -> bool:
        """True if every step is a superset of the previous (filtration-like)."""
        for i in range(1, len(self._values)):
            if not (self._compute(i - 1) <= self._compute(i)):
                return False
        return True

    # --- Queries ---

    def birth(self, element_id: str) -> Any:
        """Return the first parameter value where the element appears.

        Raises
        ------
        ValueError
            If the element does not appear at any parameter value.
        """
        for i, value in enumerate(self._values):
            if element_id in self._compute(i):
                return value
        raise ValueError(f"Element '{element_id}' not found at any parameter value")

    def death(self, element_id: str) -> Any | None:
        """Return the first parameter value where the element disappears.

        Returns None if the element is present at all values after its birth,
        or if it never appears.
        """
        appeared = False
        for i in range(len(self._values)):
            present = element_id in self._compute(i)
            if present:
                appeared = True
            elif appeared:
                return self._values[i]
        return None

    def active_at(self, element_id: str) -> list:
        """Return the list of parameter values where the element is present."""
        return [
            self._values[i]
            for i in range(len(self._values))
            if element_id in self._compute(i)
        ]

    def new_at(self, index: int) -> set[str]:
        """Return elements appearing at step index that were not in step index-1."""
        current = self._compute(index)
        if index == 0:
            return set(current)
        previous = self._compute(index - 1)
        return set(current - previous)

    def removed_at(self, index: int) -> set[str]:
        """Return elements present at step index-1 that are absent at step index."""
        if index == 0:
            return set()
        current = self._compute(index)
        previous = self._compute(index - 1)
        return set(previous - current)

    def subcomplex_at(self, index: int) -> bool:
        """Check if the slice at index is a valid subcomplex (closed under boundary)."""
        return self._kc.is_subcomplex(set(self._compute(index)))
