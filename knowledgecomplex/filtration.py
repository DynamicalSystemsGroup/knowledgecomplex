"""
knowledgecomplex.filtration — Filtrations over knowledge complexes.

A filtration F = (C₀, C₁, …, Cₘ) is a nested sequence of subcomplexes
where each Cₚ is a valid simplicial complex (closed under boundary) and
Cₚ₋₁ ⊆ Cₚ. Filtrations are semantics-agnostic — they could represent
temporal evolution, thematic layers, trust levels, or any ordering.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from knowledgecomplex.graph import KnowledgeComplex


class Filtration:
    """
    An indexed sequence of nested subcomplexes over a KnowledgeComplex.

    Each step is a valid subcomplex (closed under boundary) and each step
    contains all elements from the previous step (monotone nesting).

    Parameters
    ----------
    kc : KnowledgeComplex
        The parent complex that this filtration is defined over.

    Example
    -------
    >>> filt = Filtration(kc)
    >>> filt.append({"v1"})
    >>> filt.append({"v1", "v2", "e12"})
    >>> filt.append({"v1", "v2", "v3", "e12", "e23", "e13", "f123"})
    >>> len(filt)
    3
    >>> filt.birth("e12")
    1
    """

    def __init__(self, kc: "KnowledgeComplex") -> None:
        self._kc = kc
        self._steps: list[frozenset[str]] = []

    @property
    def complex(self) -> "KnowledgeComplex":
        """The parent KnowledgeComplex."""
        return self._kc

    @property
    def length(self) -> int:
        """Number of steps in the filtration."""
        return len(self._steps)

    @property
    def is_complete(self) -> bool:
        """True if the last step contains all elements in the complex."""
        if not self._steps:
            return False
        all_ids = set(self._kc.element_ids())
        return set(self._steps[-1]) == all_ids

    def append(self, ids: set[str]) -> "Filtration":
        """
        Append a subcomplex to the filtration.

        Parameters
        ----------
        ids : set[str]
            Element IDs forming the next step. Must be a valid subcomplex
            and a superset of the previous step.

        Returns
        -------
        Filtration (self, for chaining)

        Raises
        ------
        ValueError
            If ids is not a valid subcomplex or violates monotonicity.
        """
        ids_set = set(ids)

        if not self._kc.is_subcomplex(ids_set):
            raise ValueError(
                "Cannot append: the given element set is not a valid subcomplex "
                "(not closed under boundary)"
            )

        if self._steps and not ids_set >= set(self._steps[-1]):
            raise ValueError(
                "Cannot append: monotone nesting violated — new step must be "
                "a superset of the previous step"
            )

        self._steps.append(frozenset(ids_set))
        return self

    def append_closure(self, ids: set[str]) -> "Filtration":
        """
        Append the closure of a set of elements, unioned with the previous step.

        Takes the closure of ids (ensuring a valid subcomplex), unions it
        with the previous step (ensuring monotonicity), and appends.

        Parameters
        ----------
        ids : set[str]
            Element IDs to close over.

        Returns
        -------
        Filtration (self, for chaining)
        """
        closed = self._kc.closure(ids)
        if self._steps:
            closed = closed | set(self._steps[-1])
        self._steps.append(frozenset(closed))
        return self

    @classmethod
    def from_function(
        cls,
        kc: "KnowledgeComplex",
        fn: Callable[[str], int | float],
    ) -> "Filtration":
        """
        Build a filtration by grouping elements by a function value.

        Calls fn(id) for every element in the complex, groups by return
        value, sorts groups, and builds closure at each cumulative step.

        Parameters
        ----------
        kc : KnowledgeComplex
            The parent complex.
        fn : Callable[[str], int | float]
            Function mapping element IDs to filtration values.

        Returns
        -------
        Filtration
        """
        all_ids = kc.element_ids()
        groups: dict[int | float, list[str]] = defaultdict(list)
        for eid in all_ids:
            groups[fn(eid)].append(eid)

        filt = cls(kc)
        accumulated: set[str] = set()
        for key in sorted(groups.keys()):
            accumulated = accumulated | set(groups[key])
            closed = kc.closure(accumulated)
            filt._steps.append(frozenset(closed))

        return filt

    def __getitem__(self, index: int) -> set[str]:
        return set(self._steps[index])

    def __len__(self) -> int:
        return len(self._steps)

    def __iter__(self) -> Iterator[set[str]]:
        for step in self._steps:
            yield set(step)

    def birth(self, id: str) -> int:
        """
        Return the index of the first step containing this element.

        Parameters
        ----------
        id : str
            Element identifier.

        Returns
        -------
        int

        Raises
        ------
        ValueError
            If the element does not appear in any step.
        """
        for i, step in enumerate(self._steps):
            if id in step:
                return i
        raise ValueError(f"Element '{id}' not found in any filtration step")

    def new_at(self, index: int) -> set[str]:
        """
        Return elements added at step index (Cₚ \\ Cₚ₋₁).

        Parameters
        ----------
        index : int
            Step index.

        Returns
        -------
        set[str]
        """
        current = set(self._steps[index])
        if index == 0:
            return current
        return current - set(self._steps[index - 1])

    def elements_at(self, index: int) -> set[str]:
        """
        Return all elements at step index (same as self[index]).

        Parameters
        ----------
        index : int
            Step index.

        Returns
        -------
        set[str]
        """
        return set(self._steps[index])
