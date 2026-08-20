"""Production benchmark and model-pinning gate.

This package is deliberately dependency-light: release evaluation must be auditable
without importing heavyweight ML runtimes or downloading model weights.
"""

from .gate import BenchmarkGateError, evaluate_release_gate

__all__ = ["BenchmarkGateError", "evaluate_release_gate"]
