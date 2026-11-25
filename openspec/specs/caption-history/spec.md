# caption-history Specification

## Purpose

Keeps a full record of the English captions shown during an app run, so the user can read again or keep what was said after it has scrolled out of the overlay, by saving it to a text file on their own machine.

## Requirements

### Requirement: Record final English captions
While captioning is active, the system SHALL record every final English caption in a caption history. Partial text SHALL NOT be recorded. Korean translations SHALL NOT be recorded, whether or not Korean translation is on.

#### Scenario: Final text is recorded
- **WHEN** an English phrase becomes final while captioning
- **THEN** its text is added to the caption history

#### Scenario: Partial text is not recorded
- **WHEN** English text is still in progress and is then replaced by different final text
- **THEN** the history contains only the final text

#### Scenario: Korean translation is on
- **WHEN** captioning with Korean translation on and a sentence's Korean appears on the overlay
- **THEN** the history contains the English sentence and no Korean text

### Requirement: History is not limited by the overlay
The caption history SHALL keep all recorded captions, including those that have scrolled out of the overlay or were dropped from the overlay's own history. Resizing the overlay or changing its font size SHALL NOT remove anything from the caption history.

#### Scenario: Long session
- **WHEN** a session runs long enough that its first captions are no longer on the overlay
- **THEN** the caption history still contains those first captions

#### Scenario: Overlay made smaller
- **WHEN** the user shrinks the overlay or raises the font size while captioning
- **THEN** the caption history keeps every caption recorded so far

### Requirement: History lasts for the app run
The caption history SHALL persist across stopping and starting captioning, and across caption errors that stop captioning, for as long as the app runs. It SHALL be emptied only when the user clears it or the app quits. It SHALL NOT be written to disk unless the user saves it.

#### Scenario: Stop and start again
- **WHEN** the user stops captioning and starts it again
- **THEN** the history still contains the earlier session's captions, followed by the new session's captions

#### Scenario: Nothing written without saving
- **WHEN** the user captions without saving and then quits, choosing to discard the history
- **THEN** no caption text has been written to disk by the app

### Requirement: History grouped into timestamped sentences
The caption history SHALL be grouped into sentences, using the same sentence ends as the captions. Each sentence SHALL carry the local clock time at which its first words became final.

#### Scenario: Sentence spans two final phrases
- **WHEN** a sentence is split across two final English phrases
- **THEN** the history holds it as one sentence, timed at the first phrase

#### Scenario: Several sentences in one final phrase
- **WHEN** a final English phrase contains two complete sentences
- **THEN** the history holds them as two sentences

#### Scenario: Unfinished sentence when captioning stops
- **WHEN** captioning stops while the last final text does not end a sentence
- **THEN** that text is kept in the history as a sentence of its own and is not joined with the next session's first words

### Requirement: History shows recorded size
The control window SHALL show how many sentences the caption history holds, and SHALL update the count as captions are recorded, cleared or saved.

#### Scenario: Count grows while captioning
- **WHEN** new sentences are recorded
- **THEN** the control window shows the new sentence count

#### Scenario: Empty history
- **WHEN** nothing has been recorded yet, or the history was just cleared
- **THEN** the control window shows that the history is empty

### Requirement: Save history to a text file
The control window SHALL offer a save action that lets the user pick a file name and folder and saves the caption history there as UTF-8 plain text. Saving SHALL be possible while captioning is running or stopped. It SHALL NOT interrupt captioning and SHALL keep the history.

#### Scenario: Save after a session
- **WHEN** the user chooses to save the history and picks a file location
- **THEN** a text file containing the recorded English captions is written there, and the history is kept

#### Scenario: Save while captioning
- **WHEN** the user saves the history while captioning is active
- **THEN** the file contains everything recorded up to that moment, and captioning continues without a gap

#### Scenario: Cancel the save dialog
- **WHEN** the user opens the save dialog and cancels it
- **THEN** no file is written and the history is unchanged

#### Scenario: Nothing to save
- **WHEN** the caption history is empty
- **THEN** the save action is unavailable

#### Scenario: Suggested file name
- **WHEN** the save dialog opens
- **THEN** it suggests a `.txt` file name containing the current date and time, so successive saves do not overwrite each other by default

### Requirement: Saved file format
The saved file SHALL start with a header giving the date and time of saving. Each captioning session with recorded captions SHALL begin with a line giving its date, start time and audio source. Each sentence SHALL be on its own line, prefixed with its time as `[HH:MM:SS]`.

#### Scenario: Two sessions
- **WHEN** the user captions two sessions and then saves
- **THEN** the file shows the header, then the first session's line and its sentences in spoken order, then the second session's line and its sentences

#### Scenario: Session with no captions
- **WHEN** a session was started and stopped without any final text
- **THEN** the saved file has no line for that session

#### Scenario: Unfinished sentence at save time
- **WHEN** the user saves while the newest final text does not end a sentence yet
- **THEN** that text is included as the file's last sentence line

### Requirement: Clear history
The control window SHALL offer a clear action that empties the caption history after the user confirms. Clearing SHALL be possible while captioning is running or stopped and SHALL NOT change the overlay.

#### Scenario: Confirm clear
- **WHEN** the user chooses to clear the history and confirms
- **THEN** the history is empty, and captions recorded afterwards start a fresh history

#### Scenario: Cancel clear
- **WHEN** the user chooses to clear the history and then cancels
- **THEN** the history is unchanged

### Requirement: Ask before discarding unsaved history
When the user closes the app while the caption history holds captions that have not been saved, the system SHALL ask whether to save the history, discard it, or keep the app open. Captioning SHALL continue until the user decides to quit.

#### Scenario: Save before quitting
- **WHEN** the user closes the app with unsaved history and chooses to save
- **THEN** the save dialog opens, and the app quits after the file is written

#### Scenario: Save dialog cancelled while quitting
- **WHEN** the user closes the app with unsaved history, chooses to save, and then cancels the save dialog
- **THEN** the app stays open and the history is unchanged

#### Scenario: Discard and quit
- **WHEN** the user closes the app with unsaved history and chooses to discard it
- **THEN** the app quits without writing a file

#### Scenario: Keep the app open
- **WHEN** the user closes the app with unsaved history and chooses to cancel
- **THEN** the app stays open and captioning continues if it was running

#### Scenario: History already saved
- **WHEN** the user closes the app and every recorded caption has already been saved, or the history is empty
- **THEN** the app quits without asking

### Requirement: Save errors are visible
When the history file cannot be written, the system SHALL show the error in the control window in the same error style as other failures, SHALL keep the history unchanged, and SHALL NOT leave a partly written file in place of an existing one.

#### Scenario: Folder not writable
- **WHEN** the user saves to a location the app cannot write to
- **THEN** the control window shows a save error, the history is unchanged, and the app does not quit even if the save was part of quitting

#### Scenario: Overwriting an existing file fails
- **WHEN** the user saves over an existing file and the write fails partway
- **THEN** the existing file keeps its previous contents
