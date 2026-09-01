"""Auditory hardware interfaces for the SOPHY EARS project."""

from .xvf3800 import (
    DeviceNotFoundError,
    DirectionOfArrival,
    XVF3800,
    XVF3800Error,
)

__all__ = [
    "DeviceNotFoundError",
    "DirectionOfArrival",
    "XVF3800",
    "XVF3800Error",
]
