"""Use the existing compatible local NumPy, or a standalone virtual environment."""
from pathlib import Path
import os
import sys

for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ.setdefault(name, '1')
if sys.prefix == sys.base_prefix:
    deps = Path(__file__).resolve().parents[2] / 'deps'
    if deps.is_dir():
        sys.path.insert(0, str(deps))
