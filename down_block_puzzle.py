# SPDX-License-Identifier: MIT
# Down Block Puzzle - single-file Blender 5.x add-on

bl_info = {
    "name": "Down Block Puzzle",
    "author": "OpenAI",
    "version": (1, 1, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Down Block Puzzle",
    "description": "A falling block puzzle game inside Blender.",
    "category": "3D View",
}
import os
import random
import time
from dataclasses import dataclass, field

import bpy
import blf
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Vector


BOARD_WIDTH = 10
BOARD_HEIGHT = 20
CELL_SIZE = 1.0
BOARD_VIEW_PADDING = 1.2
BOARD_VIEW_EXTRA_PADDING = 1.1
TEMP_COLLECTION_NAME = "DBP_Temporary_Collection"
TEMP_PREFIX = "DBP_"
GHOST_PREFIX = "DBP_Ghost_"
GHOST_MESH_NAME = "DBP_Ghost_Cube_Mesh"
GHOST_MATERIAL_NAME = "DBP_Ghost_Material"
GHOST_ALPHA = 0.25
GHOST_SCALE = 0.92
GHOST_COLOR = (1.0, 1.0, 1.0, GHOST_ALPHA)
TIMER_INTERVAL = 0.03
BASE_FALL_INTERVAL = 0.8
LEVEL_SPEED_MULTIPLIER = 0.88
LEVEL_SCORE_BONUS = 0.2
LINES_PER_LEVEL = 10
MIN_FALL_INTERVAL = 0.08
DROP_INPUT_LOCK_SECONDS = 0.5
SPAWN_X = BOARD_WIDTH // 2 - 2
LINE_CLEAR_BASE_SCORES = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
LINE_CLEAR_FLASH_DURATION = 0.18
LINE_CLEAR_FLASH_COLOR = (1.0, 1.0, 1.0, 1.0)
RANDOM_MINO_GRID_SIZE = 4
RANDOM_MINO_MIN_CELL_COUNT = 5
RANDOM_MINO_MAX_CELL_COUNT = 8
RANDOM_MINO_LEVEL_RULES = (
    (5, 5, 0.10),
    (10, 6, 0.05),
    (15, 7, 0.03),
    (20, 8, 0.01),
)
RANDOM_MINO_COLORS = {
    5: (1.0, 0.55, 0.15, 1.0),
    6: (1.0, 0.35, 0.15, 1.0),
    7: (1.0, 0.15, 0.15, 1.0),
    8: (0.75, 0.10, 1.0, 1.0),
}

PIECE_KINDS = ("I", "O", "T", "S", "Z", "J", "L")
PIECE_COLORS = {
    "I": (0.0, 0.9, 1.0, 1.0),
    "O": (1.0, 0.85, 0.05, 1.0),
    "T": (0.68, 0.20, 0.95, 1.0),
    "S": (0.10, 0.85, 0.20, 1.0),
    "Z": (0.95, 0.12, 0.12, 1.0),
    "J": (0.12, 0.22, 0.95, 1.0),
    "L": (1.0, 0.52, 0.05, 1.0),
}

DBP_KEY_ITEMS = [
    ("NONE", "None", "No key assigned"),
    ("A", "A", ""), ("B", "B", ""), ("C", "C", ""), ("D", "D", ""),
    ("E", "E", ""), ("F", "F", ""), ("G", "G", ""), ("H", "H", ""),
    ("I", "I", ""), ("J", "J", ""), ("K", "K", ""), ("L", "L", ""),
    ("M", "M", ""), ("N", "N", ""), ("O", "O", ""), ("P", "P", ""),
    ("Q", "Q", ""), ("R", "R", ""), ("S", "S", ""), ("T", "T", ""),
    ("U", "U", ""), ("V", "V", ""), ("W", "W", ""), ("X", "X", ""),
    ("Y", "Y", ""), ("Z", "Z", ""),
    ("ZERO", "0", ""), ("ONE", "1", ""), ("TWO", "2", ""),
    ("THREE", "3", ""), ("FOUR", "4", ""), ("FIVE", "5", ""),
    ("SIX", "6", ""), ("SEVEN", "7", ""), ("EIGHT", "8", ""), ("NINE", "9", ""),
    ("NUMPAD_0", "Numpad 0", ""), ("NUMPAD_1", "Numpad 1", ""),
    ("NUMPAD_2", "Numpad 2", ""), ("NUMPAD_3", "Numpad 3", ""),
    ("NUMPAD_4", "Numpad 4", ""), ("NUMPAD_5", "Numpad 5", ""),
    ("NUMPAD_6", "Numpad 6", ""), ("NUMPAD_7", "Numpad 7", ""),
    ("NUMPAD_8", "Numpad 8", ""), ("NUMPAD_9", "Numpad 9", ""),
    ("RET", "Enter", ""), ("NUMPAD_ENTER", "Numpad Enter", ""),
    ("SPACE", "Space", ""), ("ESC", "Esc", ""),
]

DBP_START_LEVEL_ITEMS = [
    ("1", "Level 1", ""),
    ("5", "Level 5", ""),
    ("10", "Level 10", ""),
    ("15", "Level 15", ""),
]

DBP_CONTROL_ACTIONS = (
    ("move_left", "Move Left"),
    ("move_right", "Move Right"),
    ("rotate_left", "Rotate Left"),
    ("rotate_right", "Rotate Right"),
    ("soft_drop", "Soft Drop"),
    ("hard_drop", "Hard Drop"),
    ("quit", "Quit"),
)
DEFAULT_CONTROL_KEYS = {
    "move_left": ("A", "NUMPAD_4"),
    "move_right": ("D", "NUMPAD_6"),
    "rotate_left": ("Q", "NUMPAD_7"),
    "rotate_right": ("R", "NUMPAD_9"),
    "soft_drop": ("S", "NUMPAD_2"),
    "hard_drop": ("RET", "NUMPAD_ENTER"),
    "quit": ("ESC", "NONE"),
}

# Stable 4x4 block piece definitions. The piece origin is the lower-left of its
# 4x4 local box; y grows upward, matching the board's Z axis.
PIECE_SHAPES = {
    "I": (
        ((0, 2), (1, 2), (2, 2), (3, 2)),
        ((2, 3), (2, 2), (2, 1), (2, 0)),
        ((0, 1), (1, 1), (2, 1), (3, 1)),
        ((1, 3), (1, 2), (1, 1), (1, 0)),
    ),
    "O": (
        ((1, 1), (2, 1), (1, 2), (2, 2)),
        ((1, 1), (2, 1), (1, 2), (2, 2)),
        ((1, 1), (2, 1), (1, 2), (2, 2)),
        ((1, 1), (2, 1), (1, 2), (2, 2)),
    ),
    "T": (
        ((1, 2), (0, 1), (1, 1), (2, 1)),
        ((1, 2), (1, 1), (2, 1), (1, 0)),
        ((0, 1), (1, 1), (2, 1), (1, 0)),
        ((1, 2), (0, 1), (1, 1), (1, 0)),
    ),
    "S": (
        ((1, 2), (2, 2), (0, 1), (1, 1)),
        ((1, 2), (1, 1), (2, 1), (2, 0)),
        ((1, 1), (2, 1), (0, 0), (1, 0)),
        ((0, 2), (0, 1), (1, 1), (1, 0)),
    ),
    "Z": (
        ((0, 2), (1, 2), (1, 1), (2, 1)),
        ((2, 2), (1, 1), (2, 1), (1, 0)),
        ((0, 1), (1, 1), (1, 0), (2, 0)),
        ((1, 2), (0, 1), (1, 1), (0, 0)),
    ),
    "J": (
        ((0, 2), (0, 1), (1, 1), (2, 1)),
        ((1, 2), (2, 2), (1, 1), (1, 0)),
        ((0, 1), (1, 1), (2, 1), (2, 0)),
        ((1, 2), (1, 1), (0, 0), (1, 0)),
    ),
    "L": (
        ((2, 2), (0, 1), (1, 1), (2, 1)),
        ((1, 2), (1, 1), (1, 0), (2, 0)),
        ((0, 1), (1, 1), (2, 1), (0, 0)),
        ((0, 2), (1, 2), (1, 1), (1, 0)),
    ),
}


@dataclass
class NextPieceData:
    kind: str
    custom_cells: list | None = None
    color: tuple | None = None
    cell_count: int = 4


@dataclass
class PieceState:
    kind: str
    x: int
    y: int
    rotation: int = 0
    custom_cells: list | None = None
    color: tuple | None = None
    cell_count: int = 4


@dataclass
class DBPGameState:
    board: list = field(default_factory=lambda: [[None for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)])
    current_piece: PieceState | None = None
    next_piece: NextPieceData | None = None
    bag: list = field(default_factory=list)
    score: int = 0
    start_level: int = 1
    level: int = 1
    total_lines_cleared: int = 0
    fall_interval: float = BASE_FALL_INTERVAL
    piece_spawn_time: float = 0.0
    start_time: float = 0.0
    last_fall_time: float = 0.0
    line_clear_pending: bool = False
    line_clear_rows: list = field(default_factory=list)
    line_clear_started_at: float = 0.0
    line_clear_piece_locked: bool = False
    game_over: bool = False


@dataclass
class DBPRuntimeState:
    timer: object | None = None
    draw_handle: object | None = None
    viewport_states: list = field(default_factory=list)
    viewport_view_states: list = field(default_factory=list)
    temp_collection: object | None = None
    shared_cube_mesh: object | None = None
    ghost_mesh: object | None = None
    ghost_material: object | None = None
    active_objects: list = field(default_factory=list)
    ghost_objects: list = field(default_factory=list)
    fixed_objects: dict = field(default_factory=dict)
    game: DBPGameState | None = None
    origin: Vector = field(default_factory=lambda: Vector((0.0, 0.0, 0.0)))
    active_object_name: str | None = None
    scene_visibility_states: list = field(default_factory=list)
    bgm_device: object | None = None
    bgm_sound: object | None = None
    bgm_handle: object | None = None
    bgm_filepath: str | None = None
    bgm_loop: bool = False
    bgm_volume: float = 0.35
    bgm_started: bool = False
    bgm_stopping: bool = False
    bgm_play_started_at: float = 0.0
    bgm_duration: float | None = None
    cleaned: bool = False


@dataclass
class BGMStartResult:
    ok: bool
    message: str
    filepath: str | None = None


@dataclass
class BGMTestRuntime:
    bgm_device: object | None = None
    bgm_sound: object | None = None
    bgm_handle: object | None = None
    bgm_filepath: str | None = None
    bgm_loop: bool = False
    bgm_volume: float = 0.35
    bgm_started: bool = False
    bgm_stopping: bool = False
    bgm_play_started_at: float = 0.0
    bgm_duration: float | None = None


_DBP_RUNTIME: DBPRuntimeState | None = None
_BGM_TEST_RUNTIME: BGMTestRuntime | None = None
_BGM_TEST_TOKEN = 0


def get_runtime():
    return _DBP_RUNTIME


def is_dbp_running():
    rt = get_runtime()
    return rt is not None and not rt.cleaned


def get_dbp_preferences(context):
    addons = getattr(getattr(context, "preferences", None), "addons", None)
    if addons is None:
        return None

    addon = addons.get(__name__)
    if addon is not None:
        return addon.preferences

    module_name = __name__.split(".")[0]
    addon = addons.get(module_name)
    if addon is not None:
        return addon.preferences

    for key, addon in addons.items():
        if key == "down_block_puzzle" or key.endswith("down_block_puzzle"):
            return addon.preferences

    return None


def _bgm_fail(message, filepath=None, log_prefix="[Down Block Puzzle][BGM]"):
    print(f"{log_prefix} {message}")
    return BGMStartResult(False, message, filepath)


def play_bgm_once(rt, log_prefix="[Down Block Puzzle][BGM]"):
    filepath = getattr(rt, "bgm_filepath", None)
    if not filepath:
        return _bgm_fail("BGM filepath is empty.", log_prefix=log_prefix)

    try:
        import aud
        print(f"{log_prefix} aud import ok")
    except Exception as exc:
        return _bgm_fail(f"Failed to import Blender aud module: {exc}", filepath, log_prefix)

    try:
        sound = aud.Sound(filepath)
        print(f"{log_prefix} aud.Sound() created")
    except Exception as exc:
        return _bgm_fail(f"aud.Sound() failed. Try WAV/OGG if this is MP3. Error: {exc}", filepath, log_prefix)

    try:
        device = aud.Device()
        print(f"{log_prefix} device created")
    except Exception as exc:
        return _bgm_fail(f"aud.Device() failed. Check Blender audio device/preferences. Error: {exc}", filepath, log_prefix)

    try:
        handle = device.play(sound)
        print(f"{log_prefix} playback started")
    except Exception as exc:
        return _bgm_fail(f"device.play() failed: {exc}", filepath, log_prefix)

    volume = float(getattr(rt, "bgm_volume", 0.35))
    print(f"{log_prefix} volume: {volume}")
    try:
        handle.volume = volume
        print(f"{log_prefix} volume applied")
    except Exception as exc:
        print(f"{log_prefix} Failed to set volume: {exc}")

    duration = None
    try:
        length_attr = getattr(sound, "length", None)
        length_value = length_attr() if callable(length_attr) else length_attr
        duration = float(length_value)
        if duration <= 0:
            duration = None
        else:
            print(f"{log_prefix} sound duration: {duration}")
    except Exception as exc:
        print(f"{log_prefix} sound length unavailable: {exc}")

    try:
        print(f"{log_prefix} handle status: {handle.status}")
    except Exception as exc:
        print(f"{log_prefix} handle status unavailable: {exc}")

    rt.bgm_device = device
    rt.bgm_sound = sound
    rt.bgm_handle = handle
    rt.bgm_started = True
    rt.bgm_stopping = False
    rt.bgm_play_started_at = time.monotonic()
    rt.bgm_duration = duration
    print(f"{log_prefix} playback retained: {filepath}")
    return BGMStartResult(True, f"BGM started: {filepath}", filepath)


def start_bgm(rt, context, *, for_test=False, log_prefix="[Down Block Puzzle][BGM]"):
    print(f"{log_prefix} resolving preferences")
    prefs = get_dbp_preferences(context)
    if prefs is None:
        return _bgm_fail("BGM preferences not found. Re-enable the add-on or reinstall it.", log_prefix=log_prefix)
    print(f"{log_prefix} prefs found")

    enabled = bool(getattr(prefs, "bgm_enabled", True))
    print(f"{log_prefix} enabled: {enabled}")
    if not enabled:
        return _bgm_fail("BGM is disabled in Addon Preferences.", log_prefix=log_prefix)

    raw_filepath = getattr(prefs, "bgm_filepath", "")
    print(f"{log_prefix} raw filepath: {raw_filepath}")
    if not raw_filepath:
        return _bgm_fail("BGM file is not set.", log_prefix=log_prefix)

    filepath = bpy.path.abspath(raw_filepath)
    print(f"{log_prefix} absolute filepath: {filepath}")
    if not filepath:
        return _bgm_fail(f"BGM filepath could not be resolved: {raw_filepath}", log_prefix=log_prefix)

    exists = os.path.isfile(filepath)
    print(f"{log_prefix} file exists: {exists}")
    if not exists:
        return _bgm_fail(f"BGM file does not exist: {filepath}", filepath, log_prefix)

    rt.bgm_filepath = filepath
    rt.bgm_volume = float(getattr(prefs, "bgm_volume", 0.35))
    rt.bgm_loop = bool(getattr(prefs, "bgm_loop", True)) and not for_test
    rt.bgm_stopping = False
    rt.bgm_started = False
    rt.bgm_play_started_at = 0.0
    rt.bgm_duration = None
    if rt.bgm_loop:
        print(f"{log_prefix} timer-based loop enabled")
    else:
        print(f"{log_prefix} loop {'disabled for test' if for_test else 'disabled'}")
    return play_bgm_once(rt, log_prefix)


def stop_bgm(rt):
    if rt is None:
        return
    rt.bgm_stopping = True
    handle = getattr(rt, "bgm_handle", None)
    if handle is not None:
        try:
            handle.stop()
            print("[Down Block Puzzle][BGM] stopped")
        except Exception as exc:
            print(f"[Down Block Puzzle][BGM] stop failed: {exc}")
    rt.bgm_handle = None
    rt.bgm_sound = None
    rt.bgm_device = None
    rt.bgm_filepath = None
    rt.bgm_started = False
    rt.bgm_loop = False
    rt.bgm_duration = None
    rt.bgm_play_started_at = 0.0


def update_bgm_loop(rt):
    if rt is None or getattr(rt, "bgm_stopping", False):
        return
    if not getattr(rt, "bgm_loop", False) or not getattr(rt, "bgm_filepath", None):
        return

    handle = getattr(rt, "bgm_handle", None)
    should_restart = False

    duration = getattr(rt, "bgm_duration", None)
    if duration is not None:
        try:
            elapsed = time.monotonic() - float(getattr(rt, "bgm_play_started_at", 0.0))
            if elapsed >= max(0.1, float(duration) - 0.05):
                should_restart = True
        except Exception:
            pass

    if not should_restart and handle is None:
        should_restart = True

    if not should_restart and handle is not None:
        try:
            status = getattr(handle, "status", None)
            if callable(status):
                status = status()
        except Exception:
            status = None
        if status is not None:
            status_text = str(status).lower()
            if "stop" in status_text or "invalid" in status_text or "end" in status_text or status_text in {"0", "false"}:
                should_restart = True

    if not should_restart:
        return

    if handle is not None:
        try:
            handle.stop()
        except Exception:
            pass
    rt.bgm_handle = None
    rt.bgm_sound = None
    rt.bgm_device = None
    print("[Down Block Puzzle][BGM] loop restarting from beginning")
    result = play_bgm_once(rt, "[Down Block Puzzle][BGM]")
    if not result.ok:
        print(f"[Down Block Puzzle][BGM] loop restart failed: {result.message}")
        rt.bgm_loop = False


def stop_test_bgm():
    global _BGM_TEST_RUNTIME
    rt = _BGM_TEST_RUNTIME
    if rt is not None:
        handle = getattr(rt, "bgm_handle", None)
        rt.bgm_stopping = True
        if handle is not None:
            try:
                handle.stop()
                print("[Down Block Puzzle][BGM Test] stopped")
            except Exception as exc:
                print(f"[Down Block Puzzle][BGM Test] stop failed: {exc}")
    _BGM_TEST_RUNTIME = None


def start_test_bgm(context):
    global _BGM_TEST_RUNTIME, _BGM_TEST_TOKEN
    stop_test_bgm()
    _BGM_TEST_TOKEN += 1
    token = _BGM_TEST_TOKEN
    rt = BGMTestRuntime()
    result = start_bgm(rt, context, for_test=True, log_prefix="[Down Block Puzzle][BGM Test]")
    print(f"[Down Block Puzzle][BGM Test] Test result: {result.message}")
    if not result.ok:
        _BGM_TEST_RUNTIME = None
        return result

    _BGM_TEST_RUNTIME = rt

    def auto_stop():
        if token == _BGM_TEST_TOKEN:
            stop_test_bgm()
        return None

    try:
        bpy.app.timers.register(auto_stop, first_interval=5.0)
    except Exception as exc:
        print(f"[Down Block Puzzle][BGM Test] auto-stop timer failed: {exc}")
    return result


def make_bag():
    bag = list(PIECE_KINDS)
    random.shuffle(bag)
    return bag


def choose_random_mino_cell_count_for_level(level):
    roll = random.random()
    cumulative = 0.0
    for required_level, cell_count, chance in RANDOM_MINO_LEVEL_RULES:
        if level < required_level:
            continue
        cumulative += chance
        if roll < cumulative:
            return cell_count
    return None


def normalize_mino_cells(cells):
    min_x = min(x for x, _y in cells)
    min_y = min(y for _x, y in cells)
    return sorted((x - min_x, y - min_y) for x, y in cells)


def is_orthogonally_connected(cells):
    if not cells:
        return False
    cell_set = set(cells)
    visited = set()
    stack = [cells[0]]
    while stack:
        x, y = stack.pop()
        if (x, y) in visited:
            continue
        visited.add((x, y))
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in cell_set and (nx, ny) not in visited:
                stack.append((nx, ny))
    return len(visited) == len(cell_set)


def is_valid_random_mino_cells(cells, grid_size=RANDOM_MINO_GRID_SIZE):
    if not cells or len(set(cells)) != len(cells):
        return False
    if len(cells) < RANDOM_MINO_MIN_CELL_COUNT or len(cells) > RANDOM_MINO_MAX_CELL_COUNT:
        return False
    for x, y in cells:
        if x < 0 or y < 0 or x >= grid_size or y >= grid_size:
            return False
    return is_orthogonally_connected(cells)


def get_random_mino_fallback_cells(cell_count):
    fallback_shapes = {
        5: [(0, 0), (1, 0), (2, 0), (1, 1), (1, 2)],
        6: [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)],
        7: [(0, 0), (1, 0), (2, 0), (3, 0), (1, 1), (1, 2), (2, 2)],
        8: [(0, 0), (1, 0), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1), (3, 1)],
    }
    return normalize_mino_cells(fallback_shapes.get(cell_count, fallback_shapes[5]))


