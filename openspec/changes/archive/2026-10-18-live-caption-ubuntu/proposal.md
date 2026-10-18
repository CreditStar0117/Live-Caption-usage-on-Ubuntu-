# Proposal

## Why

Ubuntu has no built-in Live Caption like Android/ChromeOS. Users watching videos, joining calls, or listening to system audio need on-screen English captions. This change delivers a desktop Live Caption app with a caption overlay whose width and height the user can control.

## What Changes

- Add a Ubuntu desktop Live Caption application that captures audio, transcribes it to English in near real time, and shows captions in an always-on-top overlay.
- Add user-controlled caption overlay **width** and **height** (resize and persist preferred size).
- Add start/stop captioning and basic overlay visibility controls.
- Greenfield project: introduce app structure, packaging for Ubuntu, and local speech-to-text pipeline.

## Capabilities

### New Capabilities

- `audio-capture`: Capture system and/or microphone audio on Ubuntu for transcription.
- `speech-to-text`: Convert captured audio into English text with low latency suitable for live captions.
- `caption-overlay`: Display live captions in an always-on-top window with user-controlled width and height.

### Modified Capabilities

- (none — greenfield; no existing specs)

## Impact

- New application codebase under this repo (no existing source yet).
- Depends on Ubuntu audio stack (PipeWire/PulseAudio), a speech recognition engine (local-first), and a GUI toolkit for the overlay window.
- Requires desktop session permissions for audio capture; Wayland/X11 window behavior must be handled for always-on-top overlay and resizing.
- No external APIs required for the MVP if a local STT model is used; optional cloud STT is out of scope unless added later.
