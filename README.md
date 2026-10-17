# Haunted Mansion (working title)

A Halloween isometric flip-screen adventure in the style of Knight Lore and Head Over Heels. Play as Archie or Holly, explore a haunted mansion of 35 rooms over four floors, find the front door key (hidden somewhere different every game) and escape through the front door.

## Install and play

```bash
python3 -m pip install -r requirements.txt     # pygame-ce and numpy
python3 game.py
```

The game is drawn at 1280 x 800 and the window can be resized. It uses pygame-ce (the community edition of pygame), which installs ready-built on Macs where plain pygame will not build. If the old `pygame` package is installed, uninstall it first (`python3 -m pip uninstall pygame`), because the two share the name `pygame`.

## How to play

- **Left / Right (or A / D)** turn your character a quarter turn, the same as Daleks in Hedges. There are four ways to face, along the floor tiles: up-right, down-right, down-left and up-left. Hold the key to keep turning.
- **Up / Down (or W / S)** walk forwards and backwards in the direction you are facing. A quick tap takes a single step. Walking backwards keeps you facing the same way, which helps you back away from a ghost.
- You push furniture, climb stairs and search things by facing them.
- Walk through a doorway to flip to the next room. Bump into **stairs** or a **ladder** to go up; walk onto **stairs down** or an open **trapdoor** to go down.
- **Space or E** searches the furniture you are facing (wardrobes, bookcases, grandfather clocks, paintings, coffins...) or lifts a rug.
- **Walk into** chairs, armchairs, chests, crates and the rocking horse to push them. The key might be underneath. Rooms tidy themselves when you leave, so you can never get stuck.
- **Tab or M** shows the map of the rooms you have explored. **P** pauses. **Esc** goes back to the title screen.
- Ghosts and bats float through furniture; goblins, spiders, skeletons and the monster walk round it. If one touches you, you lose a life and go back to where you came in. You have three lives.
- Once you have the key, get back to the **Entrance Hall** and walk into the front door. Your time is shown at the end; your best time is saved on this computer.

## Scoring and high scores

- **1 point** for every second you are actually walking (forwards or backwards; turning on the spot, standing still or walking into a wall earns nothing).
- **5 points** the first time you go into each room in a game (the Entrance Hall, where you start, scores nothing).
- **50 points** for picking up the front door key, and **200 points** for escaping through the front door.
- Your score is shown at the top of the screen, and the bonuses float up over your head. The end screen shows your score and the best score.
- The title screen takes turns showing the controls and a shared online **Top 10** (dreamlo), with a flag for each player's country. If your score makes the Top 10 you can type a name (up to 8 letters or numbers). Without the internet, scores are kept in `~/.haunted_mansion/scores.json` and sent next time; the game never waits for the network.

## The mansion

| Floor | Rooms |
|---|---|
| Loft | Lumber Room, Dusty Attic, Water Tank Loft, Loft Landing, Servants' Quarters |
| First Floor | Nursery, Master Bedroom, Dressing Room, Bathroom, Landing, Portrait Gallery, Guest Bedroom, Sewing Room, Upper Corridor, Linen Room |
| Ground Floor | Conservatory, Drawing Room, Entrance Hall (front door), Study, Library, Music Room, West Corridor, Staircase Hall, East Corridor, Billiard Room, Ballroom, Dining Room, Kitchen, Scullery |
| Basement | Crypt, Wine Cellar, Coal Cellar, Laundry, Cellar Passage, Boiler Room |

Ways between floors: the grand stairs (Staircase Hall and Landing), the cellar steps (Kitchen and Cellar Passage), the scullery trapdoor (Scullery and Coal Cellar), the loft ladder (Upper Corridor and Loft Landing) and the back stairs (Linen Room and Servants' Quarters).

## For developers

- `mansion.py`: every room, door and staircase as plain Python data, plus validation, path-finding and key placement. Edit a room's `furn` list to move furniture.
- `objects.py`: every object and enemy type: size, behaviour, search messages and art description.
- `art.py`: loads real art from `assets/art/<name>.png` if it exists, otherwise draws a placeholder.
- `assets/ART_MANIFEST.md` / `.json`: every sprite needed, with sizes and descriptions (`python3 tools/write_manifest.py` rebuilds them). `assets/art_reference/` holds the placeholders as a layout guide.
- `tools/cut_sheets.py`: cuts the painted art sheets in `tools/art/sheets/` (cell map in `SHEETS.md`) into the 66 sprites in `assets/art/`. The background is found by flood fill from the sheet border (plus enclosed pure-white pockets), so pale pieces (ghost, cot, lace, marble) keep their whites. Edges get a soft alpha with the white unmixed. `furn1_iso.jpg` and `furn8_iso.jpg` (corner views) replace the front-on clock, wardrobe, bookcase, chest of drawers, dresser, fireplace, piano, linen press, chair, armchair, rocking horse and harp, and `furn9_iso.jpg` (right-hand object only) and `pumpkin_iso.jpg` replace the boiler and the pumpkin. The old sheets stay in the repo but are not used. Painted pale-grey ground shadows are turned into translucent black, so they darken the floor. Each piece is mirrored where needed so its front faces the viewer's lower right, its colours are gently harmonised, and the rug is warped flat onto its floor diamond. `--sheet` writes a review sheet. `art.ART_SCALE` corrects the size of a few pieces, and `tools/art_shots.py` saves room screenshots (`--iso` for the rooms with the corner-view pieces).
- `tools/make_walk.py`: builds Archie's and Holly's standing frames and 8-frame walk cycles (all four facings) from the high-resolution sources in `tools/art/`, entirely in code. Each source is cut into body, near and far legs, and near and far arms, then posed and downscaled to a 160 px figure. It also writes `assets/characters/<name>_walk.json` with the foot positions and the distance one cycle covers. In the game the walk advances by the distance actually walked, so the feet don't slide, and footsteps play on each touch-down. `tools/walk_sheets.py` makes review sheets and a GIF.
- `tools/make_sprites.py`: the older single-frame sprite builder (from Daleks in Hedges); `make_walk.py` now writes the standing frames.
- `tools/make_sounds.py`: synthesises all the spooky sounds.
- `tools/selftest.py`: headless test. It checks the data, that every room can be reached, and that every hiding place can be found, then plays the game automatically: a tour of all 35 rooms, 60 games straight to the key and out, and one game for every hiding place.
- `scores.py`: the online Top 10 (its own dreamlo board, separate from Daleks in Hedges and Dinosaur vs Bees), flags and the local scores file. Network calls run on background threads; HTTPS lookups fall back to certifi or no verification on a Python without CA certificates.
- `tools/score_test.py`: headless checks of every points rule (and whole games scored against an independent tally), plus qualifying, name entry and the faked dreamlo calls.
- `tools/shots.py`: saves sample screenshots.
- Debug: `python3 game.py --room crypt --no-enemies`, or headless `SDL_VIDEODRIVER=dummy python3 game.py --scene room --room library --screenshot out.png`.
