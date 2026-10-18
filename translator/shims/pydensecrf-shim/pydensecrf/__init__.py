"""Stand-in for the real ``pydensecrf``.

The upstream package ships no wheel for Windows/CPython 3.12 and builds from a
Cython C++ source tree, which needs an MSVC toolchain this machine does not
have.  manga-image-translator imports it at module scope in
``manga_translator/mask_refinement/text_mask_utils.py`` and uses exactly one
thing from it: a dense-CRF pass that tightens the per-textline inpainting mask
against glyph edges.

This shim keeps that import working and degrades the CRF pass to identity, so
``refine_mask`` hands back the connected-component mask it was given.  The mask
is dilated immediately afterwards anyway (``complete_mask``, and again via
``mask_dilation_offset``), so the practical effect is a slightly looser repaint
area around removed text.

To get the real thing back: install the MSVC C++ build tools, then
``pip uninstall pydensecrf-shim && pip install
'pydensecrf@https://github.com/lucasb-eyer/pydensecrf/archive/refs/heads/master.zip'``.
"""

import sys

_WARNED = False


def _warn_once():
    global _WARNED
    if not _WARNED:
        _WARNED = True
        print(
            "[pydensecrf-shim] real pydensecrf is not installed; "
            "CRF mask refinement is running as identity (masks will be slightly looser)",
            file=sys.stderr,
        )


__all__ = ["densecrf", "utils"]
