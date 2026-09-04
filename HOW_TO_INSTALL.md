# How to install MangaLiveTranslator 0.1.0

MangaLiveTranslator is distributed as a portable Windows application plus a separate external-
model package. Both archives are required for OCR and translation.

## Portable installation

1. Download `MangaLiveTranslator-0.1.0-portable.zip` and
   `MangaLiveTranslator-0.1.0-models.zip`.
2. Create a folder such as `C:\Apps\MangaLiveTranslator`.
3. Extract both ZIP files directly into that same folder.
4. Confirm that `MangaLiveTranslator.exe` and the `models` directory are immediate siblings.
5. Run `MangaLiveTranslator.exe`.

The resulting layout must be:

```text
MangaLiveTranslator/
  MangaLiveTranslator.exe
  models/
    ocr/
    translation/
      ja-en/
      zh-en/
```

Do not extract the model ZIP into an additional nested directory such as
`MangaLiveTranslator/models/MangaLiveTranslator-0.1.0-models/models`.

## Installer-based installation

1. Run `MangaLiveTranslator-0.1.0-setup.exe` and complete the wizard.
2. Extract `MangaLiveTranslator-0.1.0-models.zip` directly into:
   `%LOCALAPPDATA%\Programs\MangaLiveTranslator`
3. Accept directory merging if Windows asks. The installer already creates the empty model
   directories.
4. Start MangaLiveTranslator from the Start Menu or optional desktop shortcut.

The installer is unsigned, so Windows SmartScreen may display a warning. Verify the published
SHA-256 checksum before selecting **More info** and **Run anyway**.

## First run

1. Select the source language and reading order.
2. Select and preview the manga reader region.
3. Select **Start** and wait for the local models to load.

If the app reports missing model assets, close it and recheck that the `models` directory is beside
the executable and contains both `ocr` and `translation` subdirectories.
