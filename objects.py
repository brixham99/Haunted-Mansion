"""Object and sprite types for Haunted Mansion (working title).

One table drives the game logic (size, solid, pushable, searchable) and the
art manifest (tools/write_manifest.py turns it into assets/ART_MANIFEST.*).

Geometry (native 1280x800, no scaling):
  TILE_W x TILE_H = 112 x 56 px (2:1 isometric diamond), WALL_H = 230 px.
  Archie and Holly are 160 px tall (168 px canvas).

Footprints are (width, depth) in tiles. "width" runs along the object's front
face, "depth" is front-to-back. Art is drawn FACING EAST: the front of the
object is the lower-RIGHT face on screen, its back against the upper-left
(west) wall. The game mirrors the image for objects facing south (against
the upper-right wall). A footprint (width, depth) facing east covers
(x: depth, y: width) tiles; facing south it covers (x: width, y: depth).

Canvas for a footprint covering (gx, gy) tiles and height h px:
  width  = (gx + gy) * TILE_W / 2
  height = (gx + gy) * TILE_H / 2 + h
with the footprint diamond touching the bottom edge, its lowest vertex
gx * TILE_W / 2 px from the left.
"""

TILE_W = 112
TILE_H = 56
WALL_H = 230
DOOR_H = 185
CHAR_H = 160
WALL_ART_W = 62   # flat width of one tile of wall (the true iso edge length)
WALL_MOUNT = {"front_door": 0, "door_frame": 0, "window": 50, "cobweb": WALL_H - 62, "mirror": 85}
WALL_MOUNT_DEFAULT = 100

# kind: "furniture" (stands on a footprint), "flat" (on the floor, walk over),
# "wall" (hangs on a back wall, 1 tile wide unless "span"), "link" (stairs,
# ladders, trapdoors), "enemy", "item", "fx".
# Flags: solid, push (can be shoved one tile), lift (rug: lift to look under),
# search (interact to look inside/behind), glow (casts light).
T = {}


def _t(name, kind, size=(1, 1), h=0, desc="", **flags):
    T[name] = dict(name=name, kind=kind, size=size, h=h, desc=desc, **flags)


# ---- furniture: hiding places (search) ----
_t("grandfather_clock", "furniture", (1, 1), 215, "Tall Victorian longcase clock, dark mahogany, pale moon-faced dial, brass pendulum behind a glass door.", solid=True, search="behind")
_t("wardrobe", "furniture", (2, 1), 225, "Heavy double wardrobe, dark oak, carved cornice, two doors with brass handles, one door slightly ajar.", solid=True, search="in")
_t("bookcase", "furniture", (2, 1), 215, "Floor-to-ceiling bookcase crammed with leather-bound books, a skull and a candle on one shelf, cobwebs in a corner.", solid=True, search="behind")
_t("chest_of_drawers", "furniture", (2, 1), 100, "Bedroom chest of drawers, walnut, four drawers with brass knobs, a candle and a hand mirror on top.", solid=True, search="in")
_t("kitchen_island", "furniture", (2, 1), 90, "Victorian kitchen island: panelled cupboard base painted deep green, brass handles, on a plinth, under a scrubbed butcher-block top with a loaf, a mixing bowl and a copper pan.", solid=True, search="in")
_t("kitchen_dresser", "furniture", (2, 1), 205, "Welsh kitchen dresser, painted pale green and peeling, plates on the rack, cupboards below.", solid=True, search="in")
_t("fireplace", "furniture", (2, 1), 165, "Marble fireplace with a black iron grate, faint green ghostly flames, candlesticks on the mantelpiece.", solid=True, search="in", glow=(120, 255, 160))
_t("piano", "furniture", (2, 1), 125, "Upright piano, black lacquer, yellowed keys, sheet music and a candelabra on top.", solid=True, search="in")
_t("desk", "furniture", (2, 1), 80, "Writing desk with green leather top, ink pot, quill and scattered letters, drawers below.", solid=True, search="in")
_t("wine_rack", "furniture", (2, 1), 195, "Wooden wine rack full of dusty bottles, cobwebs between the necks.", solid=True, search="behind")
_t("barrel", "furniture", (1, 1), 90, "Oak wine barrel on its side on a cradle, iron hoops, a dripping tap.", solid=True, search="in")
_t("coffin", "furniture", (1, 2), 60, "Old wooden coffin with a slightly open lid, brass handles, cobwebs.", solid=True, search="in")
_t("toy_box", "furniture", (1, 1), 60, "Painted wooden toy box, lid ajar, a teddy's arm poking out.", solid=True, search="in")
_t("trunk", "furniture", (1, 1), 65, "Battered travel trunk with leather straps and faded shipping labels.", solid=True, search="in")
_t("suit_of_armour", "furniture", (1, 1), 200, "Suit of armour on a plinth holding a halberd, visor down, a hint of red glow inside.", solid=True, search="in")
_t("linen_press", "furniture", (2, 1), 210, "Tall linen press, painted cream, folded sheets visible through a cracked glass door.", solid=True, search="in")
_t("bed", "furniture", (2, 3), 155, "Four-poster bed with tattered dark-red curtains, rumpled sheets, pillows at the head (head end against the wall).", solid=True, search="under")
_t("coal_heap", "furniture", (2, 2), 55, "Heap of coal against the wall with a shovel stuck in it.", solid=True, search="in")
_t("cauldron", "furniture", (1, 1), 75, "Black iron cauldron with green bubbling brew and a wooden ladle.", solid=True, search="in", glow=(120, 255, 120))

