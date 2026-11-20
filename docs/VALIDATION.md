# In-game / Windows checks — 4.0

1. Build/install 4.0 and install/update its listener from Controller > Connection
   setup. Run the listener with Loop off. Existing saved assignments should remain.
2. Run Check bumpers / triggers once. Each control must require press/release/
   press. Save; verify all existing spell/pet/mouse assignments and stick settings
   are unchanged. The listener should not need restarting for this check.
3. Assign LB All Follow Me and LT left mouse as in the reported screenshot.
   Pull LT and move only the cursor stick for several seconds. Only LT should
   be active after correct calibration, with one Windows down until release.
   No All Follow Me speech should occur without actually pressing LB.
4. Assign LB left mouse, then test single click, double click and sustained drag.
   Move the cursor across monitors and out of UO. Check Windows accepted/rejected
   feedback and matching privilege levels. Verify release/reset/disconnect.
5. Compare diagram selection with List view. Click every available control,
   inspect its tooltip, Apply and confirm the corresponding physical control.
6. Confirm exactly four tabs and no extra assignment controls or weapon-preparation
   wizard. Saved profiles must retain their Default bindings after upgrade.
7. Recheck spell Self/Last/Manual, bandages/potions, pet targeting and each configured
   agent. These native features are retained; server acceptance still needs testing.
8. Record a working Ctrl+F1 macro, Apply, focus UO and use its controller button.
   Verify the actual weapon/macro action, not just the Windows-send status.
9. Test focus loss/return while holding a button or deflecting the cursor stick.
   Center movement once; no held game action should fire before release/repress.
10. If an untouched button still appears after checking, copy Support diagnostics
    immediately. Recent input transitions/source IDs distinguish incorrect mapping
    from real driver/hardware button reports. Do not assume a layer is involved.

Automated checks use simulated input and mocked Win32/RE APIs. Actual Windows
input, Bluetooth firmware, game injection, native API behavior and installer
execution cannot be confirmed by those tests alone.
