"""
Monte Carlo uncertainty analysis utilities for Digital Carbon Labels.

SECURITY NOTICE
---------------
All functions in this module rely on Python's pseudo-random number generators
(`random.random()`) for performance. They are suitable for statistical
analysis and compliance reporting but **must not** be used for
security-sensitive or cryptographic purposes. The generator is seeded
deterministically for reproducibility in testing and auditing scenarios.
"""

from __future__ import annotations

import math
import random
from typing import TypedDict


class MonteCarloSummary(TypedDict):
    """Metadata describing a Monte Carlo confidence interval."""

    method: str
    ci_lower_g: float
    ci_upper_g: float
    confidence_level_pct: float


def _sample_normal(mu: float, sigma: float, rng: random.Random) -> float:
    """
    Sample from normal distribution using Box-Muller transform.

    Uses random.random() for performance in Monte Carlo simulations,
    not requiring cryptographic security. This function is NOT suitable
    for security-sensitive applications or cryptographic purposes.
    """
    if sigma <= 0:
        return mu

    # Box-Muller: generate two independent standard normals from two uniforms.
    # Clamp u1 away from zero to avoid log(0) and extreme values in the
    # Box-Muller transform.
    u1 = max(rng.random(), 1e-12)  # nosec B311
    u2 = rng.random()  # nosec B311
    r = math.sqrt(-2.0 * math.log(u1))
    theta = 2 * math.pi * u2
    z0 = r * math.cos(theta)
    return mu + sigma * z0


def estimate_co2_distribution(
    *,
    duration_s: float,
    start_power_w: float,
    end_power_w: float,
    n: int = 1000,
    idle_baseline_w_mu: float = 0.0,
    idle_baseline_w_sigma: float = 0.0,
    power_residual_sigma_w: float = 0.0,
    pue_mu: float = 1.2,
    pue_sigma: float = 0.0,
    intensity_gco2_kwh_mu: float = 475.0,
    intensity_gco2_kwh_sigma: float = 0.0,
    seed: int | None = 42,
) -> list[float]:
    """Generate Monte Carlo CO₂ sample distribution for energy traces.

    Args:
        duration_s: Duration of the observed workload segment in seconds.
        start_power_w: Estimated starting power draw in watts.
        end_power_w: Estimated ending power draw in watts.
        n: Number of Monte Carlo iterations to perform.
        idle_baseline_w_mu: Mean idle baseline power removed from the trace.
        idle_baseline_w_sigma: Standard deviation for the idle power estimate.
        power_residual_sigma_w: Standard deviation for residual power noise.
        pue_mu: Mean power usage effectiveness applied during the simulation.
        pue_sigma: Standard deviation for the PUE distribution.
        intensity_gco2_kwh_mu: Mean grid intensity in grams CO₂ per kWh.
        intensity_gco2_kwh_sigma: Standard deviation for the grid intensity.
            seed: Optional deterministic seed; set to ``None`` for non-deterministic
                sampling.

    Returns:
        List of simulated CO₂ gram values across all iterations.

    Raises:
        Nothing.

    Notes:
        The sampling relies on Python's non-cryptographic pseudo-random number
        generators for performance. It must not be used for security-sensitive
        or cryptographic applications.
    """
    out: list[float] = []
    duration_h = max(duration_s, 0.0) / 3600.0
    rng = random.Random() if seed is None else random.Random(seed)  # nosec B311
    for _ in range(max(1, n)):
        idle_w = max(
            0.0, _sample_normal(idle_baseline_w_mu, idle_baseline_w_sigma, rng)
        )
        p_resid = _sample_normal(0.0, power_residual_sigma_w, rng)
        p_start = max(0.0, start_power_w + p_resid)
        p_end = max(0.0, end_power_w + p_resid)
        avg_power_w = max((p_start + p_end) / 2.0 - idle_w, 0.0)
        energy_kwh = avg_power_w * duration_h
        pue = max(_sample_normal(pue_mu, pue_sigma, rng), 1.0)
        total_energy_kwh = energy_kwh * pue
        intensity = max(
            _sample_normal(intensity_gco2_kwh_mu, intensity_gco2_kwh_sigma, rng),
            0.0,
        )
        grams = total_energy_kwh * intensity
        out.append(grams)
    return out


