"""Нарушение, найденное контролёром."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Violation:
    where: str          # где: путь:строка или код записи
    message: str        # что не так
    severity: str = "ERROR"

    def __str__(self) -> str:
        return f"[{self.severity}] {self.where}: {self.message}"
