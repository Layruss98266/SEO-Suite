"""Shared concurrency helper for audit phases.

Extracted to remove duplicated ThreadPoolExecutor boilerplate across
``app/blueprints/audit.py``, ``core/seo_audit.py``, ``tools/quick_tools.py``
and other call sites that need fan-out / collect over a list of work units.

See AUDIT_LOG.md C14.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable, Sequence


def run_fns_parallel(
    fns: Sequence[Callable[[], Any]],
    max_workers: int = 8,
) -> list[Any]:
    """Run a sequence of zero-arg callables in parallel.

    Returns results in *submitted* order (matches the input list). Callers that
    need fault isolation should wrap each fn themselves or use ``_collect`` in
    ``core.seo_audit``; this helper deliberately propagates exceptions from
    ``fut.result()`` to preserve existing semantics at sites that rely on it.
    """
    if not fns:
        return []
    workers = min(len(fns), max(1, max_workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futs]


def run_phase(
    items: Sequence[Any],
    work_fn: Callable[[Any], Any],
    max_workers: int = 8,
    *,
    preserve_order: bool = True,
) -> list[Any]:
    """Fan ``work_fn`` over ``items`` in parallel and collect results.

    ``preserve_order=True``  → results match the order of ``items``.
    ``preserve_order=False`` → results come in completion order (use when
    individual call latency varies and order doesn't matter downstream).
    """
    if not items:
        return []
    workers = min(len(items), max(1, max_workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work_fn, item) for item in items]
        if preserve_order:
            return [f.result() for f in futs]
        return [f.result() for f in as_completed(futs)]


def submit_and_collect(
    ex: ThreadPoolExecutor,
    fns: Iterable[Callable[[], Any]],
) -> list[Any]:
    """Submit zero-arg fns to an existing executor and return results in order.

    Useful when the caller already owns the executor (mixed fn signatures, or
    needs to manage executor lifetime across multiple batches).
    """
    futs = [ex.submit(fn) for fn in fns]
    return [f.result() for f in futs]
