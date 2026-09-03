# Third-party notices

MangaLiveTranslator 0.2 is distributed without model weights. Users who install external
models are responsible for retaining the notices required by those models.

| Component | Use | License / attribution |
|---|---|---|
| RapidOCR and PP-OCRv6 model code | Caption OCR | Apache License 2.0 |
| ONNX Runtime | Local OCR and VAD inference | MIT License |
| CTranslate2 | Local caption translation runtime | MIT License |
| SentencePiece | Translation tokenization | Apache License 2.0 |
| Helsinki-NLP OPUS-MT Japanese-to-English model | External translation model | Apache License 2.0; retain its model card |
| Helsinki-NLP OPUS-MT Chinese-to-English model | External translation model | CC BY 4.0; attribution and model card must accompany redistribution |
| whisper.cpp | Local speech translation runtime | MIT License |
| Whisper model weights | External speech model | Use under the license supplied with the selected model |
| Silero VAD | External voice-activity model | MIT License |

Exact external model repositories, pinned revisions, filenames, and hashes are recorded in
`tools/ocr_models.json`, `tools/translation_models.json`, and the release README. This file
is a distribution notice, not a replacement for the upstream license texts.

