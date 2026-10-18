"""``pydensecrf.utils`` replacements used by manga-image-translator."""

import numpy as np

_EPS = 1e-8


def unary_from_softmax(sm, scale=None, clip=1e-5):
    """Convert a (C, N) softmax array into unary energies ``-log(p)``.

    Same contract as upstream: rows are classes, columns are pixels.
    """
    sm = np.asarray(sm, dtype=np.float32)
    if scale is not None:
        sm = scale * sm / (sm.max(axis=0, keepdims=True) + _EPS)
    if clip is not None:
        sm = np.clip(sm, clip, 1.0 - clip)
    return (-np.log(sm)).astype(np.float32)


def compute_unary(labels, M, GT_PROB=0.5):
    """Unary energies from a hard label map. Kept for import compatibility."""
    labels = np.asarray(labels).ravel()
    n_energy = -np.log((1.0 - GT_PROB) / (M - 1))
    p_energy = -np.log(GT_PROB)
    u = np.full((M, len(labels)), n_energy, dtype=np.float32)
    u[labels, np.arange(len(labels))] = p_energy
    return u


def create_pairwise_gaussian(sdims, shape):
    raise NotImplementedError("pydensecrf-shim does not implement create_pairwise_gaussian")


def create_pairwise_bilateral(sdims, schan, img, chdim=-1):
    raise NotImplementedError("pydensecrf-shim does not implement create_pairwise_bilateral")
