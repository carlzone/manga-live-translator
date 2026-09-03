from enum import StrEnum


class RuntimeStatus(StrEnum):
    IDLE = "Idle"
    CAPTURING = "Capturing"
    READING = "Reading"
    READING_CAPTIONS = "Reading captions"
    TRANSLATING = "Translating"
    READY = "Ready"
    ERROR = "Error"
