# Privacy

MangaLiveTranslator processes screen captures, recognized text, and translations locally. The
application contains no telemetry, analytics, cloud translation, update checker, or network
client, and it does not upload captured content. Session translation caches exist only in memory.

Settings and rotating diagnostic logs are stored in the local per-user application-data folder.
Diagnostics include application/platform information, selected-region dimensions, status,
resource usage, and aggregate timings. They intentionally exclude pixels, OCR text, and
translations. Users choose whether to copy or share a diagnostic report.

Models are never downloaded by the application. The separate preparation script uses the network
only when a user explicitly runs it. Model providers' terms apply to those downloads.