# ---- furniture: pushable (the key can be hidden underneath) ----
_t("chair", "furniture", (1, 1), 100, "Dining chair, high carved back, faded velvet seat.", solid=True, push=True)
_t("armchair", "furniture", (1, 1), 95, "Wingback armchair, worn green velvet, stuffing poking out of one arm.", solid=True, push=True)
_t("chest", "furniture", (1, 1), 60, "Small iron-bound wooden chest on the floor (heavy, but can be pushed).", solid=True, push=True)
_t("crate", "furniture", (1, 1), 75, "Wooden packing crate stencilled FRAGILE, nails sticking out.", solid=True, push=True)
_t("rocking_horse", "furniture", (1, 1), 95, "Dappled rocking horse with a missing eye and a tatty mane.", solid=True, push=True)

# ---- furniture: solid scenery ----
_t("dining_table", "furniture", (3, 2), 70, "Long dining table, white tablecloth with stains, candelabra, a rotting feast.", solid=True)
_t("round_table", "furniture", (1, 1), 70, "Small round side table with a lace cloth and a crystal ball.", solid=True)
_t("kitchen_table", "furniture", (2, 2), 70, "Scrubbed pine kitchen table, a cleaver, a pumpkin being carved.", solid=True)
_t("sofa", "furniture", (2, 1), 80, "Chesterfield sofa, cracked oxblood leather, a moth-eaten cushion.", solid=True)
_t("billiard_table", "furniture", (3, 2), 70, "Billiard table, green baize, balls mid-game, cues against it.", solid=True)
_t("range_cooker", "furniture", (2, 1), 100, "Black cast-iron kitchen range with ovens and a kettle on the hob.", solid=True)
_t("sink", "furniture", (1, 1), 85, "Butler's sink on brick legs, a dripping brass tap.", solid=True)
_t("boiler", "furniture", (2, 2), 210, "Huge riveted iron boiler with pipes, gauges and a glowing furnace door.", solid=True, glow=(255, 140, 60))
_t("water_tank", "furniture", (2, 2), 165, "Galvanised loft water tank, rusty, a ladder up its side.", solid=True)
_t("tomb", "furniture", (1, 2), 80, "Stone sarcophagus with a carved knight lying on the lid.", solid=True)
_t("mangle", "furniture", (1, 1), 105, "Cast-iron laundry mangle with wooden rollers and a big wheel.", solid=True)
_t("washtub", "furniture", (1, 1), 60, "Zinc wash tub with a washboard and grey water.", solid=True)
_t("bath", "furniture", (2, 1), 70, "Roll-top bath on claw feet, green slime in the bottom.", solid=True)
_t("washstand", "furniture", (1, 1), 90, "Marble-topped washstand with a jug and bowl.", solid=True)
_t("cot", "furniture", (1, 2), 140, "Victorian baby cot with white painted bars and a mobile of bats.", solid=True)
_t("potted_palm", "furniture", (1, 1), 135, "Dead palm in a brass pot, brown drooping fronds.", solid=True)
_t("statue", "furniture", (1, 1), 175, "Marble statue of a weeping angel on a plinth, covered in ivy.", solid=True)
_t("candelabra", "furniture", (1, 1), 140, "Tall iron floor candelabra with five dripping lit candles.", solid=True, glow=(255, 190, 90))
_t("pumpkin", "furniture", (1, 1), 50, "Carved jack-o'-lantern, grinning face lit from inside.", solid=True, glow=(255, 150, 40))
_t("dummy", "furniture", (1, 1), 150, "Dressmaker's dummy on a stand, half-finished black gown, pins in it.", solid=True)
_t("harp", "furniture", (1, 1), 165, "Gilded concert harp with several broken strings.", solid=True)
_t("sewing_machine", "furniture", (1, 1), 85, "Treadle sewing machine on an iron stand.", solid=True)

