"""Paste-into-Slicer diagnostic for "Corridor Finder is not loaded".

Run this in Slicer's Python Interactor (Window > Python Interactor):

    exec(open(r"<path-to>/corridor-finder/tools/diagnose.py", encoding="utf-8").read())

or just copy the whole file's contents into the interactor and press Enter.

It must NOT live in CorridorFinder/: Slicer loads every .py file in a module
directory as a scripted module, so there it ran at every startup and was
reported as a module that "failed to be instantiated".

It prints, in one go, everything needed to diagnose a module that will not
load: the configured module paths, whether Slicer can see the file, the
Python/Slicer versions, whether every engine dependency imports, and — most
importantly — the FULL traceback from actually importing the module, which
is the thing Slicer's UI usually hides.

Copy the whole output and send it back.
"""

print("=" * 70)
print("CORRIDOR FINDER DIAGNOSTIC")
print("=" * 70)

import os
import sys
import traceback

# ---------------------------------------------------------------- versions
try:
    import slicer

    print("\n[1] VERSIONS")
    print("  Slicer     :", slicer.app.applicationVersion)
    print("  Slicer rev :", slicer.app.repositoryRevision)
    print("  Python     :", sys.version.replace("\n", " "))
    print("  Platform   :", sys.platform)
except Exception:
    print("  FAILED to query Slicer version:")
    traceback.print_exc()

# ----------------------------------------------------------- module paths
print("\n[2] ADDITIONAL MODULE PATHS CONFIGURED IN SLICER")
try:
    settings = slicer.app.revisionUserSettings()
    paths = settings.value("Modules/AdditionalPaths")
    print("  raw value:", repr(paths))
    if isinstance(paths, str):
        paths = [paths]
    for p in paths or []:
        print("   -", p)
        if os.path.isdir(p):
            entries = sorted(os.listdir(p))
            print("       exists, contains:", entries[:20])
            if "CorridorFinder.py" in entries:
                print("       >>> CorridorFinder.py FOUND here")
        else:
            print("       !!! THIS PATH DOES NOT EXIST OR IS NOT A DIRECTORY")
    if not paths:
        print("  !!! No additional module paths are configured at all.")
        print("      Edit > Application Settings > Modules > Additional module paths")
except Exception:
    traceback.print_exc()

# ------------------------------------------------- is the module known?
print("\n[3] DOES SLICER KNOW ABOUT THE MODULE?")
try:
    factory = slicer.app.moduleManager().factoryManager()
    names = list(factory.instantiatedModuleNames())
    matches = [n for n in names if "corridor" in n.lower()]
    print("  modules whose name contains 'corridor':", matches or "NONE")
    print("  total modules loaded:", len(names))
    if hasattr(factory, "ignoredModuleNames"):
        ignored = [n for n in factory.ignoredModuleNames() if "corridor" in n.lower()]
        print("  ignored modules matching 'corridor':", ignored or "none")
except Exception:
    traceback.print_exc()

# ------------------------------------------------------- dependencies
print("\n[4] ENGINE DEPENDENCIES IN SLICER'S PYTHON")
for mod in ("numpy", "scipy", "skimage", "jsonschema", "PIL"):
    try:
        m = __import__(mod)
        print(f"  {mod:12s} OK   version={getattr(m, '__version__', '?')}")
    except Exception as exc:
        print(f"  {mod:12s} FAIL {type(exc).__name__}: {exc}")

# --------------------------------------------- can we import the engine?
print("\n[5] CAN corridor_engine BE IMPORTED?")
this_dir = None
try:
    # Try to locate the project root from the configured module paths.
    candidates = []
    settings = slicer.app.revisionUserSettings()
    paths = settings.value("Modules/AdditionalPaths")
    if isinstance(paths, str):
        paths = [paths]
    for p in paths or []:
        if os.path.isdir(p):
            candidates.append(p)
            candidates.append(os.path.abspath(os.path.join(p, "..")))
    for c in candidates:
        if os.path.isdir(os.path.join(c, "corridor_engine")):
            this_dir = c
            break
    print("  project root guess:", this_dir)
    if this_dir and this_dir not in sys.path:
        sys.path.insert(0, this_dir)
    import corridor_engine

    print("  corridor_engine OK from", corridor_engine.__file__)
except Exception:
    print("  corridor_engine IMPORT FAILED:")
    traceback.print_exc()

# ------------------------------- the important one: import the module
print("\n[6] IMPORTING CorridorFinder.py DIRECTLY (the real error, if any)")
try:
    settings = slicer.app.revisionUserSettings()
    paths = settings.value("Modules/AdditionalPaths")
    if isinstance(paths, str):
        paths = [paths]
    module_file = None
    for p in paths or []:
        candidate = os.path.join(p, "CorridorFinder.py")
        if os.path.isfile(candidate):
            module_file = candidate
            break
    if module_file is None:
        print("  Could not find CorridorFinder.py under any configured module path.")
        print("  >>> This alone explains 'not loaded': fix the path setting.")
    else:
        print("  importing:", module_file)
        import importlib.util

        spec = importlib.util.spec_from_file_location("CorridorFinderDiag", module_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print("  >>> MODULE IMPORTED SUCCESSFULLY")
        print("  engine import error inside module:", getattr(mod, "_ENGINE_IMPORT_ERROR", None))
        try:
            logic = mod.CorridorFinderLogic()
            print("  >>> CorridorFinderLogic() constructed OK")
            print("      corridors loaded:", list(logic.corridor_defs.keys()))
        except Exception:
            print("  CorridorFinderLogic() FAILED:")
            traceback.print_exc()
except Exception:
    print("  MODULE IMPORT FAILED — this is the error that matters:")
    traceback.print_exc()

print("\n" + "=" * 70)
print("END OF DIAGNOSTIC — copy everything above this line")
print("=" * 70)