def generate_random_mino_cells(cell_count, grid_size=RANDOM_MINO_GRID_SIZE):
    cell_count = max(RANDOM_MINO_MIN_CELL_COUNT, min(int(cell_count), RANDOM_MINO_MAX_CELL_COUNT))

    for _attempt in range(500):
        cells = {(random.randrange(grid_size), random.randrange(grid_size))}
        while len(cells) < cell_count:
            bx, by = random.choice(tuple(cells))
            candidates = [
                (bx + 1, by),
                (bx - 1, by),
                (bx, by + 1),
                (bx, by - 1),
            ]
            candidates = [
                candidate
                for candidate in candidates
                if 0 <= candidate[0] < grid_size and 0 <= candidate[1] < grid_size and candidate not in cells
            ]
            if not candidates:
                break
            cells.add(random.choice(candidates))
        result = normalize_mino_cells(list(cells))
        if len(result) == cell_count and is_valid_random_mino_cells(result, grid_size):
            return result

    return get_random_mino_fallback_cells(cell_count)


def rotate_custom_cells(cells, rotation):
    result = list(cells)
    for _ in range(rotation % 4):
        result = [(y, RANDOM_MINO_GRID_SIZE - 1 - x) for x, y in result]
        result = normalize_mino_cells(result)
    return result


