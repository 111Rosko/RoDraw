# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for RoDraw.

Builds a one-folder application (dist/RoDraw/RoDraw.exe). One-folder rather
than one-file because a one-file build unpacks itself to a temp directory on
every launch, which adds seconds to start-up -- the wrong trade for a tool
someone opens and closes repeatedly during a lesson.
"""
import re
from pathlib import Path

PROJECT = Path(SPECPATH).resolve().parent


def _write_version_resource() -> str:
    """Rebuild the Windows version resource from the one authoritative number.

    It used to be a hand-edited file and duly drifted: 1.0.1 shipped with
    1.0.0 on its Properties tab. Deriving it here means the two can never
    disagree again.
    """
    source = (PROJECT / 'rodraw' / '__init__.py').read_text(encoding='utf-8')
    version = re.search(r'__version__ = "([^"]+)"', source).group(1)
    parts = tuple(int(n) for n in version.split('.'))[:4]
    quad = parts + (0,) * (4 - len(parts))
    dotted = '.'.join(str(n) for n in quad)
    path = PROJECT / 'build' / 'version_info.txt'
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'(file|prod)vers=\(\d+, \d+, \d+, \d+\)',
                  lambda m: f'{m.group(1)}vers={quad}', text)
    text = re.sub(r"(StringStruct\('(?:File|Product)Version', ')[\d.]+(')",
                  lambda m: m.group(1) + dotted + m.group(2), text)
    path.write_text(text, encoding='utf-8')
    return str(path)


VERSION_RESOURCE = _write_version_resource()

a = Analysis(
    [str(PROJECT / 'rodraw' / '__main__.py')],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=[
        (str(PROJECT / 'rodraw' / 'resources' / 'rodraw.ico'), 'rodraw/resources'),
        (str(PROJECT / 'rodraw' / 'resources' / 'logo.png'), 'rodraw/resources'),
    ],
    # The language tables are pulled in with importlib at runtime, so static
    # analysis never sees them; without this the build ships English only.
    hiddenimports=[f'rodraw.lang.{code}' for code in
                   ['bg', 'de', 'es', 'fr', 'it', 'pt', 'ru', 'tr', 'uk']],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt ships a lot we never touch; dropping these keeps the install lean.
    excludes=[
        'tkinter', 'unittest', 'pydoc_data',
        'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebChannel',
        'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuick3D', 'PyQt6.Qt3DCore',
        'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets', 'PyQt6.QtBluetooth',
        'PyQt6.QtNetwork', 'PyQt6.QtSql', 'PyQt6.QtTest', 'PyQt6.QtCharts',
        'PyQt6.QtDataVisualization', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
        'PyQt6.QtPositioning', 'PyQt6.QtSerialPort', 'PyQt6.QtSensors',
        'PySide6', 'shiboken6', 'numpy', 'PIL',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RoDraw',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,              # GUI app -- never flash a console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT / 'rodraw' / 'resources' / 'rodraw.ico'),
    version=VERSION_RESOURCE,
    # PyInstaller calls this folder "_internal" by default, which looks
    # alarming in an installed program. Everything Qt and Python need lives
    # here; only RoDraw.exe sits beside it.
    contents_directory='RoDraw',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RoDraw',
)
