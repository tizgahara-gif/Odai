# SPDX-License-Identifier: MIT
# Blender Tetris Mode - single-file Blender 4.x/5.x add-on

bl_info = {
    "name": "Tetris Mode",
    "author": "OpenAI",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Tetris / F3 Search",
    "description": "A modal Tetris mini-game that runs in Object Mode without touching scene data permanently.",
    "category": "Object",
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
TEMP_COLLECTION_NAME = "Tetris_Temporary_Collection"
TEMP_PREFIX = "Tetris_"
TIMER_INTERVAL = 0.03
INITIAL_FALL_INTERVAL = 0.8
SPEEDUP_SECONDS = 30.0
SPEEDUP_FACTOR = 0.9
MIN_FALL_INTERVAL = 0.08
DROP_INPUT_LOCK_SECONDS = 0.5
SPAWN_X = BOARD_WIDTH // 2 - 2
SCORE_LINE_CLEAR = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}

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

# Stable 4x4 tetromino definitions. The piece origin is the lower-left of its
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
class PieceState:
    kind: str
    x: int
    y: int
    rotation: int = 0


@dataclass
class TetrisGameState:
    board: list = field(default_factory=lambda: [[None for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)])
    current_piece: PieceState | None = None
    next_piece: str | None = None
    bag: list = field(default_factory=list)
    score: int = 0
    piece_spawn_time: float = 0.0
    start_time: float = 0.0
    last_fall_time: float = 0.0
    game_over: bool = False


@dataclass
class TetrisRuntimeState:
    timer: object | None = None
    draw_handle: object | None = None
    viewport_states: list = field(default_factory=list)
    viewport_view_states: list = field(default_factory=list)
    temp_collection: object | None = None
    shared_cube_mesh: object | None = None
    active_objects: list = field(default_factory=list)
    fixed_objects: dict = field(default_factory=dict)
    game: TetrisGameState | None = None
    origin: Vector = field(default_factory=lambda: Vector((0.0, 0.0, 0.0)))
    active_object_name: str | None = None
    source_object_name: str | None = None
    source_object_hidden: bool | None = None
    bgm_device: object | None = None
    bgm_factory: object | None = None
    bgm_handle: object | None = None
    bgm_filepath: str | None = None
    cleaned: bool = False


_TETRIS_RUNTIME: TetrisRuntimeState | None = None
_BGM_TEST_DEVICE = None
_BGM_TEST_FACTORY = None
_BGM_TEST_HANDLE = None
_BGM_TEST_FILEPATH = None
_BGM_TEST_TOKEN = 0


def get_runtime():
    return _TETRIS_RUNTIME


def is_tetris_running():
    rt = get_runtime()
    return rt is not None and not rt.cleaned


def get_addon_preferences(context):
    addon = context.preferences.addons.get(__name__)
    if addon is None:
        return None
    return addon.preferences


def play_bgm_from_preferences(context, log_prefix="[Tetris Mode][BGM]", force_duration_label=None):
    print(f"{log_prefix} resolving preferences")
    prefs = get_addon_preferences(context)
    if prefs is None:
        print(f"{log_prefix} preferences not found")
        return None, None, None, None
    print(f"{log_prefix} prefs found")
    enabled = bool(getattr(prefs, "bgm_enabled", True))
    print(f"{log_prefix} enabled: {enabled}")
    if not enabled:
        return None, None, None, None

    raw_filepath = getattr(prefs, "bgm_filepath", "")
    print(f"{log_prefix} raw filepath: {raw_filepath}")
    filepath = bpy.path.abspath(raw_filepath) if raw_filepath else ""
    print(f"{log_prefix} absolute filepath: {filepath}")
    if not filepath:
        print(f"{log_prefix} no BGM file configured")
        return None, None, None, None

    exists = os.path.isfile(filepath)
    print(f"{log_prefix} file exists: {exists}")
    if not exists:
        print(f"{log_prefix} BGM file not found: {filepath}")
        return None, None, None, None

    try:
        import aud
        print(f"{log_prefix} aud import ok")
    except Exception as exc:
        print(f"{log_prefix} aud import failed: {exc}")
        return None, None, None, None

    try:
        factory = aud.Factory.file(filepath)
        print(f"{log_prefix} factory created")
    except Exception as exc:
        print(f"{log_prefix} factory creation failed: {exc}")
        return None, None, None, None

    if getattr(prefs, "bgm_loop", True):
        try:
            factory = factory.loop(-1)
            print(f"{log_prefix} loop applied")
        except Exception as exc:
            print(f"{log_prefix} loop unavailable, playing once: {exc}")
    else:
        print(f"{log_prefix} loop disabled")

    try:
        device = aud.Device()
        print(f"{log_prefix} device created")
    except Exception as exc:
        print(f"{log_prefix} device creation failed: {exc}")
        return None, None, None, None

    try:
        handle = device.play(factory)
        print(f"{log_prefix} playback started")
    except Exception as exc:
        print(f"{log_prefix} device.play failed: {exc}")
        return device, factory, None, filepath

    volume = float(getattr(prefs, "bgm_volume", 0.35))
    print(f"{log_prefix} volume: {volume}")
    try:
        handle.volume = volume
        print(f"{log_prefix} volume applied")
    except Exception as exc:
        print(f"{log_prefix} volume apply failed: {exc}")

    try:
        print(f"{log_prefix} handle status: {handle.status}")
    except Exception as exc:
        print(f"{log_prefix} handle status unavailable: {exc}")

    print(f"{log_prefix} handle retained{f' ({force_duration_label})' if force_duration_label else ''}: {filepath}")
    return device, factory, handle, filepath


