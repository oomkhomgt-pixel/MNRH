"""Planned screws as DICOM SEG on the original CT (for Brainlab). Round trip:
a synthetic CT series is written, the screws exported, the SEG read back,
and the screw found where it was planned, on the same series, patient and
frame of reference."""
import numpy as np
import pytest

pydicom = pytest.importorskip("pydicom")
hd = pytest.importorskip("highdicom")

from corridor_engine.dicom_seg import ScrewObject, rasterise, write_screws_seg  # noqa: E402

SPACING = (0.8, 0.8)  # between rows, between columns
THICKNESS = 1.0


def _ct_series(n=40, rows=64, cols=64, shuffle=True):
    """A small axial CT series in LPS, its slices handed over out of order
    as a file listing would."""
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    study, series, frame = generate_uid(), generate_uid(), generate_uid()
    out = []
    for z in range(n):
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = generate_uid()
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, series, frame
        ds.PatientName, ds.PatientID, ds.PatientBirthDate, ds.PatientSex = "Test^Phantom", "PHANTOM-1", "19700101", "O"
        ds.StudyDate, ds.StudyTime, ds.StudyID, ds.AccessionNumber = "20260101", "120000", "1", "A1"
        ds.ReferringPhysicianName, ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "", "CT", 1, z + 1
        ds.Manufacturer = "test"
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [-25.0, -25.0, 100.0 + z * THICKNESS]
        ds.PixelSpacing = list(SPACING)
        ds.SliceThickness = THICKNESS
        ds.Rows, ds.Columns = rows, cols
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleIntercept, ds.RescaleSlope = -1024, 1
        ds.PixelData = np.zeros((rows, cols), dtype=np.int16).tobytes()
        out.append(ds)
    if shuffle:
        out = [out[i] for i in np.random.default_rng(0).permutation(len(out))]
    return out


def _lps_to_ras(p):
    return (-p[0], -p[1], p[2])


def test_the_screw_lands_where_it_was_planned(tmp_path):
    ct = _ct_series()
    # In LPS: from (-10, 0, 105) to (15, 5, 130); handed over in RAS.
    start, tip = _lps_to_ras((-10.0, 0.0, 105.0)), _lps_to_ras((15.0, 5.0, 130.0))
    screw = ScrewObject("LC-2 right 7.3 x 36 mm", start, tip, 7.3)
    ordered, mask = rasterise(ct, [screw])
    zs = [float(ds.ImagePositionPatient[2]) for ds in ordered]
    assert zs == sorted(zs), "slices are put in order along their normal"
    # The axis is inside; 1 mm beyond the radius is not.
    a, b = np.array([-10.0, 0.0, 105.0]), np.array([15.0, 5.0, 130.0])
    u = (b - a) / np.linalg.norm(b - a)
    side = np.cross(u, [0.0, 0.0, 1.0])
    side /= np.linalg.norm(side)

    def pixel(p):
        z = int(round((p[2] - 100.0) / THICKNESS))
        c = int(round((p[0] + 25.0) / SPACING[1]))
        r = int(round((p[1] + 25.0) / SPACING[0]))
        return z, r, c

    for t in (0.25, 0.5, 0.75):
        assert mask[pixel(a + t * (b - a)) + (0,)], f"axis at {t}"
        assert not mask[pixel(a + t * (b - a) + (3.65 + 1.0) * side) + (0,)], f"outside at {t}"
    # Nothing beyond the tip or before the start.
    assert not mask[pixel(b + 3.0 * u) + (0,)] and not mask[pixel(a - 3.0 * u) + (0,)]


def test_the_seg_references_the_same_series_patient_and_frame(tmp_path):
    ct = _ct_series()
    screws = [ScrewObject("posterior column right 6.5 x 30 mm", _lps_to_ras((-5.0, -5.0, 104.0)),
                          _lps_to_ras((-5.0, 5.0, 130.0)), 6.5),
              ScrewObject("LC-2 right 7.3 x 25 mm", _lps_to_ras((5.0, 0.0, 110.0)), _lps_to_ras((10.0, 0.0, 132.0)), 7.3)]
    path = str(tmp_path / "screws.dcm")
    summary = write_screws_seg(ct, screws, path)
    seg = hd.seg.segread(path)
    assert seg.PatientID == "PHANTOM-1" and str(seg.PatientName) == "Test^Phantom"
    assert seg.FrameOfReferenceUID == ct[0].FrameOfReferenceUID == summary["frame_of_reference"]
    assert seg.StudyInstanceUID == ct[0].StudyInstanceUID
    assert seg.SeriesInstanceUID != ct[0].SeriesInstanceUID, "a new series, alongside the CT"
    referenced = {item.ReferencedSOPInstanceUID
                  for series in seg.ReferencedSeriesSequence for item in series.ReferencedInstanceSequence}
    assert referenced == {ds.SOPInstanceUID for ds in ct}, "every CT slice is referenced"
    assert [d.SegmentLabel for d in seg.SegmentSequence] == [s.label for s in screws]
    assert all(d.SegmentedPropertyTypeCodeSequence[0].CodeMeaning in ("Screw", "Bone Screw") for d in seg.SegmentSequence)
    assert all(v > 0 for v in summary["voxels"].values())


def test_a_ct_brainlab_cannot_read_a_binary_seg_on_is_refused(tmp_path):
    ct = _ct_series(cols=60)
    with pytest.raises(ValueError, match="multiple of 8"):
        write_screws_seg(ct, [ScrewObject("s", (0.0, 0.0, 110.0), (0.0, 0.0, 120.0), 6.5)], str(tmp_path / "x.dcm"))


def test_a_screw_outside_the_ct_is_refused(tmp_path):
    with pytest.raises(ValueError, match="outside the CT"):
        write_screws_seg(_ct_series(), [ScrewObject("far", (0.0, 0.0, 500.0), (0.0, 0.0, 520.0), 6.5)],
                         str(tmp_path / "x.dcm"))
