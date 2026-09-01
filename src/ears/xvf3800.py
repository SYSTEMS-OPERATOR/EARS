"""Read-only USB control interface for the reSpeaker XVF3800.

This module preserves the small, useful seam from SOPHY-AGI/EARS-XVF3800:
firmware inspection and direction-of-arrival (DoA) telemetry. It deliberately
does not expose reboot, flash-write, configuration-save, or DFU operations.

The XMOS vendor-control response begins with a one-byte status code followed by
a little-endian payload. A status of 64 asks the host to retry the command.
"""

from __future__ import annotations

import struct
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Literal, Protocol, TypeAlias

import usb.core
import usb.util

USB_VENDOR_ID: Final = 0x2886
USB_PRODUCT_ID: Final = 0x001A
CONTROL_SUCCESS: Final = 0
CONTROL_RETRY: Final = 64
DEFAULT_TIMEOUT_MS: Final = 100_000
DEFAULT_MAX_ATTEMPTS: Final = 100
RETRY_DELAY_SECONDS: Final = 0.01

ValueKind: TypeAlias = Literal[
    "char",
    "float",
    "int32",
    "radians",
    "uint8",
    "uint16",
    "uint32",
]


class USBDevice(Protocol):
    """Minimal PyUSB device surface required by this module."""

    def ctrl_transfer(
        self,
        request_type: int,
        request: int,
        value: int,
        index: int,
        data_or_length: int,
        timeout: int,
    ) -> Sequence[int]:
        """Perform one USB control transfer."""


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Describe one read-only XVF3800 vendor command."""

    resource_id: int
    command_id: int
    value_count: int
    value_kind: ValueKind
    description: str


@dataclass(frozen=True, slots=True)
class DirectionOfArrival:
    """A single direction-of-arrival observation."""

    azimuth_degrees: int
    speech_detected: bool


class XVF3800Error(RuntimeError):
    """Base error raised by the curated XVF3800 interface."""


class DeviceNotFoundError(XVF3800Error):
    """Raised when the expected USB device is unavailable."""


class DeviceStatusError(XVF3800Error):
    """Raised when firmware returns a status other than success or retry."""


# This registry is intentionally narrow. It contains only telemetry needed for
# identification, beam inspection, and passive acoustic experiments.
_PARAMETERS: Final[dict[str, ParameterSpec]] = {
    "VERSION": ParameterSpec(
        48,
        0,
        3,
        "uint8",
        "Firmware semantic version: major, minor, patch.",
    ),
    "BUILD_MESSAGE": ParameterSpec(
        48,
        1,
        50,
        "char",
        "Firmware build configuration message.",
    ),
    "BUILD_REPOSITORY_HASH": ParameterSpec(
        48,
        3,
        40,
        "char",
        "Source revision embedded in the firmware.",
    ),
    "AEC_AZIMUTH_VALUES": ParameterSpec(
        33,
        75,
        4,
        "radians",
        "Azimuths for two fixed beams, free beam, and selected beam.",
    ),
    "AEC_SPEECH_ENERGY_VALUES": ParameterSpec(
        33,
        80,
        4,
        "float",
        "Speech-energy estimate for each beam.",
    ),
    "AUDIO_SELECTED_AZIMUTHS": ParameterSpec(
        35,
        11,
        2,
        "radians",
        "Processed and auto-selected output azimuths.",
    ),
    "DOA_VALUE": ParameterSpec(
        20,
        18,
        2,
        "uint16",
        "Azimuth in degrees followed by speech-detected flag.",
    ),
}

_STRUCT_CODES: Final[dict[ValueKind, str]] = {
    "float": "f",
    "int32": "i",
    "radians": "f",
    "uint8": "B",
    "uint16": "H",
    "uint32": "I",
}

_VALUE_WIDTHS: Final[dict[ValueKind, int]] = {
    "char": 1,
    "float": 4,
    "int32": 4,
    "radians": 4,
    "uint8": 1,
    "uint16": 2,
    "uint32": 4,
}


class XVF3800:
    """Manage passive vendor-control reads from one XVF3800 device."""

    def __init__(
        self,
        device: USBDevice,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        """Bind an already discovered PyUSB device.

        Args:
            device: PyUSB-compatible XVF3800 device object.
            timeout_ms: Timeout passed to each control transfer.
            max_attempts: Maximum transfers when firmware reports retry.
        """
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")

        self._device = device
        self._timeout_ms = timeout_ms
        self._max_attempts = max_attempts
        self._closed = False

    @classmethod
    def open(
        cls,
        *,
        vendor_id: int = USB_VENDOR_ID,
        product_id: int = USB_PRODUCT_ID,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> XVF3800:
        """Discover the default XVF3800 and return a managed interface."""
        finder = usb.core.find

        # On Windows, libusb-package can supply a bundled backend. Import it only
        # on that platform so Linux and Jetson installations stay lightweight.
        if sys.platform.startswith("win"):
            try:
                import libusb_package  # type: ignore[import-not-found]
            except ImportError as error:
                raise DeviceNotFoundError(
                    "Install the 'windows' optional dependency to access USB."
                ) from error
            finder = libusb_package.find

        device = finder(idVendor=vendor_id, idProduct=product_id)
        if device is None:
            raise DeviceNotFoundError(
                f"XVF3800 {vendor_id:#06x}:{product_id:#06x} was not found."
            )

        return cls(
            device,
            timeout_ms=timeout_ms,
            max_attempts=max_attempts,
        )

    def read(self, name: str) -> str | tuple[int | float, ...]:
        """Read and decode one allowlisted telemetry parameter."""
        if self._closed:
            raise XVF3800Error("Cannot read from a closed device.")

        try:
            spec = _PARAMETERS[name.upper()]
        except KeyError as error:
            allowed = ", ".join(sorted(_PARAMETERS))
            raise KeyError(f"Unknown parameter {name!r}; choose: {allowed}") from error

        payload_length = 1 + spec.value_count * _VALUE_WIDTHS[spec.value_kind]
        request_type = (
            usb.util.CTRL_IN
            | usb.util.CTRL_TYPE_VENDOR
            | usb.util.CTRL_RECIPIENT_DEVICE
        )
        command_id = 0x80 | spec.command_id

        for attempt in range(1, self._max_attempts + 1):
            response = self._device.ctrl_transfer(
                request_type,
                0,
                command_id,
                spec.resource_id,
                payload_length,
                self._timeout_ms,
            )
            response_bytes = bytes(response)
            if not response_bytes:
                raise DeviceStatusError(f"{name} returned an empty response.")

            status = response_bytes[0]
            if status == CONTROL_SUCCESS:
                return self._decode(spec, response_bytes[1:])
            if status != CONTROL_RETRY:
                raise DeviceStatusError(
                    f"{name} returned unsupported status {status}."
                )
            if attempt < self._max_attempts:
                time.sleep(RETRY_DELAY_SECONDS)

        raise DeviceStatusError(
            f"{name} still requested retry after {self._max_attempts} attempts."
        )

    def firmware_version(self) -> tuple[int, int, int]:
        """Return firmware version as a three-integer tuple."""
        value = self.read("VERSION")
        if not isinstance(value, tuple) or len(value) != 3:
            raise DeviceStatusError("Firmware returned an invalid version payload.")
        return tuple(int(part) for part in value)

    def direction_of_arrival(self) -> DirectionOfArrival:
        """Return the current azimuth and speech-presence decision."""
        value = self.read("DOA_VALUE")
        if not isinstance(value, tuple) or len(value) != 2:
            raise DeviceStatusError("Firmware returned an invalid DoA payload.")

        azimuth, speech_flag = (int(part) for part in value)
        if not 0 <= azimuth <= 359:
            raise DeviceStatusError(f"Firmware returned invalid azimuth {azimuth}.")

        return DirectionOfArrival(
            azimuth_degrees=azimuth,
            speech_detected=bool(speech_flag),
        )

    @staticmethod
    def _decode(
        spec: ParameterSpec,
        payload: bytes,
    ) -> str | tuple[int | float, ...]:
        """Decode a status-free little-endian payload."""
        if spec.value_kind == "char":
            return payload.rstrip(b"\x00").decode("utf-8", errors="replace")

        format_code = _STRUCT_CODES[spec.value_kind]
        expected_length = spec.value_count * _VALUE_WIDTHS[spec.value_kind]
        if len(payload) != expected_length:
            raise DeviceStatusError(
                f"Expected {expected_length} payload bytes, received {len(payload)}."
            )

        return struct.unpack(
            f"<{spec.value_count}{format_code}",
            payload,
        )

    def close(self) -> None:
        """Release PyUSB resources; repeated calls are harmless."""
        if not self._closed:
            usb.util.dispose_resources(self._device)
            self._closed = True

    def __enter__(self) -> XVF3800:
        """Return this instance for context-manager use."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the device when leaving a context."""
        self.close()