def start_bgm(rt, context):
    try:
        device, factory, handle, filepath = play_bgm_from_preferences(context, "[Tetris Mode][BGM]")
        rt.bgm_device = device
        rt.bgm_factory = factory
        rt.bgm_handle = handle
        rt.bgm_filepath = filepath
    except Exception as exc:
        print(f"[Tetris Mode][BGM] Failed to play BGM: {exc}")
        rt.bgm_device = None
        rt.bgm_factory = None
        rt.bgm_handle = None
        rt.bgm_filepath = None


def stop_bgm(rt):
    handle = getattr(rt, "bgm_handle", None)
    if handle is not None:
        try:
            handle.stop()
            print("[Tetris Mode][BGM] stopped")
        except Exception as exc:
            print(f"[Tetris Mode][BGM] stop failed: {exc}")
    rt.bgm_handle = None
    rt.bgm_factory = None
    rt.bgm_device = None
    rt.bgm_filepath = None


def stop_test_bgm():
    global _BGM_TEST_DEVICE, _BGM_TEST_FACTORY, _BGM_TEST_HANDLE, _BGM_TEST_FILEPATH
    if _BGM_TEST_HANDLE is not None:
        try:
            _BGM_TEST_HANDLE.stop()
            print("[Tetris Mode][BGM Test] stopped")
        except Exception as exc:
            print(f"[Tetris Mode][BGM Test] stop failed: {exc}")
    _BGM_TEST_HANDLE = None
    _BGM_TEST_FACTORY = None
    _BGM_TEST_DEVICE = None
    _BGM_TEST_FILEPATH = None


def start_test_bgm(context):
    global _BGM_TEST_DEVICE, _BGM_TEST_FACTORY, _BGM_TEST_HANDLE, _BGM_TEST_FILEPATH, _BGM_TEST_TOKEN
    stop_test_bgm()
    _BGM_TEST_TOKEN += 1
    token = _BGM_TEST_TOKEN
    device, factory, handle, filepath = play_bgm_from_preferences(context, "[Tetris Mode][BGM Test]", "auto-stop in 5s")
    _BGM_TEST_DEVICE = device
    _BGM_TEST_FACTORY = factory
    _BGM_TEST_HANDLE = handle
    _BGM_TEST_FILEPATH = filepath
    if handle is not None:
        def auto_stop():
            if token == _BGM_TEST_TOKEN:
                stop_test_bgm()
            return None
        try:
            bpy.app.timers.register(auto_stop, first_interval=5.0)
        except Exception as exc:
            print(f"[Tetris Mode][BGM Test] auto-stop timer failed: {exc}")
    return handle is not None



def make_bag():
    bag = list(PIECE_KINDS)
    random.shuffle(bag)
    return bag


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


def purge_tetris_orphans():
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


def create_shared_mesh(rt):
    half = CELL_SIZE * 0.46
    verts = [
        (-half, -half, -half), (half, -half, -half), (half, half, -half), (-half, half, -half),
        (-half, -half, half), (half, -half, half), (half, half, half), (-half, half, half),
    ]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    rt.shared_cube_mesh = bpy.data.meshes.new(f"{TEMP_PREFIX}Shared_Cube_Mesh")
    rt.shared_cube_mesh.from_pydata(verts, [], faces)
    rt.shared_cube_mesh.update()


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


