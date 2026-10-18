"""The mansion: room definitions (data), doors, stairs, and the pure logic
that the game and the self-test share (no pygame here).

Coordinates inside a room: x runs along the upper-right ("north") wall,
y along the upper-left ("west") wall; tile (x, y) covers [x, x+1) x [y, y+1).
On screen x goes down-right and y goes down-left. The north (N, y = 0) and
west (W, x = 0) walls are drawn; the south (S) and east (E) edges are open
to the viewer (Knight Lore style) and their doorways are marked on the floor.

Each room sits on a per-floor map grid at `map` = (mx, my). A door on side
N leads to the room at (mx, my - 1), S to (mx, my + 1), W to (mx - 1, my),
E to (mx + 1, my). Doors are two tiles wide and centred unless `at` is given.

To tweak a layout, edit the room's `furn` list:
    (type, x, y, facing[, link_target])
`facing` is where the front points: "E" (object backs onto the west wall) or
"S" (backs onto the north wall). Chairs and armchairs can face any of N, E,
S, W (art for all four), or "auto": a chair next to a table or desk faces
it, an armchair near a fireplace faces the fire, anything else faces the
middle of the room (see Room.aim_seat). Wall hangings: (type, side, index[, mount]).
Run `python3 tools/selftest.py` afterwards; it checks bounds, overlaps,
doorways kept clear, reachability and every possible key hiding place.
"""

from __future__ import annotations

import random
from collections import deque

from objects import T, TILE_H, TILE_W, WALL_MOUNT, WALL_MOUNT_DEFAULT, footprint

FLOORS = ("basement", "ground", "first", "loft")
FLOOR_NAMES = {"basement": "Basement", "ground": "Ground Floor", "first": "First Floor", "loft": "Loft"}
START_ROOM = "entrance_hall"
# Where the key goes. False (for now): always out in the open on a floor tile
# you can see and reach, in a random room. True: the original game, where it
# is usually hidden inside, behind or under something (see place_key).
KEY_HIDDEN = False
DOOR_W = 2

# floor: boards | marble | flagstone | carpet | tiles | planks ; wall: panel | damask | stripe | brick | stone | plaster | beams
STYLES = {
    "hall":      dict(floor="marble", f1=(196, 190, 176), f2=(38, 36, 40), wall="panel", w1=(46, 66, 52), w2=(98, 72, 44)),
    "drawing":   dict(floor="carpet", f1=(104, 34, 40), f2=(132, 96, 46), wall="damask", w1=(92, 34, 44), w2=(150, 110, 70)),
    "glass":     dict(floor="tiles", f1=(150, 140, 120), f2=(84, 92, 82), wall="plaster", w1=(118, 132, 120), w2=(90, 104, 92)),
    "wood":      dict(floor="boards", f1=(108, 72, 44), f2=(84, 54, 32), wall="panel", w1=(70, 44, 30), w2=(110, 74, 44)),
    "green":     dict(floor="boards", f1=(96, 66, 42), f2=(74, 50, 30), wall="stripe", w1=(44, 70, 54), w2=(60, 92, 70)),
    "blue":      dict(floor="carpet", f1=(40, 52, 96), f2=(80, 90, 140), wall="damask", w1=(40, 50, 84), w2=(100, 110, 150)),
    "ball":      dict(floor="boards", f1=(150, 110, 62), f2=(124, 88, 48), wall="damask", w1=(110, 92, 50), w2=(170, 150, 90)),
    "kitchen":   dict(floor="tiles", f1=(150, 66, 50), f2=(60, 40, 34), wall="plaster", w1=(150, 144, 120), w2=(112, 106, 86)),
    "cellar":    dict(floor="flagstone", f1=(86, 84, 80), f2=(60, 58, 56), wall="brick", w1=(92, 54, 40), w2=(60, 40, 32)),
    "crypt":     dict(floor="flagstone", f1=(70, 76, 80), f2=(48, 52, 56), wall="stone", w1=(78, 82, 88), w2=(54, 58, 64)),
    "bedroom":   dict(floor="carpet", f1=(70, 40, 74), f2=(120, 90, 120), wall="stripe", w1=(90, 70, 96), w2=(70, 52, 78)),
    "nursery":   dict(floor="boards", f1=(130, 100, 70), f2=(110, 82, 56), wall="stripe", w1=(150, 120, 120), w2=(120, 140, 150)),
    "bath":      dict(floor="tiles", f1=(200, 200, 196), f2=(40, 60, 70), wall="plaster", w1=(90, 130, 130), w2=(70, 104, 104)),
    "loft":      dict(floor="planks", f1=(92, 74, 56), f2=(70, 56, 42), wall="beams", w1=(96, 84, 70), w2=(60, 46, 34)),
    # the landings: their own walls, with a warm oak herringbone parquet floor
    "landing":   dict(floor="parquet", f1=(152, 104, 60), f2=(116, 76, 42), wall="panel", w1=(46, 66, 52), w2=(98, 72, 44)),
    "loft_landing": dict(floor="parquet", f1=(140, 98, 58), f2=(106, 72, 42), wall="beams", w1=(96, 84, 70), w2=(60, 46, 34)),
}


def R(name, floor, map_pos, size, style, furn=(), wall=(), enemies=()):
    return dict(name=name, floor=floor, map=map_pos, size=size, style=style,
                furn=list(furn), wall=list(wall), enemies=list(enemies))


