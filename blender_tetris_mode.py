# SPDX-License-Identifier: MIT
# Blender Tetris Mode - single-file Blender 4.x add-on

bl_info = {
    "name": "Tetris Mode",
    "author": "OpenAI",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Tetris / F3 Search",
    "description": "A modal Tetris mini-game that runs in Object Mode without touching scene data permanently.",
    "category": "Object",
}

import random
import time
from dataclasses import dataclass, field

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d


BOARD_WIDTH = 10
BOARD_HEIGHT = 20
CELL_SIZE = 1.0
TEMP_COLLECTION_NAME = "Tetris_Temporary_Collection"
TEMP_PREFIX = "Tetris_"
TIMER_INTERVAL = 0.03
INITIAL_FALL_INTERVAL = 0.8
SPEEDUP_SECONDS = 30.0
SPEEDUP_FACTOR = 0.9
MIN_FALL_INTERVAL = 0.08
SPAWN_X = BOARD_WIDTH // 2 - 2
SPAWN_Y = BOARD_HEIGHT
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

# Stable 4x4 tetromino definitions.  The piece origin is the lower-left of its
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
    x: int = SPAWN_X
    y: int = SPAWN_Y
    rotation: int = 0


@dataclass
class TetrisGameState:
    board: list = field(default_factory=lambda: [[None for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)])
    current_piece: PieceState | None = None
    next_piece: str | None = None
    hold_piece: str | None = None
    hold_used: bool = False
    bag: list = field(default_factory=list)
    score: int = 0
    start_time: float = 0.0
    last_fall_time: float = 0.0
    game_over: bool = False


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


