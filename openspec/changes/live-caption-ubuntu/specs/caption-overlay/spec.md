# Spec Delta

## Purpose

Shows live English captions in an always-on-top Ubuntu overlay window whose width and height the user can control and persist.

## ADDED Requirements

### Requirement: Live caption overlay window
The system SHALL display an always-on-top overlay window that shows the latest live caption text while captioning is active.

#### Scenario: Captions appear while active
- **WHEN** captioning is active and new transcription text is available
- **THEN** the overlay updates to show the latest caption text

#### Scenario: Overlay stays above other windows
- **WHEN** the user focuses another application
- **THEN** the caption overlay remains visible above other windows when the session allows always-on-top windows

### Requirement: User-controlled overlay width and height
The system SHALL let the user set the caption overlay width and height, and SHALL apply those dimensions to the overlay window.

#### Scenario: Resize by dragging
- **WHEN** the user resizes the overlay by dragging its edges or corners
- **THEN** the overlay width and height change to match the new size

#### Scenario: Resize via explicit controls
- **WHEN** the user sets width and/or height through size controls (for example numeric fields or presets)
- **THEN** the overlay adopts the requested width and height within supported bounds

#### Scenario: Minimum and maximum size
- **WHEN** the user attempts a size below the minimum or above the maximum
- **THEN** the system clamps to the allowed range and still keeps the overlay usable for reading captions

### Requirement: Persist overlay size
The system SHALL remember the user's preferred overlay width and height across application restarts.

#### Scenario: Size restored on launch
- **WHEN** the user previously set a custom width and height and later relaunches the app
- **THEN** the overlay opens at that saved width and height

### Requirement: Show and hide overlay
The system SHALL allow the user to show or hide the caption overlay without uninstalling the application.

#### Scenario: Hide overlay
- **WHEN** the user chooses to hide the overlay
- **THEN** the overlay is not visible on screen

#### Scenario: Show overlay again
- **WHEN** the user chooses to show the overlay while captioning is available
- **THEN** the overlay becomes visible at the saved size
