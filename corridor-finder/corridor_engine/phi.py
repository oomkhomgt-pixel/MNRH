"""PHI (protected health information) hygiene helpers.

Used before writing anything derived from DICOM headers or patient records
into a plan file, report, or log: strip identifiers down to a technical
whitelist, and assert that no obviously-identifying data survived.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

PHI_SAFE_KEYS = (
    "Modality",
    "PixelSpacing",
    "SliceThickness",
    "ImageOrientationPatient",
    "Rows",
    "Columns",
    "ManufacturerModelName",
    "KVP",
    "ConvolutionKernel",
)

PHI_DENYLIST_KEYS = (
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "AccessionNumber",
    "PatientAddress",
    "OtherPatientIDs",
    "InstitutionName",
)

_UID_RE = re.compile(r"^[0-9.]{16,}$")


def hash_uid(uid: str, salt: str = "") -> str:
    """Stable, non-reversible pseudonym for a UID, e.g. "sha256:1a2b3c...".

    Uses the first 16 hex characters of a sha256 digest of ``salt + uid``.
    """
    digest = hashlib.sha256((salt + str(uid)).encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def strip_phi(header: dict, *, salt: str = "") -> dict:
    """Whitelist-only copy of a DICOM-like header dict.

    Keeps only PHI_SAFE_KEYS verbatim (if present), replaces
    StudyInstanceUID/SeriesInstanceUID with hashed pseudonyms, and drops
    everything else. Never raises on unexpected input.
    """
    out: Dict[str, Any] = {}
    if not isinstance(header, dict):
        return out
    for key in PHI_SAFE_KEYS:
        if key in header:
            out[key] = header[key]
    if "StudyInstanceUID" in header:
        out["study_uid_hash"] = hash_uid(header["StudyInstanceUID"], salt=salt)
    if "SeriesInstanceUID" in header:
        out["series_uid_hash"] = hash_uid(header["SeriesInstanceUID"], salt=salt)
    return out


def _key_is_phi(key: Any) -> bool:
    return isinstance(key, str) and key in PHI_DENYLIST_KEYS


def _value_is_phi(value: Any) -> bool:
    if isinstance(value, str) and _UID_RE.match(value):
        return True
    return False


def assert_no_phi(obj: Any, _path: str = "$") -> None:
    """Recursively walk a JSON-able structure and raise ValueError naming
    the offending key path if any dict key matches the PHI denylist, or any
    string value looks like a raw numeric UID."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{_path}.{key}"
            if _key_is_phi(key):
                raise ValueError(f"PHI key found at {path}")
            if _value_is_phi(key):
                raise ValueError(f"PHI-like key found at {path}")
            assert_no_phi(value, path)
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            assert_no_phi(item, f"{_path}[{i}]")
    elif isinstance(obj, str):
        if _value_is_phi(obj):
            raise ValueError(f"PHI-like value found at {_path}")
    # numbers, bools, None: nothing to check
