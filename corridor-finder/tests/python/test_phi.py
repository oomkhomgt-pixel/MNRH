import pytest

from corridor_engine import phi


def test_strip_phi_drops_identifiers_keeps_whitelist():
    header = {
        "Modality": "CT",
        "PixelSpacing": [0.5, 0.5],
        "PatientName": "Doe^Jane",
        "PatientID": "12345",
        "PatientBirthDate": "19800101",
        "StudyInstanceUID": "1.2.840.10008.1.2.3.999",
        "SeriesInstanceUID": "1.2.840.10008.1.2.3.888",
        "InstitutionName": "Some Hospital",
        "SomeUnknownField": "whatever",
    }
    cleaned = phi.strip_phi(header)

    assert cleaned["Modality"] == "CT"
    assert cleaned["PixelSpacing"] == [0.5, 0.5]
    for key in ("PatientName", "PatientID", "PatientBirthDate", "InstitutionName", "SomeUnknownField"):
        assert key not in cleaned
    assert "StudyInstanceUID" not in cleaned
    assert "SeriesInstanceUID" not in cleaned
    assert cleaned["study_uid_hash"].startswith("sha256:")
    assert cleaned["series_uid_hash"].startswith("sha256:")

    # Never raises on unexpected input
    assert phi.strip_phi({}) == {}
    assert phi.strip_phi({"garbage": 1}) == {}


def test_hash_uid_stable_and_irreversible():
    uid = "1.2.840.10008.1.2.3.999"
    h1 = phi.hash_uid(uid)
    h2 = phi.hash_uid(uid)
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert uid not in h1

    # Different salt gives a different hash
    h3 = phi.hash_uid(uid, salt="other-salt")
    assert h3 != h1


def test_assert_no_phi_flags_nested_value():
    nested_key = {"outer": {"inner": {"PatientName": "Doe^Jane"}}}
    with pytest.raises(ValueError):
        phi.assert_no_phi(nested_key)

    nested_uid_value = {"outer": [{"some_field": "1234567890123456"}]}
    with pytest.raises(ValueError):
        phi.assert_no_phi(nested_uid_value)

    # Clean nested structure should not raise
    phi.assert_no_phi({"outer": {"inner": {"Modality": "CT", "count": 3}}})
