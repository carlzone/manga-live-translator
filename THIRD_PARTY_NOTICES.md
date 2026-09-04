# Third-party notices

MangaLiveTranslator 0.1 is distributed without model weights. Users who install external
models are responsible for retaining the notices required by those models.

| Component | Use | License / attribution |
|---|---|---|
| RapidOCR and PP-OCRv6 model code | Caption OCR | Apache License 2.0 |
| ONNX Runtime | Local OCR inference | MIT License |
| CTranslate2 | Local caption translation runtime | MIT License |
| SentencePiece | Translation tokenization | Apache License 2.0 |
| Helsinki-NLP OPUS-MT Japanese-to-English model | External translation model | Apache License 2.0; retain its model card |
| Helsinki-NLP OPUS-MT Chinese-to-English model | External translation model | CC BY 4.0; attribution and model card must accompany redistribution |
Exact external model repositories, pinned revisions, filenames, and hashes are recorded in
`tools/ocr_models.json`, `tools/translation_models.json`, and the release README. This file
is a distribution notice, not a replacement for the upstream license texts.

