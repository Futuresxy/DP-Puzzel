"""Stable entry points for workload, precision-plan and array evaluation."""

from .precision import compare_plans, resolve_plan
from .tiling import evaluate_operator, evaluate_workload
from .workload import build_workload, validate_workload

__all__ = ["build_workload", "validate_workload", "resolve_plan", "compare_plans",
           "evaluate_operator", "evaluate_workload"]