# ---- flat floor objects ----
_t("rug", "flat", (2, 2), 6, "Persian rug, faded red and gold, frayed tassels (lies flat; the player can lift a corner).", lift=True)
_t("rug_lifted", "flat", (2, 2), 22, "The same rug with one corner rolled back.")

# ---- wall hangings (drawn flat-on; the game shears them onto the wall) ----
# Flat art is WALL_ART_W px per tile of span wide and h px tall; on screen it
# is squeezed to TILE_W / 2 px per tile and sheared along the wall.
# `mount` = px from the floor to the bottom of the hanging.
_t("painting", "wall", (1, 1), 84, "Gilt-framed oil portrait of a stern Victorian gentleman whose eyes follow you. Flat front view, portrait 3:4.", search="behind")
_t("painting_lady", "wall", (1, 1), 84, "Gilt-framed portrait of a pale lady in a black mourning dress. Flat front view, portrait 3:4.", search="behind")
_t("painting_landscape", "wall", (2, 1), 70, "Wide gilt-framed painting of this mansion on a hill at night under a full moon. Flat front view, landscape 2:1.", search="behind")
_t("mirror", "wall", (1, 1), 90, "Tarnished oval mirror in a black frame, a faint ghostly face in the glass. Flat front view.")
_t("window", "wall", (1, 1), 140, "Tall arched leaded window, moonlight and bare branches outside, torn curtain. Flat front view.")
_t("cobweb", "wall", (1, 1), 62, "Big corner cobweb with a small spider. Flat front view, transparent background.")
_t("front_door", "wall", (2, 1), 185, "Grand double front door, studded oak, iron hinges, big keyhole, fanlight above. Flat front view.")
_t("door_frame", "wall", (2, 1), 185, "Interior doorway frame: painted wooden architrave round a dark opening. Flat front view, centre transparent.")

# ---- links between floors ----
_t("stairs_up", "link", (2, 2), 230, "Wooden staircase rising towards the back wall, carved banister (bump into it to go up).", solid=True)
_t("stairs_down", "link", (2, 2), 6, "Opening in the floor with stone steps going down into darkness, low railing (walk onto it to go down).")
_t("ladder_up", "link", (1, 1), 230, "Wooden ladder against the wall up to a square loft hatch in the ceiling (bump into it to climb).", solid=True)
_t("trapdoor", "link", (1, 1), 6, "Open wooden trapdoor in the floor, a ladder going down into darkness (walk onto it to drop down).")

# ---- items ----
_t("key", "item", (1, 1), 50, "Large ornate iron front door key with a skull bow, faint golden glint.", glow=(255, 230, 120))

# ---- enemies (one image each, facing screen-right; mirrored for left) ----
_t("ghost", "enemy", (1, 1), 150, "Floating Victorian ghost in a tattered white sheet, hollow black eyes, wispy tail instead of feet, semi-transparent.")
_t("goblin", "enemy", (1, 1), 105, "Small green goblin with pointy ears, ragged brown tunic, toothy grin, holding a candle stub.")
_t("bat", "enemy", (1, 1), 60, "Black bat, wings spread, red eyes (flies at head height).")
_t("spider", "enemy", (1, 1), 70, "Big hairy black spider with red markings, eight legs, glinting eyes.")
_t("skeleton", "enemy", (1, 1), 198, "Rattling skeleton in a tattered top hat, bony arms reaching forward.")
_t("vampire", "enemy", (1, 1), 196, "Floating Victorian vampire, black tailcoat and waistcoat, black cape lined with red, high collar, pale face, clawed hands reaching (casts no shadow).")
_t("monster", "enemy", (1, 1), 190, "Hulking Frankenstein-style monster, green-grey skin, neck bolts, stitched face, too-small black suit.")

