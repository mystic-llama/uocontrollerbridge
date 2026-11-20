# 4.0.0-beta.1

- Removed extra LB assignment sets from runtime, templates, profiles and both UIs.
- Combined Play/Setup into Controller; retained Assignments, Preferences, Support.
- Added a scalable Qt controller silhouette with clickable controls, tooltips,
  selected/live input states and optional List view. Larger UI text.
- Removed weapon preparation and duplicate profile selection in Preferences.
- Corrected calibration accepting analog sticks as digital buttons. Added strict
  source conflict checks, digital-trigger priority and confirmed two-press learning.
- Added focused four-button input repair that preserves assignments and stick axes.
- Blocked suspect old mappings, and exposed physical sources/recent transitions.
- Added checked direct Win32 mouse down/up and rejected-release retry handling.
- Backed up existing local configuration once before retaining Default mappings.

# 3.3.0-beta.1

- Desktop Assignments tab: native category/search, all spell schools and a real
  single-chord keyboard recorder. Apply works live through a revision-checked
  host transaction with matching request/reply IDs and no Gump resume step.
- The optional Gump starts hidden. Preferences can re-enable it.
- Mouse-mapped LB never selects a modifier layer. Extra assignments default off.
- Movement arming is independent of cursor deflection and held buttons. Held
  buttons are quarantined until released, without blocking movement.
- Resume / recover clears both pause owners and controller-owned pending work
  without restarting processes. It preserves unrelated manual targeting.
- Keyboard shortcuts run on a bounded cancellable worker: modifier lead-in,
  minimum 60 ms hold, selected-process focus check, expiry and release cleanup.
- Play shows last input, native ACK errors and keyboard send status. Listener
  feedback distinguishes pending targets/recovery; copied diagnostics redact
  newly added free-form error strings.
- Incompatible connected listeners reject live desktop changes clearly.

# 4.0.0-beta.1

- New native action categories: Pets, Items / Hands, Agents, General, All.
- Six pet commands, Use Last Item, Arm Last Weapon, left/right/both hand controls.
- Start/stop/toggle controls for ten public agent/utility entries, Add Friend,
  and built-in Bone Cutter / Auto Carver / Auto Remount / Graphic Filter commands.
- Default mouse mappings remain active when L Bumper selects the shifted layer.
- Mouse assignments override scroll modifiers. Physical edges implement click,
  double-click and hold/drag; mouse lease refreshes while polling continues.
- Renamed confusing (hold) mouse labels to click / drag.
- Layer editor tabs use separate square hit targets and explain what they edit.
- Optional LB layer On/Off setting leaves saved assignments intact.
- Action buttons use a separate ID range so long lists cannot collide with
  direction / spell controls. Automatic action migration retains existing bindings.
- Includes the 3.1.1 Apply / Resume race and pause-owner fixes.

# 4.0.0-beta.1

- Fixes a reproduced neutral-arming race after Apply/Resume. The first neutral poll
  now arms controller and gameplay together. A button press immediately afterward
  can no longer strand game input waiting for another neutral sample.
- Separates application pause and Gump pause ownership, including resume feedback.
- Adds actual host action/layer and blocking reason to button telemetry and logs.
- Shows unassigned bindings, wrong game focus, neutral requirements and pause sources
  in the Gump footer rather than silently reporting only the detected button.
- Uses readable spell names in action-result messages and reports arming state in
  the desktop application.
- Adds host-loop tests exercising Apply, Resume, immediate button input, movement,
  and interleaved app/Gump pause controls using simulated hardware.

# 3.1.0-beta.1

- Adds a school-based picker for all 137 standard spells/abilities across seven books.
- Adds school search, Magery-circle filtering, pages and Manual/Self/Last targeting.
- Adds a configurable recovery lock for each chosen spell variant.
- Validates spell bindings in the host and stores only chosen variants.
- Keeps distinct targeting/recovery variants immutable so edits cannot alter another binding.
- Prunes unused generated spell actions while retaining variants used by inactive profiles.
- Adds Bushido and Ninjitsu native API dispatch and retains Chivalry support.
- Preserves all existing bindings, profiles, controller calibration and settings location.
- Uses close 4018, minimize 4015, and compact-view restore/maximize 4006 artwork.
- Keeps the curved controller silhouette and exact MysticLlama item/label signature.
- Reports a clear app-upgrade message if the picker connects to an older desktop host.

Requires rebuilding the desktop application and installing its matching listener.

# 3.0.0-beta.1

- Replaces the command-line setup with a Qt desktop app and guided calibration.
- Adds tray controls, whole-device pause, readable status and redacted diagnostics.
- Bundles a listener-installation workflow, with per-user settings outside the app.
- Adds Windows installer/portable build automation and draft GitHub release workflow.
- Preserves Devin's binding-list Gump, minimization, cursor curve and preview tool.
- Adds separate Caster, Dexxer, Blank and Custom saved assignments and filtered actions.
- Fixes class-specific custom keyboard chords overwriting each other's definitions.
- Uses the direct Windows desktop cursor as primary backend; retains absolute
  SendInput as a developer-selectable fallback. Keeps subpixel accumulation.
- Separates global cursor operation from strictly focused game input.
- Requires selected title/executable AND connected listener process ID for game input.
- Updates privilege notices even when changing between allowed game windows.
- Corrects D-pad Up graphics to 9900/9901 and refreshes button-learning UI reliably.
- Uses per-install token/HMAC session authentication; requires the new listener.
- Does not bundle the old virtual environment, personal calibration, logs or UO art.

This is a development beta. Automated checks do not replace real Windows/UO testing.
