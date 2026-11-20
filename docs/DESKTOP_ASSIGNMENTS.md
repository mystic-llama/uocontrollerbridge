# Desktop assignments — 4.0

Choose a profile, click a controller button, choose an action and Apply. Hover
for the saved assignment. Green highlights reported active input. The diagram
uses native Qt vector drawing; it needs no UO client artwork. List view is an
alternative view of the same controls. Unavailable rear paddles are disabled.

There is exactly one assignment set per profile. No extra LB feature remains.
The one-time upgrade selects the old Default row in every profile, never replaces
it with shifted bindings, and backs up the original local configuration. Selecting
another profile previews it; Apply commits the profile plus selected assignment.

The editor accepts native actions with category/search, all 137 spells with target
and recovery settings, and actual recorded shortcut combinations. Keyboard macros
must already be assigned in Razor/ClassicUO. The worker cancels queued shortcuts
on focus loss/reset; a send report is not proof that the intended macro ran.

Apply uses a transaction with a revision and matching reply ID. A stale draft or
incompatible listener is rejected clearly. Native action calls stay in the RE
listener. Configuration is written by the running host; with it stopped the app
uses the same validator. The old Gump is optional and edits the same single set.

## Repair a mislearned bumper or trigger

Controller > Connection setup > Check bumpers / triggers checks LB, RB, LT, RT.
The selected physical input is pressed, released and pressed again. It preserves
all other sources and assignments. If previously running, the bridge stops while
the dialog owns pygame, then restarts after the dialog closes. The RE listener
is not stopped. Full Learn controller remains available for other bad sources.

A detected analog stick cannot be saved as a bumper or digital button. Analog
triggers cannot share movement/cursor axes. Duplicate physical control identities
are rejected. Combined triggers with opposite directions on the same non-stick
axis remain distinguishable. Rear paddles mirroring a button are not independent.

Suspect legacy mappings are blocked at runtime. Support includes physical source
IDs, recent down/up transitions, active controls and mapping diagnostics; copied
support data excludes tokens, character names, paths and free-form error text.
Only physical source data can establish whether an untouched bumper is reporting
an actual button event, a wrong axis or another duplicate source.

## Mouse

Direct Win32 SendInput emits left/right down and up separately, without moving
the pointer during a click. The cursor stick keeps moving while held. Events are
not repeated during a hold. Rejected down events are never marked held; failed up
attempts remain pending and are retried. Reset/disconnect releases held inputs.
Windows acceptance is shown on Controller, independently of any native RE ACK.

If game and bridge privileges differ, Windows may block input. The existing
privilege notice and Preferences > Restart as administrator remain available.
This cannot bypass Windows security boundaries or guarantee that a particular
ClassicUO input implementation accepts injected events.

API references:
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-mouseinput
- https://doc.qt.io/qtforpython-6.10/PySide6/QtWidgets/QKeySequenceEdit.html