def get_random_mino_color(cell_count):
    return RANDOM_MINO_COLORS.get(cell_count, RANDOM_MINO_COLORS[RANDOM_MINO_MIN_CELL_COUNT])


def make_random_next_piece_data(cell_count):
    cell_count = max(RANDOM_MINO_MIN_CELL_COUNT, min(int(cell_count), RANDOM_MINO_MAX_CELL_COUNT))
    cells = generate_random_mino_cells(cell_count=cell_count)
    return NextPieceData(
        kind="RANDOM",
        custom_cells=cells,
        color=get_random_mino_color(cell_count),
        cell_count=cell_count,
    )


def make_next_piece_data(rt):
    cell_count = choose_random_mino_cell_count_for_level(rt.game.level)
    if cell_count is not None:
        return make_random_next_piece_data(cell_count)
    return NextPieceData(kind=draw_from_bag(rt), cell_count=4)


def draw_text(text, x, y, size=16, color=(1.0, 1.0, 1.0, 1.0), align="LEFT"):
    font_id = 0
    blf.size(font_id, size)
    width, height = blf.dimensions(font_id, text)
    if align == "CENTER":
        x -= width * 0.5
    elif align == "RIGHT":
        x -= width
    blf.color(font_id, *color)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)
    return width, height


def calculate_level(start_level, total_lines_cleared):
    return max(1, int(start_level) + total_lines_cleared // LINES_PER_LEVEL)


def calculate_fall_interval(level):
    return max(MIN_FALL_INTERVAL, BASE_FALL_INTERVAL * (LEVEL_SPEED_MULTIPLIER ** (max(1, level) - 1)))


def calculate_score_multiplier(level):
    return 1.0 + (max(1, level) - 1) * LEVEL_SCORE_BONUS


def draw_rect(shader, x, y, w, h, color):
    vertices = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    batch = batch_for_shader(shader, "TRI_FAN", {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_line(shader, x1, y1, x2, y2, color):
    batch = batch_for_shader(shader, "LINES", {"pos": ((x1, y1), (x2, y2))})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def safe_remove_collection_by_name(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        return
    for obj in list(coll.objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass
    for child in list(coll.children):
        safe_remove_collection_by_name(child.name)
    try:
        bpy.data.collections.remove(coll)
    except ReferenceError:
        pass


def purge_dbp_orphans():
    for datablocks in (bpy.data.objects, bpy.data.meshes, bpy.data.materials):
        for datablock in list(datablocks):
            if datablock.name.startswith(TEMP_PREFIX) and getattr(datablock, "users", 0) == 0:
                try:
                    datablocks.remove(datablock)
                except ReferenceError:
                    pass


def create_temp_collection(rt, context):
    rt.temp_collection = bpy.data.collections.new(TEMP_COLLECTION_NAME)
    context.scene.collection.children.link(rt.temp_collection)


def create_cube_mesh(name, scale=1.0):
    half = CELL_SIZE * 0.46 * scale
    verts = [
        (-half, -half, -half), (half, -half, -half), (half, half, -half), (-half, half, -half),
        (-half, -half, half), (half, -half, half), (half, half, half), (-half, half, half),
    ]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def create_shared_mesh(rt):
    rt.shared_cube_mesh = create_cube_mesh(f"{TEMP_PREFIX}Shared_Cube_Mesh")


def get_or_create_ghost_material(rt):
    if rt.ghost_material is not None:
        return rt.ghost_material
    mat = bpy.data.materials.new(GHOST_MATERIAL_NAME)
    mat.diffuse_color = GHOST_COLOR
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = GHOST_ALPHA
    except Exception:
        pass
    try:
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True
    except Exception:
        pass
    rt.ghost_material = mat
    return mat


def get_or_create_ghost_mesh(rt):
    if rt.ghost_mesh is not None:
        return rt.ghost_mesh
    rt.ghost_mesh = create_cube_mesh(GHOST_MESH_NAME, GHOST_SCALE)
    mat = get_or_create_ghost_material(rt)
    try:
        rt.ghost_mesh.materials.append(mat)
    except Exception:
        pass
    return rt.ghost_mesh


def save_viewports(rt, context):
    rt.viewport_states.clear()
    windows = getattr(context.window_manager, "windows", [])
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in getattr(screen, "areas", []):
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D":
                    continue
                shading = space.shading
                rt.viewport_states.append({
                    "space": space,
                    "type": getattr(shading, "type", None),
                    "color_type": getattr(shading, "color_type", None),
                    "wireframe_color_type": getattr(shading, "wireframe_color_type", None) if hasattr(shading, "wireframe_color_type") else None,
                })


def set_game_viewports(rt, context):
    for state in rt.viewport_states:
        space = state.get("space")
        try:
            space.shading.type = "SOLID"
            space.shading.color_type = "OBJECT"
            if hasattr(space.shading, "wireframe_color_type"):
                space.shading.wireframe_color_type = "OBJECT"
        except Exception:
            pass
    tag_redraw_all(context)


def restore_viewports(rt):
    for state in rt.viewport_states:
        space = state.get("space")
        try:
            shading = space.shading
            if state.get("type") is not None:
                shading.type = state["type"]
            if state.get("color_type") is not None:
                shading.color_type = state["color_type"]
            if state.get("wireframe_color_type") is not None and hasattr(shading, "wireframe_color_type"):
                shading.wireframe_color_type = state["wireframe_color_type"]
        except Exception:
            pass
    rt.viewport_states.clear()


def iter_view3d_spaces(context):
    windows = getattr(context.window_manager, "windows", [])
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in getattr(screen, "areas", []):
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    yield area, space


def save_view_states(rt, context):
    rt.viewport_view_states.clear()
    for _area, space in iter_view3d_spaces(context):
        rv3d = getattr(space, "region_3d", None)
        if rv3d is None:
            continue
        try:
            rt.viewport_view_states.append({
                "space": space,
                "region_3d": rv3d,
                "view_location": rv3d.view_location.copy(),
                "view_distance": rv3d.view_distance,
                "view_rotation": rv3d.view_rotation.copy(),
                "view_perspective": rv3d.view_perspective,
            })
        except Exception:
            pass


def focus_viewports_on_board(rt, context):
    board_height_world = BOARD_HEIGHT * CELL_SIZE
    board_width_world = BOARD_WIDTH * CELL_SIZE
    base_view_distance = max(board_height_world, board_width_world) * 1.05
    view_distance = base_view_distance * BOARD_VIEW_PADDING * BOARD_VIEW_EXTRA_PADDING
    # Front-like view for an X-Z board: look along the Y axis so X is horizontal
    # and Z is vertical. This modifies only RegionView3D, never scene cameras.
    board_view_rotation = Euler((1.57079632679, 0.0, 0.0), "XYZ").to_quaternion()
    for area, space in iter_view3d_spaces(context):
        rv3d = getattr(space, "region_3d", None)
        if rv3d is None:
            continue
        try:
            rv3d.view_perspective = "ORTHO"
            rv3d.view_location = rt.origin.copy()
            rv3d.view_distance = view_distance
            rv3d.view_rotation = board_view_rotation
            area.tag_redraw()
        except Exception:
            pass


def restore_view_states(rt):
    for state in rt.viewport_view_states:
        rv3d = state.get("region_3d")
        try:
            if state.get("view_perspective") is not None:
                rv3d.view_perspective = state["view_perspective"]
            if state.get("view_location") is not None:
                rv3d.view_location = state["view_location"]
            if state.get("view_distance") is not None:
                rv3d.view_distance = state["view_distance"]
            if state.get("view_rotation") is not None:
                rv3d.view_rotation = state["view_rotation"]
        except Exception:
            pass
    rt.viewport_view_states.clear()


def init_game_state(rt, context=None):
    now = time.monotonic()
    start_level = 1
    prefs = get_dbp_preferences(context or bpy.context)
    if prefs is not None:
        try:
            start_level = int(getattr(prefs, "start_level", "1"))
        except Exception:
            start_level = 1
    if start_level not in {1, 5, 10, 15}:
        start_level = 1
    rt.game = DBPGameState(start_time=now, last_fall_time=now, start_level=start_level, level=start_level, score=0)
    rt.game.total_lines_cleared = 0
    rt.game.fall_interval = calculate_fall_interval(rt.game.level)
    rt.game.bag = make_bag()
    rt.game.next_piece = make_next_piece_data(rt)


def draw_from_bag(rt):
    if not rt.game.bag:
        rt.game.bag = make_bag()
    return rt.game.bag.pop(0)


# Spawn Y is shape-dependent. Do not create spawn pieces with PieceState(kind)
# directly; use this helper so the lowest occupied cell starts at BOARD_HEIGHT,
# one row above the visible board.
def make_spawn_piece(piece_data):
    if isinstance(piece_data, str):
        piece_data = NextPieceData(kind=piece_data, cell_count=4)
    cells = piece_data.custom_cells if piece_data.custom_cells is not None else PIECE_SHAPES[piece_data.kind][0]
    min_local_y = min(dy for _dx, dy in cells)
    return PieceState(
        kind=piece_data.kind,
        x=SPAWN_X,
        y=BOARD_HEIGHT - min_local_y,
        rotation=0,
        custom_cells=list(piece_data.custom_cells) if piece_data.custom_cells is not None else None,
        color=piece_data.color,
        cell_count=piece_data.cell_count,
    )


def spawn_next_as_current(rt):
    piece_data = rt.game.next_piece or make_next_piece_data(rt)
    rt.game.next_piece = make_next_piece_data(rt)
    rt.game.current_piece = make_spawn_piece(piece_data)
    rt.game.piece_spawn_time = time.monotonic()
    if collides(rt, rt.game.current_piece):
        set_game_over(rt)


def get_piece_color(piece_or_kind):
    if isinstance(piece_or_kind, PieceState) and piece_or_kind.color is not None:
        return piece_or_kind.color
    if isinstance(piece_or_kind, NextPieceData) and piece_or_kind.color is not None:
        return piece_or_kind.color
    kind = getattr(piece_or_kind, "kind", piece_or_kind)
    return PIECE_COLORS.get(kind, get_random_mino_color(RANDOM_MINO_MIN_CELL_COUNT) if kind == "RANDOM" else (1.0, 1.0, 1.0, 1.0))


def apply_piece_color(obj, piece_or_kind):
    obj.color = get_piece_color(piece_or_kind)


def _hide_get_for_view_layer(obj, view_layer):
    try:
        return obj.hide_get(view_layer=view_layer)
    except TypeError:
        return obj.hide_get()


def _hide_set_for_view_layer(obj, hidden, view_layer):
    try:
        obj.hide_set(hidden, view_layer=view_layer)
    except TypeError:
        obj.hide_set(hidden)


def hide_non_dbp_scene_objects(rt, context):
    view_layer = getattr(context, "view_layer", None)
    rt.scene_visibility_states.clear()
    temp_names = set()
    if rt.temp_collection is not None:
        try:
            temp_names = {obj.name for obj in rt.temp_collection.objects}
        except Exception:
            temp_names = set()

    for obj in list(getattr(context.scene, "objects", [])):
        if obj is None:
            continue
        if obj.name.startswith(TEMP_PREFIX) or obj.name in temp_names:
            continue
        try:
            hidden = _hide_get_for_view_layer(obj, view_layer)
        except Exception:
            hidden = None
        rt.scene_visibility_states.append({
            "object": obj,
            "name": obj.name,
            "view_layer": view_layer,
            "hidden": hidden,
        })
        try:
            _hide_set_for_view_layer(obj, True, view_layer)
        except Exception:
            pass


def restore_non_dbp_scene_objects(rt):
    for state in getattr(rt, "scene_visibility_states", []):
        obj = state.get("object")
        name = state.get("name")
        hidden = state.get("hidden")
        view_layer = state.get("view_layer")
        if hidden is None:
            continue
        try:
            if obj is not None:
                _hide_set_for_view_layer(obj, hidden, view_layer)
                continue
        except ReferenceError:
            pass
        except Exception:
            pass
        if name:
            found = bpy.data.objects.get(name)
            if found is not None:
                try:
                    _hide_set_for_view_layer(found, hidden, view_layer)
                except Exception:
                    pass
    rt.scene_visibility_states.clear()


def ensure_active_object_count(rt, count):
    if rt.temp_collection is None or rt.shared_cube_mesh is None:
        return
    while len(rt.active_objects) < count:
        index = len(rt.active_objects)
        obj = bpy.data.objects.new(f"{TEMP_PREFIX}Active_Block_{index}", rt.shared_cube_mesh)
        obj.data = rt.shared_cube_mesh
        obj.show_name = False
        obj.hide_render = True
        rt.temp_collection.objects.link(obj)
        rt.active_objects.append(obj)
    while len(rt.active_objects) > count:
        obj = rt.active_objects.pop()
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass


def create_active_piece_objects(rt):
    delete_active_piece_objects(rt)
    if rt.temp_collection is None or rt.shared_cube_mesh is None or rt.game.current_piece is None:
        return
    ensure_active_object_count(rt, len(piece_cells(rt.game.current_piece)))
    for obj in rt.active_objects:
        apply_piece_color(obj, rt.game.current_piece)


def delete_active_piece_objects(rt):
    for obj in list(rt.active_objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass
    rt.active_objects.clear()


def ensure_ghost_object_count(rt, count):
    if rt.temp_collection is None:
        return
    mesh = get_or_create_ghost_mesh(rt)
    while len(rt.ghost_objects) < count:
        index = len(rt.ghost_objects)
        obj = bpy.data.objects.new(f"{GHOST_PREFIX}{index}", mesh)
        obj.show_name = False
        obj.hide_render = True
        obj.color = GHOST_COLOR
        try:
            obj.display_type = "TEXTURED"
        except Exception:
            pass
        rt.temp_collection.objects.link(obj)
        rt.ghost_objects.append(obj)
    while len(rt.ghost_objects) > count:
        obj = rt.ghost_objects.pop()
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass


def clear_ghost_objects(rt):
    for obj in list(getattr(rt, "ghost_objects", [])):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass
        except Exception:
            pass
    rt.ghost_objects.clear()


def copy_piece_state(piece):
    if piece is None:
        return None
    return PieceState(
        kind=piece.kind,
        x=piece.x,
        y=piece.y,
        rotation=piece.rotation,
        custom_cells=list(piece.custom_cells) if piece.custom_cells is not None else None,
        color=piece.color,
        cell_count=getattr(piece, "cell_count", 4),
    )


def piece_local_cells(piece):
    if piece.custom_cells is not None:
        return rotate_custom_cells(piece.custom_cells, piece.rotation)
    return list(PIECE_SHAPES[piece.kind][piece.rotation % 4])


def piece_cells(piece):
    return [(piece.x + dx, piece.y + dy) for dx, dy in piece_local_cells(piece)]


def world_from_grid(rt, x, y):
    return Vector((
        rt.origin.x + (x - (BOARD_WIDTH - 1) / 2.0) * CELL_SIZE,
        rt.origin.y,
        rt.origin.z + (y - (BOARD_HEIGHT - 1) / 2.0) * CELL_SIZE,
    ))


def collides(rt, piece):
    for x, y in piece_cells(piece):
        if x < 0 or x >= BOARD_WIDTH:
            return True
        if y < 0:
            return True
        # Cells above BOARD_HEIGHT are allowed while a piece is spawning/falling
        # in; top-out is checked when the piece locks.
        if y >= BOARD_HEIGHT:
            continue
        if rt.game.board[y][x] is not None:
            return True
    return False


def calculate_ghost_piece(rt, piece):
    if piece is None or rt.game is None or rt.game.game_over:
        return None
    ghost = copy_piece_state(piece)
    while True:
        test_piece = copy_piece_state(ghost)
        test_piece.y -= 1
        if collides(rt, test_piece):
            break
        ghost.y -= 1
    return ghost


def get_ghost_color_for_piece(piece):
    base = get_piece_color(piece)
    return (base[0], base[1], base[2], GHOST_ALPHA)


def update_ghost_objects(rt):
    if rt.game is None or rt.game.game_over or rt.game.current_piece is None:
        clear_ghost_objects(rt)
        return
    ghost_piece = calculate_ghost_piece(rt, rt.game.current_piece)
    if ghost_piece is None:
        clear_ghost_objects(rt)
        return
    cells = piece_cells(ghost_piece)
    ensure_ghost_object_count(rt, len(cells))
    color = get_ghost_color_for_piece(rt.game.current_piece)
    for obj, (x, y) in zip(rt.ghost_objects, cells):
        obj.location = world_from_grid(rt, x, y)
        obj.hide_render = True
        obj.hide_viewport = False
        obj.color = color
        obj.name = f"{GHOST_PREFIX}{ghost_piece.kind}_{x}_{y}"
    for obj in rt.ghost_objects[len(cells):]:
        try:
            obj.hide_viewport = True
        except Exception:
            pass


def update_active_piece_objects(rt):
    piece = rt.game.current_piece
    if piece is None:
        return
    cells = piece_cells(piece)
    ensure_active_object_count(rt, len(cells))
    for obj, (x, y) in zip(rt.active_objects, cells):
        obj.location = world_from_grid(rt, x, y)
        obj.hide_viewport = y < 0
        obj.hide_render = True
        obj.name = f"{TEMP_PREFIX}Active_{piece.kind}_{x}_{y}"
        apply_piece_color(obj, piece)
    update_ghost_objects(rt)


def event_has_modifier(event):
    return bool(getattr(event, "shift", False) or getattr(event, "ctrl", False) or getattr(event, "alt", False) or getattr(event, "oskey", False))


def get_configured_keys(prefs, action_name):
    default_1, default_2 = DEFAULT_CONTROL_KEYS.get(action_name, ("NONE", "NONE"))
    if prefs is None:
        key_1, key_2 = default_1, default_2
    else:
        key_1 = getattr(prefs, f"{action_name}_key_1", default_1)
        key_2 = getattr(prefs, f"{action_name}_key_2", default_2)
    return {key for key in (key_1, key_2) if key and key != "NONE"}


def key_matches(event_type, prefs, action_name):
    return event_type in get_configured_keys(prefs, action_name)


def get_duplicate_key_assignments(prefs):
    if prefs is None:
        return []
    seen = {}
    duplicates = set()
    for action_name, _label in DBP_CONTROL_ACTIONS:
        for key in get_configured_keys(prefs, action_name):
            if key in seen and seen[key] != action_name:
                duplicates.add(key)
            else:
                seen[key] = action_name
    return sorted(duplicates)


def should_quit_from_event(event, context):
    if event.value != "PRESS" or event_has_modifier(event):
        return False
    prefs = get_dbp_preferences(context)
    return key_matches(event.type, prefs, "quit")


def should_finish_game_over_from_event(event, context):
    if event.value != "PRESS" or event_has_modifier(event):
        return False
    prefs = get_dbp_preferences(context)
    return key_matches(event.type, prefs, "quit") or key_matches(event.type, prefs, "hard_drop")


def is_drop_input_locked(rt):
    if rt.game is None:
        return False
    return (time.monotonic() - rt.game.piece_spawn_time) < DROP_INPUT_LOCK_SECONDS


def handle_key(rt, context, event):
    if event.value != "PRESS" or event_has_modifier(event):
        return False
    prefs = get_dbp_preferences(context)
    key_type = event.type

    # Duplicate assignments are resolved by this explicit priority order.
    if key_matches(key_type, prefs, "quit"):
        cleanup_runtime(context)
        return True
    if key_matches(key_type, prefs, "hard_drop"):
        if is_drop_input_locked(rt):
            return True
        hard_drop(rt)
        return True
    if key_matches(key_type, prefs, "soft_drop"):
        # Consume manual drop inputs during the short post-spawn lockout; do not
        # pass them through to Blender, and do not pause automatic gravity.
        if is_drop_input_locked(rt):
            return True
        if try_move(rt, 0, -1):
            rt.game.score += 1
        else:
            lock_current_piece(rt)
        return True
    if key_matches(key_type, prefs, "rotate_left"):
        return try_rotate(rt, -1)
    if key_matches(key_type, prefs, "rotate_right"):
        return try_rotate(rt, 1)
    if key_matches(key_type, prefs, "move_left"):
        return try_move(rt, -1, 0)
    if key_matches(key_type, prefs, "move_right"):
        return try_move(rt, 1, 0)
    return False

def try_move(rt, dx, dy):
    piece = rt.game.current_piece
    if piece is None:
        return False
    candidate = PieceState(piece.kind, piece.x + dx, piece.y + dy, piece.rotation, piece.custom_cells, piece.color, piece.cell_count)
    if collides(rt, candidate):
        return False
    rt.game.current_piece = candidate
    update_active_piece_objects(rt)
    return True


def try_rotate(rt, direction):
    piece = rt.game.current_piece
    if piece is None:
        return False
    new_rot = (piece.rotation + direction) % 4
    for kick in (0, -1, 1, -2, 2):
        candidate = PieceState(piece.kind, piece.x + kick, piece.y, new_rot, piece.custom_cells, piece.color, piece.cell_count)
        if not collides(rt, candidate):
            rt.game.current_piece = candidate
            update_active_piece_objects(rt)
            return True
    return True


def hard_drop(rt):
    piece = rt.game.current_piece
    if piece is None:
        return
    ghost = calculate_ghost_piece(rt, piece)
    if ghost is None:
        return
    dropped = max(0, piece.y - ghost.y)
    rt.game.current_piece = ghost
    update_active_piece_objects(rt)
    rt.game.score += dropped * 2
    lock_current_piece(rt)


def current_fall_interval(rt):
    return max(MIN_FALL_INTERVAL, getattr(rt.game, "fall_interval", BASE_FALL_INTERVAL))


def on_timer(rt, context):
    if rt.game is None or rt.game.game_over or rt.game.line_clear_pending:
        return
    now = time.monotonic()
    if now - rt.game.last_fall_time >= current_fall_interval(rt):
        rt.game.last_fall_time = now
        if not try_move(rt, 0, -1):
            lock_current_piece(rt)
        tag_redraw_all(context)


def lock_current_piece(rt):
    piece = rt.game.current_piece
    if piece is None or rt.game.game_over or rt.game.line_clear_pending:
        return
    cells = piece_cells(piece)
    # If a piece locks while any occupied cell is still above the visible board,
    # that is a top-out game over. Do not discard those cells and continue play.
    if any(y >= BOARD_HEIGHT for _x, y in cells):
        set_game_over(rt)
        return
    for obj, (x, y) in zip(list(rt.active_objects), cells):
        if 0 <= y < BOARD_HEIGHT and 0 <= x < BOARD_WIDTH:
            obj.name = f"{TEMP_PREFIX}Fixed_{piece.kind}_{x}_{y}"
            obj.location = world_from_grid(rt, x, y)
            obj.hide_viewport = False
            apply_piece_color(obj, piece)
            rt.fixed_objects[(x, y)] = obj
            rt.game.board[y][x] = piece.kind
        else:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                pass
    rt.active_objects.clear()
    full_rows = find_full_rows(rt)
    if full_rows:
        start_line_clear_flash(rt, full_rows)
        return
    spawn_next_as_current(rt)
    if not rt.game.game_over:
        create_active_piece_objects(rt)
        update_active_piece_objects(rt)


def find_full_rows(rt):
    return [y for y in range(BOARD_HEIGHT) if all(rt.game.board[y][x] is not None for x in range(BOARD_WIDTH))]


def start_line_clear_flash(rt, rows):
    rt.game.line_clear_pending = True
    rt.game.line_clear_rows = list(rows)
    rt.game.line_clear_started_at = time.monotonic()
    rt.game.line_clear_piece_locked = True
    clear_ghost_objects(rt)
    for y in rows:
        for x in range(BOARD_WIDTH):
            obj = rt.fixed_objects.get((x, y))
            if obj is not None:
                try:
                    obj.color = LINE_CLEAR_FLASH_COLOR
                except Exception:
                    pass


def update_line_clear_flash(rt):
    if rt.game is None or not rt.game.line_clear_pending:
        return
    if time.monotonic() - rt.game.line_clear_started_at < LINE_CLEAR_FLASH_DURATION:
        return
    rows = list(rt.game.line_clear_rows)
    rt.game.line_clear_pending = False
    rt.game.line_clear_rows.clear()
    rt.game.line_clear_started_at = 0.0
    rt.game.line_clear_piece_locked = False
    apply_line_clear(rt, rows)
    spawn_next_as_current(rt)
    if not rt.game.game_over:
        create_active_piece_objects(rt)
        update_active_piece_objects(rt)


def apply_line_clear(rt, rows):
    rows = sorted(set(rows))
    if not rows:
        return 0
    for y in rows:
        for x in range(BOARD_WIDTH):
            obj = rt.fixed_objects.pop((x, y), None)
            if obj is not None:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except ReferenceError:
                    pass
    old_board = rt.game.board
    old_objects = dict(rt.fixed_objects)
    new_board = [[None for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
    new_objects = {}
    write_y = 0
    for read_y in range(BOARD_HEIGHT):
        if read_y in rows:
            continue
        for x in range(BOARD_WIDTH):
            kind = old_board[read_y][x]
            if kind is not None:
                new_board[write_y][x] = kind
                obj = old_objects.get((x, read_y))
                if obj is not None:
                    obj.location = world_from_grid(rt, x, write_y)
                    obj.name = f"{TEMP_PREFIX}Fixed_{kind}_{x}_{write_y}"
                    new_objects[(x, write_y)] = obj
        write_y += 1
    rt.game.board = new_board
    rt.fixed_objects = new_objects

    cleared = len(rows)
    rt.game.total_lines_cleared += cleared
    rt.game.level = calculate_level(rt.game.start_level, rt.game.total_lines_cleared)
    rt.game.fall_interval = calculate_fall_interval(rt.game.level)
    base_score = LINE_CLEAR_BASE_SCORES.get(cleared, 0)
    multiplier = calculate_score_multiplier(rt.game.level)
    rt.game.score += int(base_score * multiplier)
    return cleared


def clear_lines(rt):
    return apply_line_clear(rt, find_full_rows(rt))


def set_game_over(rt):
    rt.game.game_over = True
    delete_active_piece_objects(rt)
    clear_ghost_objects(rt)


def get_draw_context():
    context = bpy.context
    region = getattr(context, "region", None)
    space_data = getattr(context, "space_data", None)
    rv3d = getattr(space_data, "region_3d", None) if space_data else None
    if region is None:
        return None, None, None, None
    return context, region, space_data, rv3d


def draw_overlay():
    rt = get_runtime()
    context, region, _space_data, rv3d = get_draw_context()
    if rt is None or rt.game is None or region is None:
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    try:
        gpu.state.blend_set("ALPHA")
        width = region.width
        height = region.height
        draw_board_grid_overlay(rt, region, rv3d, shader, outline_only=False)
        if not rt.game.game_over:
            next_x, next_y = get_next_preview_origin(rt, region, rv3d, width, height)
            draw_text(f"LEVEL {rt.game.level}", next_x, next_y + 132, 18, (1, 1, 1, 1))
            draw_text(f"SCORE {rt.game.score}", next_x, next_y + 108, 18, (1, 1, 1, 1))
            draw_text("NEXT", next_x, next_y + 78, 15, (0.9, 0.9, 0.9, 1))
            draw_mini_piece(shader, rt.game.next_piece, next_x, next_y)
        if rt.game.game_over:
            draw_rect(shader, 0, 0, width, height, (0.0, 0.0, 0.0, 0.18))
            # 2D overlay projection uses the current draw context and falls back
            # safely when projection is unavailable. This keeps the single draw
            # handler robust across split/changed viewports.
            draw_board_gray_overlay(rt, region, rv3d, shader, width, height)
            draw_board_grid_overlay(rt, region, rv3d, shader, outline_only=True)
            cx, cy = get_board_center_2d(rt, region, rv3d, width, height)
            draw_text("GAME OVER", cx, cy + 22, 46, (1.0, 0.25, 0.2, 1.0), align="CENTER")
            draw_text(f"SCORE {rt.game.score}", cx, cy - 28, 26, (1.0, 1.0, 1.0, 1.0), align="CENTER")
            draw_text(f"LEVEL {rt.game.level}", cx, cy - 58, 20, (1.0, 1.0, 1.0, 1.0), align="CENTER")
            draw_text("Press Esc or Enter", cx, cy - 88, 16, (0.9, 0.9, 0.9, 1.0), align="CENTER")
    except Exception:
        # Draw handlers should never stop the modal operator because a viewport
        # context changed while Blender was redrawing.
        pass
    finally:
        try:
            gpu.state.blend_set("NONE")
        except Exception:
            pass


def get_board_rect_2d(rt, region, rv3d):
    points = []
    for x, y in ((-0.5, -0.5), (BOARD_WIDTH - 0.5, -0.5), (BOARD_WIDTH - 0.5, BOARD_HEIGHT - 0.5), (-0.5, BOARD_HEIGHT - 0.5)):
        projected = project_board_point(rt, region, rv3d, x, y)
        if projected is not None:
            points.append(projected)
    if len(points) < 2:
        return None
    return (
        min(point.x for point in points),
        max(point.x for point in points),
        min(point.y for point in points),
        max(point.y for point in points),
    )


def get_next_preview_origin(rt, region, rv3d, width, height):
    cell = 14
    gap = 2
    preview_w = cell * 4 + gap * 3 + 12
    preview_h = cell * 4 + gap * 3 + 12
    ui_total_h = preview_h + 150
    board_rect = get_board_rect_2d(rt, region, rv3d)
    if board_rect is not None:
        _min_x, max_x, min_y, max_y = board_rect
        x = max_x + 24
        y = (min_y + max_y) * 0.5 - preview_h * 0.5
    else:
        x = width - 175
        y = height * 0.5 - preview_h * 0.5
    x = max(20, min(x, width - preview_w - 20))
    y = max(20, min(y, height - ui_total_h - 20))
    return x, y


def get_board_center_2d(rt, region, rv3d, width, height):
    if region is not None and rv3d is not None:
        try:
            center_world = world_from_grid(rt, (BOARD_WIDTH - 1) / 2.0, (BOARD_HEIGHT - 1) / 2.0)
            projected = location_3d_to_region_2d(region, rv3d, center_world)
            if projected is not None:
                return projected.x, projected.y
        except Exception:
            pass
    return width / 2.0, height / 2.0


def project_board_point(rt, region, rv3d, x, y):
    if region is None or rv3d is None:
        return None
    try:
        return location_3d_to_region_2d(region, rv3d, world_from_grid(rt, x, y))
    except Exception:
        return None


def draw_board_grid_overlay(rt, region, rv3d, shader, outline_only=False):
    if region is None or rv3d is None:
        return
    inner_color = (0.55, 0.95, 1.0, 0.22)
    outer_color = (0.85, 1.0, 1.0, 0.85)
    left = -0.5
    right = BOARD_WIDTH - 0.5
    bottom = -0.5
    top = BOARD_HEIGHT - 0.5

    if not outline_only:
        for x in range(1, BOARD_WIDTH):
            p1 = project_board_point(rt, region, rv3d, x - 0.5, bottom)
            p2 = project_board_point(rt, region, rv3d, x - 0.5, top)
            if p1 is not None and p2 is not None:
                draw_line(shader, p1.x, p1.y, p2.x, p2.y, inner_color)
        for y in range(1, BOARD_HEIGHT):
            p1 = project_board_point(rt, region, rv3d, left, y - 0.5)
            p2 = project_board_point(rt, region, rv3d, right, y - 0.5)
            if p1 is not None and p2 is not None:
                draw_line(shader, p1.x, p1.y, p2.x, p2.y, inner_color)

    corners = (
        project_board_point(rt, region, rv3d, left, bottom),
        project_board_point(rt, region, rv3d, right, bottom),
        project_board_point(rt, region, rv3d, right, top),
        project_board_point(rt, region, rv3d, left, top),
    )
    if any(corner is None for corner in corners):
        return
    for p1, p2 in zip(corners, corners[1:] + corners[:1]):
        draw_line(shader, p1.x, p1.y, p2.x, p2.y, outer_color)
        draw_line(shader, p1.x + 1, p1.y, p2.x + 1, p2.y, outer_color)
        draw_line(shader, p1.x, p1.y + 1, p2.x, p2.y + 1, outer_color)


def draw_board_gray_overlay(rt, region, rv3d, shader, region_width, region_height):
    points = []
    if region is not None and rv3d is not None:
        board_corners = (
            world_from_grid(rt, -0.5, -0.5),
            world_from_grid(rt, BOARD_WIDTH - 0.5, -0.5),
            world_from_grid(rt, BOARD_WIDTH - 0.5, BOARD_HEIGHT - 0.5),
            world_from_grid(rt, -0.5, BOARD_HEIGHT - 0.5),
        )
        for corner in board_corners:
            try:
                projected = location_3d_to_region_2d(region, rv3d, corner)
            except Exception:
                projected = None
            if projected is not None:
                points.append(projected)
    if len(points) >= 2:
        min_x = max(0, min(point.x for point in points) - 10)
        max_x = min(region_width, max(point.x for point in points) + 10)
        min_y = max(0, min(point.y for point in points) - 10)
        max_y = min(region_height, max(point.y for point in points) + 10)
        if max_x > min_x and max_y > min_y:
            draw_rect(shader, min_x, min_y, max_x - min_x, max_y - min_y, (0.45, 0.45, 0.45, 0.58))
            return
    fallback_w = min(region_width * 0.55, 360)
    fallback_h = min(region_height * 0.72, 560)
    draw_rect(shader, (region_width - fallback_w) * 0.5, (region_height - fallback_h) * 0.5, fallback_w, fallback_h, (0.45, 0.45, 0.45, 0.58))


def draw_mini_piece(shader, piece_data, x, y):
    cell = 14
    gap = 2
    draw_rect(shader, x - 6, y - 6, cell * 4 + gap * 3 + 12, cell * 4 + gap * 3 + 12, (0.02, 0.02, 0.02, 0.45))
    for gx in range(4):
        for gy in range(4):
            draw_rect(shader, x + gx * (cell + gap), y + gy * (cell + gap), cell, cell, (0.15, 0.15, 0.15, 0.45))
    if not piece_data:
        return
    if isinstance(piece_data, str):
        piece_data = NextPieceData(kind=piece_data, cell_count=4)
    color = get_piece_color(piece_data)
    cells = piece_data.custom_cells if piece_data.custom_cells is not None else PIECE_SHAPES[piece_data.kind][0]
    for dx, dy in cells:
        draw_rect(shader, x + dx * (cell + gap), y + dy * (cell + gap), cell, cell, color)


def consume_undo_redo(event):
    if event.value != "PRESS":
        return False
    return event.ctrl and event.type in {"Z", "Y"}


def consume_view_navigation(event):
    nav_events = {
        "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
        "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "MOUSEPAN", "MOUSEZOOM",
        "NDOF_MOTION", "NDOF_BUTTON_MENU", "NDOF_BUTTON_FIT", "NDOF_BUTTON_TOP", "NDOF_BUTTON_BOTTOM",
        "NDOF_BUTTON_LEFT", "NDOF_BUTTON_RIGHT", "NDOF_BUTTON_FRONT", "NDOF_BUTTON_BACK",
        "NDOF_BUTTON_ISO1", "NDOF_BUTTON_ISO2", "NDOF_BUTTON_ROLL_CW", "NDOF_BUTTON_ROLL_CCW",
        "NDOF_BUTTON_SPIN_CW", "NDOF_BUTTON_SPIN_CCW", "NDOF_BUTTON_TILT_CW", "NDOF_BUTTON_TILT_CCW",
    }
    return event.type in nav_events


def tag_redraw_all(context):
    wm = getattr(context, "window_manager", None)
    if wm is None:
        return
    for window in getattr(wm, "windows", []):
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in getattr(screen, "areas", []):
            if area.type == "VIEW_3D":
                try:
                    area.tag_redraw()
                except Exception:
                    pass


def remove_temp_data(rt):
    if rt.temp_collection is not None:
        try:
            safe_remove_collection_by_name(rt.temp_collection.name)
        except Exception:
            pass
    else:
        safe_remove_collection_by_name(TEMP_COLLECTION_NAME)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith(TEMP_PREFIX) and mesh.users == 0:
            try:
                bpy.data.meshes.remove(mesh)
            except ReferenceError:
                pass
    for mat in list(bpy.data.materials):
        if mat.name.startswith(TEMP_PREFIX) and mat.users == 0:
            try:
                bpy.data.materials.remove(mat)
            except ReferenceError:
                pass
    purge_dbp_orphans()


def restore_object_mode_and_active(rt, context):
    try:
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    if rt.active_object_name:
        obj = bpy.data.objects.get(rt.active_object_name)
        if obj is not None:
            try:
                context.view_layer.objects.active = obj
                obj.select_set(True)
            except Exception:
                pass


def cleanup_runtime(context):
    global _DBP_RUNTIME
    rt = _DBP_RUNTIME
    if rt is None:
        return
    if rt.cleaned:
        _DBP_RUNTIME = None
        return
    rt.cleaned = True
    wm = getattr(context, "window_manager", None)
    if rt.timer is not None and wm is not None:
        try:
            wm.event_timer_remove(rt.timer)
        except Exception:
            pass
        rt.timer = None
    if rt.draw_handle is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(rt.draw_handle, "WINDOW")
        except Exception:
            pass
        rt.draw_handle = None
    stop_bgm(rt)
    restore_viewports(rt)
    restore_view_states(rt)
    restore_non_dbp_scene_objects(rt)
    clear_ghost_objects(rt)
    remove_temp_data(rt)
    restore_object_mode_and_active(rt, context)
    rt.active_objects.clear()
    rt.ghost_objects.clear()
    rt.fixed_objects.clear()
    rt.scene_visibility_states.clear()
    rt.shared_cube_mesh = None
    rt.ghost_mesh = None
    rt.ghost_material = None
    rt.temp_collection = None
    rt.game = None
    _DBP_RUNTIME = None
    tag_redraw_all(context)


class DBP_OT_test_bgm(bpy.types.Operator):
    bl_idname = "down_block_puzzle.test_bgm"
    bl_label = "Test BGM"
    bl_description = "Play the configured Down Block Puzzle BGM for five seconds for diagnostics"
    bl_options = set()

    def execute(self, context):
        result = start_test_bgm(context)
        if result.ok:
            self.report({"INFO"}, result.message)
            return {"FINISHED"}
        self.report({"WARNING"}, result.message)
        return {"CANCELLED"}


class DBP_OT_stop_test_bgm(bpy.types.Operator):
    bl_idname = "down_block_puzzle.stop_test_bgm"
    bl_label = "Stop Test BGM"
    bl_description = "Stop Down Block Puzzle BGM test playback"
    bl_options = set()

    def execute(self, context):
        stop_test_bgm()
        self.report({"INFO"}, "Stopped BGM test playback.")
        return {"FINISHED"}


class DownBlockPuzzleAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    bgm_enabled: bpy.props.BoolProperty(
        name="Enable BGM",
        default=True,
    )
    bgm_filepath: bpy.props.StringProperty(
        name="BGM File",
        description="MP3/WAV/OGG file to play during Down Block Puzzle",
        subtype="FILE_PATH",
        default="",
    )
    bgm_volume: bpy.props.FloatProperty(
        name="BGM Volume",
        default=0.35,
        min=0.0,
        max=1.0,
    )
    bgm_loop: bpy.props.BoolProperty(
        name="Loop BGM",
        default=True,
    )
    start_level: bpy.props.EnumProperty(
        name="Start Level",
        items=DBP_START_LEVEL_ITEMS,
        default="1",
    )
    move_left_key_1: bpy.props.EnumProperty(name="Move Left 1", items=DBP_KEY_ITEMS, default="A")
    move_left_key_2: bpy.props.EnumProperty(name="Move Left 2", items=DBP_KEY_ITEMS, default="NUMPAD_4")
    move_right_key_1: bpy.props.EnumProperty(name="Move Right 1", items=DBP_KEY_ITEMS, default="D")
    move_right_key_2: bpy.props.EnumProperty(name="Move Right 2", items=DBP_KEY_ITEMS, default="NUMPAD_6")
    rotate_left_key_1: bpy.props.EnumProperty(name="Rotate Left 1", items=DBP_KEY_ITEMS, default="Q")
    rotate_left_key_2: bpy.props.EnumProperty(name="Rotate Left 2", items=DBP_KEY_ITEMS, default="NUMPAD_7")
    rotate_right_key_1: bpy.props.EnumProperty(name="Rotate Right 1", items=DBP_KEY_ITEMS, default="R")
    rotate_right_key_2: bpy.props.EnumProperty(name="Rotate Right 2", items=DBP_KEY_ITEMS, default="NUMPAD_9")
    soft_drop_key_1: bpy.props.EnumProperty(name="Soft Drop 1", items=DBP_KEY_ITEMS, default="S")
    soft_drop_key_2: bpy.props.EnumProperty(name="Soft Drop 2", items=DBP_KEY_ITEMS, default="NUMPAD_2")
    hard_drop_key_1: bpy.props.EnumProperty(name="Hard Drop 1", items=DBP_KEY_ITEMS, default="RET")
    hard_drop_key_2: bpy.props.EnumProperty(name="Hard Drop 2", items=DBP_KEY_ITEMS, default="NUMPAD_ENTER")
    quit_key_1: bpy.props.EnumProperty(name="Quit 1", items=DBP_KEY_ITEMS, default="ESC")
    quit_key_2: bpy.props.EnumProperty(name="Quit 2", items=DBP_KEY_ITEMS, default="NONE")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "start_level")
        controls = layout.box()
        controls.label(text="Controls")
        for action_name, label in DBP_CONTROL_ACTIONS:
            row = controls.row(align=True)
            row.label(text=label)
            row.prop(self, f"{action_name}_key_1", text="")
            row.prop(self, f"{action_name}_key_2", text="")
        duplicates = get_duplicate_key_assignments(self)
        if duplicates:
            controls.label(text="Warning: duplicate key assignments detected.", icon="ERROR")
        layout.separator()
        layout.prop(self, "bgm_enabled")
        layout.prop(self, "bgm_filepath")
        layout.prop(self, "bgm_volume")
        layout.prop(self, "bgm_loop")
        layout.label(text="If MP3 does not play, test WAV or OGG. Playback depends on Blender/aud codec support.")
        row = layout.row(align=True)
        row.operator("down_block_puzzle.test_bgm", text="Test BGM", icon="PLAY")
        row.operator("down_block_puzzle.stop_test_bgm", text="Stop Test BGM", icon="CANCEL")


class OBJECT_OT_down_block_puzzle_start(bpy.types.Operator):
    bl_idname = "object.down_block_puzzle_start"
    bl_label = "Start Down Block Puzzle"
    bl_description = "Start a modal Down Block Puzzle game centered on the active mesh object"
    bl_options = set()

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.object is not None and context.object.type == "MESH"

    def invoke(self, context, event):
        global _DBP_RUNTIME
        if is_dbp_running():
            self.report({"WARNING"}, "Down Block Puzzle is already running.")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            self.report({"WARNING"}, "Down Block Puzzle can only start in Object Mode.")
            return {"CANCELLED"}
        if context.object is None or context.object.type != "MESH":
            self.report({"WARNING"}, "Select an active mesh object such as a Cube before starting Down Block Puzzle.")
            return {"CANCELLED"}

        source_obj = context.object
        _DBP_RUNTIME = DBPRuntimeState(
            origin=source_obj.location.copy(),
            active_object_name=source_obj.name,
        )
        rt = _DBP_RUNTIME
        try:
            safe_remove_collection_by_name(TEMP_COLLECTION_NAME)
            purge_dbp_orphans()
            create_temp_collection(rt, context)
            hide_non_dbp_scene_objects(rt, context)
            create_shared_mesh(rt)
            save_viewports(rt, context)
            save_view_states(rt, context)
            set_game_viewports(rt, context)
            focus_viewports_on_board(rt, context)
            init_game_state(rt, context)
            spawn_next_as_current(rt)
            if not rt.game.game_over:
                create_active_piece_objects(rt)
                update_active_piece_objects(rt)
            rt.draw_handle = bpy.types.SpaceView3D.draw_handler_add(draw_overlay, (), "WINDOW", "POST_PIXEL")
            rt.timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)
            start_bgm(rt, context)
            context.window_manager.modal_handler_add(self)
            tag_redraw_all(context)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to start Down Block Puzzle: {exc}")
            cleanup_runtime(context)
            return {"CANCELLED"}

    def modal(self, context, event):
        rt = get_runtime()
        if rt is None or rt.cleaned or rt.game is None:
            return {"CANCELLED"}
        try:
            if consume_undo_redo(event):
                return {"RUNNING_MODAL"}
            if consume_view_navigation(event):
                return {"RUNNING_MODAL"}
            if should_quit_from_event(event, context):
                cleanup_runtime(context)
                return {"CANCELLED"}
            if rt.game.game_over:
                if should_finish_game_over_from_event(event, context):
                    cleanup_runtime(context)
                    return {"FINISHED"}
                if event.type == "TIMER":
                    update_bgm_loop(rt)
                    tag_redraw_all(context)
                return {"RUNNING_MODAL"}
            if rt.game.line_clear_pending:
                if event.type == "TIMER":
                    update_bgm_loop(rt)
                    update_line_clear_flash(rt)
                    tag_redraw_all(context)
                return {"RUNNING_MODAL"}
            if event.type == "TIMER":
                update_bgm_loop(rt)
                on_timer(rt, context)
                return {"RUNNING_MODAL"}
            if event.value == "PRESS":
                handled = handle_key(rt, context, event)
                if handled:
                    tag_redraw_all(context)
                    return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, f"Down Block Puzzle stopped after an error: {exc}")
            cleanup_runtime(context)
            return {"CANCELLED"}


class VIEW3D_PT_down_block_puzzle_panel(bpy.types.Panel):
    bl_label = "Down Block Puzzle"
    bl_idname = "VIEW3D_PT_down_block_puzzle_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Down Block Puzzle"

    def draw(self, context):
        layout = self.layout
        running = is_dbp_running()
        layout.label(text="Down Block Puzzle")
        row = layout.row()
        row.enabled = not running and context.mode == "OBJECT" and context.object is not None and context.object.type == "MESH"
        row.operator(OBJECT_OT_down_block_puzzle_start.bl_idname, text="Start Down Block Puzzle", icon="PLAY")
        if running:
            layout.label(text="Already running", icon="INFO")
        prefs = get_dbp_preferences(context)
        if prefs is not None:
            layout.separator()
            settings = layout.box()
            settings.label(text="Start Settings")
            settings.prop(prefs, "start_level")

            controls = layout.box()
            controls.label(text="Controls")
            for action_name, label in DBP_CONTROL_ACTIONS:
                row = controls.row(align=True)
                row.label(text=label)
                row.prop(prefs, f"{action_name}_key_1", text="")
                row.prop(prefs, f"{action_name}_key_2", text="")
            if get_duplicate_key_assignments(prefs):
                controls.label(text="Warning: duplicate key assignments detected.", icon="ERROR")

            layout.separator()
            if getattr(prefs, "bgm_enabled", True):
                bgm_path = bpy.path.abspath(getattr(prefs, "bgm_filepath", ""))
                if bgm_path:
                    layout.label(text=f"BGM: {os.path.basename(bgm_path)}", icon="SPEAKER")
                else:
                    layout.label(text="BGM: Not Set", icon="SPEAKER")
            else:
                layout.label(text="BGM: Disabled", icon="SPEAKER")
        else:
            layout.label(text="Addon preferences unavailable", icon="ERROR")


classes = (
    DBP_OT_test_bgm,
    DBP_OT_stop_test_bgm,
    DownBlockPuzzleAddonPreferences,
    OBJECT_OT_down_block_puzzle_start,
    VIEW3D_PT_down_block_puzzle_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    cleanup_runtime(bpy.context)
    stop_test_bgm()
    safe_remove_collection_by_name(TEMP_COLLECTION_NAME)
    purge_dbp_orphans()
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()