class OBJECT_OT_tetris_mode_start(bpy.types.Operator):
    bl_idname = "object.tetris_mode_start"
    bl_label = "Start Tetris Mode"
    bl_description = "Start a modal Tetris mini-game centered on the active mesh object"
    bl_options = set()

    _running_instance = None

    def __init__(self, *args, **kwargs):
        self._timer = None
        self._draw_handle = None
        self._viewport_states = []
        self._temp_collection = None
        self._shared_cube_mesh = None
        self._materials = {}
        self._gray_material = None
        self._active_objects = []
        self._fixed_objects = {}
        self._game = None
        self._origin = Vector((0.0, 0.0, 0.0))
        self._active_object_name = None
        self._cleaned = False

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.object is not None and context.object.type == "MESH"

    def invoke(self, context, event):
        if OBJECT_OT_tetris_mode_start._running_instance is not None:
            self.report({"WARNING"}, "Tetris Mode is already running.")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            self.report({"WARNING"}, "Tetris Mode can only start in Object Mode.")
            return {"CANCELLED"}
        if context.object is None or context.object.type != "MESH":
            self.report({"WARNING"}, "Select an active mesh object such as a Cube before starting Tetris Mode.")
            return {"CANCELLED"}

        try:
            OBJECT_OT_tetris_mode_start._running_instance = self
            self._cleaned = False
            self._origin = context.object.location.copy()
            self._active_object_name = context.object.name
            safe_remove_collection_by_name(TEMP_COLLECTION_NAME)
            purge_tetris_orphans()
            self._create_temp_collection(context)
            self._create_shared_mesh_and_materials()
            self._save_viewports(context)
            self._set_game_viewports(context)
            self._init_game_state()
            self._spawn_next_as_current()
            self._create_active_piece_objects()
            self._update_active_piece_objects()
            self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(self._draw_overlay, (context,), "WINDOW", "POST_PIXEL")
            self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)
            context.window_manager.modal_handler_add(self)
            self._tag_redraw_all(context)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to start Tetris Mode: {exc}")
            self.cleanup(context)
            return {"CANCELLED"}

    def modal(self, context, event):
        try:
            if self._consume_undo_redo(event):
                return {"RUNNING_MODAL"}
            if self._consume_view_navigation(event):
                return {"RUNNING_MODAL"}
            if event.type in {"ESC"} and event.value == "PRESS":
                self.cleanup(context)
                return {"CANCELLED"}
            if self._game and self._game.game_over:
                if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                    self.cleanup(context)
                    return {"FINISHED"}
                if event.type == "TIMER":
                    self._tag_redraw_all(context)
                return {"RUNNING_MODAL"}
            if event.type == "TIMER":
                self._on_timer(context)
                return {"RUNNING_MODAL"}
            if event.value == "PRESS":
                handled = self._handle_key(context, event.type)
                if handled:
                    self._tag_redraw_all(context)
                    return {"RUNNING_MODAL"}
            # Tetris Mode intentionally owns input while active, including mouse clicks
            # and unrelated keystrokes, so Blender navigation and editing are disabled.
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, f"Tetris Mode stopped after an error: {exc}")
            self.cleanup(context)
            return {"CANCELLED"}

    def cleanup(self, context):
        if self._cleaned:
            return
        self._cleaned = True
        wm = getattr(context, "window_manager", None)
        if self._timer is not None and wm is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        if self._draw_handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            except Exception:
                pass
            self._draw_handle = None
        self._restore_viewports()
        self._remove_temp_data()
        self._restore_object_mode_and_active(context)
        self._active_objects.clear()
        self._fixed_objects.clear()
        self._materials.clear()
        self._gray_material = None
        self._shared_cube_mesh = None
        self._temp_collection = None
        self._game = None
        if OBJECT_OT_tetris_mode_start._running_instance is self:
            OBJECT_OT_tetris_mode_start._running_instance = None
        self._tag_redraw_all(context)

    def _create_temp_collection(self, context):
        self._temp_collection = bpy.data.collections.new(TEMP_COLLECTION_NAME)
        context.scene.collection.children.link(self._temp_collection)

    def _create_shared_mesh_and_materials(self):
        half = CELL_SIZE * 0.46
        verts = [
            (-half, -half, -half), (half, -half, -half), (half, half, -half), (-half, half, -half),
            (-half, -half, half), (half, -half, half), (half, half, half), (-half, half, half),
        ]
        faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        self._shared_cube_mesh = bpy.data.meshes.new(f"{TEMP_PREFIX}Shared_Cube_Mesh")
        self._shared_cube_mesh.from_pydata(verts, [], faces)
        self._shared_cube_mesh.update()
        for kind, color in PIECE_COLORS.items():
            mat = bpy.data.materials.new(f"{TEMP_PREFIX}Material_{kind}")
            mat.diffuse_color = color
            self._materials[kind] = mat
        self._gray_material = bpy.data.materials.new(f"{TEMP_PREFIX}Material_Game_Over_Gray")
        self._gray_material.diffuse_color = (0.35, 0.35, 0.35, 1.0)

    def _save_viewports(self, context):
        self._viewport_states.clear()
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
                    state = {
                        "space": space,
                        "type": getattr(shading, "type", None),
                        "color_type": getattr(shading, "color_type", None),
                        "wireframe_color_type": getattr(shading, "wireframe_color_type", None) if hasattr(shading, "wireframe_color_type") else None,
                    }
                    self._viewport_states.append(state)

    def _set_game_viewports(self, context):
        for state in self._viewport_states:
            space = state.get("space")
            try:
                space.shading.type = "SOLID"
                space.shading.color_type = "RANDOM"
                if hasattr(space.shading, "wireframe_color_type"):
                    space.shading.wireframe_color_type = "RANDOM"
            except Exception:
                pass
        self._tag_redraw_all(context)

    def _restore_viewports(self):
        for state in self._viewport_states:
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
        self._viewport_states.clear()

    def _init_game_state(self):
        now = time.monotonic()
        self._game = TetrisGameState(start_time=now, last_fall_time=now)
        self._game.bag = make_bag()
        self._game.next_piece = self._draw_from_bag()

    def _draw_from_bag(self):
        if not self._game.bag:
            self._game.bag = make_bag()
        return self._game.bag.pop(0)

    def _spawn_next_as_current(self):
        kind = self._game.next_piece or self._draw_from_bag()
        self._game.next_piece = self._draw_from_bag()
        self._game.current_piece = PieceState(kind=kind)
        self._game.hold_used = False
        if self._collides(self._game.current_piece):
            self._set_game_over()

    def _create_active_piece_objects(self):
        self._delete_active_piece_objects()
        for i in range(4):
            obj = bpy.data.objects.new(f"{TEMP_PREFIX}Active_Block_{i}", self._shared_cube_mesh)
            obj.data = self._shared_cube_mesh
            obj.show_name = False
            self._assign_material(obj, self._game.current_piece.kind)
            self._temp_collection.objects.link(obj)
            self._active_objects.append(obj)

    def _delete_active_piece_objects(self):
        for obj in list(self._active_objects):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                pass
        self._active_objects.clear()

    def _assign_material(self, obj, kind_or_gray):
        mat = self._gray_material if kind_or_gray == "GRAY" else self._materials.get(kind_or_gray)
        if mat is None:
            return
        obj.data = self._shared_cube_mesh
        # Mesh material slots are shared by all block objects because they reuse one
        # cube mesh.  Per-piece display therefore relies on Object.color/random solid
        # colors; the shared temporary material is still useful for Blender data
        # hygiene and game-over greying.
        if not obj.data.materials:
            obj.data.materials.append(mat)
        obj.color = mat.diffuse_color

    def _piece_cells(self, piece):
        return [(piece.x + dx, piece.y + dy) for dx, dy in PIECE_SHAPES[piece.kind][piece.rotation % 4]]

    def _world_from_grid(self, x, y):
        return Vector((
            self._origin.x + (x - (BOARD_WIDTH - 1) / 2.0) * CELL_SIZE,
            self._origin.y,
            self._origin.z + (y - (BOARD_HEIGHT - 1) / 2.0) * CELL_SIZE,
        ))

    def _collides(self, piece):
        for x, y in self._piece_cells(piece):
            if x < 0 or x >= BOARD_WIDTH:
                return True
            if y < 0:
                return True
            if y >= BOARD_HEIGHT:
                continue
            if self._game.board[y][x] is not None:
                return True
        return False

    def _update_active_piece_objects(self):
        piece = self._game.current_piece
        if piece is None:
            return
        cells = self._piece_cells(piece)
        for obj, (x, y) in zip(self._active_objects, cells):
            obj.location = self._world_from_grid(x, y)
            obj.hide_viewport = y < 0
            obj.hide_render = True
            obj.name = f"{TEMP_PREFIX}Active_{piece.kind}_{x}_{y}"
            obj.color = PIECE_COLORS[piece.kind]

    def _handle_key(self, context, key_type):
        if key_type in {"A", "FOUR", "NUMPAD_4"}:
            return self._try_move(-1, 0)
        if key_type in {"D", "SIX", "NUMPAD_6"}:
            return self._try_move(1, 0)
        if key_type in {"S", "TWO", "NUMPAD_2"}:
            if self._try_move(0, -1):
                self._game.score += 1
            else:
                self._lock_current_piece()
            return True
        if key_type in {"Q", "SEVEN", "NUMPAD_7"}:
            return self._try_rotate(-1)
        if key_type in {"R", "NINE", "NUMPAD_9"}:
            return self._try_rotate(1)
        if key_type in {"E", "FIVE", "NUMPAD_5"}:
            self._hold_current_piece()
            return True
        if key_type in {"RET", "NUMPAD_ENTER"}:
            self._hard_drop()
            return True
        return False

    def _try_move(self, dx, dy):
        piece = self._game.current_piece
        candidate = PieceState(piece.kind, piece.x + dx, piece.y + dy, piece.rotation)
        if self._collides(candidate):
            return False
        self._game.current_piece = candidate
        self._update_active_piece_objects()
        return True

    def _try_rotate(self, direction):
        piece = self._game.current_piece
        new_rot = (piece.rotation + direction) % 4
        for kick in (0, -1, 1, -2, 2):
            candidate = PieceState(piece.kind, piece.x + kick, piece.y, new_rot)
            if not self._collides(candidate):
                self._game.current_piece = candidate
                self._update_active_piece_objects()
                return True
        return True

    def _hold_current_piece(self):
        if self._game.hold_used or self._game.current_piece is None:
            return
        current_kind = self._game.current_piece.kind
        if self._game.hold_piece is None:
            self._game.hold_piece = current_kind
            self._spawn_next_as_current()
        else:
            swap_kind = self._game.hold_piece
            self._game.hold_piece = current_kind
            self._game.current_piece = PieceState(kind=swap_kind)
            if self._collides(self._game.current_piece):
                self._set_game_over()
        self._game.hold_used = True
        if not self._game.game_over:
            if len(self._active_objects) != 4:
                self._create_active_piece_objects()
            self._update_active_piece_objects()

    def _hard_drop(self):
        dropped = 0
        while self._try_move(0, -1):
            dropped += 1
        self._game.score += dropped * 2
        self._lock_current_piece()

    def _current_fall_interval(self):
        elapsed = time.monotonic() - self._game.start_time
        steps = int(elapsed // SPEEDUP_SECONDS)
        return max(MIN_FALL_INTERVAL, INITIAL_FALL_INTERVAL * (SPEEDUP_FACTOR ** steps))

    def _on_timer(self, context):
        if self._game is None or self._game.game_over:
            return
        now = time.monotonic()
        if now - self._game.last_fall_time >= self._current_fall_interval():
            self._game.last_fall_time = now
            if not self._try_move(0, -1):
                self._lock_current_piece()
            self._tag_redraw_all(context)

    def _lock_current_piece(self):
        piece = self._game.current_piece
        if piece is None or self._game.game_over:
            return
        cells = self._piece_cells(piece)
        for obj, (x, y) in zip(list(self._active_objects), cells):
            if 0 <= y < BOARD_HEIGHT and 0 <= x < BOARD_WIDTH:
                obj.name = f"{TEMP_PREFIX}Fixed_{piece.kind}_{x}_{y}"
                obj.location = self._world_from_grid(x, y)
                obj.hide_viewport = False
                obj.color = PIECE_COLORS[piece.kind]
                self._fixed_objects[(x, y)] = obj
                self._game.board[y][x] = piece.kind
            else:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except ReferenceError:
                    pass
        self._active_objects.clear()
        cleared = self._clear_lines()
        self._game.score += SCORE_LINE_CLEAR.get(cleared, 0)
        self._spawn_next_as_current()
        if not self._game.game_over:
            self._create_active_piece_objects()
            self._update_active_piece_objects()

    def _clear_lines(self):
        full_rows = [y for y in range(BOARD_HEIGHT) if all(self._game.board[y][x] is not None for x in range(BOARD_WIDTH))]
        if not full_rows:
            return 0
        for y in full_rows:
            for x in range(BOARD_WIDTH):
                obj = self._fixed_objects.pop((x, y), None)
                if obj is not None:
                    try:
                        bpy.data.objects.remove(obj, do_unlink=True)
                    except ReferenceError:
                        pass
        old_board = self._game.board
        old_objects = dict(self._fixed_objects)
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
                        obj.location = self._world_from_grid(x, write_y)
                        obj.name = f"{TEMP_PREFIX}Fixed_{kind}_{x}_{write_y}"
                        new_objects[(x, write_y)] = obj
            write_y += 1
        self._game.board = new_board
        self._fixed_objects = new_objects
        return len(full_rows)

    def _set_game_over(self):
        self._game.game_over = True
        self._delete_active_piece_objects()

    def _draw_overlay(self, context):
        region = context.region
        if region is None or self._game is None:
            return
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        try:
            gpu.state.blend_set("ALPHA")
        except Exception:
            pass
        width = region.width
        height = region.height
        right_x = max(20, width - 175)
        top_y = max(180, height - 45)
        draw_text(f"SCORE {self._game.score}", right_x, top_y, 20, (1, 1, 1, 1))
        draw_text("NEXT", right_x, top_y - 34, 15, (0.9, 0.9, 0.9, 1))
        self._draw_mini_piece(shader, self._game.next_piece, right_x, top_y - 115)
        hold_y = 115
        draw_text("HOLD", right_x, hold_y + 75, 15, (0.9, 0.9, 0.9, 1))
        self._draw_mini_piece(shader, self._game.hold_piece, right_x, hold_y)
        if self._game.game_over:
            draw_rect(shader, 0, 0, width, height, (0.0, 0.0, 0.0, 0.18))
            self._draw_board_gray_overlay(context, shader, width, height)
            draw_text("GAME OVER", width / 2, height / 2 + 22, 46, (1.0, 0.25, 0.2, 1.0), align="CENTER")
            draw_text(f"SCORE {self._game.score}", width / 2, height / 2 - 28, 26, (1.0, 1.0, 1.0, 1.0), align="CENTER")
            draw_text("Press Esc or Enter", width / 2, height / 2 - 62, 16, (0.9, 0.9, 0.9, 1.0), align="CENTER")
        try:
            gpu.state.blend_set("NONE")
        except Exception:
            pass


    def _draw_board_gray_overlay(self, context, shader, region_width, region_height):
        region = context.region
        rv3d = getattr(context.space_data, "region_3d", None) if context.space_data else None
        points = []
        if region is not None and rv3d is not None:
            board_corners = (
                self._world_from_grid(-0.5, -0.5),
                self._world_from_grid(BOARD_WIDTH - 0.5, -0.5),
                self._world_from_grid(BOARD_WIDTH - 0.5, BOARD_HEIGHT - 0.5),
                self._world_from_grid(-0.5, BOARD_HEIGHT - 0.5),
            )
            for corner in board_corners:
                projected = location_3d_to_region_2d(region, rv3d, corner)
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
        draw_rect(
            shader,
            (region_width - fallback_w) * 0.5,
            (region_height - fallback_h) * 0.5,
            fallback_w,
            fallback_h,
            (0.45, 0.45, 0.45, 0.58),
        )

    def _draw_mini_piece(self, shader, kind, x, y):
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

    def _consume_undo_redo(self, event):
        if event.value != "PRESS":
            return False
        if event.ctrl and event.type in {"Z", "Y"}:
            return True
        return False

    def _consume_view_navigation(self, event):
        nav_events = {
            "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
            "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "MOUSEPAN", "MOUSEZOOM",
            "NDOF_MOTION", "NDOF_BUTTON_MENU", "NDOF_BUTTON_FIT", "NDOF_BUTTON_TOP", "NDOF_BUTTON_BOTTOM",
            "NDOF_BUTTON_LEFT", "NDOF_BUTTON_RIGHT", "NDOF_BUTTON_FRONT", "NDOF_BUTTON_BACK",
            "NDOF_BUTTON_ISO1", "NDOF_BUTTON_ISO2", "NDOF_BUTTON_ROLL_CW", "NDOF_BUTTON_ROLL_CCW",
            "NDOF_BUTTON_SPIN_CW", "NDOF_BUTTON_SPIN_CCW", "NDOF_BUTTON_TILT_CW", "NDOF_BUTTON_TILT_CCW",
        }
        return event.type in nav_events

    def _tag_redraw_all(self, context):
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

    def _remove_temp_data(self):
        if self._temp_collection is not None:
            try:
                safe_remove_collection_by_name(self._temp_collection.name)
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

    def _restore_object_mode_and_active(self, context):
        try:
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
        if self._active_object_name:
            obj = bpy.data.objects.get(self._active_object_name)
            if obj is not None:
                try:
                    context.view_layer.objects.active = obj
                    obj.select_set(True)
                except Exception:
                    pass


class VIEW3D_PT_tetris_mode_panel(bpy.types.Panel):
    bl_label = "Tetris"
    bl_idname = "VIEW3D_PT_tetris_mode_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tetris"

    def draw(self, context):
        layout = self.layout
        running = OBJECT_OT_tetris_mode_start._running_instance is not None
        layout.label(text="Tetris Mode")
        row = layout.row()
        row.enabled = not running and context.mode == "OBJECT" and context.object is not None and context.object.type == "MESH"
        row.operator(OBJECT_OT_tetris_mode_start.bl_idname, text="Start Tetris Mode", icon="PLAY")
        if running:
            layout.label(text="Already running", icon="INFO")
        layout.separator()
        layout.label(text="Move: A/D or 4/6")
        layout.label(text="Rotate: Q/R or 7/9")
        layout.label(text="Drop: S/Enter or 2")
        layout.label(text="Hold: E or 5")
        layout.label(text="Exit: Esc")


classes = (
    OBJECT_OT_tetris_mode_start,
    VIEW3D_PT_tetris_mode_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    inst = OBJECT_OT_tetris_mode_start._running_instance
    if inst is not None:
        try:
            inst.cleanup(bpy.context)
        except Exception:
            OBJECT_OT_tetris_mode_start._running_instance = None
    safe_remove_collection_by_name(TEMP_COLLECTION_NAME)
    purge_tetris_orphans()
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()