def init_game_state(rt):
    now = time.monotonic()
    rt.game = TetrisGameState(start_time=now, last_fall_time=now)
    rt.game.bag = make_bag()
    rt.game.next_piece = draw_from_bag(rt)


def draw_from_bag(rt):
    if not rt.game.bag:
        rt.game.bag = make_bag()
    return rt.game.bag.pop(0)


# Spawn Y is shape-dependent. Do not create spawn pieces with PieceState(kind)
# directly; use this helper so the lowest occupied cell starts at BOARD_HEIGHT,
# one row above the visible board.
def make_spawn_piece(kind):
    shape = PIECE_SHAPES[kind][0]
    min_local_y = min(dy for _dx, dy in shape)
    return PieceState(kind=kind, x=SPAWN_X, y=BOARD_HEIGHT - min_local_y, rotation=0)


def spawn_next_as_current(rt):
    kind = rt.game.next_piece or draw_from_bag(rt)
    rt.game.next_piece = draw_from_bag(rt)
    rt.game.current_piece = make_spawn_piece(kind)
    rt.game.piece_spawn_time = time.monotonic()
    if collides(rt, rt.game.current_piece):
        set_game_over(rt)


def apply_piece_color(obj, kind):
    obj.color = PIECE_COLORS.get(kind, (1.0, 1.0, 1.0, 1.0))


def hide_source_object_for_game(rt, obj):
    rt.source_object_name = obj.name
    # Hide source object instead of modifying its material transparency, Object.color,
    # hide_viewport, or hide_render. Restore the original per-view-layer hidden state
    # during cleanup.
    try:
        rt.source_object_hidden = obj.hide_get()
        obj.hide_set(True)
    except Exception:
        rt.source_object_hidden = None


def restore_source_object_visibility(rt):
    if not rt.source_object_name or rt.source_object_hidden is None:
        return
    obj = bpy.data.objects.get(rt.source_object_name)
    if obj is not None:
        try:
            obj.hide_set(rt.source_object_hidden)
        except Exception:
            pass


def create_active_piece_objects(rt):
    delete_active_piece_objects(rt)
    if rt.temp_collection is None or rt.shared_cube_mesh is None or rt.game.current_piece is None:
        return
    for i in range(4):
        obj = bpy.data.objects.new(f"{TEMP_PREFIX}Active_Block_{i}", rt.shared_cube_mesh)
        obj.data = rt.shared_cube_mesh
        obj.show_name = False
        obj.hide_render = True
        apply_piece_color(obj, rt.game.current_piece.kind)
        rt.temp_collection.objects.link(obj)
        rt.active_objects.append(obj)


