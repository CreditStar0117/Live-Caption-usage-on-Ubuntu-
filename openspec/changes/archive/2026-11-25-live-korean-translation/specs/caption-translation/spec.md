# Spec Delta

## Purpose

Translates final English captions into Korean on the user's own machine, so Korean-speaking users can follow English speech live without sending audio or text anywhere.

## ADDED Requirements

### Requirement: Optional Korean translation setting
The system SHALL let the user turn Korean translation on or off in the control window. Translation SHALL be off by default. The choice SHALL be remembered across restarts and SHALL apply the next time captioning starts.

#### Scenario: Default is off
- **WHEN** the user launches the app for the first time, or with saved settings that predate translation support
- **THEN** Korean translation is off, captions are English only, and the other saved settings still load

#### Scenario: Turn translation on
- **WHEN** the user turns Korean translation on while captioning is stopped and then starts captioning
- **THEN** final English captions are shown with Korean translations

#### Scenario: Setting locked while captioning
- **WHEN** captioning is active
- **THEN** the Korean translation setting cannot be changed until captioning stops

#### Scenario: Choice remembered
- **WHEN** the user turned Korean translation on and relaunches the app
- **THEN** the control window shows translation on and the next captioning session translates

### Requirement: On-device translation
The system SHALL translate captions entirely on the user's machine. No caption text or audio SHALL be sent over the network for translation. Network access SHALL be used only to download the translation model the first time it is needed.

#### Scenario: Offline translation
- **WHEN** the translation model has been downloaded and the machine has no network connection
- **THEN** Korean translation works normally

#### Scenario: No text leaves the machine
- **WHEN** captioning with Korean translation is active
- **THEN** the app makes no network requests that contain caption text or audio

### Requirement: Translation model first-use download
When translation is on and its model is not on disk yet, the system SHALL download the model when captioning starts. It SHALL show the download and loading status in the control window, and English captions SHALL start without waiting for the download.

#### Scenario: First start with translation on
- **WHEN** the user starts captioning with translation on and the translation model has never been downloaded
- **THEN** the control window shows that the translation model is downloading, English captions appear as usual meanwhile, and Korean starts appearing once the model is ready

#### Scenario: Sentences finished during the download
- **WHEN** English sentences become final while the translation model is still downloading or loading
- **THEN** those sentences are translated once the model is ready, as long as they are still in the caption history

#### Scenario: Model already downloaded
- **WHEN** the translation model is already on disk and the user starts captioning with translation on
- **THEN** no download happens and Korean starts appearing without a download delay

### Requirement: Translate final text only, by sentence
The system SHALL translate only final English text, never partial text. It SHALL translate each completed sentence once, so a Korean translation does not change after it appears. Final text whose sentence is unfinished SHALL be translated once its sentence completes.

#### Scenario: Partial text is not translated
- **WHEN** English text is still in progress
- **THEN** no Korean translation is shown for it

#### Scenario: Sentence spans two final phrases
- **WHEN** a sentence is split across two final English phrases
- **THEN** the system translates the whole sentence once after the second phrase becomes final, rather than translating each fragment

#### Scenario: Several sentences in one final phrase
- **WHEN** a final English phrase contains complete sentences
- **THEN** those sentences are translated without waiting for later speech

#### Scenario: Unfinished sentence when the speaker stops
- **WHEN** final English text does not end a sentence and no further final text arrives for about 2 seconds
- **THEN** the system translates that text as it is, so it does not stay untranslated

### Requirement: Translation does not delay English captions
English captions SHALL keep the latency and update rate they have without translation, whether the translation model is downloading, loading, translating or has failed. Translation SHALL run separately from speech recognition and from the user interface.

#### Scenario: Slow translation
- **WHEN** translating a sentence takes longer than usual
- **THEN** new English partial and final text keeps appearing on schedule, and the Korean appears when it is ready

#### Scenario: Translation backlog
- **WHEN** several sentences finish while a translation is still running
- **THEN** they are translated together as soon as the running translation ends, in their spoken order

### Requirement: Timely Korean text
With the default speech model on a typical 8-core desktop CPU, the median delay from an English sentence becoming complete to its Korean translation appearing SHALL be at most 2 seconds. This applies once the translation model is loaded.

#### Scenario: Continuous speech with translation
- **WHEN** a speaker talks continuously, captioning is active and the translation model is loaded
- **THEN** each completed sentence's Korean appears within 2 seconds of the sentence becoming complete in the median case

### Requirement: Translation errors are visible and non-fatal
When the translation model fails to download, load or run, the system SHALL show the error in the control window in the same error style as other failures. English captioning SHALL continue, and translation SHALL stay off for the rest of that session.

#### Scenario: Download fails
- **WHEN** the translation model cannot be downloaded (for example, no network on first use)
- **THEN** the control window shows a translation error, English captions continue, and no Korean is shown until captioning is restarted with a working model

#### Scenario: Translation fails mid-session
- **WHEN** translating a sentence fails while captioning is active
- **THEN** the control window shows a translation error, English captions continue, and Korean already on the overlay stays

#### Scenario: Retry after an error
- **WHEN** the cause of a translation error is fixed and the user stops and starts captioning again
- **THEN** translation is attempted again

### Requirement: Stopping discards pending translations
When captioning stops or restarts, the system SHALL drop any translation still pending or in progress from that session, and SHALL never show it in a later session.

#### Scenario: Stop during translation
- **WHEN** the user stops captioning while a sentence is being translated
- **THEN** its Korean is not shown, and starting again begins with an empty overlay
