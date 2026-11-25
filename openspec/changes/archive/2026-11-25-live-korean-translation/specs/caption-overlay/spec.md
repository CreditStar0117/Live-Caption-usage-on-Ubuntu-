# Spec Delta

## ADDED Requirements

### Requirement: Two-language caption layout
When Korean translation is on, the overlay SHALL show final English captions in blocks, each followed directly below by its Korean translation. Korean text SHALL be styled so it is easy to tell apart from English. Text not yet translated SHALL be shown in English only.

#### Scenario: Translated block
- **WHEN** a block of final English text has been translated
- **THEN** the overlay shows the English block with its Korean translation on the line or lines directly below it

#### Scenario: English still in progress
- **WHEN** English text is partial, or final but its sentence is not complete yet
- **THEN** the overlay shows that English after the last translated block, with no Korean below it yet

#### Scenario: Translation arrives
- **WHEN** the Korean translation of a block becomes available
- **THEN** the overlay adds it below that block without moving or changing the English text of other blocks

#### Scenario: Korean easy to tell apart
- **WHEN** English and Korean are both shown
- **THEN** the Korean is visually distinct from the English (for example, in a different color) and both are readable at the chosen font size

#### Scenario: Translation off
- **WHEN** Korean translation is off
- **THEN** the overlay shows English captions exactly as it does without translation support

### Requirement: Hangul text renders correctly
The overlay SHALL render Korean text with a font that contains Hangul, so no Korean character shows as an empty box or placeholder on a standard Ubuntu desktop. Font size changes SHALL apply to Korean text as they do to English.

#### Scenario: Korean characters display
- **WHEN** a Korean translation is shown on a standard Ubuntu desktop install
- **THEN** every Hangul character renders as a readable glyph

#### Scenario: Font size applies to Korean
- **WHEN** the user changes the caption font size while Korean is shown
- **THEN** the Korean text is redrawn at the new size along with the English

### Requirement: Two-language history fills the overlay
When Korean translation is on, the caption history SHALL include Korean lines and allow for the wider Hangul characters. The overlay SHALL still fill with history, and the oldest blocks SHALL leave the view only when newer text needs the space.

#### Scenario: Overlay is full with translation on
- **WHEN** new English or Korean text no longer fits in the overlay
- **THEN** the oldest lines scroll out of view at the top, and the newest English text and its Korean (when available) stay visible at the bottom

#### Scenario: Enough history kept
- **WHEN** captioning with translation has run long enough to fill the overlay
- **THEN** the overlay is filled with English and Korean text, not left partly empty because too little history was kept

## MODIFIED Requirements

### Requirement: Fixed gap between sentences
The system SHALL separate consecutive sentences in the caption text with a fixed gap that is clearly wider than the space between words and scales with the font size. Sentences SHALL stay in one flowing paragraph rather than each starting a new line. When Korean translation is on, each caption block starts on a new line, and the sentences within a block's English text, and within its Korean text, follow these same rules.

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

#### Scenario: Sentences within a translated block
- **WHEN** Korean translation is on and a block's English or Korean text contains several sentences
- **THEN** those sentences flow on the same line with the fixed sentence gap, and the next block starts on a new line
