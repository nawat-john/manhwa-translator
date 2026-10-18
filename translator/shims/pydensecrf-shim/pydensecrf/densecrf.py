"""``pydensecrf.densecrf`` replacement: an identity dense-CRF.

Pairwise terms are accepted and ignored.  ``inference`` returns the negated
unary energies, i.e. the log-probabilities the caller started from, so the
caller's ``np.argmax(Q, axis=0)`` reproduces its own input mask instead of a
CRF-refined one.
"""

import numpy as np

from . import _warn_once

# Kernel / normalization enums, kept so attribute access matches upstream.
CONST_KERNEL = 0
DIAG_KERNEL = 1
FULL_KERNEL = 2

NO_NORMALIZATION = 0
NORMALIZE_BEFORE = 1
NORMALIZE_AFTER = 2
NORMALIZE_SYMMETRIC = 3


class DenseCRF:
    def __init__(self, npixels, nlabels):
        _warn_once()
        self.npixels = int(npixels)
        self.nlabels = int(nlabels)
        self._unary = None

    def setUnaryEnergy(self, unary, normalization=None):
        u = np.asarray(unary, dtype=np.float32)
        if u.ndim != 2:
            raise ValueError(f"unary must be 2-D (nlabels, npixels), got shape {u.shape}")
        self._unary = u

    # Pairwise terms have no effect in the shim.
    def addPairwiseEnergy(self, features, compat=None, kernel=DIAG_KERNEL,
                          normalization=NORMALIZE_SYMMETRIC):
        return None

    def inference(self, n_iterations=5):
        if self._unary is None:
            raise RuntimeError("setUnaryEnergy must be called before inference")
        # -unary == log p, so argmax over this equals argmax over the input
        # class probabilities: the identity refinement.
        return -self._unary

    def startInference(self):
        return self.inference(), None, None

    def stepInference(self, *args, **kwargs):
        return None

    def klDivergence(self, *args, **kwargs):
        return 0.0

    def map(self, n_iterations=5):
        return np.argmax(self.inference(n_iterations), axis=0)


class DenseCRF2D(DenseCRF):
    def __init__(self, w, h, nlabels):
        super().__init__(int(w) * int(h), nlabels)
        self.w = int(w)
        self.h = int(h)

    def addPairwiseGaussian(self, sxy, compat, kernel=DIAG_KERNEL,
                            normalization=NORMALIZE_SYMMETRIC):
        return None

    def addPairwiseBilateral(self, sxy, srgb, rgbim, compat,
                             kernel=DIAG_KERNEL, normalization=NORMALIZE_SYMMETRIC):
        return None
