"""Lightweight math utilities replacing numpy/scipy for basic statistics.

These provide stdlib-only alternatives so the core SDK doesn't require
heavy scientific computing packages. For performance-critical workloads,
users should install numpy directly.
"""

from __future__ import annotations

import math
import statistics
from typing import Sequence


def mean(values: Sequence[float]) -> float:
    """Mean of values. Replaces np.mean()."""
    return statistics.fmean(values)


def stdev(values: Sequence[float]) -> float:
    """Population standard deviation. Replaces np.std()."""
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)


def median(values: Sequence[float]) -> float:
    """Median of values. Replaces np.median()."""
    return statistics.median(values)


def percentile(values: Sequence[float], p: float) -> float:
    """p-th percentile (0-100). Replaces np.percentile()."""
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_v[int(k)]
    return sorted_v[f] * (c - k) + sorted_v[c] * (k - f)


def linregress(x: Sequence[float], y: Sequence[float]) -> tuple[float, float, float]:
    """Simple linear regression. Returns (slope, intercept, r_value).
    Replaces scipy.stats.linregress() for the fields we actually use."""
    n = len(x)
    if n < 2:
        return 0.0, 0.0, 0.0
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-15:
        return 0.0, sum_y / n, 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    y_mean = sum_y / n
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    r_value = math.sqrt(max(0, 1 - ss_res / ss_tot)) if ss_tot > 0 else 0.0
    return slope, intercept, r_value


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product of two vectors. Replaces np.dot()."""
    return sum(ai * bi for ai, bi in zip(a, b))


def norm(v: Sequence[float]) -> float:
    """Euclidean norm. Replaces np.linalg.norm()."""
    return math.sqrt(sum(x * x for x in v))


def variance(values: Sequence[float]) -> float:
    """Population variance. Replaces np.var()."""
    if len(values) < 2:
        return 0.0
    return statistics.pvariance(values)


def arange(n: int) -> list[int]:
    """Range as list. Replaces np.arange()."""
    return list(range(n))


def linspace(start: float, stop: float, num: int) -> list[float]:
    """Linearly spaced values. Replaces np.linspace()."""
    if num < 2:
        return [start]
    step = (stop - start) / (num - 1)
    return [start + i * step for i in range(num)]


def fft_magnitudes(values: Sequence[float]) -> tuple[list[float], list[float]]:
    """Simple DFT magnitude spectrum. Replaces np.fft.fft() + np.abs().
    Returns (frequencies, magnitudes) for the positive half spectrum.
    For production FFT, install numpy."""
    n = len(values)
    magnitudes = []
    for k in range(n // 2):
        real = sum(values[j] * math.cos(2 * math.pi * k * j / n) for j in range(n))
        imag = sum(values[j] * math.sin(2 * math.pi * k * j / n) for j in range(n))
        magnitudes.append(math.sqrt(real * real + imag * imag))
    frequencies = [k / n for k in range(n // 2)]
    return frequencies, magnitudes
