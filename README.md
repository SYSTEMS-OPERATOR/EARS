# EARS

Curated research and control software for SOPHY's auditory system.

EARS is intentionally not a binary mirror of upstream hardware repositories. It
keeps the parts we can inspect, explain, test, and evolve:

- machine-readable research notes in `research/notes/*.json`;
- hardware profiles and provenance in `hardware/*/*.json`;
- small, documented Python control modules under `src/ears`;
- operator-facing scripts under `scripts`.

## First-pass hardware target

The initial target is the Seeed Studio reSpeaker XVF3800 USB 4-Mic Array used by
`SOPHY-AGI/EARS-XVF3800`. Opaque executables, shared libraries, firmware images,
and duplicated legacy speech-recognition code are excluded. They remain
available upstream and are recorded in the source ledger.

## Layout

```text
hardware/xvf3800/       Baseline device profile and provenance
hardware/respeaker_flex/ Flex profile, compatibility, firmware, and topology
references/sources.json  Canonical source-material link ledger
research/notes/         Timestamped JSON research records
scripts/                Small executable entry points
src/ears/               Reviewed Python control code
```

## Safety boundary

Read operations are the default. Commands that write configuration, save to
flash, clear configuration, reboot, or enter DFU must be explicit operator
actions. The first-pass Python module therefore exposes only read-only status
and direction-of-arrival functions.

## Quick start

```bash
python -m pip install -e .
python scripts/read_doa.py
```

Linux may require an appropriate udev rule or elevated USB permissions.

## Provenance

Every imported or adapted artifact must retain its source repository, path,
revision, and license status. Stable source IDs and links live in
`references/sources.json`; hardware-specific lineage remains beside the device
profile.

## Flex compatibility

The current read-only EARS control subset is source-compatible with reSpeaker
Flex. Compatibility boundaries, firmware selection, DFU recovery, and proposed
Jetson/ESP32 topologies are recorded under `hardware/respeaker_flex/`. Firmware
images remain upstream and are never selected by version number alone.

## Dimensional references

Machine-readable mechanical facts live in `hardware/dimensions/registry.json`.
The companion SVGs under `hardware/dimensions/diagrams/` show only published
envelopes and acoustic coordinates. Unknown board widths, thicknesses, component
positions, and mounting-hole coordinates remain explicitly unresolved rather
than being estimated from product photographs.
