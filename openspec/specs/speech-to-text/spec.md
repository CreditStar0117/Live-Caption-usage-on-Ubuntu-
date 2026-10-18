# speech-to-text Specification

## Purpose

Converts captured live audio into English text with latency low enough for on-screen live captions.

## Requirements

### Requirement: English live transcription
The system SHALL transcribe captured audio into English text and emit partial or final results while captioning is active.

#### Scenario: Speech produces captions
- **WHEN** English speech is present in the captured audio stream and captioning is active
- **THEN** the system produces corresponding English text for display

#### Scenario: Silence produces no new speech text
- **WHEN** the captured stream contains only silence or non-speech noise for an extended period
- **THEN** the system does not invent speech text for that period

### Requirement: Streaming results for live display
The system SHALL provide transcription results incrementally so the caption overlay can update without waiting for the full utterance to end when partial results are available.

#### Scenario: Partial then final result
- **WHEN** a spoken phrase is in progress
- **THEN** the system MAY emit partial text and MUST eventually emit a stable final result for that phrase when recognition completes

### Requirement: Transcription errors are visible
When the speech engine fails to load, run, or process audio, the system SHALL report the failure to the user and stop presenting new captions until captioning is restarted successfully.

#### Scenario: Model or engine unavailable
- **WHEN** the speech engine cannot start
- **THEN** the system shows an error and does not pretend captioning is active
