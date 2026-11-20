# Native assignment actions — 4.0

Choose a controller control, then a category. Page arrows show the remaining
choices. Apply saves the draft; Resume enables gameplay. No new actions are
assigned automatically, and calibration / existing profiles are retained.

| Category | Actions |
| --- | --- |
| Pets | All Follow Me, All Come, All Guard Me, All Kill, All Stay, All Stop |
| Items / Hands | Use last item; Arm last weapon; Disarm, Arm, Toggle left / right / both hands |
| Agents | Start, Stop, Toggle for AutoLoot, Scavenger, BandageHeal, Organizer, Restock, Dress, UnDress, BuyAgent, SellAgent, DPSMeter; Add Friend; Bone Cutter / Auto Carver / Auto Remount toggles and target setup; Graphic Filter toggle |

Pets use Player.ChatSay with the corresponding spoken command. All Kill opens the
native targeting cursor; use the cursor stick and mouse button, or a Target Last
assignment, to select its target. These are native pet commands, not repeated loops.

Agents use the currently selected lists and bag/settings in Razor Enhanced.
Configure the agent in Razor first. A controller binding does not create lists,
choose containers or edit agent rules. Toggle queries the agent's native status.
Buy/Sell enable/disable their vendor agents; they do not open a vendor themselves.
Dress and Undress have independent running status; DPSMeter is included as a utility.

Add Friend uses Friend.AddFriendTarget and opens native targeting. Bone Cutter,
Auto Carver, Auto Remount and Graphic Filter have no public agent start/stop APIs
in the checked build. Their native hotkey commands are available directly in the
Agents picker without a registered keyboard key. An isolated .NET reflection
adapter calls only fixed, allowlisted Razor hotkey handlers, marshalled onto the
Razor UI thread. It supports Toggle and Set blade/mount as those native handlers
provide. Configure these tools in Razor before toggling them. If a fork changes
its handler or window implementation, the adapter reports an explicit error and
the other controller actions remain available. These internal integrations need
live validation against your particular Razor release.

Disarm removes equipped items to your backpack; it is distinct from the Disarm
weapon ability. Arm left/right/both restores items remembered by this running
listener's Disarm/Toggle commands. That memory survives pauses but is lost on a
listener restart. Arm last weapon uses Player.EquipLastWeapon and Razor/client
state instead. Two hand operations are spaced 600 ms apart in the listener loop,
without a blocking sleep; reset/disconnect cancels remaining operations.
Server inventory restrictions may reject an operation; check the game journal.

Use last item follows Razor's own Last Item state, including manually used items.
RE currently exposes no public Items.UseLastItem API, so this action reads the
internal Assistant.World.Player.LastObject property using .NET reflection, then
calls Items.UseItem. Normal IronPython imports cannot access the internal World
type. If a future Razor build changes this state, the action reports an error;
it never substitutes a guessed or remembered controller item. A manually assigned
Razor hotkey remains available for incompatible builds.

## Mouse assignments

Every control has one assignment. Extra LB assignments no longer exist. Tap to
click, tap twice to double-click, hold to drag, release to drop. Mouse bindings
override legacy run/scroll roles for that same control. Application pause disables
mouse too; the optional Gump's game pause retains mouse access for editing.

See DESKTOP_ASSIGNMENTS.md for button checking, checked Win32 injection and
privilege behavior. The removed weapon preparation wizard will not reopen from
an old capture flag; existing configured weapon actions/hotkeys remain usable.

## API references

Checked against Razor Enhanced's upstream source and generated API documentation:
- https://razorenhanced.github.io/doc/api/AutoLoot.html
- https://razorenhanced.github.io/doc/api/Organizer.html
- https://razorenhanced.github.io/doc/api/Restock.html
- https://razorenhanced.github.io/doc/api/Dress.html
- https://razorenhanced.github.io/doc/api/BuyAgent.html
- https://razorenhanced.github.io/doc/api/SellAgent.html
- https://razorenhanced.github.io/doc/api/Player.html
- https://github.com/UltimaTools/RazorEnhanced/blob/release/1.0/Razor/RazorEnhanced/HotKey.cs
- https://github.com/UltimaTools/RazorEnhanced/blob/release/1.0/Razor/Core/World.cs
- https://github.com/UltimaTools/RazorEnhanced/blob/release/1.0/Razor/Core/Player.cs
