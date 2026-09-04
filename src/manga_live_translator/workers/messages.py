from enum import StrEnum


class RuntimeStatus(StrEnum):
    IDLE = "Idle"
    PAUSED = "Paused"
    CAPTURING = "Capturing"
    MOVING = "Waiting for scroll to stop"
    SETTLING = "Settling"
    READING = "Reading"
    READING_CAPTIONS = "Reading captions"
    TRANSLATING = "Translating"
    READY = "Ready"
    ERROR = "Error"
