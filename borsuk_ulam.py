"""
Continuous Borsuk-Ulam sanity demo on S^1.
f(w) = c.w for w = (cos t, sin t) over a (gas, coal) pair.
g(t) = f(t) - f(t + pi) is odd, so it changes sign -> a root exists
-> f(w) = f(-w) -> (for linear f) net carbon exposure is 0.
"""
import numpy as np


def borsuk_ulam_circle(c_clean, c_dirty=1.0, tol=1e-10):
    if c_dirty == 0:
        raise ValueError("c_dirty must be non-zero")
    f = lambda t: c_clean * np.cos(t) + c_dirty * np.sin(t)
    g = lambda t: f(t) - f(t + np.pi)
    lo, hi = 0.0, np.pi
    if abs(g(lo)) <= tol:
        return lo, np.array([1.0, 0.0])
    if abs(g(hi)) <= tol:
        return hi, np.array([-1.0, 0.0])
    if np.sign(g(lo)) == np.sign(g(hi)):
        raise ValueError("The antipodal endpoint bracket was not found")
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if np.sign(g(mid)) == np.sign(g(lo)) else (lo, mid)
    t = (lo + hi) / 2
    return t, np.array([np.cos(t), np.sin(t)])
