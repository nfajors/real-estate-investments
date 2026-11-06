"""Scenario construction, sensitivity grids and assumption path helpers."""

from __future__ import annotations

import copy
from typing import Any

from .underwriting import UnderwritingResult, run_underwriting

# Metric keys exposed for sensitivity tables and comparisons.
SENSITIVITY_METRICS = (
    "irr_levered",
    "irr_unlevered",
    "npv_levered",
    "npv_unlevered",
    "equity_multiple_levered",
    "cash_on_cash_year1",
    "dscr_year1",
    "going_in_cap_rate",
    "noi_year1",
)

# Default conservative / optimistic shifts relative to the base case.
DEFAULT_SCENARIO_SHIFTS: dict[str, dict[str, float]] = {
    "Conservative": {"rent_growth": -0.01, "vacancy_rate": 0.02, "opex_growth": 0.005, "exit_cap_rate": 0.005},
    "Optimistic": {"rent_growth": 0.01, "vacancy_rate": -0.01, "opex_growth": -0.0025, "exit_cap_rate": -0.0025},
}


def get_path(data: dict[str, Any], path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


def set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            raise KeyError(path)
        node = node[part]
    node[parts[-1]] = value


def apply_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``base`` with dotted-path ``overrides`` set."""
    out = copy.deepcopy(base)
    for path, value in overrides.items():
        set_path(out, path, value)
    return out


def shift_assumptions(base: dict[str, Any], shifts: dict[str, float]) -> dict[str, Any]:
    """Add ``shifts`` to numeric assumptions (vacancy floored at zero)."""
    out = copy.deepcopy(base)
    for path, delta in shifts.items():
        new_value = get_path(out, path) + delta
        if path in ("vacancy_rate", "credit_loss_rate"):
            new_value = max(0.0, new_value)
        set_path(out, path, round(new_value, 10))
    return out


def default_scenarios(base: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Base + conservative + optimistic assumption sets."""
    out = {"Base": copy.deepcopy(base)}
    for name, shifts in DEFAULT_SCENARIO_SHIFTS.items():
        out[name] = shift_assumptions(base, shifts)
    return out


def metric_value(result: UnderwritingResult, metric: str) -> float | None:
    if metric not in SENSITIVITY_METRICS:
        raise ValueError(f"Unsupported metric '{metric}'")
    return getattr(result.metrics, metric)


def sensitivity_table(
    base: dict[str, Any],
    row_path: str,
    row_values: list[float],
    col_path: str,
    col_values: list[float],
    metric: str = "irr_levered",
) -> dict[str, Any]:
    """Two-way sensitivity grid. ``grid[i][j]`` = metric at (row_values[i], col_values[j])."""
    if metric not in SENSITIVITY_METRICS:
        raise ValueError(f"Unsupported metric '{metric}'")
    get_path(base, row_path)
    get_path(base, col_path)
    grid: list[list[float | None]] = []
    for rv in row_values:
        row: list[float | None] = []
        for cv in col_values:
            scenario = apply_overrides(base, {row_path: rv, col_path: cv})
            row.append(metric_value(run_underwriting(scenario), metric))
        grid.append(row)
    return {
        "metric": metric,
        "row_path": row_path,
        "row_values": row_values,
        "col_path": col_path,
        "col_values": col_values,
        "grid": grid,
    }


def centered_range(center: float, step: float, count: int = 5) -> list[float]:
    """``count`` values centred on ``center`` spaced by ``step``."""
    half = count // 2
    return [round(center + step * (i - half), 10) for i in range(count)]
