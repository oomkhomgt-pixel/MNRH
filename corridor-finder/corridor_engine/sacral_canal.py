"""The sacral canal and the sacral foramina, as structures a screw keeps the
full margin from (DECISIONS.md 7.4, 7.9; the surgeon, 2026-10-04).

The segmentation leaves both as empty space inside the sacrum, so the one
breach rule already keeps the margin from them. They are found explicitly
so that nothing else can count them as bone: neither the sacroiliac bridge
(DECISIONS.md 2) nor a marked fracture's gap (7.14), which in a zone II
fracture runs straight through the foramina. Making them non-bone only
ever makes the check stricter.

Found from the sacrum's own label:
* the canal is the hole the sacrum encloses on an axial slice (the
  posterior arch closes it);
* the foramina are the channels through it, about a centimetre across: the
  empty space a closing of FORAMEN_CLOSING_MM bridges;
* and of the foramina, only what is thicker than 2 x MIN_THICKNESS_MM (the
  canal is kept whole: an enclosed hole is never a fracture): a foramen is
  a round channel 8-10 mm across, a fracture gap a thin sheet. Without this
  a sacral fracture gap was taken for a foramen and the surgeon's marked
  fracture (7.14) could never be bridged. A gap wider than that next to the
  foramina stays protected, which is the safe side (and such a fracture is
  reduced first).
Space within NEAR_HIP_MM of a hip bone is left out: that is the sacroiliac
joint, not a foramen. Taking sacrum-labelled voxels darker than fat as well
(in case the segmentation painted into a foramen) was tried on CLINIC_0012
and dropped: it took in cancellous bone and fracture haematoma. A foramen
the segmentation filled is therefore not found; the panel shows what is
protected so the surgeon can see that.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

from .volume import Volume

FORAMEN_CLOSING_MM = 7.0
NEAR_HIP_MM = 8.0
MIN_THICKNESS_MM = 2.5  # an opening of this radius: sheets thinner than 5 mm drop out


def canal_and_foramina(labels: Volume, sacrum_label: int, hip_labels=()) -> np.ndarray:
    """Boolean mask (labels' grid) of the sacral canal and foramina."""
    arr = labels.array
    sacrum = arr == sacrum_label
    out = np.zeros(arr.shape, dtype=bool)
    if not sacrum.any():
        return out
    sampling = np.array([labels.spacing[2], labels.spacing[1], labels.spacing[0]], dtype=float)
    idx = np.argwhere(sacrum)
    pad = np.ceil((FORAMEN_CLOSING_MM + NEAR_HIP_MM) / sampling).astype(int) + 2
    lo = np.maximum(idx.min(axis=0) - pad, 0)
    hi = np.minimum(idx.max(axis=0) + pad + 1, arr.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    s = sacrum[box]
    # Canal: enclosed on axial slices.
    enclosed = np.zeros_like(s)
    for z in range(s.shape[0]):
        if s[z].any():
            enclosed[z] = ndi.binary_fill_holes(s[z])
    # Foramina: bridged by a closing of about a centimetre.
    near = ndi.distance_transform_edt(~s, sampling=sampling) <= FORAMEN_CLOSING_MM
    closed = ndi.distance_transform_edt(near, sampling=sampling) > FORAMEN_CLOSING_MM
    empty = ~s & (arr[box] == 0)
    canal = enclosed & empty
    foramina = closed & empty & ~canal
    hips = np.isin(arr[box], list(hip_labels)) if hip_labels else np.zeros_like(s)
    if hips.any():
        away = ndi.distance_transform_edt(~hips, sampling=sampling) > NEAR_HIP_MM
        canal &= away
        foramina &= away
    if foramina.any():
        # Opening by a ball of MIN_THICKNESS_MM, by distance transforms;
        # the canal beside it counts as room, so a foramen opening into the
        # canal keeps its mouth.
        room = foramina | canal
        core = (ndi.distance_transform_edt(room, sampling=sampling) > MIN_THICKNESS_MM) & room
        foramina &= ndi.distance_transform_edt(~core, sampling=sampling) <= MIN_THICKNESS_MM + max(labels.spacing)
    out[box] = canal | foramina
    return out
