"""Entry point for both `python -m rodraw` and the PyInstaller build.

The import is absolute on purpose. PyInstaller runs this file as the
top-level script, where its module name is `__main__` and it has no parent
package, so `from .app import main` raises ImportError at startup.
"""
import sys

from rodraw.app import main

if __name__ == "__main__":
    sys.exit(main())
