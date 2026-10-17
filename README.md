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
- `tools/cut_sheets.py`: cuts the painted art sheets in `tools/art/sheets/` (cell map in `SHEETS.md`) into the 66 sprites in `assets/art/`. The background is found by flood fill from the sheet border (plus enclosed pure-white pockets), so pale pieces (ghost, cot, lace, marble) keep their whites. Edges get a soft alpha with the white unmixed. Each piece is mirrored where needed so its front faces the viewer's lower right, its colours are gently harmonised, and the rug is warped flat onto its floor diamond. `--sheet` writes a review sheet. `art.ART_SCALE` corrects the size of a few pieces, and `tools/art_shots.py` saves room screenshots.
- `tools/make_walk.py`: builds Archie's and Holly's standing frames and 8-frame walk cycles (all four facings) from the high-resolution sources in `tools/art/`, entirely in code. Each source is cut into body, near and far legs, and near and far arms, then posed and downscaled to a 160 px figure. It also writes `assets/characters/<name>_walk.json` with the foot positions and the distance one cycle covers. In the game the walk advances by the distance actually walked, so the feet don't slide, and footsteps play on each touch-down. `tools/walk_sheets.py` makes review sheets and a GIF.
- `tools/make_sprites.py`: the older single-frame sprite builder (from Daleks in Hedges); `make_walk.py` now writes the standing frames.
- `tools/make_sounds.py`: synthesises all the spooky sounds.
- `tools/selftest.py`: headless test. It checks the data, that every room can be reached, and that every hiding place can be found, then plays the game automatically: a tour of all 35 rooms, 60 games straight to the key and out, and one game for every hiding place.
- `tools/shots.py`: saves sample screenshots.
- Debug: `python3 game.py --room crypt --no-enemies`, or headless `SDL_VIDEODRIVER=dummy python3 game.py --scene room --room library --screenshot out.png`.
