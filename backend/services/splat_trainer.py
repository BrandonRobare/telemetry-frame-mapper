"""Compatibility alias for the CUDA gsplat implementation.

Training enters through ``backend.services.splat_backends``. Existing renderer
callers remain aliased to the CUDA module until #815 introduces their separate
boundary.
"""

import sys

from backend.services.splat_backends import cuda_gsplat as _cuda_gsplat

sys.modules[__name__] = _cuda_gsplat