ROOMS = {
    # ------------------------------------------------------------ ground floor
    "entrance_hall": R("Entrance Hall", "ground", (2, 0), (9, 8), "hall",
        furn=[("grandfather_clock", 0, 1, "E"), ("suit_of_armour", 1, 0, "S"), ("suit_of_armour", 6, 0, "S"),
              ("rug", 3, 3, "S"), ("potted_palm", 0, 7, "E"), ("pumpkin", 8, 6, "S"), ("candelabra", 8, 0, "S")],
        wall=[("front_door", "N", 3), ("painting", "W", 5), ("window", "N", 7)]),
    "drawing_room": R("Drawing Room", "ground", (1, 0), (8, 7), "drawing",
        furn=[("fireplace", 3, 0, "S"), ("armchair", 2, 1, "auto"), ("armchair", 5, 1, "auto"), ("sofa", 0, 5, "E"),
              ("round_table", 6, 4, "S"), ("rug", 3, 3, "S"), ("piano", 6, 0, "S")],
        wall=[("painting_lady", "N", 1), ("mirror", "W", 0), ("window", "W", 5)], enemies=["ghost"]),
    "conservatory": R("Conservatory", "ground", (0, 0), (8, 8), "glass",
        furn=[("potted_palm", 0, 0, "E"), ("potted_palm", 0, 7, "E"), ("statue", 7, 0, "S"), ("potted_palm", 3, 0, "S"),
              ("round_table", 4, 4, "S"), ("chair", 5, 4, "auto"), ("chest", 1, 5, "S")],
        wall=[("window", "N", 2), ("window", "N", 5), ("window", "W", 2), ("window", "W", 5)], enemies=["bat", "goblin"]),
    "music_room": R("Music Room", "ground", (0, 1), (8, 7), "blue",
        furn=[("piano", 0, 0, "E"), ("harp", 6, 0, "S"), ("chair", 2, 3, "auto"), ("chair", 5, 3, "auto"), ("candelabra", 0, 5, "S")],
        wall=[("painting_landscape", "N", 1), ("painting_lady", "W", 3)], enemies=["ghost"]),
    "west_corridor": R("West Corridor", "ground", (1, 1), (9, 4), "wood",
        furn=[("suit_of_armour", 1, 0, "S"), ("suit_of_armour", 6, 0, "S"), ("chair", 7, 3, "auto")],
        wall=[("painting", "N", 7), ("painting_lady", "N", 0)], enemies=["goblin"]),
    "staircase_hall": R("Staircase Hall", "ground", (2, 1), (8, 8), "hall",
        furn=[("stairs_up", 6, 0, "S", "landing"), ("grandfather_clock", 0, 0, "S"), ("statue", 0, 7, "E"),
              ("rug", 2, 5, "S"), ("candelabra", 0, 1, "E")],
        wall=[("painting", "W", 5), ("painting_landscape", "N", 1)], enemies=["ghost"]),
    "east_corridor": R("East Corridor", "ground", (3, 1), (9, 4), "wood",
        furn=[("suit_of_armour", 7, 0, "S"), ("potted_palm", 0, 0, "S"), ("round_table", 1, 3, "S"), ("chair", 6, 3, "auto")],
        wall=[("painting", "N", 2), ("painting_lady", "N", 5), ("cobweb", "N", 8)], enemies=["skeleton"]),
    "study": R("Study", "ground", (3, 0), (7, 7), "green",
        furn=[("desk", 3, 0, "S"), ("chair", 3, 1, "auto"), ("bookcase", 0, 0, "E"), ("round_table", 5, 5, "S"),
              ("armchair", 1, 5, "auto"), ("trunk", 6, 0, "S")],
        wall=[("painting", "N", 1), ("window", "N", 5)], enemies=["goblin"]),
    "library": R("Library", "ground", (4, 0), (8, 8), "wood",
        furn=[("bookcase", 0, 0, "E"), ("bookcase", 0, 5, "E"), ("bookcase", 1, 0, "S"), ("bookcase", 3, 0, "S"),
              ("bookcase", 5, 0, "S"), ("desk", 3, 4, "S"), ("armchair", 5, 5, "auto"), ("candelabra", 7, 0, "S")],
        wall=[("cobweb", "W", 7)], enemies=["ghost", "spider"]),
    "billiard_room": R("Billiard Room", "ground", (4, 1), (8, 8), "green",
        furn=[("billiard_table", 2, 3, "S"), ("chair", 6, 1, "auto"), ("armchair", 7, 6, "auto"), ("round_table", 0, 0, "S"),
              ("suit_of_armour", 0, 6, "E")],
        wall=[("painting_landscape", "W", 1), ("window", "N", 6), ("painting", "N", 1)], enemies=["goblin", "skeleton"]),
    "ballroom": R("Ballroom", "ground", (0, 2), (9, 9), "ball",
        furn=[("statue", 0, 0, "E"), ("statue", 8, 0, "S"), ("candelabra", 0, 8, "E"), ("candelabra", 8, 8, "S"),
              ("piano", 0, 5, "E"), ("chair", 2, 1, "auto"), ("chair", 6, 1, "auto"), ("harp", 1, 0, "S")],
        wall=[("mirror", "N", 2), ("mirror", "N", 6), ("window", "W", 1), ("window", "W", 7)], enemies=["ghost", "ghost"]),
    "dining_room": R("Dining Room", "ground", (1, 2), (9, 8), "drawing",
        furn=[("dining_table", 3, 3, "S"), ("chair", 3, 2, "auto"), ("chair", 5, 2, "auto"),
              ("chair", 3, 5, "auto"), ("chair", 5, 5, "auto"), ("chair", 2, 3, "auto"), ("chair", 6, 4, "auto"),
              ("fireplace", 6, 0, "S"),
              ("kitchen_dresser", 0, 6, "E")],
        wall=[("painting", "N", 1), ("painting_lady", "W", 1)], enemies=["goblin"]),
    "kitchen": R("Kitchen", "ground", (2, 2), (8, 8), "kitchen",
        furn=[("stairs_down", 6, 0, "S", "cellar_passage"), ("range_cooker", 0, 0, "E"), ("kitchen_table", 3, 3, "S"),
              ("sink", 0, 6, "E"), ("kitchen_dresser", 1, 0, "S"), ("cauldron", 2, 6, "S"), ("pumpkin", 5, 6, "S"),
              ("barrel", 0, 7, "E"), ("chair", 3, 2, "auto"), ("chair", 4, 5, "auto"), ("chair", 2, 4, "auto"),
              ("chair", 5, 3, "auto")],
        wall=[("window", "N", 5)], enemies=["goblin"]),
    "scullery": R("Scullery", "ground", (3, 2), (7, 7), "kitchen",
        furn=[("trapdoor", 5, 1, "S", "coal_cellar"), ("sink", 0, 0, "E"), ("washtub", 1, 0, "S"), ("crate", 3, 5, "S"),
              ("crate", 4, 5, "S"), ("barrel", 6, 6, "S")],
        wall=[("cobweb", "N", 6), ("window", "N", 4)], enemies=["spider"]),
    # ---------------------------------------------------------------- basement
    "cellar_passage": R("Cellar Passage", "basement", (1, 1), (8, 6), "cellar",
        furn=[("stairs_up", 6, 0, "S", "kitchen"), ("barrel", 0, 0, "E"), ("crate", 1, 5, "S"), ("candelabra", 5, 0, "S")],
        wall=[("cobweb", "W", 5)], enemies=["bat"]),
    "wine_cellar": R("Wine Cellar", "basement", (1, 0), (8, 8), "cellar",
        furn=[("wine_rack", 0, 0, "E"), ("wine_rack", 1, 0, "S"), ("wine_rack", 5, 0, "S"), ("barrel", 0, 6, "E"),
              ("barrel", 6, 6, "S"), ("crate", 3, 5, "S"), ("barrel", 7, 0, "S")],
        enemies=["spider", "bat"]),
    "crypt": R("Crypt", "basement", (0, 0), (8, 8), "crypt",
        furn=[("coffin", 2, 1, "S"), ("coffin", 5, 1, "S"), ("tomb", 3, 5, "E"), ("candelabra", 0, 0, "E"),
              ("candelabra", 7, 0, "S"), ("statue", 0, 7, "E"), ("coffin", 0, 3, "E")],
        wall=[("cobweb", "N", 4)], enemies=["skeleton", "ghost"]),
    "coal_cellar": R("Coal Cellar", "basement", (2, 0), (7, 7), "cellar",
        furn=[("ladder_up", 5, 0, "S", "scullery"), ("coal_heap", 0, 5, "E"), ("crate", 3, 3, "S"), ("barrel", 0, 0, "E")],
        wall=[("cobweb", "N", 2)], enemies=["spider"]),
    "laundry": R("Laundry", "basement", (0, 1), (7, 7), "cellar",
        furn=[("mangle", 0, 0, "E"), ("washtub", 2, 0, "S"), ("washtub", 0, 5, "E"), ("chest", 4, 4, "S"),
              ("linen_press", 4, 0, "S")],
        enemies=["ghost"]),
    "boiler_room": R("Boiler Room", "basement", (2, 1), (8, 8), "cellar",
        furn=[("boiler", 0, 0, "E"), ("crate", 5, 5, "S"), ("coal_heap", 5, 0, "S"), ("crate", 6, 6, "S")],
        enemies=["monster"]),
    # ------------------------------------------------------------- first floor
    "landing": R("Landing", "first", (1, 1), (8, 8), "landing",
        furn=[("stairs_down", 6, 0, "S", "staircase_hall"), ("grandfather_clock", 0, 0, "E"), ("rug", 3, 4, "S"),
              ("statue", 0, 7, "E"), ("potted_palm", 7, 7, "S")],
        wall=[("painting", "N", 1), ("painting_lady", "W", 6)], enemies=["ghost"]),
    "master_bedroom": R("Master Bedroom", "first", (1, 0), (9, 8), "bedroom",
        furn=[("bed", 1, 0, "S"), ("chest_of_drawers", 5, 0, "S"), ("wardrobe", 0, 6, "E"), ("armchair", 7, 5, "auto"),
              ("candelabra", 8, 0, "S")],
        wall=[("painting_lady", "N", 4), ("window", "N", 7), ("mirror", "W", 1)], enemies=["ghost"]),
    "nursery": R("Nursery", "first", (0, 0), (8, 8), "nursery",
        furn=[("cot", 1, 0, "S"), ("rocking_horse", 4, 4, "S"), ("toy_box", 0, 5, "E"), ("chair", 6, 1, "auto"),
              ("toy_box", 3, 0, "S"), ("rug", 3, 2, "S")],
        wall=[("window", "N", 5), ("painting", "W", 1)], enemies=["ghost", "bat"]),
    "dressing_room": R("Dressing Room", "first", (2, 0), (7, 7), "bedroom",
        furn=[("wardrobe", 0, 0, "E"), ("wardrobe", 3, 0, "S"), ("dummy", 6, 0, "S"), ("trunk", 5, 5, "S"),
              ("chair", 2, 4, "auto")],
        wall=[("mirror", "W", 5), ("mirror", "N", 1)], enemies=["skeleton"]),
    "bathroom": R("Bathroom", "first", (0, 1), (7, 7), "bath",
        furn=[("bath", 0, 0, "E"), ("washstand", 3, 0, "S"), ("linen_press", 0, 5, "E"), ("chair", 4, 4, "auto")],
        wall=[("mirror", "N", 3), ("window", "N", 5)], enemies=["ghost"]),
    "portrait_gallery": R("Portrait Gallery", "first", (2, 1), (9, 5), "drawing",
        furn=[("statue", 4, 4, "S"), ("suit_of_armour", 0, 4, "E"), ("candelabra", 8, 0, "S")],
        wall=[("painting", "N", 1), ("painting_lady", "N", 3), ("painting", "N", 5), ("painting_lady", "N", 7),
              ("painting_landscape", "W", 3)], enemies=["ghost", "skeleton"]),
    "guest_bedroom": R("Guest Bedroom", "first", (3, 1), (8, 8), "blue",
        furn=[("bed", 5, 0, "S"), ("wardrobe", 0, 0, "E"), ("chest_of_drawers", 2, 0, "S"), ("armchair", 1, 6, "auto"),
              ("trunk", 7, 7, "S")],
        wall=[("painting", "W", 6), ("window", "N", 4)], enemies=["goblin"]),
    "upper_corridor": R("Upper Corridor", "first", (1, 2), (9, 4), "wood",
        furn=[("ladder_up", 7, 0, "S", "loft_landing"), ("potted_palm", 0, 0, "S"), ("chair", 1, 3, "auto")],
        wall=[("painting", "N", 1), ("cobweb", "N", 5)], enemies=["bat"]),
    "sewing_room": R("Sewing Room", "first", (0, 2), (7, 7), "nursery",
        furn=[("dummy", 0, 0, "E"), ("sewing_machine", 2, 0, "S"), ("dummy", 5, 0, "S"), ("chest_of_drawers", 0, 5, "E"),
              ("chair", 2, 1, "auto")],
        wall=[("window", "N", 3)], enemies=["ghost"]),
    "linen_room": R("Linen Room", "first", (2, 2), (7, 6), "bath",
        furn=[("stairs_up", 4, 0, "S", "servants_quarters"), ("linen_press", 0, 0, "E"), ("trunk", 6, 5, "S"),
              ("chest", 2, 4, "S")],
        enemies=["spider"]),
    # -------------------------------------------------------------------- loft
    "loft_landing": R("Loft Landing", "loft", (1, 1), (7, 7), "loft_landing",
        furn=[("trapdoor", 5, 0, "S", "upper_corridor"), ("crate", 0, 5, "S"), ("trunk", 0, 0, "E")],
        wall=[("cobweb", "W", 4)], enemies=["bat"]),
    "dusty_attic": R("Dusty Attic", "loft", (1, 0), (9, 8), "loft",
        furn=[("trunk", 0, 0, "E"), ("crate", 2, 0, "S"), ("crate", 1, 6, "S"), ("rocking_horse", 6, 2, "S"),
              ("dummy", 7, 0, "S"), ("chest", 4, 5, "S"), ("toy_box", 8, 7, "S")],
        wall=[("cobweb", "N", 5), ("window", "N", 3)], enemies=["ghost", "spider"]),
    "lumber_room": R("Lumber Room", "loft", (0, 0), (8, 7), "loft",
        furn=[("crate", 0, 0, "E"), ("crate", 1, 0, "S"), ("crate", 0, 1, "E"), ("wardrobe", 3, 0, "S"),
              ("armchair", 6, 5, "auto"), ("chair", 5, 1, "auto"), ("trunk", 0, 5, "E")],
        wall=[("painting", "W", 3)], enemies=["goblin"]),
    "water_tank_loft": R("Water Tank Loft", "loft", (2, 0), (7, 7), "loft",
        furn=[("water_tank", 4, 0, "S"), ("crate", 0, 5, "S"), ("barrel", 0, 0, "E")],
        wall=[("cobweb", "W", 5)], enemies=["bat"]),
    "servants_quarters": R("Servants' Quarters", "loft", (2, 1), (8, 7), "loft",
        furn=[("stairs_down", 6, 0, "S", "linen_room"), ("bed", 0, 4, "E"), ("chest_of_drawers", 1, 0, "S"),
              ("washstand", 5, 6, "S"), ("chair", 4, 3, "auto")],
        wall=[("window", "N", 5)], enemies=["skeleton"]),
}

