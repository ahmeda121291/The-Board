"""Allow ``python -m boardroom ...`` as an alias for the ``boardroom`` CLI.

Mirrors the ``boardroom`` console-script entry point (``boardroom.cli:main``) so
the package can be driven either way. Run inside the project venv so the deps
are present (``.venv\\Scripts\\python.exe -m boardroom decide``).
"""

from __future__ import annotations

import sys

from boardroom.cli import main

if __name__ == "__main__":
    sys.exit(main())
