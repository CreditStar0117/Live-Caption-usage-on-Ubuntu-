# Spec Delta

## ADDED Requirements

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
