"""Monte Carlo simulation over key underwriting inputs (seeded, reproducible)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .assumptions import AssumptionError
from .scenarios import apply_overrides, get_path
from .underwriting import run_underwriting

DISTRIBUTIONS = ("normal", "triangular", "uniform")


@dataclass
class InputDistribution:
    path: str
    kind: str = "normal"
    mean: float | None = None  # defaults to the base-case value
    std: float = 0.0  # normal
    low: float | None = None  # triangular / uniform, also a hard floor for normal
    high: float | None = None
    mode: float | None = None  # triangular


def _sample(dist: InputDistribution, base_value: float, rng: np.random.Generator, n: int) -> np.ndarray:
    center = base_value if dist.mean is None else dist.mean
    if dist.kind == "normal":
        draws = rng.normal(center, dist.std, n)
    elif dist.kind == "triangular":
        low = center if dist.low is None else dist.low
        high = center if dist.high is None else dist.high
        mode = center if dist.mode is None else dist.mode
        if not low <= mode <= high or low == high:
            raise ValueError(f"Invalid triangular bounds for {dist.path}")
        draws = rng.triangular(low, mode, high, n)
    elif dist.kind == "uniform":
        if dist.low is None or dist.high is None or dist.low >= dist.high:
            raise ValueError(f"Uniform distribution for {dist.path} needs low < high")
        draws = rng.uniform(dist.low, dist.high, n)
    else:
        raise ValueError(f"Unknown distribution '{dist.kind}'")
    if dist.low is not None or dist.high is not None:
        draws = np.clip(draws, dist.low, dist.high)
    return draws


def run_monte_carlo(
    base: dict[str, Any],
    distributions: list[InputDistribution | dict[str, Any]],
    iterations: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Simulate IRR / NPV / equity-multiple distributions.

    Iterations whose sampled inputs are invalid (e.g. a negative exit cap) are
    discarded and counted in ``rejected``.
    """
    if not 10 <= iterations <= 20000:
        raise ValueError("iterations must be between 10 and 20000")
    dists = [d if isinstance(d, InputDistribution) else InputDistribution(**d) for d in distributions]
    if not dists:
        raise ValueError("At least one input distribution is required")
    rng = np.random.default_rng(seed)
    samples = {d.path: _sample(d, float(get_path(base, d.path)), rng, iterations) for d in dists}

    irr_lev: list[float] = []
    irr_unlev: list[float] = []
    npvs: list[float] = []
    multiples: list[float] = []
    rejected = 0
    for i in range(iterations):
        scenario = apply_overrides(base, {p: float(v[i]) for p, v in samples.items()})
        try:
            m = run_underwriting(scenario).metrics
        except AssumptionError:
            rejected += 1
            continue
        if m.irr_levered is None or m.irr_unlevered is None:
            rejected += 1
            continue
        irr_lev.append(m.irr_levered)
        irr_unlev.append(m.irr_unlevered)
        npvs.append(m.npv_levered)
        multiples.append(m.equity_multiple_levered or 0.0)

    def summarize(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"mean": None, "std": None, "percentiles": {}, "histogram": []}
        arr = np.asarray(values)
        counts, edges = np.histogram(arr, bins=20)
        return {
            "mean": float(arr.mean()),
            "std": float(arr.std()),
            "min": float(arr.min()),
            "max": float(arr.max()),
            "percentiles": {f"p{p}": float(np.percentile(arr, p)) for p in (5, 10, 25, 50, 75, 90, 95)},
            "histogram": [
                {"bin_start": float(edges[k]), "bin_end": float(edges[k + 1]), "count": int(counts[k])}
                for k in range(len(counts))
            ],
        }

    target = float(base.get("discount_rate", 0.0))
    return {
        "iterations": iterations,
        "completed": len(irr_lev),
        "rejected": rejected,
        "seed": seed,
        "irr_levered": summarize(irr_lev),
        "irr_unlevered": summarize(irr_unlev),
        "npv_levered": summarize(npvs),
        "equity_multiple_levered": summarize(multiples),
        "prob_irr_below_discount_rate": (sum(1 for x in irr_lev if x < target) / len(irr_lev)) if irr_lev else None,
        "prob_loss": (sum(1 for x in multiples if x < 1.0) / len(multiples)) if multiples else None,
    }
