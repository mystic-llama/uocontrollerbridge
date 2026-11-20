# Development validation — 4.0.0-beta.1

108 automated checks passed under CPython 3.12 on Linux using offscreen Qt and
simulated controllers. The standalone listener parses with Python-2-compatible
grammar. No live Windows/RE execution is claimed.

New regression coverage:
- A large stick deflection is not learned as a bumper; ambiguous multi-button
  presses are rejected, and digital triggers take priority over incidental axes.
- An old bumper-as-cursor-axis mapping is blocked while a trigger continues holding
  left mouse through 30 movement samples; no All Follow Me action is dispatched.
- Duplicate physical IDs and trigger/stick overlap are detected.
- Four-button repair preserves action assignments and stick axes.
- Qt's button-check flow requires two matching presses with a release between.
- Old extra layers cannot activate or accept edits. Migration preserves Default
  bindings across profiles and saves the original configuration once locally.
- Native SendInput flags are checked for left/right down/up with zero cursor delta.
- Rejected presses are not marked held; rejected releases retry without a new down.
- The real Qt diagram selects buttons, saves LB pet / LT mouse assignments,
  highlights reported controls and switches to an equivalent list view.
- The UI has exactly Controller, Assignments, Preferences, Support; no weapon
  preparation button remains.

Retained checks cover all 137 spells, native agent/pet/item dispatch using mocks,
shortcut recording/playback worker cleanup, live configuration transactions,
revision/old-listener rejection, input recovery, target ownership, profile storage,
connection authentication and redacted support diagnostics.

The diagrams/screenshots are renders of the actual Qt implementation. They use
no UO Gump artwork. Windows build, installer execution, controller firmware and
actual game delivery require the steps in VALIDATION.md.
