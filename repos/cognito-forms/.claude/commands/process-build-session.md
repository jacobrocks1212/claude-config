# Process Build Page Recording Session

Process a recorded build page session and update the master requirements document.

## Required Inputs

Parse the user's message for these inputs:
- **Jam Session**: A Jam session ID or URL (e.g., `abc123` or `https://jam.dev/c/abc123`)
- **Video File**: Path to the recorded video file (e.g., `.webm`, `.mp4`)
- **Model Snapshots**: Path to the model snapshots JSON file exported from `CognitoModelCapture.export()`

**Optional Inputs** (for enhanced documentation):
- **Visual Captures**: Path to visual captures JSON file exported from `CognitoModelCapture.exportVisual()`
- **Style Spec**: Path to style specification JSON file exported from `CognitoModelCapture.exportStyleSpec()`
- **API Contracts**: Path to API contracts JSON file exported from `CognitoModelCapture.exportApi()`
- **State Transitions**: Path to state transitions JSON file exported from `CognitoModelCapture.exportState()`

If the required inputs are missing, ask the user to provide them before proceeding.

## Processing Pipeline

Execute these steps in order:

### Step 1: Setup Session Directory

Create a session working directory:
```
.claude.local/sessions/<jam-session-id>/
```

### Step 2: Extract Audio from Video

Use ffmpeg to extract audio:
```bash
ffmpeg -i "<video-path>" -vn -acodec libmp3lame "<session-dir>/audio.mp3"
```

### Step 3: Transcribe Audio

Run the transcription script:
```bash
ASSEMBLYAI_API_KEY=<key> python "C:\Users\JacobMadsen\Desktop\transcribe.py" "<session-dir>/audio.mp3" -o "<session-dir>/transcript.json"
```

The API key is: `40b0486dabef4dcfad906dc6d5052652`

### Step 4: Fetch Jam Session Data

Use the Jam MCP tools to fetch all session data:

1. Extract the Jam session ID from the URL if needed (e.g., `https://jam.dev/c/abc123` -> `abc123`)

2. Call these MCP tools and save results:
   - `mcp__Jam__getDetails` - Get session metadata
   - `mcp__Jam__getConsoleLogs` - Get console output
   - `mcp__Jam__getNetworkRequests` - Get network activity
   - `mcp__Jam__analyzeVideo` - Get AI video analysis with timestamps

3. Combine all data into `<session-dir>/jam-data.json` using this structure:
```json
{
  "version": "1.0",
  "sessionId": "<id>",
  "fetchedAt": "<ISO timestamp>",
  "details": { /* from getDetails */ },
  "consoleLogs": [ /* from getConsoleLogs */ ],
  "networkRequests": [ /* from getNetworkRequests */ ],
  "videoAnalysis": [ /* from analyzeVideo */ ]
}
```

### Step 5: Copy Session Data Files

Copy the provided files to the session directory:
- Model snapshots → `<session-dir>/model-snapshots.json`
- Visual captures (if provided) → `<session-dir>/visual-captures.json`
- Style spec (if provided) → `<session-dir>/style-spec.json`
- API contracts (if provided) → `<session-dir>/api-contracts.json`
- State transitions (if provided) → `<session-dir>/state-transitions.json`

### Step 6: Correlate Session Data

Run the correlation tool with all available data sources:

```bash
node ".claude.local/tools/correlate-session-data.js" \
  --snapshots "<session-dir>/model-snapshots.json" \
  --transcript "<session-dir>/transcript.json" \
  --jam "<session-dir>/jam-data.json" \
  --visual "<session-dir>/visual-captures.json" \
  --styles "<session-dir>/style-spec.json" \
  --api "<session-dir>/api-contracts.json" \
  --state "<session-dir>/state-transitions.json" \
  --format json \
  --output "<session-dir>/correlated-timeline.json"
```

Note: Omit flags for files that weren't provided (e.g., `--visual`, `--styles`, `--api`, `--state`).

### Step 7: Update Master Requirements Document

The master document is located at: `.claude.local/build-page-requirements.md`

Read the correlated timeline and intelligently merge the new session's findings into the master document:

1. **If master document doesn't exist**: Create it with standard structure (sections for Field Operations, Form Settings, Workflow Configuration, etc.)

2. **If master document exists**:
   - Read existing content
   - Identify which sections the new session data belongs to
   - Merge new requirements, avoiding duplicates
   - Add new sections if the session covers previously undocumented areas
   - Preserve existing content while enriching with new details

3. **For each correlated event group**, extract:
   - What action the user performed (from transcript/video analysis)
   - What UI elements were involved (from Jam user events)
   - What model changes resulted (from snapshots)
   - What UI component was active (from visual captures)
   - What styles apply to that component (from style spec)
   - What API calls were made (from API contracts)
   - What state changes occurred (from state transitions)
   - Any patterns or requirements this reveals

4. **Document format** for each requirement:
   ```markdown
   ### [Feature/Action Name]

   **User Intent:** What the user is trying to accomplish

   **UI Flow:**
   1. Step-by-step interaction sequence

   **Active Component:** [Component name from visual capture]

   **Model Impact:**
   - Properties added/changed
   - Side effects

   **Style Specification:** (collapsible if present)
   - Key visual properties (font, colors, spacing)
   - Component selector

   **Sessions:** [list of session IDs that documented this]
   ```

### Step 8: Update Style Reference Document (if visual data provided)

If visual captures and style specs were provided, also update/create:
`.claude.local/build-page-style-reference.md`

This document aggregates all captured styles organized by component:

```markdown
# Build Page Style Reference

## FieldSettingsPanel
- Selector: `.c-forms-settings-field`
- Font: 14px/1.4 'Segoe UI'
- Background: #ffffff
- Border: 1px solid #e0e0e0
- ...

## FormSettingsPanel
...
```

### Step 9: Report Summary

After processing, report to the user:
- Session ID processed
- Number of events correlated
- Number of visual captures processed
- Number of unique components with style specs
- Number of API endpoints captured
- Number of state transitions and dependency edges
- Sections of master document updated
- Any notable findings or patterns
- Paths to updated documents:
  - Master requirements: `.claude.local/build-page-requirements.md`
  - Style reference: `.claude.local/build-page-style-reference.md` (if visual data was provided)
  - Expression language: `.claude.local/build-page-expression-language.md` (static reference)

## Capture Instructions for Users

To capture a session with full data (model, visual, API, and state):

1. Open the build page
2. Start Jam recording
3. In browser console, paste the combined capture script from `.claude.local/tools/capture-all.js`
   - This automatically initializes all capture modules
4. Use the build page while narrating your actions
5. When done, export all data:
   ```javascript
   CognitoModelCapture.exportAll('my-session');
   // Downloads:
   //   my-session-model-snapshots.json
   //   my-session-visual-captures.json
   //   my-session-style-spec.json
   //   my-session-api-contracts.json
   //   my-session-state-transitions.json
   ```
6. Stop Jam recording
7. Download the video from Jam

**Optional: Capture Schema**
To also capture the form's type schema:
```javascript
CognitoSchemaCapture.capture();
CognitoSchemaCapture.export('my-session-schema.json');
```

## Error Handling

- If ffmpeg fails, check the video path and format
- If transcription fails, verify the API key and audio file
- If Jam MCP tools fail, verify the session ID is accessible
- If correlation produces empty results, check timestamp alignment between sources
- If visual capture files are missing, proceed without visual data (behavioral docs only)

## User Input

$ARGUMENTS
