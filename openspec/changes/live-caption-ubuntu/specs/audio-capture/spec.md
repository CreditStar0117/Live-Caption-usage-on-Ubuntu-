# Spec Delta

## Purpose

Captures live audio on Ubuntu (system playback and/or microphone) and delivers a continuous stream suitable for speech recognition.

## ADDED Requirements

### Requirement: Start and stop audio capture
The system SHALL start and stop audio capture on user request without requiring an application restart.

#### Scenario: User starts capture
- **WHEN** the user starts Live Caption
- **THEN** the system begins capturing audio from the configured source within 2 seconds

#### Scenario: User stops capture
- **WHEN** the user stops Live Caption
- **THEN** the system stops capturing audio and releases the audio device

### Requirement: Selectable audio source
The system SHALL allow the user to choose between system playback audio, microphone input, or both when available on the host.

#### Scenario: System audio selected
- **WHEN** the user selects system playback as the source and starts captioning
- **THEN** the system captures audio that is playing through the default output device

#### Scenario: Microphone selected
- **WHEN** the user selects microphone as the source and starts captioning
- **THEN** the system captures audio from the default input device

### Requirement: Capture failure is reported
When audio capture cannot start or fails mid-session, the system SHALL surface a clear error and SHALL NOT leave captioning in a silently broken state.

#### Scenario: No permission or device unavailable
- **WHEN** capture cannot start because the device is missing or access is denied
- **THEN** the system shows an error explaining the failure and captioning remains stopped

#### Scenario: Device disconnect mid-session
- **WHEN** the active audio device becomes unavailable while captioning
- **THEN** the system stops capture, notifies the user, and stops updating captions from that stream
