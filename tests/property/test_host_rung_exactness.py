"""Property tier — the conditional honesty rule of the offered arm.

The dual allocation contract's honesty property is *conditional* (design §3):
not "declared acceptance must visibly change output" but *when passed integer
`H`, the returned Block has exactly `H` rows* (law 5, property-testable). This
generalizes the example cases in the integration tier over all non-negative
offers:

  * a conforming height renderer's result (exactly `H` rows) passes the
    `_verify_height` check for every `H >= 0`, including `H = 0`;
  * any Block whose height differs from the offer raises `ContractError` — the
    host never crops or pads into apparent compliance (§5).

`_verify_height` is the offer-site helper later slices call; here it is exercised
directly, since no shipped S1 path offers an integer `H` yet.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

import pytest

from painted.cli.runner import CliRunner
from painted.core.block import Block
from painted.core.errors import ContractError


@given(height=st.integers(min_value=0, max_value=200))
def test_conforming_result_passes_the_exactness_check(height: int) -> None:
    """For arbitrary H >= 0, an exactly-H-row Block satisfies the offer — no
    raise. H=0 (Block.empty(w, 0)) is a valid offer, evidence-waived (§5)."""
    block = Block.empty(4, height)
    assert block.height == height
    CliRunner._verify_height(block, height)  # must not raise


@given(
    height=st.integers(min_value=0, max_value=200),
    actual=st.integers(min_value=0, max_value=200),
)
def test_any_height_mismatch_faults(height: int, actual: int) -> None:
    """Whenever the returned height differs from the offer, `_verify_height`
    faults `ContractError` — the host never silently reconciles the two."""
    if actual == height:
        # The conforming case — covered by the sibling property; exactness holds.
        CliRunner._verify_height(Block.empty(4, actual), height)
        return
    with pytest.raises(ContractError):
        CliRunner._verify_height(Block.empty(4, actual), height)


@given(height=st.integers(min_value=0, max_value=200))
def test_none_offer_is_always_the_omitted_arm(height: int) -> None:
    """A `height=None` offer is natural sizing — no exactness check for any
    natural content height (§5, the omitted arm)."""
    CliRunner._verify_height(Block.empty(4, height), None)  # must not raise
