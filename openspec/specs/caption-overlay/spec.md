# caption-overlay Specification

## Purpose

Shows live English captions in an always-on-top Ubuntu overlay window whose width and height the user can control and persist.

## Requirements

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

### Requirement: User-controlled caption font size
The system SHALL let the user set the caption text font size from the control window and SHALL apply it to the overlay immediately, without restarting captioning. Font sizes outside the supported range of 12 to 72 pixels SHALL be clamped to that range.

#### Scenario: Increase font size
- **WHEN** the user raises the font size in the control window while captions are shown
- **THEN** the overlay redraws the existing caption text at the new size without clearing it

#### Scenario: Font size out of range
- **WHEN** the user enters a font size below 12 or above 72 pixels
- **THEN** the system clamps it to the nearest bound and the overlay remains readable

### Requirement: Persist caption font size
The system SHALL remember the user's caption font size across application restarts and SHALL use 22 pixels when no font size has been saved.

#### Scenario: Font size restored on launch
- **WHEN** the user previously set a custom font size and later relaunches the app
- **THEN** the overlay shows captions at that saved font size and the control window shows the same value

#### Scenario: No saved font size
- **WHEN** the saved settings predate font-size support or the value is missing or invalid
- **THEN** the overlay uses 22 pixels and the other saved settings still load

### Requirement: Fixed gap between sentences
The system SHALL separate consecutive sentences in the caption text with a fixed gap that is clearly wider than the space between words and scales with the font size. Sentences SHALL stay in one flowing paragraph rather than each starting a new line.

#### Scenario: Two sentences in the captions
- **WHEN** the caption text contains a sentence ending in `.`, `?` or `!` followed by another sentence
- **THEN** the overlay shows the same fixed wide gap between them, on the same line when it fits

#### Scenario: Sentence continues across recognized phrases
- **WHEN** a sentence is split across two recognized phrases with no sentence-ending punctuation between them
- **THEN** the overlay joins them with a normal word space, not a sentence gap

#### Scenario: In-progress sentence
- **WHEN** the in-progress (not yet final) text begins a new sentence after a finished one
- **THEN** the same sentence gap separates them

#### Scenario: Gap follows font size
- **WHEN** the user changes the caption font size
- **THEN** the sentence gap grows or shrinks in proportion to the new size

#### Scenario: Numbers and inline periods
- **WHEN** a period is not followed by whitespace (for example `3.5` or `example.com`)
- **THEN** the system does not treat it as a sentence boundary

### Requirement: Caption history fills the overlay
The system SHALL keep earlier caption text on the overlay until the overlay is full, so a larger overlay or smaller font shows more history. Older text SHALL leave the visible area only when newer text needs the space, and the newest text SHALL always stay visible.

#### Scenario: Room left on the overlay
- **WHEN** the caption text since captioning started fits in the overlay
- **THEN** all of it stays visible, filling the overlay from the bottom up

#### Scenario: Overlay is full
- **WHEN** new caption text no longer fits in the overlay
- **THEN** the oldest lines scroll out of view at the top and the newest line stays visible at the bottom

#### Scenario: Larger overlay shows more
- **WHEN** the user enlarges the overlay or reduces the font size
- **THEN** further captions fill the larger area before older text leaves the view

#### Scenario: New captioning session
- **WHEN** the user stops and starts captioning again
- **THEN** the overlay starts empty and fills with the new session's captions
