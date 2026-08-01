"""
parallel.py
Order-preserving parallel map, shared by any pipeline step that processes
independent per-file work (inventory.py, profiler.py, pipeline.py's blocks
step).
"""

from concurrent.futures import ProcessPoolExecutor


def pmap(func, arg_tuples, workers):
    """
    Order-preserving map: func(*args) for each args in arg_tuples.

    workers <= 1 -> sequential, in the current process (plain generator —
    the exact same code path as the parallel branch, just without a pool).
    workers > 1  -> ProcessPoolExecutor.

    Generator: results are yielded in input order as soon as each one is
    ready, not after the whole batch completes — callers can act on each
    result incrementally (e.g. profiler.py writes each file's audit CSV as
    soon as it's available, without waiting for the rest).

    `func` must be a module-level, top-level function (not a closure or
    bound method) — it has to be picklable to cross into worker processes.
    """
    if not arg_tuples:
        return
    if workers <= 1:
        for args in arg_tuples:
            yield func(*args)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(func, *zip(*arg_tuples))
