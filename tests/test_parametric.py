"""
tests/test_parametric.py

Tests for ParametricSequence: parameterized subcomplex slicing.
"""

import pytest

from knowledgecomplex.schema import SchemaBuilder, vocab, text
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.parametric import ParametricSequence


@pytest.fixture
def temporal_kc() -> KnowledgeComplex:
    """People joining/leaving over quarters Q1-Q4."""
    sb = SchemaBuilder(namespace="proj")
    sb.add_vertex_type("Person", attributes={
        "active_from": text(),
        "active_until": text(),
    })
    sb.add_edge_type("WorksWith", attributes={
        "active_from": text(),
        "active_until": text(),
    })
    sb.add_face_type("Squad")

    kc = KnowledgeComplex(schema=sb)
    kc.add_vertex("alice", type="Person", active_from="1", active_until="9999")
    kc.add_vertex("bob",   type="Person", active_from="1", active_until="3")
    kc.add_vertex("carol", type="Person", active_from="2", active_until="9999")
    kc.add_vertex("dave",  type="Person", active_from="3", active_until="9999")

    kc.add_edge("w-ab", type="WorksWith", vertices={"alice", "bob"},
                active_from="1", active_until="3")
    kc.add_edge("w-ac", type="WorksWith", vertices={"alice", "carol"},
                active_from="2", active_until="9999")
    kc.add_edge("w-cd", type="WorksWith", vertices={"carol", "dave"},
                active_from="3", active_until="9999")
    kc.add_edge("w-ad", type="WorksWith", vertices={"alice", "dave"},
                active_from="3", active_until="9999")

    kc.add_face("squad-1", type="Squad", boundary=["w-ac", "w-cd", "w-ad"])
    return kc


def _temporal_filter(elem, t):
    af = elem.attrs.get("active_from", "0")
    au = elem.attrs.get("active_until", "9999")
    return af <= t < au


@pytest.fixture
def seq(temporal_kc) -> ParametricSequence:
    return ParametricSequence(
        temporal_kc,
        values=["1", "2", "3", "4"],
        filter=_temporal_filter,
    )


# ===========================================================================
# Indexing
# ===========================================================================

class TestIndexing:

    def test_getitem_int(self, seq):
        step0 = seq[0]
        assert isinstance(step0, set)
        assert "alice" in step0

    def test_getitem_value(self, seq):
        step = seq["2"]
        assert "carol" in step

    def test_getitem_value_matches_int(self, seq):
        assert seq["2"] == seq[1]

    def test_getitem_invalid_value(self, seq):
        with pytest.raises(KeyError):
            seq["99"]

    def test_len(self, seq):
        assert len(seq) == 4


# ===========================================================================
# Iteration
# ===========================================================================

class TestIteration:

    def test_yields_value_and_set(self, seq):
        items = list(seq)
        assert len(items) == 4
        for value, ids in items:
            assert isinstance(value, str)
            assert isinstance(ids, set)

    def test_first_value(self, seq):
        value, ids = list(seq)[0]
        assert value == "1"
        assert "alice" in ids


# ===========================================================================
# Birth / death / active_at
# ===========================================================================

class TestLifecycle:

    def test_birth(self, seq):
        assert seq.birth("alice") == "1"
        assert seq.birth("carol") == "2"
        assert seq.birth("dave") == "3"

    def test_birth_nonexistent(self, seq):
        with pytest.raises(ValueError):
            seq.birth("ghost")

    def test_death(self, seq):
        assert seq.death("bob") == "3"

    def test_death_never_dies(self, seq):
        assert seq.death("alice") is None

    def test_death_never_appears(self, seq):
        assert seq.death("ghost") is None

    def test_active_at(self, seq):
        active = seq.active_at("bob")
        assert "1" in active
        assert "2" in active
        assert "3" not in active


# ===========================================================================
# new_at / removed_at
# ===========================================================================

class TestDelta:

    def test_new_at_first_step(self, seq):
        new = seq.new_at(0)
        assert "alice" in new
        assert "bob" in new

    def test_new_at_second_step(self, seq):
        new = seq.new_at(1)
        assert "carol" in new
        assert "alice" not in new  # already present

    def test_removed_at_first_step(self, seq):
        assert seq.removed_at(0) == set()

    def test_removed_at_bob_leaves(self, seq):
        # bob active_until="3", so at step index 2 (value="3") he's gone
        removed = seq.removed_at(2)
        assert "bob" in removed


# ===========================================================================
# Subcomplex and monotonicity
# ===========================================================================

class TestStructure:

    def test_subcomplex_at_invalid(self, seq):
        """Step 0 includes squad-1 (no temporal attrs) but not its boundary edges — not a subcomplex."""
        assert seq.subcomplex_at(0) is False

    def test_subcomplex_at_valid(self, temporal_kc):
        """A filter that only includes elements with explicit temporal attrs gives valid subcomplexes."""
        def strict_filter(elem, t):
            af = elem.attrs.get("active_from")
            au = elem.attrs.get("active_until")
            if af is None or au is None:
                return False
            return af <= t < au

        seq = ParametricSequence(temporal_kc, values=["1", "2", "3"], filter=strict_filter)
        # Step 0: alice, bob, w-ab — edges + their vertices = valid
        assert seq.subcomplex_at(0) is True

    def test_not_monotone(self, seq):
        """Temporal sequence is NOT monotone (bob leaves)."""
        assert seq.is_monotone is False

    def test_monotone_sequence(self, temporal_kc):
        """A filter that only adds elements is monotone."""
        def cumulative(elem, t):
            af = elem.attrs.get("active_from", "0")
            return af <= t

        mono_seq = ParametricSequence(
            temporal_kc, values=["1", "2", "3", "4"],
            filter=cumulative,
        )
        assert mono_seq.is_monotone is True


# ===========================================================================
# Properties and repr
# ===========================================================================

class TestProperties:

    def test_complex_reference(self, seq, temporal_kc):
        assert seq.complex is temporal_kc

    def test_values(self, seq):
        assert seq.values == ["1", "2", "3", "4"]

    def test_repr(self, seq):
        r = repr(seq)
        assert "ParametricSequence" in r
        assert "steps=4" in r
