import numpy as np
import pytest

from corridor_engine.register import (
    invert,
    kabsch,
    ransac_rigid,
    rotation_deg,
    transform_points,
    travel_mm,
    trimmed_icp,
)


def _rigid(axis, angle_deg, translation):
    axis = np.asarray(axis, dtype=float)
    axis /= np.linalg.norm(axis)
    a = np.radians(angle_deg)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    out = np.eye(4)
    out[:3, :3] = np.eye(3) + np.sin(a) * k + (1 - np.cos(a)) * (k @ k)
    out[:3, 3] = translation
    return out


def _cloud(n=600, seed=3):
    """An irregular blob of points, with no symmetry a fit could slide along."""
    rng = np.random.default_rng(seed)
    p = rng.normal(size=(n, 3)) * np.array([30.0, 18.0, 10.0])
    return p + 0.002 * p[:, [1]] ** 2 * np.array([1.0, 0.0, 0.5])


def test_kabsch_recovers_an_exact_rigid_transform():
    truth = _rigid((0.3, -0.5, 1.0), 12.0, (4.0, -7.0, 2.5))
    a = _cloud()
    found = kabsch(a, transform_points(truth, a))
    assert np.allclose(found, truth, atol=1e-9)


def test_kabsch_never_returns_a_reflection():
    """Mirrored points have no rigid fit; the answer must still be a
    rotation, since a reflection applied to a fragment would turn it
    inside out."""
    a = _cloud()
    b = a * np.array([-1.0, 1.0, 1.0])
    assert np.linalg.det(kabsch(a, b)[:3, :3]) == pytest.approx(1.0)


def test_invert_and_the_measures_of_a_transform():
    truth = _rigid((0, 0, 1), 30.0, (10.0, 0.0, 0.0))
    assert np.allclose(invert(truth) @ truth, np.eye(4))
    assert rotation_deg(truth) == pytest.approx(30.0)
    assert travel_mm(_rigid((0, 0, 1), 0.0, (3.0, 4.0, 0.0)), _cloud(5)) == pytest.approx([5.0] * 5)


def test_ransac_finds_the_transform_most_pairs_agree_with():
    """70% of the pairs follow one transform and 30% follow another: the
    answer is the majority's, and exactly its pairs are the inliers."""
    a = _cloud()
    main = _rigid((0, 1, 0), 3.0, (1.0, 0.0, 0.0))
    other = _rigid((1, 0, 0), 10.0, (0.0, 8.0, -5.0))
    b = transform_points(main, a)
    minority = np.arange(len(a)) % 10 < 3
    b[minority] = transform_points(other, a[minority])
    found, inliers = ransac_rigid(a, b, threshold_mm=0.5)
    assert np.allclose(found, main, atol=1e-6)
    assert np.array_equal(inliers, ~minority)
    # And on what is left, the minority's own transform.
    found2, inliers2 = ransac_rigid(a[minority], b[minority], threshold_mm=0.5)
    assert np.allclose(found2, other, atol=1e-6) and inliers2.all()


def test_ransac_with_too_few_pairs_claims_nothing():
    found, inliers = ransac_rigid(np.zeros((2, 3)), np.ones((2, 3)), threshold_mm=1.0)
    assert np.allclose(found, np.eye(4)) and not inliers.any()


def test_trimmed_icp_ignores_the_part_with_no_counterpart():
    """A fifth of the source is somewhere the target has nothing; ICP on
    the rest still lands the transform."""
    target = _cloud(1500)
    truth = _rigid((0.2, 1.0, 0.1), 4.0, (2.0, -1.5, 1.0))
    source = transform_points(invert(truth), target[:1200])
    source = np.vstack([source, np.random.default_rng(1).normal(size=(300, 3)) * 5 + [80.0, 0.0, 0.0]])
    found, dist = trimmed_icp(source, target, keep_fraction=0.7)
    assert np.allclose(transform_points(found, source[:1200]), target[:1200], atol=0.05)
    assert np.median(dist[:1200]) < 0.05
