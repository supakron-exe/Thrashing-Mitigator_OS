# Local FluentUI patches

Upstream remains pinned to `617986a17c9850ecb365bc02713433abab79c7aa`. The MIT notices remain unchanged.

13 October 2026 — `FluentUI/FluFrameless.py`: decode the two WM_NCHITTEST screen-coordinate words as signed 16-bit values, matching GET_X_LPARAM / GET_Y_LPARAM. Negative coordinates on monitors left of or above the primary monitor previously made client controls return resize hit codes. Also correct the bottom-edge branch from a duplicate top condition to the bottom condition. Window resizing remains enabled.

Regression coverage: `tests/test_frameless.py` (client area, four edges, four corners on positive/negative monitor origins) and `tests/check_native_frame.py` (native messages on real Qt windows plus pointer clicks on a theme button).
