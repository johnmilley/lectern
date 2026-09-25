# PyInstaller spec: builds a standalone Lectern app for the platform you run it on.
#   pip install pyinstaller
#   pyinstaller packaging/lectern.spec
# Output: dist/Lectern/ (Linux, Windows) or dist/Lectern.app (macOS).
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "packaging", "launch.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "lectern", "resources"), os.path.join("lectern", "resources"))],
    hiddenimports=["mobi", "lectern.importer.mobi_rsv"],
    excludes=["tkinter", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtMultimedia", "PySide6.QtQuick3D", "PySide6.QtSql", "PySide6.QtTest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Lectern", console=False,
          icon=os.path.join(ROOT, "packaging", "lectern.ico") if sys.platform == "win32"
          and os.path.exists(os.path.join(ROOT, "packaging", "lectern.ico")) else None)
coll = COLLECT(exe, a.binaries, a.datas, name="Lectern")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="Lectern.app", bundle_identifier="app.lectern.reader",
                 info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "1.0.0"})
