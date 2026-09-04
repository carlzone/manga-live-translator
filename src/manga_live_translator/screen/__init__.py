"""Screen discovery, region selection metadata, and bounded frame capture."""

from manga_live_translator.screen.automation import (
    FrameFingerprint,
    ScrollDisplacement,
    VerticalScrollTracker,
    ViewportSettlingController,
    ViewportSnapshot,
    ViewportState,
    fingerprint_difference,
    fingerprint_frame,
)
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
    "FrameFingerprint",
    "ScrollDisplacement",
    "VerticalScrollTracker",
    "LatestFrameQueue",
    "QtScreenProvider",
    "RegionCaptureWorker",
    "ScreenDescriptor",
    "ViewportSnapshot",
    "ViewportState",
    "ViewportSettlingController",
    "WindowsGdiCaptureProvider",
    "fingerprint_difference",
    "fingerprint_frame",
    "validate_caption_region",
]
