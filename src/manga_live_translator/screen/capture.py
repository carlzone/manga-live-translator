"""Restartable bounded screen-region capture and frame-change detection."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PySide6.QtCore import QThread, Signal

from manga_live_translator.config import CaptionRegion
from manga_live_translator.screen.displays import ScreenDescriptor
from manga_live_translator.workers.messages import RuntimeStatus


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    pixels: bytes
    width: int
    height: int
    stride: int
    captured_at: float
    region: CaptionRegion


class PixelCaptureProvider(Protocol):
    def capture(self, region: CaptionRegion, screen: ScreenDescriptor) -> CapturedFrame: ...

    def close(self) -> None: ...


class LatestFrameQueue:
    """A capacity-one queue where newly captured work replaces stale work."""

    def __init__(self) -> None:
        self._frame: CapturedFrame | None = None
        self._lock = threading.Lock()

    def put(self, frame: CapturedFrame) -> None:
        with self._lock:
            self._frame = frame

    def take(self) -> CapturedFrame | None:
        with self._lock:
            frame, self._frame = self._frame, None
            return frame

    def clear(self) -> None:
        with self._lock:
            self._frame = None


class FrameChangeDetector:
    def __init__(self, threshold: float = 0.015) -> None:
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between zero and one")
        self.threshold = threshold
        self._previous: np.ndarray[tuple[int, ...], np.dtype[np.uint8]] | None = None

    def changed(self, frame: CapturedFrame) -> bool:
        pixels = np.frombuffer(frame.pixels, dtype=np.uint8)
        expected = frame.height * frame.stride
        if pixels.size != expected:
            raise ValueError("captured frame has an invalid pixel buffer")
        image = pixels.reshape(frame.height, frame.stride)[:, : frame.width * 4]
        bgra = image.reshape(frame.height, frame.width, 4)
        gray = (
            bgra[:, :, 0].astype(np.uint16)
            + bgra[:, :, 1].astype(np.uint16)
            + bgra[:, :, 2].astype(np.uint16)
        ) // 3
        current = gray.astype(np.uint8)
        if self._previous is None or self._previous.shape != current.shape:
            changed = True
        else:
            difference = np.abs(current.astype(np.int16) - self._previous.astype(np.int16))
            changed = float(np.mean(difference)) / 255 >= self.threshold
        self._previous = current.copy()
        return changed

    def reset(self) -> None:
        self._previous = None


class WindowsGdiCaptureProvider:  # pragma: no cover - native Windows integration
    """Capture BGRA pixels from the Windows desktop using GDI."""

    def capture(self, region: CaptionRegion, screen: ScreenDescriptor) -> CapturedFrame:
        if sys.platform != "win32":
            raise OSError("Screen-region capture is supported on Windows only")
        scale = screen.device_pixel_ratio
        left = round((screen.x + region.x) * scale)
        top = round((screen.y + region.y) * scale)
        width = max(1, round(region.width * scale))
        height = max(1, round(region.height * scale))
        return self._capture_gdi(left, top, width, height, region)

    @staticmethod
    def _capture_gdi(
        left: int, top: int, width: int, height: int, region: CaptionRegion
    ) -> CapturedFrame:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        source_dc = user32.GetDC(0)
        memory_dc = gdi32.CreateCompatibleDC(source_dc)
        bitmap = gdi32.CreateCompatibleBitmap(source_dc, width, height)
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not gdi32.BitBlt(memory_dc, 0, 0, width, height, source_dc, left, top, 0x00CC0020):
                raise OSError("Windows could not capture the selected screen region")

            class BitmapInfoHeader(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32),
                    ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            header = BitmapInfoHeader()
            header.biSize = ctypes.sizeof(BitmapInfoHeader)
            header.biWidth = width
            header.biHeight = -height
            header.biPlanes = 1
            header.biBitCount = 32
            buffer = ctypes.create_string_buffer(width * height * 4)
            if not gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0):
                raise OSError("Windows could not read captured screen pixels")
            return CapturedFrame(
                pixels=buffer.raw,
                width=width,
                height=height,
                stride=width * 4,
                captured_at=time.monotonic(),
                region=region,
            )
        finally:
            gdi32.SelectObject(memory_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(0, source_dc)

    def close(self) -> None:
        pass


class RegionCaptureWorker(QThread):
    """Capture at a bounded rate and publish every sample plus material changes."""

    frame_sampled = Signal(object)
    frame_changed = Signal(object)
    frame_available = Signal()
    status_changed = Signal(object, object)
    error = Signal(str)

    def __init__(
        self,
        provider: PixelCaptureProvider,
        region: CaptionRegion,
        screen: ScreenDescriptor,
        *,
        frames_per_second: float = 5.0,
        change_threshold: float = 0.015,
    ) -> None:
        super().__init__()
        if frames_per_second <= 0:
            raise ValueError("frames_per_second must be positive")
        self.provider = provider
        self.region = region
        self.screen = screen
        self.frames_per_second = frames_per_second
        self.frames = LatestFrameQueue()
        self.detector = FrameChangeDetector(change_threshold)
        self._wake = threading.Event()

    def start_capture(self) -> None:
        if self.isRunning():
            return
        self.detector.reset()
        self.frames.clear()
        self._wake.clear()
        self.start()

    def request_capture(self) -> None:
        """Wake the producer so the next sample is captured without interval delay."""
        self._wake.set()

    def run(self) -> None:
        interval = 1 / self.frames_per_second
        self.status_changed.emit(RuntimeStatus.READING_CAPTIONS, self.region.screen_name)
        try:
            while not self.isInterruptionRequested():
                started = time.monotonic()
                frame = self.provider.capture(self.region, self.screen)
                self.frames.put(frame)
                self.frame_sampled.emit(frame)
                if self.detector.changed(frame):
                    self.frame_changed.emit(frame)
                self.frame_available.emit()
                remaining = interval - (time.monotonic() - started)
                if remaining > 0:
                    self._wake.wait(remaining)
                    self._wake.clear()
        except (OSError, RuntimeError, ValueError) as exc:
            self.error.emit(str(exc))
            self.status_changed.emit(RuntimeStatus.ERROR, str(exc))

    def stop_capture(self) -> None:
        self.requestInterruption()
        self._wake.set()
        if self.isRunning() and not self.wait(3000):
            self.error.emit("Region capture did not stop within three seconds")
        self.frames.clear()
        self.detector.reset()

    def close(self) -> None:
        self.stop_capture()
        self.provider.close()
