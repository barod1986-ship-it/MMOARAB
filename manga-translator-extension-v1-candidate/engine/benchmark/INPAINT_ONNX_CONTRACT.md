# MTE ONNX Inpainting Contract v1

Production V1 does not execute upstream LaMa/AOT Python repositories or permit runtime model downloads. A benchmark candidate must be converted offline into a reviewed local package and pinned by SHA-256 in the production model catalog/freeze.

The materialized package root must contain exactly the runtime model plus a sidecar named `mte-inpaint-contract.json`. Extra provenance/license files are allowed, but the model entry point must be a local regular `.onnx` file.

Required sidecar fields:

```json
{
  "schemaVersion": 1,
  "contract": "mte-onnx-inpaint-contract-v1",
  "candidateId": "lama-inpaint",
  "modelFile": "model.onnx",
  "imageInput": "image",
  "maskInput": "mask",
  "output": "output",
  "tensorLayout": "NCHW",
  "imageRange": "0..1-rgb",
  "maskSemantics": "1=erase",
  "padMultiple": 8
}
```

`candidateId` is either `lama-inpaint` or `aot-inpaint`. The conversion wrapper must expose RGB float32 `0..1` NCHW input and a float32 NCHW mask where `1` means erase. Output must be RGB float32 `0..1` NCHW and preserve input spatial dimensions after padding.

The Engine uses `CPUExecutionProvider` as the portable V1 baseline. It pads bottom/right with edge pixels to `padMultiple`, refuses non-finite or malformed outputs, clips output to `0..1`, and composites model output **only under the erase mask**. Unmasked source pixels are copied from the original image. The staged pipeline then applies the independent protected-SFX composite and exact lossless encode/decode verification.

A converted package is **not release-ready** merely because it loads. Before freeze it still needs: exact artifact SHA-256, checkpoint provenance/license approval, benchmark-use approval, the clean-reference and human inpainting gates, and the platform/hardware runtime evidence required by REV10.
