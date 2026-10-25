"""Sanitized, machine-readable errors shared by admission and transport."""


class ModelError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")