# (room, side, other room); the other room's door is on the opposite side.
DOORS = [
    ("entrance_hall", "S", "staircase_hall"), ("entrance_hall", "W", "drawing_room"), ("entrance_hall", "E", "study"),
    ("drawing_room", "W", "conservatory"), ("drawing_room", "S", "west_corridor"),
    ("conservatory", "S", "music_room"), ("study", "E", "library"), ("library", "S", "billiard_room"),
    ("staircase_hall", "W", "west_corridor"), ("staircase_hall", "E", "east_corridor"), ("staircase_hall", "S", "kitchen"),
    ("west_corridor", "W", "music_room"), ("west_corridor", "S", "dining_room"),
    ("east_corridor", "E", "billiard_room"), ("east_corridor", "S", "scullery"),
    ("ballroom", "N", "music_room"), ("ballroom", "E", "dining_room"), ("dining_room", "E", "kitchen"),
    ("kitchen", "E", "scullery"),
    ("cellar_passage", "N", "wine_cellar"), ("cellar_passage", "W", "laundry"), ("cellar_passage", "E", "boiler_room"),
    ("wine_cellar", "W", "crypt"), ("wine_cellar", "E", "coal_cellar"),
    ("landing", "N", "master_bedroom"), ("landing", "W", "bathroom"), ("landing", "E", "portrait_gallery"),
    ("landing", "S", "upper_corridor"), ("master_bedroom", "W", "nursery"), ("master_bedroom", "E", "dressing_room"),
    ("portrait_gallery", "E", "guest_bedroom"), ("upper_corridor", "W", "sewing_room"), ("upper_corridor", "E", "linen_room"),
    ("loft_landing", "N", "dusty_attic"), ("loft_landing", "E", "servants_quarters"),
    ("dusty_attic", "W", "lumber_room"), ("dusty_attic", "E", "water_tank_loft"), ("water_tank_loft", "S", "servants_quarters"),
]

OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}
SIDE_DIR = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
FACING_DIR = SIDE_DIR
LINK_TYPES = ("stairs_up", "stairs_down", "ladder_up", "trapdoor")
SEAT_AT = ("dining_table", "kitchen_table", "desk", "billiard_table", "sewing_machine")
LINK_VERB = {"stairs_up": "up the stairs", "stairs_down": "down the stairs", "ladder_up": "up the ladder",
             "trapdoor": "down through the trapdoor"}


class Obj:
    """A placed object (furniture, flat thing, link or wall hanging)."""
    __slots__ = ("id", "type", "x", "y", "facing", "gx", "gy", "link", "side", "index", "mount",
                 "home", "searched", "lifted", "dx", "dy", "slide_t")

    def __init__(self, oid, typ, x, y, facing, link=None):
        self.id, self.type, self.x, self.y, self.facing, self.link = oid, typ, x, y, facing, link
        self.gx, self.gy = footprint(typ, facing)
        self.home = (x, y)
        self.side = self.index = self.mount = None
        self.searched = False
        self.lifted = False
        self.dx = self.dy = 0.0
        self.slide_t = 0.0

    @property
    def t(self):
        return T[self.type]

    def cells(self):
        return [(self.x + i, self.y + j) for i in range(self.gx) for j in range(self.gy)]

    def front_cells(self):
        """Tiles just in front of the object (where you stand to search it)."""
        fx, fy = FACING_DIR.get(self.facing, (0, 1))
        if fx:
            x = self.x + self.gx if fx > 0 else self.x - 1
            return [(x, self.y + j) for j in range(self.gy)]
        y = self.y + self.gy if fy > 0 else self.y - 1
        return [(self.x + i, y) for i in range(self.gx)]

    def exit_pos(self):
        """Where you arrive after coming through this link: in front of it."""
        fx, fy = FACING_DIR.get(self.facing, (0, 1))
        if fx:
            return (self.x + self.gx + 0.5 if fx > 0 else self.x - 0.5, self.y + self.gy / 2.0)
        return (self.x + self.gx / 2.0, self.y + self.gy + 0.5 if fy > 0 else self.y - 0.5)


