"""Pure-Python percutaneous screw corridor search engine.

No Slicer, Qt, or VTK imports live in this package — everything here must be
importable and testable with plain numpy/scipy under CPython 3.9+, so it can
run both inside 3D Slicer's Python and in a headless CI job. The one file
that talks to Slicer's MRML scene is ``CorridorFinder/CorridorFinder.py``,
which converts volumes/segmentations to the plain ``Volume``/numpy arrays
used here and back.
"""

__version__ = "0.1.0"
