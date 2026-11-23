import csv
from tkinter import filedialog, messagebox
from config import PRESET_MAPS, MAX_TILE_CAPACITY
from models import Tile


class LevelEditorMixin:
    def init_editor_grid(self):
        er = max(4, min(18, self.editor_rows_var.get()))
        ec = max(4, min(22, self.editor_cols_var.get()))
        self.editor_rows_var.set(er)
        self.editor_cols_var.set(ec)
        self.editor_grid = [[Tile(r, c) for c in range(ec)] for r in range(er)]
        self.render_editor_canvas()

    def get_editor_geometry(self):
        er = len(self.editor_grid)
        ec = len(self.editor_grid[0]) if er > 0 else 1
        cw = max(100, self.editor_canvas.winfo_width())
        ch = max(100, self.editor_canvas.winfo_height())
        pad = 15
        tile_px = min((cw - 2 * pad) / ec, (ch - 2 * pad) / er)
        return (cw - tile_px * ec) / 2, (ch - tile_px * er) / 2, tile_px

    def on_editor_canvas_paint(self, event):
        if not self.editor_grid:
            return
        ox, oy, tpx = self.get_editor_geometry()
        c, r = int((event.x - ox) // tpx), int((event.y - oy) // tpx)
        er, ec = len(self.editor_grid), len(self.editor_grid[0])
        if not (0 <= r < er and 0 <= c < ec):
            return

        tile = self.editor_grid[r][c]
        brush = self.editor_brush_var.get()

        if brush == "Obstacle (X)":
            tile.is_obstacle = True
            tile.terrain_type = "normal"
            tile.owner = 0
            tile.set_units(0)
        elif brush == "Neutral (.)":
            tile.is_obstacle = False
            tile.terrain_type = "normal"
            tile.owner = 0
            tile.set_units(0)
        elif brush.startswith("Player"):
            tile.is_obstacle = False
            pid = int(brush.split()[1])
            tile.owner = pid
            tile.set_units(self.editor_unit_val_var.get())
        else:
            # Terrain brushes preserve any existing player owner/units on the tile
            tile.is_obstacle = False
            terrain_lookup = {
                "Fortress (#)": "fortress",
                "Factory (^)": "factory",
                "Flag Base (F)": "flag",
                "Hill Monolith (*)": "hill",
                "VIP Commander (@)": "commander",
                "Relic Payload ($)": "relic",
                "Beacon Node (+)": "beacon",
            }
            if brush in terrain_lookup:
                tile.terrain_type = terrain_lookup[brush]

        self.render_editor_canvas()

    def render_editor_canvas(self):
        if not self.editor_canvas:
            return
        self.editor_canvas.delete("all")
        if not self.editor_grid:
            return
        er, ec = len(self.editor_grid), len(self.editor_grid[0])
        ox, oy, tpx = self.get_editor_geometry()
        obs_bg = self.get_obstacle_bg_tint()

        for r in range(er):
            for c in range(ec):
                tile = self.editor_grid[r][c]
                x1, y1 = ox + c * tpx, oy + r * tpx
                x2, y2 = x1 + tpx, y1 + tpx

                bg = obs_bg if tile.is_obstacle else self.get_player_bg_tint(tile.owner)
                border = self.obstacle_color if tile.is_obstacle else ("#ffff55" if self.use_chunky_pixels else "#3d4a55")
                bw = 2 if tile.is_obstacle else 1

                self.editor_canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline=border, width=bw)

                if tile.is_obstacle:
                    self.editor_canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="X", fill=self.obstacle_color, font=(self.font_family, max(10, int(tpx * 0.45)), "bold"))
                    continue

                icon_map = {
                    "fortress": ("#", "#00ffff"),
                    "factory": ("^", "#f1c40f"),
                    "flag": ("F", "#ff55ff"),
                    "hill": ("*", "#ffaa00"),
                    "commander": ("@", "#ff2222"),
                    "relic": ("$", "#55ff55"),
                    "beacon": ("+", "#55ffff")
                }
                if tile.terrain_type in icon_map:
                    sym, col = icon_map[tile.terrain_type]
                    if tile.terrain_type == "flag" and tile.owner in self.player_colors:
                        col = self.player_colors[tile.owner]
                    self.editor_canvas.create_text((x1 + x2) / 2, y1 + tpx * 0.25, text=sym, fill=col, font=(self.font_family, max(10, int(tpx * 0.28)), "bold"))

                if tile.units > 0 or tile.owner != 0:
                    tc = self.player_colors.get(tile.owner, "#ffffff")
                    self.editor_canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2 + tpx * 0.12, text=f"P{tile.owner}:{tile.units}", fill=tc, font=(self.font_family, max(8, int(tpx * 0.24)), "bold"))

    def _apply_cell_token(self, tile, token):
        """Parses map cell tokens like 'X', '#', 'F', 'P1', 'P1:20', 'P2F:15', 'P1@'."""
        val = token.strip()
        if not val or val == ".":
            return

        symbol_to_terrain = {
            "#": "fortress",
            "^": "factory",
            "F": "flag",
            "*": "hill",
            "@": "commander",
            "$": "relic",
            "+": "beacon",
        }

        if val == "X":
            tile.is_obstacle = True
            return

        if val in symbol_to_terrain:
            tile.terrain_type = symbol_to_terrain[val]
            return

        if val.startswith("P") and len(val) >= 2 and val[1].isdigit():
            pid = max(1, min(4, int(val[1])))
            tile.owner = pid
            units = self.editor_unit_val_var.get()

            rest = val[2:]
            if ":" in rest:
                terr_part, unit_part = rest.split(":", 1)
                if unit_part.isdigit():
                    units = max(0, min(MAX_TILE_CAPACITY, int(unit_part)))
            else:
                terr_part = rest

            if terr_part in symbol_to_terrain:
                tile.terrain_type = symbol_to_terrain[terr_part]

            tile.set_units(units)

    def load_preset_into_editor(self):
        preset_name = self.preset_map_var.get()
        layout = PRESET_MAPS.get(preset_name)
        if not layout:
            return
        rows = len(layout)
        cols = len(layout[0].split())
        self.editor_rows_var.set(rows)
        self.editor_cols_var.set(cols)
        self.editor_grid = [[Tile(r, c) for c in range(cols)] for r in range(rows)]

        for r in range(rows):
            tokens = layout[r].split()
            for c in range(min(cols, len(tokens))):
                self._apply_cell_token(self.editor_grid[r][c], tokens[c])

        self.play_sound("click_ui")
        self.render_editor_canvas()

    def play_editor_map(self):
        if not self.editor_grid:
            return
        if self.match_event_log:
            self.save_match_log_to_disk(winner="Reset/Interrupted")
        self.match_event_log.clear()

        er, ec = len(self.editor_grid), len(self.editor_grid[0])
        self.grid_rows_var.set(er)
        self.grid_cols_var.set(ec)
        self.rows, self.cols = er, ec

        max_owner_on_map = max(
            (self.editor_grid[r][c].owner for r in range(er) for c in range(ec)),
            default=2
        )
        self.num_players = max(2, min(4, max(self.num_players_var.get(), max_owner_on_map)))
        self.num_players_var.set(self.num_players)

        self.grid = [[Tile(r, c) for c in range(ec)] for r in range(er)]
        self.flag_home_coords = {}
        self.hill_hold_timers = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        self.player_tickets = {1: 100, 2: 100, 3: 100, 4: 100}

        for r in range(er):
            for c in range(ec):
                src = self.editor_grid[r][c]
                dst = self.grid[r][c]
                dst.is_obstacle = src.is_obstacle
                dst.terrain_type = src.terrain_type
                dst.owner = src.owner
                dst.set_units(src.units)
                if dst.terrain_type == "flag" and dst.owner > 0:
                    dst.flag_owner = dst.owner
                    self.flag_home_coords[dst.owner] = (r, c)

        self.moving_groups.clear()
        self.combat_effects.clear()
        self.selected_tile = None
        self.valid_targets.clear()
        self.set_pause_state(False)
        self.current_turn_player = 1
        self.turn_time_left = float(max(5.0, min(15.0, self.turn_duration_var.get())))
        self.match_elapsed_seconds = 0.0
        self.ai_acted_this_turn = False
        self.ai_action_timer = 0.0
        self.game_running = True
        self.apply_theme_selection()
        self.update_scoreboard()
        self.log_match_event("GAME_START", {"rows": er, "cols": ec, "players": self.num_players, "victory_mode": self.victory_mode_var.get(), "source": "editor"})
        if self.notebook:
            self.notebook.select(self.tab_game)

    def save_map_to_csv(self):
        if not self.editor_grid:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return
        terrain_to_symbol = {
            "fortress": "#",
            "factory": "^",
            "flag": "F",
            "hill": "*",
            "commander": "@",
            "relic": "$",
            "beacon": "+",
        }
        try:
            er, ec = len(self.editor_grid), len(self.editor_grid[0])
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for r in range(er):
                    row_data = []
                    for c in range(ec):
                        tile = self.editor_grid[r][c]
                        if tile.is_obstacle:
                            code = "X"
                        elif tile.owner > 0:
                            sym = terrain_to_symbol.get(tile.terrain_type, "")
                            code = f"P{tile.owner}{sym}:{tile.units}"
                        else:
                            code = terrain_to_symbol.get(tile.terrain_type, ".")
                        row_data.append(code)
                    writer.writerow(row_data)
            messagebox.showinfo("Success", f"Custom map saved to {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save map: {e}")

    def load_map_from_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = [row for row in csv.reader(f) if any(cell.strip() for cell in row)]
                rows = len(reader)
                cols = max((len(row) for row in reader), default=0)
                if rows < 4 or cols < 4 or rows > 18 or cols > 22:
                    messagebox.showerror("Error", "Invalid map dimensions (must be 4x4 to 18x22).")
                    return
                self.editor_rows_var.set(rows)
                self.editor_cols_var.set(cols)
                self.editor_grid = [[Tile(r, c) for c in range(cols)] for r in range(rows)]
                for r in range(rows):
                    for c in range(len(reader[r])):
                        self._apply_cell_token(self.editor_grid[r][c], reader[r][c])
            self.render_editor_canvas()
            messagebox.showinfo("Success", "CSV loaded into Level Editor!")
        except Exception as e:
            messagebox.showerror("Error", f"Could not load map: {e}")