class Room:
    def __init__(self, rid, spec):
        self.id = rid
        self.spec = spec
        self.name = spec["name"]
        self.floor = spec["floor"]
        self.map = tuple(spec["map"])
        self.w, self.d = spec["size"]
        self.style = STYLES[spec["style"]]
        self.style_name = spec["style"]
        self.doors = {}     # side -> dict(to=room id, at=first tile index)
        self.objs = []
        self.walls = []
        for i, f in enumerate(spec["furn"]):
            typ, x, y, facing = f[:4]
            link = f[4] if len(f) > 4 else None
            self.objs.append(Obj(f"{rid}:{i}", typ, x, y, facing, link))
        for o in self.objs:
            if o.facing == "auto":
                o.facing = self.aim_seat(o)
        for j, wdef in enumerate(spec["wall"]):
            typ, side, index = wdef[:3]
            o = Obj(f"{rid}:w{j}", typ, 0, 0, "S" if side == "N" else "E")
            o.side, o.index = side, index
            o.mount = wdef[3] if len(wdef) > 3 else WALL_MOUNT.get(typ, WALL_MOUNT_DEFAULT)
            self.walls.append(o)
        self.enemies = list(spec["enemies"])

    def aim_seat(self, o):
        """Facing for a chair or armchair marked "auto"."""
        cx, cy = o.x + 0.5, o.y + 0.5
        occ = {}
        for p in self.objs:
            if p is not o and p.facing != "auto":
                for c in p.cells():
                    occ[c] = p
        def toward(px, py):
            dx, dy = px - cx, py - cy
            if abs(dx) >= abs(dy):
                return "E" if dx > 0 else "W"
            return "S" if dy > 0 else "N"
        if o.type == "armchair":          # draw up to the fire
            for p in self.objs:
                if p.type == "fireplace":
                    fx, fy = p.exit_pos()            # just in front of the hearth
                    if abs(fx - cx) <= 3.5 and abs(fy - cy) <= 3.5:
                        return toward(p.x + p.gx / 2, p.y + p.gy / 2)
        for kinds in (SEAT_AT, ("round_table",)):   # at a table or desk: face it
            for d, (dx, dy) in (("E", (1, 0)), ("W", (-1, 0)), ("S", (0, 1)), ("N", (0, -1))):
                p = occ.get((o.x + dx, o.y + dy))
                if p is not None and p.type in kinds:
                    return d
        return toward(self.w / 2, self.d / 2)

    # --- geometry ---
    def side_len(self, side):
        return self.w if side in ("N", "S") else self.d

    def door_range(self, side):
        d = self.doors.get(side)
        if d is None:
            return None
        return range(d["at"], d["at"] + DOOR_W)

    def door_cells(self, side):
        rng = self.door_range(side)
        if rng is None:
            return []
        if side == "N":
            return [(i, 0) for i in rng]
        if side == "S":
            return [(i, self.d - 1) for i in rng]
        if side == "W":
            return [(0, i) for i in rng]
        return [(self.w - 1, i) for i in rng]

    def door_entry(self, side):
        """Arrival point just inside the doorway on `side`."""
        rng = self.door_range(side)
        mid = rng.start + DOOR_W / 2.0
        return {"N": (mid, 0.6), "S": (mid, self.d - 0.6), "W": (0.6, mid), "E": (self.w - 0.6, mid)}[side]

    def front_door(self):
        for o in self.walls:
            if o.type == "front_door":
                return o
        return None

    def keep_clear(self):
        cells = set()
        for side in self.doors:
            cells.update(self.door_cells(side))
        for o in self.objs:
            if o.type in LINK_TYPES:
                ex, ey = o.exit_pos()
                cells.add((int(ex), int(ey)))
                if o.gx == 2 and o.facing in ("S", "N"):
                    cells.add((int(ex) - 1, int(ey)))
                if o.gy == 2 and o.facing in ("E", "W"):
                    cells.add((int(ex), int(ey) - 1))
        fd = self.front_door()
        if fd is not None:
            cells.update((fd.index + i, 0) for i in range(T["front_door"]["size"][0]))
        return cells

    def solid_cells(self, include_push=True):
        out = {}
        for o in self.objs:
            t = o.t
            if t.get("solid") and (include_push or not t.get("push")):
                for c in o.cells():
                    out[c] = o
        return out

    def trigger_cells(self):
        """Floor links you walk onto (stairs down, trapdoors)."""
        out = {}
        for o in self.objs:
            if o.type in ("stairs_down", "trapdoor"):
                for c in o.cells():
                    out[c] = o
        return out

    def inside(self, c):
        return 0 <= c[0] < self.w and 0 <= c[1] < self.d

    def walkable(self, c, blocked=None):
        if not self.inside(c):
            return False
        blocked = self.solid_cells() if blocked is None else blocked
        return c not in blocked and c not in self.trigger_cells()

    def flood(self, start, blocked=None):
        """Tiles reachable on foot from `start` (pushables count as walls)."""
        blocked = self.solid_cells() if blocked is None else blocked
        trig = self.trigger_cells()
        start = (int(start[0]), int(start[1]))
        seen = {start}
        q = deque([start])
        while q:
            c = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n in seen or not self.inside(n) or n in blocked or n in trig:
                    continue
                seen.add(n)
                q.append(n)
        return seen

    def path(self, start, goal, blocked=None):
        """Shortest 4-way tile path start -> goal (list of tiles, both included) or None."""
        blocked = self.solid_cells() if blocked is None else blocked
        trig = self.trigger_cells()
        start, goal = (int(start[0]), int(start[1])), (int(goal[0]), int(goal[1]))
        prev = {start: None}
        q = deque([start])
        while q:
            c = q.popleft()
            if c == goal:
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n in prev or not self.inside(n) or n in blocked or (n in trig and n != goal):
                    continue
                prev[n] = c
                q.append(n)
        if goal not in prev:
            return None
        out = [goal]
        while prev[out[-1]] is not None:
            out.append(prev[out[-1]])
        return out[::-1]

    def free_floor(self):
        """Open floor tiles: not furniture, not links, not doorway tiles."""
        blocked = self.solid_cells()
        trig = self.trigger_cells()
        flat = {c for o in self.objs if o.t["kind"] == "flat" for c in o.cells()}
        clear = self.keep_clear()
        return [(x, y) for x in range(self.w) for y in range(self.d)
                if (x, y) not in blocked and (x, y) not in trig and (x, y) not in flat and (x, y) not in clear]

    def reset_pushables(self):
        for o in self.objs:
            if o.t.get("push"):
                o.x, o.y = o.home
                o.dx = o.dy = 0.0


