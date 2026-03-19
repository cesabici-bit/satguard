"""M4: CW analytical vs numerical Hill equations integration.

Two-tool verification: compare CW linearized displacement against
numerical integration of Hill's (relative motion) equations using
scipy.integrate.solve_ivp.

Reference:
  Hill (1878), "Researches in the Lunar Theory"
  Curtis, "Orbital Mechanics", 4th Ed, Ch.7

For circular orbits with e < 0.05, CW and Hill should agree within 1%.
"""

from __future__ import annotations

import math
import sys

import numpy as np
from scipy.integrate import solve_ivp

# Constants
MU_EARTH = 398600.4418  # km^3/s^2


def mean_motion(sma_km: float) -> float:
    return math.sqrt(MU_EARTH / sma_km**3)


def cw_displacement(dv_km_s: float, tau_s: float, n: float) -> tuple[float, float]:
    """CW analytical displacement (in-track, radial) from in-track burn.

    Returns (dx_intrack_km, dz_radial_km).
    """
    nt = n * tau_s
    dx = dv_km_s * (4.0 / n * math.sin(nt) - 3.0 * tau_s)
    dz = dv_km_s * (2.0 / n * (1.0 - math.cos(nt)))
    return dx, dz


def hill_displacement(dv_km_s: float, tau_s: float, n: float) -> tuple[float, float]:
    """Numerically integrate Hill's equations for comparison.

    Hill/CW equations for relative motion (Curtis Ch.7, Eq.7.36):
    Using convention: x = in-track (along-track), z = radial (outward)

        x'' = -2n * z'                    (in-track: Coriolis only)
        z'' =  2n * x' + 3n^2 * z         (radial: Coriolis + gravity gradient)

    State: [x, z, x_dot, z_dot]
    Initial condition: [0, 0, dv_km_s, 0] (impulsive in-track burn)
    Integrate for tau_s seconds.
    """
    def hill_ode(t: float, state: np.ndarray) -> np.ndarray:
        x, z, xdot, zdot = state
        xddot = -2.0 * n * zdot
        zddot = 2.0 * n * xdot + 3.0 * n**2 * z
        return np.array([xdot, zdot, xddot, zddot])

    # Initial condition: at burn time, velocity kick in x (in-track)
    y0 = np.array([0.0, 0.0, dv_km_s, 0.0])

    sol = solve_ivp(
        hill_ode,
        [0.0, tau_s],
        y0,
        method="RK45",
        rtol=1e-12,
        atol=1e-14,
        dense_output=True,
    )

    if not sol.success:
        raise RuntimeError(f"Hill integration failed: {sol.message}")

    # Final state
    x_final = sol.y[0, -1]  # in-track displacement
    z_final = sol.y[1, -1]  # radial displacement

    return float(x_final), float(z_final)


def compare(sma_km: float, dv_ms: float, tau_frac: float) -> dict:
    """Compare CW vs Hill for given parameters.

    Args:
        sma_km: Semi-major axis [km].
        dv_ms: Delta-v [m/s].
        tau_frac: Fraction of orbital period (0 to 1).

    Returns:
        dict with results and error percentages.
    """
    n = mean_motion(sma_km)
    T = 2 * math.pi / n
    tau = tau_frac * T
    dv_km_s = dv_ms / 1000.0

    dx_cw, dz_cw = cw_displacement(dv_km_s, tau, n)
    dx_hill, dz_hill = hill_displacement(dv_km_s, tau, n)

    err_dx = abs(dx_cw - dx_hill) / max(abs(dx_hill), 1e-15) * 100 if abs(dx_hill) > 1e-10 else 0.0
    err_dz = abs(dz_cw - dz_hill) / max(abs(dz_hill), 1e-15) * 100 if abs(dz_hill) > 1e-10 else 0.0

    return {
        "sma_km": sma_km,
        "dv_ms": dv_ms,
        "tau_frac": tau_frac,
        "tau_s": tau,
        "dx_cw": dx_cw,
        "dz_cw": dz_cw,
        "dx_hill": dx_hill,
        "dz_hill": dz_hill,
        "err_dx_pct": err_dx,
        "err_dz_pct": err_dz,
    }


def main() -> int:
    """Run M4 verification: CW vs Hill comparison."""
    print("=" * 70)
    print("M4 Verification: CW Analytical vs Hill Numerical Integration")
    print("=" * 70)
    print()

    test_cases = [
        # (sma_km, dv_ms, tau_frac, description)
        (6778.0, 0.1, 0.25, "ISS orbit, 0.1 m/s, T/4"),
        (6778.0, 0.1, 0.50, "ISS orbit, 0.1 m/s, T/2"),
        (6778.0, 0.5, 0.25, "ISS orbit, 0.5 m/s, T/4"),
        (6778.0, 0.5, 0.50, "ISS orbit, 0.5 m/s, T/2"),
        (6778.0, 1.0, 0.50, "ISS orbit, 1.0 m/s, T/2"),
        (7178.0, 0.1, 0.50, "800km LEO, 0.1 m/s, T/2"),
        (42164.0, 0.1, 0.25, "GEO, 0.1 m/s, T/4"),
    ]

    all_pass = True
    for sma, dv, tau_frac, desc in test_cases:
        r = compare(sma, dv, tau_frac)
        status = "PASS" if r["err_dx_pct"] < 1.0 and r["err_dz_pct"] < 1.0 else "FAIL"
        if status == "FAIL":
            all_pass = False

        print(f"[{status}] {desc}")
        print(f"       CW:   dx={r['dx_cw']:+.6f} km, dz={r['dz_cw']:+.6f} km")
        print(f"       Hill: dx={r['dx_hill']:+.6f} km, dz={r['dz_hill']:+.6f} km")
        print(f"       Error: dx={r['err_dx_pct']:.4f}%, dz={r['err_dz_pct']:.4f}%")
        print()

    print("=" * 70)
    if all_pass:
        print("ALL TESTS PASSED — CW matches Hill within 1% for all cases.")
        return 0
    else:
        print("SOME TESTS FAILED — CW diverges from Hill beyond 1%.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
