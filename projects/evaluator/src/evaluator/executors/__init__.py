"""Test execution backends for running tests in different environments."""

from evaluator.executors.base import (
    ExecutionContext,
    ExecutionError,
    ExecutorBackend,
    SandboxConfig,
)
from evaluator.executors.e2b import E2BExecutor, SandboxPool
from evaluator.executors.local import LocalExecutor

__all__ = [
    "ExecutionContext",
    "ExecutorBackend",
    "ExecutionError",
    "SandboxConfig",
    "LocalExecutor",
    "E2BExecutor",
    "SandboxPool",
]