def bootstrap_ci(
    samples: list[float],
    alpha: float = 0.05,
    iters: int = 1000,
    seed: int | None = 42,
) -> tuple[float, float]:
    """Compute percentile bootstrap confidence interval for the mean.

    Args:
        samples: Observed samples to bootstrap.
        alpha: Two-sided significance level for the confidence interval.
        iters: Number of bootstrap resamples.
        seed: Deterministic seed; pass ``None`` for non-deterministic draws.

    Returns:
        Lower and upper bounds of the percentile bootstrap confidence interval.

    Raises:
        Nothing.

    Notes:
        The bootstrap procedure uses Python's default pseudo-random number
        generator, which is not suitable for cryptographic applications.
    """
    if not samples:
        return (0.0, 0.0)
    means: list[float] = []
    n = len(samples)
    rng = random.Random() if seed is None else random.Random(seed)  # nosec B311
    for _ in range(max(1, iters)):
        draw = [samples[rng.randrange(n)] for _ in range(n)]
        means.append(sum(draw) / n)
    means.sort()
    lo_idx = int((alpha / 2.0) * (iters - 1))
    hi_idx = int((1 - alpha / 2.0) * (iters - 1))
    return (means[lo_idx], means[hi_idx])


def power_analysis_required_n(
    stddev: float, effect: float, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Estimate sample size for a two-sample t-test power analysis.

    Args:
        stddev: Pooled standard deviation estimate for the outcome metric.
        effect: Minimum detectable difference between group means.
        alpha: Two-sided significance level for the hypothesis test.
        power: Target statistical power for detecting the specified effect.

    Returns:
        Sample size per group required to achieve the requested power.

    Raises:
        ValueError: If ``alpha`` or ``power`` fall outside ``(0, 1)``, if
            ``power`` is less than ``0.5``, or if ``effect`` equals zero.

    Notes:
        This helper targets statistical planning contexts and should not be
        repurposed for cryptographic workloads.
    """

    if not 0 < alpha < 1:
        raise ValueError("alpha must be within the open interval (0, 1)")
    if not 0 < power < 1:
        raise ValueError("power must be within the open interval (0, 1)")
    if power < 0.5:
        raise ValueError("power must be at least 0.5 for meaningful analysis")
    if effect == 0:
        raise ValueError("effect must be non-zero")

    def _z(p: float) -> float:
        """
        Approximate the inverse CDF (quantile / probit) of the standard normal.

        This uses Peter J. Acklam's rational approximation for Φ⁻¹(p), which
        provides close to double-precision accuracy (absolute error typically
        below 1e-9) over the open interval 0 < p < 1.

        Parameters
        ----------
        p : float
            Cumulative probability with 0 < p < 1. Values of exactly 0 or 1 are
            not supported, and calling code should clamp or avoid such inputs.

        Returns
        -------
        float
            z such that P(Z ≤ z) ≈ p for Z ~ N(0, 1).

        Notes
        -----
        This implementation is suitable for statistical calculations such as
        power analysis and confidence interval construction, but is not intended
        for cryptographic or security-sensitive applications.

        """
        # Rational approximation for inverse CDF of standard normal (Acklam)
        a1 = -39.69683028665376
        a2 = 220.9460984245205
        a3 = -275.9285104469687
        a4 = 138.3577518672690
        a5 = -30.66479806614716
        a6 = 2.506628277459239
        b1 = -54.47609879822406
        b2 = 161.5858368580405
        b3 = -155.6989798598866
        b4 = 66.80131188771972
        b5 = -13.28068155288572
        c1 = -0.007784894002430293
        c2 = -0.3223964580411365
        c3 = -2.400758277161838
        c4 = -2.549732539343734
        c5 = 4.374664141464968
        c6 = 2.938163982698783
        d1 = 0.007784695709041462
        d2 = 0.3224671290700398
        d3 = 2.445134137142996
        d4 = 3.754408661907416
        plow = 0.02425
        phigh = 1 - plow
        if p < plow:
            q = math.sqrt(-2 * math.log(p))
            return (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / (
                (((d1 * q + d2) * q + d3) * q + d4) * q + 1
            )
        if p > phigh:
            q = math.sqrt(-2 * math.log(1 - p))
            return -(((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / (
                (((d1 * q + d2) * q + d3) * q + d4) * q + 1
            )
        q = p - 0.5
        r = q * q
        return (
            (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6)
            * q
            / (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1)
        )

    z_alpha2 = abs(_z(1 - alpha / 2))
    z_power = abs(_z(power))
    n = 2 * ((z_alpha2 + z_power) ** 2) * (stddev**2) / (effect**2)
    return max(2, int(math.ceil(n)))


def monte_carlo_summary(
    samples: list[float],
    *,
    alpha: float = 0.05,
    iters: int = 1000,
    seed: int | None = 42,
) -> MonteCarloSummary:
    """Summarise Monte Carlo samples with confidence bounds metadata."""

    lower, upper = bootstrap_ci(samples, alpha=alpha, iters=iters, seed=seed)
    lower = max(lower, 0.0)
    upper = max(upper, lower)
    confidence_pct = max(0.0, min(100.0, (1.0 - alpha) * 100.0))
    return {
        "method": "monte_carlo",
        "ci_lower_g": lower,
        "ci_upper_g": upper,
        "confidence_level_pct": confidence_pct,
    }