ENEMY_STATS = {
    # speed (tiles/s), sense (tiles), floats (through furniture), radius (tiles)
    "ghost": dict(speed=1.1, sense=5.0, floats=True, r=0.32, z=24),
    "bat": dict(speed=2.4, sense=4.0, floats=True, r=0.25, z=80),
    "goblin": dict(speed=1.7, sense=4.5, floats=False, r=0.30, z=0),
    "spider": dict(speed=2.2, sense=3.0, floats=False, r=0.30, z=0),
    "skeleton": dict(speed=1.4, sense=5.0, floats=False, r=0.30, z=0),
    "monster": dict(speed=1.0, sense=6.0, floats=False, r=0.36, z=0),
    "vampire": dict(speed=1.15, sense=5.0, floats=True, r=0.30, z=44),   # hovers, drifts, glides at you
}

# British English flavour text when a search finds nothing.
SEARCH_LINES = {
    "grandfather_clock": ["Just the tick of the pendulum.", "Nothing behind the clock but dust."],
    "wardrobe": ["Moth-eaten coats and nothing else.", "Something rustles... just a moth."],
    "bookcase": ["Dusty old books. No key here.", "A book falls open: 'Beware the cellar'."],
    "chest_of_drawers": ["Old socks and a dead spider.", "Lavender bags, long gone stale."],
    "kitchen_dresser": ["Cracked plates and a jar of pickled eyes.", "Nothing but crockery."],
    "kitchen_island": ["Wooden spoons, a rolling pin and a mousetrap (empty).", "Pudding basins and string."],
    "fireplace": ["Cold ashes. Nothing here.", "The chimney moans at you."],
    "piano": ["A wrong note plays all by itself.", "Nothing inside but felt and wire."],
    "desk": ["Unpaid bills from 1887.", "A quill, some ink, no key."],
    "wine_rack": ["Very old wine. Very empty.", "Nothing behind the bottles."],
    "barrel": ["It smells of vinegar.", "Empty, and very sticky."],
    "coffin": ["Thankfully empty.", "Just a lot of cobwebs."],
    "toy_box": ["A teddy bear stares at you.", "Broken toys, no key."],
    "trunk": ["Old letters and a top hat.", "Nothing but moth-balls."],
    "suit_of_armour": ["You lift the visor. Empty. Probably.", "Clank! Nothing inside."],
    "linen_press": ["Neatly folded sheets. Spooky.", "Nothing between the pillowcases."],
    "bed": ["Nothing under the bed. This time.", "Dust bunnies the size of cats."],
    "coal_heap": ["Lots of coal. Mucky hands.", "No key in the coal."],
    "cauldron": ["It bubbles. No key, just eyeballs.", "You'd rather not put your hand in again."],
    "painting": ["Nothing behind the painting.", "The eyes follow you. No key."],
    "painting_lady": ["Nothing behind the portrait.", "She seems to sigh. No key."],
    "painting_landscape": ["Nothing behind the picture.", "Just a damp patch on the wall."],
}

SEARCH_PHRASE = {"behind": "behind the {n}", "in": "in the {n}", "under": "under the {n}"}

NICE_NAMES = {"grandfather_clock": "grandfather clock", "chest_of_drawers": "chest of drawers",
              "kitchen_dresser": "kitchen dresser", "kitchen_island": "kitchen island", "wine_rack": "wine rack", "toy_box": "toy box",
              "suit_of_armour": "suit of armour", "linen_press": "linen press", "coal_heap": "coal heap",
              "painting_lady": "portrait", "painting_landscape": "painting", "rocking_horse": "rocking horse"}


def nice(name: str) -> str:
    return NICE_NAMES.get(name, name.replace("_", " "))


def footprint(name: str, facing: str):
    """(gx, gy) tiles covered by an object of this type facing E/W or S/N."""
    w, d = T[name]["size"]
    return (d, w) if facing in ("E", "W") else (w, d)


def canvas_size(gx: int, gy: int, h: int):
    return (gx + gy) * TILE_W // 2, (gx + gy) * TILE_H // 2 + h
