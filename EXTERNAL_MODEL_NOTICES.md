# External model notices

This archive contains external machine-learning model assets used locally by
MangaLiveTranslator 0.1.0. The application source and installer are distributed separately.

## RapidOCR / PaddleOCR assets

- Project: RapidOCR and PaddleOCR PP-OCR models
- Source: https://github.com/RapidAI/RapidOCR
- Distributed assets: PP-OCRv6 detection and recognition models, recognition dictionary, and
  PP-OCRv4 orientation classifier
- License: Apache License 2.0 — https://www.apache.org/licenses/LICENSE-2.0
- Changes: none to the downloaded ONNX model data or dictionary

Exact download URLs and SHA-256 hashes are recorded in `manifests/ocr_models.json`.

## Helsinki-NLP OPUS-MT Japanese-to-English

- Model: `Helsinki-NLP/opus-mt-ja-en`
- Source: https://huggingface.co/Helsinki-NLP/opus-mt-ja-en
- Pinned revision: `0770961`
- License: Apache License 2.0 — https://www.apache.org/licenses/LICENSE-2.0
- Changes: converted to CTranslate2 format with int8 quantization

## Helsinki-NLP OPUS-MT Chinese-to-English

- Model: `Helsinki-NLP/opus-mt-zh-en`
- Source: https://huggingface.co/Helsinki-NLP/opus-mt-zh-en
- Pinned revision: `cf10909`
- License: Creative Commons Attribution 4.0 International —
  https://creativecommons.org/licenses/by/4.0/
- Attribution: Helsinki-NLP / Language Technology Research Group, University of Helsinki
- Changes: converted to CTranslate2 format with int8 quantization

Exact required filenames and conversion metadata are recorded in
`manifests/translation_models.json`. `MODEL_HASHES.json` records the files included in this
archive and their SHA-256 hashes.
