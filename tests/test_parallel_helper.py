"""
test_parallel_helper.py
Tests for forti4d.lib.parallel.pmap: order preservation even when tasks
finish out of order, sequential/parallel parity, and exception propagation.

Helper functions are module-level (not closures) — ProcessPoolExecutor
requires picklable callables.
"""

from __future__ import annotations

import time

import pytest

from forti4d.lib.parallel import pmap


def _sleep_then_return(delay, value):
    time.sleep(delay)
    return value


def _square(x):
    return x * x


def _raise_if_negative(x):
    if x < 0:
        raise ValueError(f"negative: {x}")
    return x


def test_pmap_preserves_order_even_when_tasks_finish_out_of_order():
    # First task sleeps longest — if pmap returned completion order instead
    # of input order, this would come back as ["c", "b", "a"].
    arg_tuples = [(0.3, "a"), (0.15, "b"), (0.0, "c")]
    assert list(pmap(_sleep_then_return, arg_tuples, workers=3)) == ["a", "b", "c"]


def test_pmap_sequential_matches_parallel():
    arg_tuples = [(x,) for x in range(10)]
    sequential = list(pmap(_square, arg_tuples, workers=1))
    parallel = list(pmap(_square, arg_tuples, workers=3))
    assert sequential == parallel == [x * x for x in range(10)]


def test_pmap_empty_input():
    assert list(pmap(_square, [], workers=1)) == []
    assert list(pmap(_square, [], workers=3)) == []


@pytest.mark.parametrize("workers", [1, 3])
def test_pmap_propagates_exceptions(workers):
    arg_tuples = [(1,), (-1,), (2,)]
    with pytest.raises(ValueError, match="negative"):
        list(pmap(_raise_if_negative, arg_tuples, workers=workers))
