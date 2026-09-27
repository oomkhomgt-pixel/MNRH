"""Rigid registration: the closed-form fit, trimmed ICP, and RANSAC over pairs.

These are the three tools the fragment finder (fragments.py) is built from.
Every transform is a 4x4 homogeneous matrix acting on world (x, y, z) mm
points as ``p' = T[:3, :3] @ p + T[:3, 3]``.

**Why consensus is over correspondence pairs, not over surface patches.**
Measured on the four CLINIC cases: every asymmetry patch, fitted on its own,
dropped to 1.0-1.8 mm residual under a fabricated 5-14 mm, 1.6-14.2 degree
transform. A freely fitted patch always "fits", so a patch's residual under
its own transform is no evidence it moved. RANSAC instead asks how many
individual point pairs agree with one transform, which a small patch of
look-alike surface cannot inflate.

Pure numpy/scipy; the random draws are seeded, so the same case always
gives the same answer.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

RANSAC_ITERATIONS = 400
RANSAC_REFINEMENTS = 4  # refit on the inliers and recount, this many times
MIN_SAMPLE_SPREAD_MM = 10.0  # three pairs closer than this fix no rotation


def transform_points(transform: np.ndarray, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    return points @ transform[:3, :3].T + transform[:3, 3]


def invert(transform: np.ndarray) -> np.ndarray:
    out = np.eye(4)
    out[:3, :3] = transform[:3, :3].T
    out[:3, 3] = -transform[:3, :3].T @ transform[:3, 3]
    return out


def rotation_deg(transform: np.ndarray) -> float:
    """The angle of the transform's rotation, in degrees."""
    cos = (np.trace(transform[:3, :3]) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def travel_mm(transform: np.ndarray, points: np.ndarray) -> np.ndarray:
    """How far the transform moves each point."""
    points = np.asarray(points, dtype=float)
    return np.linalg.norm(transform_points(transform, points) - points, axis=1)


def kabsch(a: np.ndarray, b: np.ndarray, weights: Optional[np.ndarray] = None) -> np.ndarray:
    """The rigid transform (no reflection, no scale) that best carries the
    points ``a`` onto their partners ``b`` in the least-squares sense."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    w = np.ones(a.shape[0]) if weights is None else np.asarray(weights, dtype=float)
    w = w / w.sum()
    ca, cb = w @ a, w @ b
    h = (a - ca).T @ ((b - cb) * w[:, None])
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    r = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    out = np.eye(4)
    out[:3, :3] = r
    out[:3, 3] = cb - r @ ca
    return out


def point_to_plane(src: np.ndarray, dst: np.ndarray, dst_normals: np.ndarray) -> np.ndarray:
    """One linearised step of the rigid transform that brings each point
    ``src[i]`` onto the tangent plane at ``dst[i]``. Along a smooth surface
    this converges where point-to-point pairing stalls, because sliding
    along the surface costs nothing and is not pulled back."""
    src = np.asarray(src, dtype=float)
    n = np.asarray(dst_normals, dtype=float)
    a = np.hstack([np.cross(src, n), n])
    b = np.einsum("ij,ij->i", np.asarray(dst, dtype=float) - src, n)
    x, *_ = np.linalg.lstsq(a, b, rcond=None)
    angle = float(np.linalg.norm(x[:3]))
    out = np.eye(4)
    if angle > 0:
        axis = x[:3] / angle
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        out[:3, :3] = np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * (k @ k)
    out[:3, 3] = x[3:]
    return out


def _kabsch_batch(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """kabsch for a stack of minimal samples, shape (n, k, 3) each."""
    ca, cb = a.mean(axis=1), b.mean(axis=1)
    h = np.einsum("nki,nkj->nij", a - ca[:, None], b - cb[:, None])
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(np.einsum("nji,nkj->nik", vt, u)))
    d[d == 0] = 1.0
    fix = np.tile(np.eye(3), (len(d), 1, 1))
    fix[:, 2, 2] = d
    r = np.einsum("nji,njk,nlk->nil", vt, fix, u)
    out = np.tile(np.eye(4), (len(d), 1, 1))
    out[:, :3, :3] = r
    out[:, :3, 3] = cb - np.einsum("nij,nj->ni", r, ca)
    return out


def ransac_rigid(src: np.ndarray, dst: np.ndarray, threshold_mm: float,
                 iterations: int = RANSAC_ITERATIONS, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """The rigid transform that the largest number of pairs (src[i],
    dst[i]) agree with to within ``threshold_mm``, refitted on those pairs.

    Returns (transform, inlier mask). With fewer than three pairs, or no
    well-spread sample, returns the identity and no inliers."""
    src = np.asarray(src, dtype=float)
    dst = np.asarray(dst, dtype=float)
    n = src.shape[0]
    if n < 3:
        return np.eye(4), np.zeros(n, dtype=bool)
    rng = np.random.default_rng(seed)
    samples = np.array([rng.choice(n, 3, replace=False) for _ in range(iterations)])
    a, b = src[samples], dst[samples]
    # A sample of three nearly collinear or bunched points fixes no rotation.
    spread = np.linalg.norm(np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]), axis=1)
    keep = spread >= MIN_SAMPLE_SPREAD_MM ** 2 / 2.0
    if not keep.any():
        return np.eye(4), np.zeros(n, dtype=bool)
    candidates = _kabsch_batch(a[keep], b[keep])
    moved = np.einsum("nij,mj->nmi", candidates[:, :3, :3], src) + candidates[:, None, :3, 3]
    counts = (np.linalg.norm(moved - dst[None], axis=2) < threshold_mm).sum(axis=1)
    best = candidates[int(np.argmax(counts))]
    inliers = np.linalg.norm(transform_points(best, src) - dst, axis=1) < threshold_mm
    for _ in range(RANSAC_REFINEMENTS):
        if inliers.sum() < 3:
            break
        best = kabsch(src[inliers], dst[inliers])
        inliers = np.linalg.norm(transform_points(best, src) - dst, axis=1) < threshold_mm
    return best, inliers


def trimmed_icp(source: np.ndarray, target: np.ndarray, init: Optional[np.ndarray] = None,
                keep_fraction: float = 0.7, iterations: int = 60, tolerance_mm: float = 1e-3,
                target_tree: Optional[cKDTree] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Iterative closest point that fits only the best ``keep_fraction`` of
    the pairs each round, so a part of the source with no counterpart in the
    target does not drag the fit. Returns (transform, each source point's
    closest-point distance under it).

    Its residual says nothing on its own about whether the source moved
    (see the module docstring); use it to estimate, never to accept."""
    source = np.asarray(source, dtype=float)
    tree = target_tree if target_tree is not None else cKDTree(np.asarray(target, dtype=float))
    target = tree.data
    transform = np.eye(4) if init is None else np.array(init, dtype=float)
    for _ in range(iterations):
        moved = transform_points(transform, source)
        dist, idx = tree.query(moved)
        keep = dist <= np.quantile(dist, keep_fraction)
        step = kabsch(moved[keep], target[idx[keep]])
        transform = step @ transform
        if np.linalg.norm(step[:3, 3]) < tolerance_mm and rotation_deg(step) < 1e-3:
            break
    dist, _ = tree.query(transform_points(transform, source))
    return transform, dist
