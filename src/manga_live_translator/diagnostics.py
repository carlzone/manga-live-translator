"""Bounded, privacy-safe runtime measurements for support and release checks."""

from __future__ import annotations

import os
import platform
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from statistics import median

from manga_live_translator.config import CaptionRegion, ReadingDirection


def _process_memory_bytes() -> int | None:
    """Return resident process memory without adding a runtime dependency."""
    if sys.platform == "win32":  # pragma: no cover - exercised by Windows acceptance
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        )
        get_info.restype = wintypes.BOOL
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        if get_info(get_process(), ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
        return None
    try:  # pragma: no cover - platform-dependent fallback
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(usage * (1 if sys.platform == "darwin" else 1024))
    except (ImportError, OSError):
        return None


@dataclass(slots=True)
class RuntimeDiagnostics:
    """Collect session summaries while retaining only a bounded number of timings."""

    maximum_samples: int = 500
    started_at: float = field(default_factory=time.monotonic)
    started_cpu: float = field(default_factory=time.process_time)
    accepted_viewports: int = 0
    translated_blocks: int = 0
    failed_blocks: int = 0
    start_stop_cycles: int = 0
    latest_scroll_physical_dy: float = 0.0
    latest_scroll_logical_dy: float = 0.0
    cumulative_scroll_logical_dy: float = 0.0
    latest_tracking_confidence: float = 0.0
    tracking_clear_count: int = 0
    post_render_rebase_count: int = 0
    clean_frame_drain_count: int = 0
    prevented_feedback_scan_count: int = 0
    _ocr_seconds: deque[float] = field(init=False)
    _translation_seconds: deque[float] = field(init=False)
    _completion_seconds: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        if self.maximum_samples <= 0:
            raise ValueError("maximum_samples must be positive")
        self._ocr_seconds = deque(maxlen=self.maximum_samples)
        self._translation_seconds = deque(maxlen=self.maximum_samples)
        self._completion_seconds = deque(maxlen=self.maximum_samples)

    def record_viewport(
        self,
        *,
        ocr_seconds: float,
        translation_seconds: float,
        completion_seconds: float,
        translated_blocks: int,
        failed_blocks: int,
    ) -> None:
        self.accepted_viewports += 1
        self.translated_blocks += translated_blocks
        self.failed_blocks += failed_blocks
        self._ocr_seconds.append(max(0.0, ocr_seconds))
        self._translation_seconds.append(max(0.0, translation_seconds))
        self._completion_seconds.append(max(0.0, completion_seconds))

    def record_scroll(
        self,
        *,
        physical_dy: float,
        logical_dy: float,
        confidence: float,
        cleared: bool = False,
    ) -> None:
        self.latest_scroll_physical_dy = physical_dy
        self.latest_scroll_logical_dy = logical_dy
        self.cumulative_scroll_logical_dy += logical_dy
        self.latest_tracking_confidence = confidence
        if cleared:
            self.tracking_clear_count += 1

    def record_clean_frame_drain(self) -> None:
        self.clean_frame_drain_count += 1

    def record_post_render_rebase(self) -> None:
        self.post_render_rebase_count += 1
        self.prevented_feedback_scan_count += 1

    @staticmethod
    def _timing_line(label: str, samples: deque[float]) -> str:
        if not samples:
            return f"{label}: no samples"
        ordered = sorted(samples)
        p95 = ordered[min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))]
        return f"{label}: median {median(samples) * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms"

    def report(
        self,
        *,
        region: CaptionRegion | None,
        reading_direction: ReadingDirection,
        state: str,
        overlay_geometry: tuple[int, int, int, int] | None = None,
        overlay_scale: tuple[float, float] | None = None,
        rendered_boxes: int = 0,
        collision_adjustments: int = 0,
        capture_exclusion_mode: str = "not_attempted",
        capture_exclusion_verified: bool = False,
        capture_exclusion_error: int = 0,
    ) -> str:
        elapsed = max(time.monotonic() - self.started_at, 1e-9)
        cpu_percent = 100 * max(0.0, time.process_time() - self.started_cpu) / elapsed
        memory = _process_memory_bytes()
        lines = [
            "MangaLiveTranslator diagnostics",
            f"App version: {__import__('manga_live_translator').__version__}",
            f"Platform: {platform.platform()}",
            f"Python: {platform.python_version()} ({platform.architecture()[0]})",
            f"Process: {os.getpid()}",
            f"Status: {state}",
            f"Session: {elapsed:.1f} s; CPU average {cpu_percent:.1f}%; memory "
            + (f"{memory / 1024 / 1024:.1f} MiB" if memory is not None else "unavailable"),
            f"Viewports: {self.accepted_viewports}; translated blocks: {self.translated_blocks}; "
            f"failed blocks: {self.failed_blocks}; start/stop cycles: {self.start_stop_cycles}",
            self._timing_line("OCR", self._ocr_seconds),
            self._timing_line("Translation", self._translation_seconds),
            self._timing_line("Settled viewport completion", self._completion_seconds),
            f"Selected layout: {reading_direction.value}",
            f"Scroll tracking: physical dy {self.latest_scroll_physical_dy:.1f}px; "
            f"logical dy {self.latest_scroll_logical_dy:.1f}px; cumulative "
            f"{self.cumulative_scroll_logical_dy:.1f}px; confidence "
            f"{self.latest_tracking_confidence:.2f}; low-confidence clears "
            f"{self.tracking_clear_count}",
            f"Capture safeguards: affinity={capture_exclusion_mode}; verified="
            f"{capture_exclusion_verified}; error={capture_exclusion_error}; post-render rebases "
            f"{self.post_render_rebase_count}; drained frames {self.clean_frame_drain_count}; "
            f"prevented feedback scans {self.prevented_feedback_scan_count}",
        ]
        if region is None:
            lines.append("Region: not selected")
        else:
            physical_width = round(region.width * region.device_pixel_ratio)
            physical_height = round(region.height * region.device_pixel_ratio)
            lines.append(
                f"Region: {region.screen_name}; logical {region.width}x{region.height}; "
                f"physical {physical_width}x{physical_height}; "
                f"scale {region.device_pixel_ratio:.2f}"
            )
        if overlay_geometry is not None and overlay_scale is not None:
            x, y, width, height = overlay_geometry
            scale_x, scale_y = overlay_scale
            lines.append(
                f"Overlay: {width}x{height} at ({x}, {y}); coordinate scale "
                f"{scale_x:.3f}x{scale_y:.3f}; boxes {rendered_boxes}; "
                f"collision adjustments {collision_adjustments}"
            )
        lines.append(
            "Privacy: diagnostics contain no captured pixels, recognized text, or translations."
        )
        return "\n".join(lines)
