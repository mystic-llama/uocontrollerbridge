# Spell-name verification

The standard book list contains 137 entries. It excludes passive Bushido features,
weapon-special lists, skill masteries and shard-specific custom spells.

User-provided reference tables: Magery(1).pdf, Mysticism(1).pdf, Necromancy(1).pdf,
Spellweaving(1).pdf. Only spell-name facts were used; descriptive text and artwork
are not redistributed. PDF text uses some ligatures and alternate naming:
Nightsight / Night Sight, Remove Trap / Magic Untrap, Archcure / Arch Cure, and
Archprotection / Arch Protection are searchable through the native names/aliases.

Native call names and accepted spell strings were checked against the public
Razor Enhanced spell dictionaries in:
https://raw.githubusercontent.com/UltimaTools/RazorEnhanced/master/Razor/RazorEnhanced/Spells.cs

This resolves omissions/typos in the generated API documentation, including
Mysticism Nether Bolt / Purge Magic / Spell Trigger, Ninjitsu Death Strike, and
Spellweaving Summon Fiend. Only factual spell names/IDs are retained; none of the
upstream C# implementation is incorporated. The controller validation/picker code
is independently implemented.

Official books/skills:
- https://uo.com/wiki/ultima-online-wiki/skills/bushido/
- https://uo.com/wiki/ultima-online-wiki/skills/ninjitsu/
- https://uo.com/wiki/ultima-online-wiki/skills/chivalry/
- https://razorenhanced.github.io/doc/api/Spells.html

The user screenshot specifies close 4018 (0xFB2), maximize 4006 (0xFA6), and
minimize 4015 (0xFAF). Pressed states use the matching 4019 / 4007 / 4016 artwork.
The maximize arrow restores the full Gump from compact view.

Live casting still depends on character skill, spellbook, mana, reagents,
followers, combat state and shard rules. Automated API-dispatch tests exercise
mock APIs, not the live client or server.
