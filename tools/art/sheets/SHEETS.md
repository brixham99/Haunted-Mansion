# Generated art sheets (white background, 1024x576 JPEG); read left-to-right, top-to-bottom
enemies.jpg (3x2): ghost, goblin, bat | spider, skeleton, monster
furn1.jpg (3x2): grandfather_clock, wardrobe, bookcase | chest_of_drawers, kitchen_dresser, fireplace  -- SUPERSEDED by furn1_iso.jpg (kept, unused)
furn1_iso.jpg (3x2): grandfather_clock, wardrobe, bookcase | chest_of_drawers, kitchen_dresser, fireplace  (corner views)
furn2.jpg (3x2): piano, desk, wine_rack | barrel, coffin, toy_box
furn3.jpg (3x2): trunk, suit_of_armour, linen_press | bed, coal_heap, cauldron
furn4.jpg (3x2): chair, armchair, chest | crate, rocking_horse, dining_table
furn5.jpg (3x2): round_table, kitchen_table, sofa | billiard_table, range_cooker, sink
furn6.jpg (3x2): boiler, water_tank, tomb | mangle, washtub, bath  (boiler replaced by furn9_iso.jpg; old version kept, unused)
furn7.jpg (4x2): washstand, cot, potted_palm, statue | candelabra, pumpkin, dummy, harp  (pumpkin replaced by pumpkin_iso.jpg, harp by furn8_iso.jpg; old versions kept, unused)
wall.jpg: top row painting, painting_lady, painting_landscape, mirror, window, cobweb | bottom: key, sewing_machine
links.jpg: top row front_door, door_frame, stairs_up, stairs_down, ladder_up, trapdoor | bottom: rug, rug_lifted
furn8_iso.jpg (3x2): piano, linen_press, chair | armchair, rocking_horse, harp  (corner views; replace those items in furn2/3/4/7, whose old versions are kept but unused)
furn9_iso.jpg (2x1, 1280x720): (front-on pumpkin, unused), boiler  (corner view; furnace door faces lower left, mirrored)
pumpkin_iso.jpg (1x1, 1280x720): pumpkin  (corner view; face already to the lower right, not mirrored)
Note: furniture faces vary (some front-on/lower-left rather than lower-right); mirror where needed so the front faces lower right per the manifest.
faces1.jpg (3x3, 1280x720): flat elevations: fireplace front, fireplace pilaster side, marble mantel top | dresser base front, dresser plate-rack front, green side panel | chest of drawers front, mahogany side, mahogany top  (used by tools/iso_box.py)
faces2.jpg (4x3, 1280x720): flat elevations: bookcase front, oak side, wardrobe front, walnut side | piano front, piano keyboard top, black side panel, grandfather clock front | linen press front, desk front, desk top, toy box front  (used by tools/iso_box.py)
  -> fireplace, kitchen_dresser, chest_of_drawers, bookcase, wardrobe, piano, grandfather_clock, linen_press, desk, toy_box, kitchen_island are BUILT by `python3 tools/iso_box.py --build` (exact 2:1 boxes), not cut; their furn1_iso/furn8_iso/furn2 versions are unused.
organic_iso.jpg (4x1, 1280x720): armchair, chair, harp, rocking_horse  (corner views, front already to the lower right, not mirrored; replace the furn8_iso versions)
coffin, tomb, cot (furn2/furn6/furn7) are now mirrored so their long side lies along the 2-tile (lower-left) edge of the footprint.
chairs_back_iso.jpg (2x1, 1280x720): chair_ne, armchair_ne  (rear corner views: backrest on the near lower-left edge, seat running away to the upper right = facing N/upper right; not mirrored). cut_sheets.make_views() writes chair_/armchair_ se (front view, = chair.png/armchair.png), sw (mirror), ne (rear), nw (mirror).
bat_flap.jpg (4x1): bat animation: wings up, wings outstretched, wings down, wings folded  (cut by tools/cut_anims.py -> assets/art/bat_1..4.png; body centre fixed; the old bat.png stays as the fallback)
skeleton_walk.jpg (4x1): skeleton walk, purple coat, 3/4 view walking to screen right: stride, legs together, other stride, jolt  (cut by tools/cut_anims.py -> assets/art/skeleton_walk_1..4.png; boots on one ground line; mirrored in the game when walking to screen left, like every enemy)
vampire.jpg (4x1, 1280x720): floating Victorian vampire, black tailcoat and red-lined cape, hovering, feet hanging: cape flared, settling, settled, lifting  (cut by tools/cut_anims.py -> assets/art/vampire_1..4.png at the skeleton's height; head and shoulders centred, halo and cape-tip specks cleaned; looped at 6 fps, mirrored to screen left; NO shadow drawn)
kitchen_island (no sheet): Victorian kitchen island, green-painted cupboard base (the dresser's faces recoloured) under a butcher-block top with bread board, loaf, bowl and pan; BUILT by `python3 tools/iso_box.py --build` (3x3 tiles, solid, no floor shadow)

## The mummy and the black cat (cut by tools/cut_anims.py)

- `mummy_se.jpg`, `mummy_ne.jpg`: the Lumber Room mummy's four-frame shamble, arms straight out, front 3/4 (walking to the lower right) and back 3/4 (to the upper right). Mirrored in the game for the other two directions.
- `cat_e.jpg`, `cat_se.jpg`, `cat_s.jpg`, `cat_ne.jpg`, `cat_n.jpg`: the black cat's four-frame walk in five views. Mirrored, they give eight directions.
- `cat_poses.jpg`: sit, hiss (arched), curled up asleep, welcome stretch (front 3/4).
- `cat_poses_back.jpg`: sit, tail flick, bristling, bristling (from behind, facing the upper right).
