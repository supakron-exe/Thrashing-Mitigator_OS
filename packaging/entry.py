"""Windowed distribution entry point. Optional diagnostic never runs Optimize."""
import sys

if '--verify-package' in sys.argv:
    from package_check import run
    raise SystemExit(run())

from main import main
raise SystemExit(main())