class Mansion:
    def __init__(self, rooms=ROOMS, doors=DOORS):
        self.rooms = {rid: Room(rid, spec) for rid, spec in rooms.items()}
        for d in doors:
            a, side, b = d[:3]
            opts = d[3] if len(d) > 3 else {}
            ra, rb = self.rooms[a], self.rooms[b]
            os_ = OPPOSITE[side]
            ra.doors[side] = dict(to=b, at=opts.get("at", (ra.side_len(side) - DOOR_W) // 2))
            rb.doors[os_] = dict(to=a, at=opts.get("at_other", (rb.side_len(os_) - DOOR_W) // 2))

    def room_reach(self, room: Room):
        """Tiles you can walk to from any doorway or landing (cached while
        nothing has been pushed)."""
        key = (room.id, tuple((o.x, o.y) for o in room.objs if o.t.get("push")))
        cache = self.__dict__.setdefault("_reach", {})
        if key not in cache:
            reach = set()
            for p in self.entry_points(room):
                if p not in reach:
                    reach |= room.flood(p)
            cache[key] = reach
        return cache[key]

    def link_target(self, room: Room, obj: Obj):
        """(other room, its matching link object)."""
        other = self.rooms[obj.link]
        for o in other.objs:
            if o.type in LINK_TYPES and o.link == room.id:
                return other, o
        raise KeyError(f"{room.id}: {obj.type} to {obj.link} has no partner")

    # ------------------------------------------------------------ validation
    def validate(self):
        """List of problems (empty when the data is sound)."""
        errs = []
        maps = {}
        for r in self.rooms.values():
            key = (r.floor, r.map)
            if key in maps:
                errs.append(f"{r.id}: map cell {key} also used by {maps[key]}")
            maps[key] = r.id
            if r.floor not in FLOORS:
                errs.append(f"{r.id}: unknown floor {r.floor}")
            if r.w + r.d > 18:
                errs.append(f"{r.id}: {r.w}x{r.d} too big for the screen (w + d <= 18)")
            for side, d in r.doors.items():
                o = self.rooms[d["to"]]
                dx, dy = SIDE_DIR[side]
                if o.floor != r.floor or o.map != (r.map[0] + dx, r.map[1] + dy):
                    errs.append(f"{r.id}: {side} door to {o.id} but the map cells are not neighbours")
                if d["at"] < 0 or d["at"] + DOOR_W > r.side_len(side):
                    errs.append(f"{r.id}: {side} door off the wall")
            used = {}
            clear = r.keep_clear()
            for o in r.objs:
                if o.type not in T:
                    errs.append(f"{r.id}: unknown type {o.type}")
                    continue
                if o.t["kind"] not in ("furniture", "flat", "link"):
                    errs.append(f"{r.id}: {o.type} is not a floor object")
                for c in o.cells():
                    if not r.inside(c):
                        errs.append(f"{r.id}: {o.type} at {c} is outside the room")
                    if c in used:
                        errs.append(f"{r.id}: {o.type} overlaps {used[c].type} at {c}")
                    used[c] = o
                    if c in clear and o.type not in LINK_TYPES:
                        errs.append(f"{r.id}: {o.type} at {c} blocks a doorway or stair landing")
                if o.type in LINK_TYPES:
                    try:
                        self.link_target(r, o)
                    except KeyError as e:
                        errs.append(str(e))
                    ex, ey = o.exit_pos()
                    if not r.inside((int(ex), int(ey))):
                        errs.append(f"{r.id}: {o.type} lands you outside the room")
            spans = {"N": [], "W": []}
            for side in ("N", "W"):
                rng = r.door_range(side)
                if rng is not None:
                    spans[side].append((rng.start, rng.stop, "doorway"))
            for o in r.walls:
                if o.side not in ("N", "W"):
                    errs.append(f"{r.id}: {o.type} must hang on the N or W wall")
                    continue
                n = T[o.type]["size"][0]
                if o.index < 0 or o.index + n > r.side_len(o.side):
                    errs.append(f"{r.id}: {o.type} off the {o.side} wall")
                for a, b, what in spans[o.side]:
                    if o.index < b and o.index + n > a:
                        errs.append(f"{r.id}: {o.type} on {o.side} wall overlaps {what}")
                spans[o.side].append((o.index, o.index + n, o.type))
            # all doorways and links of a room joined up on foot
            points = [r.door_cells(s)[0] for s in r.doors]
            points += [(int(o.exit_pos()[0]), int(o.exit_pos()[1])) for o in r.objs if o.type in LINK_TYPES]
            if r.front_door():
                points.append((r.front_door().index, 0))
            if points:
                reach = r.flood(points[0])
                for p in points[1:]:
                    if p not in reach:
                        errs.append(f"{r.id}: {p} cannot be reached from {points[0]} on foot")
        return errs

    def room_graph(self):
        g = {rid: set() for rid in self.rooms}
        for r in self.rooms.values():
            for d in r.doors.values():
                g[r.id].add(d["to"])
            for o in r.objs:
                if o.type in LINK_TYPES:
                    g[r.id].add(o.link)
        return g

    def reachable_rooms(self, start=START_ROOM):
        g = self.room_graph()
        seen = {start}
        q = deque([start])
        while q:
            for n in g[q.popleft()]:
                if n not in seen:
                    seen.add(n)
                    q.append(n)
        return seen

    def route(self, a, b):
        """Room ids from a to b (breadth-first over doors and stairs)."""
        g = self.room_graph()
        prev = {a: None}
        q = deque([a])
        while q:
            c = q.popleft()
            if c == b:
                break
            for n in sorted(g[c]):
                if n not in prev:
                    prev[n] = c
                    q.append(n)
        out = [b]
        while prev[out[-1]] is not None:
            out.append(prev[out[-1]])
        return out[::-1]

    def entry_points(self, room: Room):
        """Every tile you can arrive on in this room."""
        pts = [room.door_entry(s) for s in room.doors]
        pts += [o.exit_pos() for o in room.objs if o.type in LINK_TYPES]
        return [(int(x), int(y)) for x, y in pts]

    # ------------------------------------------------------------ the key
    def hiding_places(self):
        """Every possible key location: (room id, how, object id or tile)."""
        out = []
        for r in self.rooms.values():
            if r.id == START_ROOM:
                continue
            for o in r.objs + r.walls:
                t = o.t
                if t.get("search"):
                    out.append((r.id, "search", o.id))
                elif t.get("push"):
                    out.append((r.id, "under", o.id))
                elif t.get("lift"):
                    out.append((r.id, "rug", o.id))
            for c in r.free_floor():
                out.append((r.id, "open", c))
        return out

    def in_view(self, room: Room, cell, margin=10):
        """A key on this floor tile isn't hidden behind furniture from the
        camera: no object drawn in front of it overlaps the key on screen
        (with a few pixels to spare). Pushable things count where they start
        (rooms tidy themselves when you come in)."""
        hw, hh = TILE_W / 2, TILE_H / 2
        cx, cy = cell
        kx, ky = cx + 0.5, cy + 0.5
        sx, sy = (kx - ky) * hw, (kx + ky) * hh
        key = (sx - 16 - margin, sy - 44 - margin, sx + 16 + margin, sy + 4)
        for o in room.objs:
            h = o.t.get("h", 0)
            if o.t["kind"] == "flat" or h <= 0:
                continue
            x0, y0, x1, y1 = o.x, o.y, o.x + o.gx, o.y + o.gy
            if x1 <= cx or y1 <= cy:              # wholly behind the key's tile: drawn first
                continue
            if not (x0 >= cx + 1 or y0 >= cy + 1):
                continue                          # (the tile itself: solid, never chosen)
            box = ((x0 - y1) * hw, (x0 + y0) * hh - h, (x1 - y0) * hw, (x1 + y1) * hh)
            if box[0] < key[2] and key[0] < box[2] and box[1] < key[3] and key[1] < box[3]:
                return False
        return True

    def open_places(self):
        """Every floor tile the key may lie on when it isn't hidden: open
        floor (not a rug, doorway, stair end or a seat at a table) that you
        can reach from a way in, and that no furniture hides from view."""
        if "_open" not in self.__dict__:
            self._open = [p for p in self.hiding_places() if p[1] == "open" and self.obtainable(p)
                          and self.in_view(self.rooms[p[0]], p[2])]
        return self._open

    def place_key(self, rng: random.Random, hidden=None):
        """Where the key goes this game. Not hidden (KEY_HIDDEN False, for
        now): a random room, then a random visible, reachable floor tile in
        it. Hidden: a random, always-obtainable spot, about half inside or
        behind things, a fifth under something you can move, some under rugs
        and the rest out in the open."""
        if hidden is None:
            hidden = KEY_HIDDEN
        if not hidden:
            by_room = {}
            for p in self.open_places():
                by_room.setdefault(p[0], []).append(p)
            rid = rng.choice(sorted(by_room))
            return rng.choice(by_room[rid])
        if "_places" not in self.__dict__:
            self._places = [p for p in self.hiding_places() if self.obtainable(p)]
        places = self._places
        by = {"search": [], "under": [], "rug": [], "open": []}
        for p in places:
            by[p[1]].append(p)
        roll = rng.random()
        kind = "search" if roll < 0.5 else ("under" if roll < 0.7 else ("rug" if roll < 0.82 else "open"))
        pool = by[kind] or places
        return rng.choice(pool)

    def find_obj(self, room: Room, oid):
        for o in room.objs + room.walls:
            if o.id == oid:
                return o
        return None

    def push_plan(self, room: Room, o: Obj):
        """A push that moves `o` off its tile: (stand tile, direction) or None.
        You must be able to reach the tile behind it, and the tile it moves to
        must be empty floor that is not a doorway."""
        reach = self.room_reach(room)
        blocked = room.solid_cells()
        trig = room.trigger_cells()
        clear = room.keep_clear()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            stand = (o.x - dx, o.y - dy)
            dest = (o.x + dx, o.y + dy)
            if stand in reach and room.inside(dest) and dest not in blocked and dest not in trig and dest not in clear:
                return stand, (dx, dy)
        return None

    def obtainable(self, place):
        rid, how, what = place
        room = self.rooms[rid]
        reach = self.room_reach(room)
        if how == "open":
            return tuple(what) in reach
        o = self.find_obj(room, what)
        if how == "under":
            return self.push_plan(room, o) is not None
        if how == "rug":
            return any(c in reach for c in o.cells())
        if o.side == "N":
            return any((o.index + i, 0) in reach for i in range(o.gx))
        if o.side == "W":
            return any((0, o.index + i) in reach for i in range(o.gy))
        return any(c in reach for c in o.front_cells()) or any(
            (c[0] + dx, c[1] + dy) in reach for c in o.cells() for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
