"""Frame fingerprints and the scrolling viewport state machine."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from manga_live_translator.screen.capture import CapturedFrame


class ViewportState(StrEnum):
    MOVING = "moving"
    SETTLING = "settling"
    PROCESSING = "processing"
    STABLE = "stable"


@dataclass(frozen=True, slots=True)
class FrameFingerprint:
    pixels: bytes
    width: int
    height: int
    digest: str


@dataclass(frozen=True, slots=True)
class ViewportSnapshot:
    frame: CapturedFrame
    fingerprint: FrameFingerprint


@dataclass(frozen=True, slots=True)
class ScrollDisplacement:
    physical_dy: float
    confidence: float
    trackable: bool
    reason: str = ""


class VerticalScrollTracker:
    """Estimate vertical content displacement between bounded grayscale fingerprints."""

    def __init__(
        self,
        *,
        maximum_shift_ratio: float = 0.35,
        minimum_texture: float = 0.02,
        minimum_improvement: float = 0.01,
        maximum_match_difference: float = 0.12,
    ) -> None:
        if not 0 < maximum_shift_ratio <= 0.5:
            raise ValueError("maximum_shift_ratio must be between zero and 0.5")
        self.maximum_shift_ratio = maximum_shift_ratio
        self.minimum_texture = minimum_texture
        self.minimum_improvement = minimum_improvement
        self.maximum_match_difference = maximum_match_difference
        self._previous: FrameFingerprint | None = None

    def reset(self) -> None:
        self._previous = None

    def observe(self, current: FrameFingerprint, *, physical_height: int) -> ScrollDisplacement:
        previous, self._previous = self._previous, current
        if previous is None:
            return ScrollDisplacement(0.0, 0.0, False, "initial frame")
        return self.estimate(previous, current, physical_height=physical_height)

    def estimate(
        self,
        previous: FrameFingerprint,
        current: FrameFingerprint,
        *,
        physical_height: int,
    ) -> ScrollDisplacement:
        if physical_height <= 0:
            raise ValueError("physical_height must be positive")
        if (previous.width, previous.height) != (current.width, current.height):
            return ScrollDisplacement(0.0, 0.0, False, "frame dimensions changed")
        left = np.frombuffer(previous.pixels, dtype=np.uint8)
        right = np.frombuffer(current.pixels, dtype=np.uint8)
        expected = previous.width * previous.height
        if left.size != expected or right.size != expected:
            return ScrollDisplacement(0.0, 0.0, False, "invalid fingerprint")
        before = left.reshape(previous.height, previous.width).astype(np.int16)
        after = right.reshape(current.height, current.width).astype(np.int16)
        texture = min(float(np.std(before)), float(np.std(after))) / 255
        if texture < self.minimum_texture:
            return ScrollDisplacement(0.0, 0.0, False, "insufficient texture")
        zero_score = float(np.mean(np.abs(before - after))) / 255
        maximum_shift = max(1, round(previous.height * self.maximum_shift_ratio))
        scores: list[tuple[float, int]] = []
        for shift in range(-maximum_shift, maximum_shift + 1):
            if shift < 0:
                old_rows = before[-shift:, :]
                new_rows = after[: previous.height + shift, :]
            elif shift > 0:
                old_rows = before[: previous.height - shift, :]
                new_rows = after[shift:, :]
            else:
                old_rows, new_rows = before, after
            scores.append((float(np.mean(np.abs(old_rows - new_rows))) / 255, shift))
        best_score, best_shift = min(scores)
        improvement = zero_score - best_score
        if best_shift == 0:
            if best_score <= self.maximum_match_difference:
                return ScrollDisplacement(0.0, max(0.0, 1 - best_score), True)
            return ScrollDisplacement(0.0, 0.0, False, "motion is not vertical")
        if best_score > self.maximum_match_difference or improvement < self.minimum_improvement:
            return ScrollDisplacement(0.0, max(0.0, improvement), False, "weak vertical match")
        physical_dy = best_shift * physical_height / previous.height
        confidence = min(1.0, improvement / max(zero_score, 1e-9))
        return ScrollDisplacement(physical_dy, confidence, True)


def fingerprint_frame(frame: CapturedFrame, *, maximum_size: int = 64) -> FrameFingerprint:
    """Create a bounded grayscale fingerprint from a BGRA frame."""
    if maximum_size <= 0:
        raise ValueError("maximum_size must be positive")
    pixels = np.frombuffer(frame.pixels, dtype=np.uint8)
    if pixels.size != frame.height * frame.stride or frame.stride < frame.width * 4:
        raise ValueError("captured frame has an invalid pixel buffer")
    rows = pixels.reshape(frame.height, frame.stride)[:, : frame.width * 4]
    bgra = rows.reshape(frame.height, frame.width, 4)
    gray = (
        bgra[:, :, 0].astype(np.uint16)
        + bgra[:, :, 1].astype(np.uint16)
        + bgra[:, :, 2].astype(np.uint16)
    ) // 3
    target_width = min(maximum_size, frame.width)
    target_height = min(maximum_size, frame.height)
    x_indices = np.linspace(0, frame.width - 1, target_width, dtype=np.intp)
    y_indices = np.linspace(0, frame.height - 1, target_height, dtype=np.intp)
    sampled = gray[np.ix_(y_indices, x_indices)].astype(np.uint8)
    data = sampled.tobytes()
    return FrameFingerprint(data, target_width, target_height, hashlib.sha256(data).hexdigest())


def fingerprint_difference(first: FrameFingerprint, second: FrameFingerprint) -> float:
    if (first.width, first.height) != (second.width, second.height):
        return 1.0
    left = np.frombuffer(first.pixels, dtype=np.uint8).astype(np.int16)
    right = np.frombuffer(second.pixels, dtype=np.uint8).astype(np.int16)
    if left.size != first.width * first.height or right.size != left.size:
        raise ValueError("fingerprint has an invalid pixel buffer")
    return float(np.mean(np.abs(left - right))) / 255


class ViewportSettlingController:
    """Accept one snapshot after motion is followed by uninterrupted stability."""

    def __init__(self, *, threshold: float = 0.015, settle_seconds: float = 0.4) -> None:
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between zero and one")
        if settle_seconds < 0:
            raise ValueError("settle_seconds cannot be negative")
        self.threshold = threshold
        self.settle_seconds = settle_seconds
        self.state = ViewportState.MOVING
        self._previous: FrameFingerprint | None = None
        self._settling_since: float | None = None
        self._accepted = False

    def observe(self, frame: CapturedFrame) -> ViewportSnapshot | None:
        current = fingerprint_frame(frame)
        if self._previous is None:
            self._previous = current
            self.state = ViewportState.MOVING
            return None

        changed = fingerprint_difference(self._previous, current) >= self.threshold
        self._previous = current
        if changed:
            self._settling_since = None
            self._accepted = False
            self.state = ViewportState.MOVING
            return None

        if self._settling_since is None:
            self._settling_since = frame.captured_at
            self.state = ViewportState.SETTLING
            return None
        if frame.captured_at - self._settling_since + 1e-9 < self.settle_seconds:
            self.state = ViewportState.SETTLING
            return None
        if self._accepted:
            self.state = ViewportState.STABLE
            return None
        self._accepted = True
        self.state = ViewportState.PROCESSING
        return ViewportSnapshot(frame, current)

    def manual_snapshot(self, frame: CapturedFrame) -> ViewportSnapshot:
        fingerprint = fingerprint_frame(frame)
        self._previous = fingerprint
        self._accepted = True
        self._settling_since = frame.captured_at
        self.state = ViewportState.PROCESSING
        return ViewportSnapshot(frame, fingerprint)

    def mark_stable(self) -> None:
        if self.state is ViewportState.PROCESSING:
            self.state = ViewportState.STABLE

    def adopt_stable(self, frame: CapturedFrame) -> None:
        """Adopt a post-render frame without treating controlled UI changes as motion."""
        self._previous = fingerprint_frame(frame)
        self._settling_since = frame.captured_at
        self._accepted = True
        self.state = ViewportState.STABLE

    def reset(self) -> None:
        self.state = ViewportState.MOVING
        self._previous = None
        self._settling_since = None
        self._accepted = False
