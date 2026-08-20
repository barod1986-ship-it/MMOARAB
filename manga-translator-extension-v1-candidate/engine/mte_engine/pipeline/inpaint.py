from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from ..errors import EngineApiError
from ..benchmark.common import is_sha256, sha256_path


INPAINT_SELECTION_REVISION = "mte-onnx-inpaint-contract-v1"
INPAINT_CONTRACT_FILENAME = "mte-inpaint-contract.json"
SUPPORTED_INPAINT_CANDIDATES = frozenset({"lama-inpaint", "aot-inpaint"})


class ReferenceSolidInpainter:
    adapter_id = "reference-solid-inpaint-v1"

    def inpaint(self, image: Image.Image, erase_mask: Image.Image) -> Image.Image:
        base = image.convert("RGBA").copy()
        fill = Image.new("RGBA", base.size, (255, 255, 255, 255))
        base.paste(fill, (0, 0), erase_mask)
        return base


class ProductionInpainter:
    """Run a frozen inpainting candidate through the MTE ONNX wrapper contract.

    Upstream LaMa/AOT implementation details are handled by a reviewed conversion
    step. Runtime accepts only a local model package whose sidecar declares the fixed
    MTE input/output contract. The model is never allowed to modify pixels outside the
    supplied erase mask.
    """

    adapter_id = INPAINT_SELECTION_REVISION

    def __init__(
        self,
        *,
        candidate_id: str,
        model_dir: Path,
        session_factory: Callable[[str, list[str]], Any] | None = None,
    ) -> None:
        if candidate_id not in SUPPORTED_INPAINT_CANDIDATES:
            raise EngineApiError("model_not_ready", f"Unsupported frozen inpainting candidate: {candidate_id}.", 409)
        self.candidate_id = candidate_id
        self.model_dir = Path(model_dir)
        self.contract = _load_contract(self.model_dir, candidate_id)
        model_path = self.model_dir / self.contract["modelFile"]
        if not model_path.is_file() or model_path.is_symlink():
            raise EngineApiError("model_not_ready", "Frozen ONNX inpainting model is missing or unsafe.", 409)
        if sha256_path(model_path) != self.contract["modelSha256"]:
            raise EngineApiError("model_not_ready", "Frozen ONNX inpainting model hash does not match its reviewed package contract.", 409)
        derivation_path = self.model_dir / self.contract["derivationManifest"]
        if not derivation_path.is_file() or derivation_path.is_symlink() or sha256_path(derivation_path) != self.contract["derivationManifestSha256"]:
            raise EngineApiError("model_not_ready", "Frozen ONNX inpainting derivation manifest is missing or hash-mismatched.", 409)
        try:
            derivation = json.loads(derivation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EngineApiError("model_not_ready", "Frozen ONNX inpainting derivation manifest is unreadable.", 409) from exc
        expected_artifact_id = "lama-big" if candidate_id == "lama-inpaint" else "aot-gan-places2"
        if not isinstance(derivation, dict) or derivation.get("artifactId") != expected_artifact_id or derivation.get("candidateId") != candidate_id or derivation.get("runtimeContract") != INPAINT_SELECTION_REVISION or derivation.get("modelSha256") != self.contract["modelSha256"]:
            raise EngineApiError("model_not_ready", "Frozen ONNX inpainting derivation identity does not match its runtime contract.", 409)
        if session_factory is None:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise EngineApiError("model_not_ready", "ONNX Runtime production dependency is not installed.", 409) from exc

            def session_factory(path: str, providers: list[str]):
                opts = ort.SessionOptions()
                opts.enable_mem_pattern = True
                opts.enable_cpu_mem_arena = True
                return ort.InferenceSession(path, sess_options=opts, providers=providers)

        # CPUExecutionProvider is the portable V1 baseline. Hardware-accelerated
        # variants can be benchmarked/frozen under a new runtime revision later.
        self.session = session_factory(str(model_path), ["CPUExecutionProvider"])
        self._validate_session_io()

    def _validate_session_io(self) -> None:
        inputs = {item.name for item in self.session.get_inputs()}
        outputs = {item.name for item in self.session.get_outputs()}
        required_inputs = {self.contract["imageInput"], self.contract["maskInput"]}
        if not required_inputs.issubset(inputs) or self.contract["output"] not in outputs:
            raise EngineApiError("model_not_ready", "Frozen ONNX inpainting model does not match the MTE I/O contract.", 409)

    def inpaint(self, image: Image.Image, erase_mask: Image.Image) -> Image.Image:
        try:
            import numpy as np
        except ImportError as exc:
            raise EngineApiError("model_not_ready", "NumPy production inpainting dependency is not installed.", 409) from exc
        if image.size != erase_mask.size:
            raise EngineApiError("inpaint_failed", "Inpainting mask dimensions do not match source image.", 500)
        mask_l = erase_mask.convert("L")
        if mask_l.getbbox() is None:
            return image.convert("RGBA").copy()

        source = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        mask = np.asarray(mask_l, dtype=np.float32) / 255.0
        mask = (mask >= 0.5).astype(np.float32)
        h, w = source.shape[:2]
        multiple = int(self.contract["padMultiple"])
        pad_h = (-h) % multiple
        pad_w = (-w) % multiple
        source_pad = np.pad(source, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
        mask_pad = np.pad(mask, ((0, pad_h), (0, pad_w)), mode="constant", constant_values=0.0)
        image_tensor = np.transpose(source_pad, (2, 0, 1))[None, ...].astype(np.float32, copy=False)
        mask_tensor = mask_pad[None, None, ...].astype(np.float32, copy=False)

        try:
            result = self.session.run(
                [self.contract["output"]],
                {
                    self.contract["imageInput"]: image_tensor,
                    self.contract["maskInput"]: mask_tensor,
                },
            )[0]
        except Exception as exc:
            raise EngineApiError("inpaint_failed", "Frozen ONNX inpainting inference failed.", 500) from exc

        array = np.asarray(result, dtype=np.float32)
        if array.ndim != 4 or array.shape[0] != 1 or array.shape[1] != 3:
            raise EngineApiError("inpaint_failed", "Frozen ONNX inpainting output shape is invalid.", 500)
        array = np.transpose(array[0], (1, 2, 0))[:h, :w, :]
        if array.shape != source.shape or not np.isfinite(array).all():
            raise EngineApiError("inpaint_failed", "Frozen ONNX inpainting output is invalid.", 500)
        array = np.clip(array, 0.0, 1.0)

        # Even if a model predicts a full image, only the reviewed erase mask is
        # composited. This is a second destructive-edit boundary before the pipeline's
        # protected-pixel composite and final exact-lossless verification.
        blend = mask[..., None]
        composed = source * (1.0 - blend) + array * blend
        rgb = Image.fromarray(np.rint(composed * 255.0).astype(np.uint8), mode="RGB")
        rgba = rgb.convert("RGBA")
        rgba.putalpha(image.convert("RGBA").getchannel("A"))
        return rgba


def _load_contract(model_dir: Path, candidate_id: str) -> dict[str, Any]:
    path = model_dir / INPAINT_CONTRACT_FILENAME
    if not path.is_file() or path.is_symlink():
        raise EngineApiError("model_not_ready", "Frozen inpainting package has no MTE contract sidecar.", 409)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineApiError("model_not_ready", "Frozen inpainting contract is unreadable.", 409) from exc
    expected = {
        "schemaVersion": 1,
        "contract": INPAINT_SELECTION_REVISION,
        "candidateId": candidate_id,
        "imageInput": "image",
        "maskInput": "mask",
        "output": "output",
        "tensorLayout": "NCHW",
        "imageRange": "0..1-rgb",
        "maskSemantics": "1=erase",
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise EngineApiError("model_not_ready", f"Frozen inpainting contract field is invalid: {key}.", 409)
    model_file = data.get("modelFile")
    pad_multiple = data.get("padMultiple")
    model_sha256 = data.get("modelSha256")
    derivation_manifest = data.get("derivationManifest")
    derivation_manifest_sha256 = data.get("derivationManifestSha256")
    if not isinstance(model_file, str) or not model_file.endswith(".onnx") or "/" in model_file or "\\" in model_file or model_file in {"", ".", ".."}:
        raise EngineApiError("model_not_ready", "Frozen inpainting modelFile is invalid.", 409)
    if not isinstance(pad_multiple, int) or isinstance(pad_multiple, bool) or pad_multiple < 1 or pad_multiple > 256:
        raise EngineApiError("model_not_ready", "Frozen inpainting padMultiple is invalid.", 409)
    if not is_sha256(model_sha256):
        raise EngineApiError("model_not_ready", "Frozen inpainting modelSha256 is invalid.", 409)
    if derivation_manifest != "mte-derivation.json" or not is_sha256(derivation_manifest_sha256):
        raise EngineApiError("model_not_ready", "Frozen inpainting derivation manifest pin is invalid.", 409)
    return data