def delete_active_piece_objects(rt):
    for obj in list(rt.active_objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass
    rt.active_objects.clear()


def piece_cells(piece):
    return [(piece.x + dx, piece.y + dy) for dx, dy in PIECE_SHAPES[piece.kind][piece.rotation % 4]]


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


def update_active_piece_objects(rt):
    piece = rt.game.current_piece
    if piece is None:
        return
    for obj, (x, y) in zip(rt.active_objects, piece_cells(piece)):
        obj.location = world_from_grid(rt, x, y)
        obj.hide_viewport = y < 0
        obj.hide_render = True
        obj.name = f"{TEMP_PREFIX}Active_{piece.kind}_{x}_{y}"
        apply_piece_color(obj, piece.kind)


def is_drop_input_locked(rt):
    if rt.game is None:
        return False
    return (time.monotonic() - rt.game.piece_spawn_time) < DROP_INPUT_LOCK_SECONDS


def handle_key(rt, context, key_type):
    if key_type in {"A", "FOUR", "NUMPAD_4"}:
        return try_move(rt, -1, 0)
    if key_type in {"D", "SIX", "NUMPAD_6"}:
        return try_move(rt, 1, 0)
    if key_type in {"S", "TWO", "NUMPAD_2"}:
        # Consume manual drop inputs during the short post-spawn lockout; do not
        # pass them through to Blender, and do not pause automatic gravity.
        if is_drop_input_locked(rt):
            return True
        if try_move(rt, 0, -1):
            rt.game.score += 1
        else:
            lock_current_piece(rt)
        return True
    if key_type in {"Q", "SEVEN", "NUMPAD_7"}:
        return try_rotate(rt, -1)
    if key_type in {"R", "NINE", "NUMPAD_9"}:
        return try_rotate(rt, 1)
    if key_type in {"RET", "NUMPAD_ENTER"}:
        if is_drop_input_locked(rt):
            return True
        hard_drop(rt)
        return True
    return False


def try_move(rt, dx, dy):
    piece = rt.game.current_piece
    if piece is None:
        return False
    candidate = PieceState(piece.kind, piece.x + dx, piece.y + dy, piece.rotation)
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
        candidate = PieceState(piece.kind, piece.x + kick, piece.y, new_rot)
        if not collides(rt, candidate):
            rt.game.current_piece = candidate
            update_active_piece_objects(rt)
            return True
    return True


def hard_drop(rt):
    dropped = 0
    while try_move(rt, 0, -1):
        dropped += 1
    rt.game.score += dropped * 2
    lock_current_piece(rt)


def current_fall_interval(rt):
    elapsed = time.monotonic() - rt.game.start_time
    steps = int(elapsed // SPEEDUP_SECONDS)
    return max(MIN_FALL_INTERVAL, INITIAL_FALL_INTERVAL * (SPEEDUP_FACTOR ** steps))


def on_timer(rt, context):
    if rt.game is None or rt.game.game_over:
        return
    now = time.monotonic()
    if now - rt.game.last_fall_time >= current_fall_interval(rt):
        rt.game.last_fall_time = now
        if not try_move(rt, 0, -1):
            lock_current_piece(rt)
        tag_redraw_all(context)


def lock_current_piece(rt):
    piece = rt.game.current_piece
    if piece is None or rt.game.game_over:
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
            apply_piece_color(obj, piece.kind)
            rt.fixed_objects[(x, y)] = obj
            rt.game.board[y][x] = piece.kind
        else:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                pass
    rt.active_objects.clear()
    cleared = clear_lines(rt)
    rt.game.score += SCORE_LINE_CLEAR.get(cleared, 0)
    spawn_next_as_current(rt)
    if not rt.game.game_over:
        create_active_piece_objects(rt)
        update_active_piece_objects(rt)


def clear_lines(rt):
    full_rows = [y for y in range(BOARD_HEIGHT) if all(rt.game.board[y][x] is not None for x in range(BOARD_WIDTH))]
    if not full_rows:
        return 0
    for y in full_rows:
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
        if read_y in full_rows:
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
    return len(full_rows)


def set_game_over(rt):
    rt.game.game_over = True
    delete_active_piece_objects(rt)


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
            draw_text(f"SCORE {rt.game.score}", next_x, next_y + 108, 20, (1, 1, 1, 1))
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
            draw_text("Press Esc or Enter", cx, cy - 62, 16, (0.9, 0.9, 0.9, 1.0), align="CENTER")
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
    ui_total_h = preview_h + 110
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


def draw_mini_piece(shader, kind, x, y):
    cell = 14
    gap = 2
    draw_rect(shader, x - 6, y - 6, cell * 4 + gap * 3 + 12, cell * 4 + gap * 3 + 12, (0.02, 0.02, 0.02, 0.45))
    for gx in range(4):
        for gy in range(4):
            draw_rect(shader, x + gx * (cell + gap), y + gy * (cell + gap), cell, cell, (0.15, 0.15, 0.15, 0.45))
    if not kind:
        return
    color = PIECE_COLORS[kind]
    for dx, dy in PIECE_SHAPES[kind][0]:
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
    purge_tetris_orphans()


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
    global _TETRIS_RUNTIME
    rt = _TETRIS_RUNTIME
    if rt is None:
        return
    if rt.cleaned:
        _TETRIS_RUNTIME = None
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
    restore_source_object_visibility(rt)
    remove_temp_data(rt)
    restore_object_mode_and_active(rt, context)
    rt.active_objects.clear()
    rt.fixed_objects.clear()
    rt.shared_cube_mesh = None
    rt.temp_collection = None
    rt.game = None
    _TETRIS_RUNTIME = None
    tag_redraw_all(context)


class TETRIS_MODE_OT_test_bgm(bpy.types.Operator):
    bl_idname = "tetris_mode.test_bgm"
    bl_label = "Test BGM"
    bl_description = "Play the configured Tetris Mode BGM for five seconds for diagnostics"
    bl_options = set()

    def execute(self, context):
        ok = start_test_bgm(context)
        if ok:
            self.report({"INFO"}, "Testing BGM for 5 seconds. See System Console for diagnostics.")
        else:
            self.report({"WARNING"}, "BGM test did not start. See System Console for diagnostics.")
        return {"FINISHED"}


class TetrisModeAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    bgm_enabled: bpy.props.BoolProperty(
        name="Enable BGM",
        default=True,
    )
    bgm_filepath: bpy.props.StringProperty(
        name="BGM File",
        description="MP3/WAV/OGG file to play during Tetris Mode",
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

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "bgm_enabled")
        layout.prop(self, "bgm_filepath")
        layout.prop(self, "bgm_volume")
        layout.prop(self, "bgm_loop")
        layout.label(text="If MP3 does not play, test WAV or OGG. Playback depends on Blender/aud codec support.")
        layout.operator("tetris_mode.test_bgm", text="Test BGM", icon="PLAY")


class OBJECT_OT_tetris_mode_start(bpy.types.Operator):
    bl_idname = "object.tetris_mode_start"
    bl_label = "Start Tetris Mode"
    bl_description = "Start a modal Tetris mini-game centered on the active mesh object"
    bl_options = set()

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.object is not None and context.object.type == "MESH"

    def invoke(self, context, event):
        global _TETRIS_RUNTIME
        if is_tetris_running():
            self.report({"WARNING"}, "Tetris Mode is already running.")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            self.report({"WARNING"}, "Tetris Mode can only start in Object Mode.")
            return {"CANCELLED"}
        if context.object is None or context.object.type != "MESH":
            self.report({"WARNING"}, "Select an active mesh object such as a Cube before starting Tetris Mode.")
            return {"CANCELLED"}

        source_obj = context.object
        _TETRIS_RUNTIME = TetrisRuntimeState(
            origin=source_obj.location.copy(),
            active_object_name=source_obj.name,
            source_object_name=source_obj.name,
        )
        rt = _TETRIS_RUNTIME
        try:
            hide_source_object_for_game(rt, source_obj)
            safe_remove_collection_by_name(TEMP_COLLECTION_NAME)
            purge_tetris_orphans()
            create_temp_collection(rt, context)
            create_shared_mesh(rt)
            save_viewports(rt, context)
            save_view_states(rt, context)
            set_game_viewports(rt, context)
            focus_viewports_on_board(rt, context)
            init_game_state(rt)
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
            self.report({"ERROR"}, f"Failed to start Tetris Mode: {exc}")
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
            if event.type == "ESC" and event.value == "PRESS":
                cleanup_runtime(context)
                return {"CANCELLED"}
            if rt.game.game_over:
                if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                    cleanup_runtime(context)
                    return {"FINISHED"}
                if event.type == "TIMER":
                    tag_redraw_all(context)
                return {"RUNNING_MODAL"}
            if event.type == "TIMER":
                on_timer(rt, context)
                return {"RUNNING_MODAL"}
            if event.value == "PRESS":
                handled = handle_key(rt, context, event.type)
                if handled:
                    tag_redraw_all(context)
                    return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, f"Tetris Mode stopped after an error: {exc}")
            cleanup_runtime(context)
            return {"CANCELLED"}


class VIEW3D_PT_tetris_mode_panel(bpy.types.Panel):
    bl_label = "Tetris"
    bl_idname = "VIEW3D_PT_tetris_mode_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tetris"

    def draw(self, context):
        layout = self.layout
        running = is_tetris_running()
        layout.label(text="Tetris Mode")
        row = layout.row()
        row.enabled = not running and context.mode == "OBJECT" and context.object is not None and context.object.type == "MESH"
        row.operator(OBJECT_OT_tetris_mode_start.bl_idname, text="Start Tetris Mode", icon="PLAY")
        if running:
            layout.label(text="Already running", icon="INFO")
        prefs = get_addon_preferences(context)
        if prefs is not None and getattr(prefs, "bgm_enabled", True):
            bgm_path = bpy.path.abspath(getattr(prefs, "bgm_filepath", ""))
            if bgm_path:
                layout.label(text=f"BGM: {os.path.basename(bgm_path)}", icon="SPEAKER")
            else:
                layout.label(text="BGM: Not Set", icon="SPEAKER")
        else:
            layout.label(text="BGM: Disabled", icon="SPEAKER")
        layout.separator()
        layout.label(text="Move: A/D or 4/6")
        layout.label(text="Rotate: Q/R or 7/9")
        layout.label(text="Drop: S/Enter or 2")
        layout.label(text="Exit: Esc")


classes = (
    TETRIS_MODE_OT_test_bgm,
    TetrisModeAddonPreferences,
    OBJECT_OT_tetris_mode_start,
    VIEW3D_PT_tetris_mode_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    cleanup_runtime(bpy.context)
    stop_test_bgm()
    safe_remove_collection_by_name(TEMP_COLLECTION_NAME)
    purge_tetris_orphans()
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()
