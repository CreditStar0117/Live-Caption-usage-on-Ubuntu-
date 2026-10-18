# Spec Delta

## ADDED Requirements

### Requirement: Low-latency caption updates
While speech is present, the system SHALL refresh the in-progress caption text at least twice per second of audio when recognition keeps up. With the default model on a typical 8-core desktop CPU, the median delay from a spoken word to its first appearance on screen SHALL be at most 0.9 seconds.

#### Scenario: Words appear while still speaking
- **WHEN** a speaker talks continuously and captioning is active with the default model
- **THEN** each new word appears on screen within 0.9 seconds of being spoken in the median case, without waiting for a pause

#### Scenario: Recognition slower than refresh rate
- **WHEN** a recognition pass takes longer than the refresh interval
- **THEN** the next pass starts as soon as the previous one ends and covers all audio received so far, so the caption delay does not keep growing

### Requirement: Timely final text during continuous speech
The system SHALL turn in-progress text into final text when the speaker pauses, and also while the speaker keeps talking: finished sentences SHALL become final once the in-progress phrase is about 5 seconds long. No text SHALL stay in progress for more than 10 seconds of audio.

#### Scenario: Speaker pauses
- **WHEN** at least 0.5 seconds of silence follows speech
- **THEN** the phrase becomes final within 1 second after the silence began

#### Scenario: Long continuous speech with sentence boundaries
- **WHEN** the speaker talks without pausing and the in-progress phrase grows past about 5 seconds containing a finished sentence
- **THEN** the finished sentences become final text and only the unfinished remainder stays in progress

#### Scenario: Long continuous speech without a boundary
- **WHEN** the in-progress phrase reaches 10 seconds without any recognized boundary
- **THEN** the whole phrase becomes final text and a new phrase begins

#### Scenario: No words lost or duplicated at a split
- **WHEN** a phrase is split while the speaker is still talking
- **THEN** the split falls in a pause between words when one is near the recognized boundary, so no word is cut in half

### Requirement: Bounded recognition work
The system SHALL run at most one recognition pass at a time and SHALL NOT run speech recognition on audio that contains no new speech since the previous pass.

#### Scenario: Silence between phrases
- **WHEN** the captured audio is silent
- **THEN** no speech recognition pass runs until speech returns

#### Scenario: Pause after speech
- **WHEN** no new speech has arrived since a recognition pass that already covered the end of the speech
- **THEN** the system reuses that result rather than recognizing the same audio again

### Requirement: Selectable speed or accuracy model
The system SHALL let the user choose the speech model in the control window, between Accurate (`base.en`, the default) and Fast (`tiny.en`). The system SHALL remember the choice across restarts and SHALL apply it the next time captioning starts.

#### Scenario: Choose the fast model
- **WHEN** the user selects Fast while captioning is stopped and then starts captioning
- **THEN** captions are produced by the fast model

#### Scenario: Model not downloaded yet
- **WHEN** the selected model has never been downloaded and the user starts captioning
- **THEN** the system shows that the model is downloading, then starts captioning, and reports an error instead if the download fails

#### Scenario: Model locked while captioning
- **WHEN** captioning is active
- **THEN** the model choice cannot be changed until captioning stops

#### Scenario: Choice remembered
- **WHEN** the user selected a model and relaunches the app
- **THEN** the control window shows the same model and captioning uses it
