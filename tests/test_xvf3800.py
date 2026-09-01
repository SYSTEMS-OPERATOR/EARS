"""Protocol-level tests that require no physical microphone array."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from ears.xvf3800 import XVF3800, DeviceStatusError


class FakeDevice:
    """Return deterministic USB responses keyed by resource and command."""

    def __init__(self, responses: dict[tuple[int, int], list[bytes]]) -> None:
        """Store a queue of responses for each command pair."""
        self._responses = responses

    def ctrl_transfer(
        self,
        request_type: int,
        request: int,
        value: int,
        index: int,
        data_or_length: int,
        timeout: int,
    ) -> Sequence[int]:
        """Return the next prepared response for one vendor-control read."""
        del request_type, request, data_or_length, timeout
        return self._responses[(index, value)].pop(0)


def test_firmware_version_and_direction_of_arrival() -> None:
    """Decode version and two-value uint16 DoA payloads."""
    device = FakeDevice(
        {
            (48, 0x80): [bytes([0, 2, 1, 0])],
            (20, 0x80 | 18): [bytes([0, 91, 0, 1, 0])],
        }
    )

    ears = XVF3800(device)
    assert ears.firmware_version() == (2, 1, 0)

    observation = ears.direction_of_arrival()
    assert observation.azimuth_degrees == 91
    assert observation.speech_detected is True


def test_retry_status_is_reissued() -> None:
    """Repeat a command when firmware returns the documented retry status."""
    device = FakeDevice(
        {
            (48, 0x80): [
                bytes([64, 0, 0, 0]),
                bytes([0, 2, 1, 0]),
            ]
        }
    )

    ears = XVF3800(device, max_attempts=2)
    assert ears.firmware_version() == (2, 1, 0)


def test_unknown_status_is_rejected() -> None:
    """Reject firmware statuses outside success and retry."""
    device = FakeDevice({(48, 0x80): [bytes([7, 0, 0, 0])]})
    ears = XVF3800(device)

    with pytest.raises(DeviceStatusError):
        ears.firmware_version()
