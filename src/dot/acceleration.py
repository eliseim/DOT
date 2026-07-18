"""Optional, hardware-safe acceleration support.

DOT remains fully functional without Numba.  The standard launcher attempts
to install it, while source installations can omit the ``acceleration`` extra
and use the same deterministic Python kernels.  Set ``DOT_DISABLE_JIT=1``
before starting Python to force the fallback (useful for diagnosis).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar, cast

_Function = TypeVar("_Function", bound=Callable[..., Any])
_disable_value = os.environ.get("DOT_DISABLE_JIT", "").strip().lower()
JIT_REQUESTED = _disable_value not in {"1", "true", "yes", "on"}

try:
    if not JIT_REQUESTED:
        raise ImportError("disabled by DOT_DISABLE_JIT")
    from numba import njit as _numba_njit
except Exception as exc:  # Numba may reject an unsupported Python/NumPy pair.
    JIT_ENABLED = False
    JIT_UNAVAILABLE_REASON = str(exc)

    def compiled(function: _Function) -> _Function:
        """Return an unchanged Python function when Numba is unavailable."""

        return function

else:
    JIT_ENABLED = True
    JIT_UNAVAILABLE_REASON = None

    def compiled(function: _Function) -> _Function:
        """Compile a serial, cacheable kernel which releases the GIL.

        ``parallel=True`` is deliberately not used: campaign-level process
        parallelism is optional and combining both would oversubscribe CPUs.
        """

        return cast(_Function, _numba_njit(cache=True, nogil=True)(function))


def jit_status() -> str:
    """Return a concise status string suitable for the GUI campaign log."""

    if JIT_ENABLED:
        return "Numba JIT enabled"
    if not JIT_REQUESTED:
        return "Numba JIT disabled by DOT_DISABLE_JIT"
    return f"Numba JIT unavailable ({JIT_UNAVAILABLE_REASON})"


def recommended_process_workers() -> int:
    """Return a conservative cross-platform worker count for GUI campaigns.

    Leaving one logical CPU for Tk/the operating system keeps the interface
    responsive.  Four is a deliberate memory/serialization cap selected by
    the end-to-end benchmark, and the
    Windows ProcessPoolExecutor limit is 61.
    """

    logical_cpus = os.cpu_count() or 1
    return max(1, min(logical_cpus - 1, 4, 61))
