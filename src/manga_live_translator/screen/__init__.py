"""Screen discovery, region selection metadata, and bounded frame capture."""

from manga_live_translator.screen.capture import (
    CapturedFrame,
    FrameChangeDetector,
    LatestFrameQueue,
    RegionCaptureWorker,
    WindowsGdiCaptureProvider,
)
from manga_live_translator.screen.displays import (
    QtScreenProvider,
    ScreenDescriptor,
    validate_caption_region,
)

__all__ = [
    "CapturedFrame",
    "FrameChangeDetector",
    "LatestFrameQueue",
    "QtScreenProvider",
    "RegionCaptureWorker",
    "ScreenDescriptor",
    "WindowsGdiCaptureProvider",
    "validate_caption_region",
]
