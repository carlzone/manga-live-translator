# Model Preparation

MangaLiveTranslator uses four RapidOCR assets and CPU-int8 CTranslate2 OPUS-MT models for
Japanese-to-English and Chinese-to-English translation. Models remain external to source and
release packages and are never downloaded by the application.

```powershell
.\tools\download-models.ps1
.\tools\download-models.ps1 -IncludeTranslation
uv run python tools\model_preflight.py --output build\model-preflight.json
```

Pinned OCR URLs and hashes are in `tools/ocr_models.json`. Translation source repositories,
revisions, required files, licenses, and conversion settings are in
`tools/translation_models.json`. `-IncludeTranslation` requires Hugging Face CLI and the
CTranslate2 Transformers converter. Retain upstream model cards when distributing converted
weights.

Expected layout:

```text
models/ocr/PP-OCRv6_det_small.onnx
models/ocr/PP-OCRv6_rec_small.onnx
models/ocr/ppocrv6_dict.txt
models/ocr/ch_ppocr_mobile_v2.0_cls_mobile.onnx
models/translation/ja-en/{model.bin,config.json,source.spm,target.spm}
models/translation/zh-en/{model.bin,config.json,source.spm,target.spm}
```

Run OCR and translation benchmarks explicitly after preflight. Unit tests mock inference and do
not require model downloads.
