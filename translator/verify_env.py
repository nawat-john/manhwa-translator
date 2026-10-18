"""Sanity-check the venv: imports resolve, CUDA is visible, caches point at D:."""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "manga-image-translator"))
os.environ.setdefault("HF_HOME", str(HERE / "hf-cache"))

ok = True


def check(label, fn):
    global ok
    try:
        print(f"{label:<22} {fn()}")
    except Exception as e:  # noqa: BLE001 - a failed check should not stop the rest
        ok = False
        print(f"{label:<22} FAILED: {type(e).__name__}: {e}")


def _torch():
    import torch
    dev = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu only"
    return f"{torch.__version__}  cuda={torch.cuda.is_available()}  {dev}"


check("python", lambda: sys.version.split()[0])
check("executable", lambda: sys.executable)
check("torch", _torch)
check("numpy", lambda: __import__("numpy").__version__)
check("opencv", lambda: __import__("cv2").__version__)
check("transformers", lambda: __import__("transformers").__version__)
check("shapely", lambda: __import__("shapely").__version__)
check("onnxruntime", lambda: __import__("onnxruntime").__version__)
check("img2pdf", lambda: __import__("img2pdf").__version__)
check("pydensecrf shim", lambda: __import__("pydensecrf.densecrf", fromlist=["x"]).__file__)
check("manga_ocr", lambda: __import__("manga_ocr").__name__)
check("manga_translator", lambda: __import__("manga_translator.config", fromlist=["Config"]).__name__)
check("HF_HOME", lambda: os.environ["HF_HOME"])

print("\nOK" if ok else "\nsome checks failed")
sys.exit(0 if ok else 1)
