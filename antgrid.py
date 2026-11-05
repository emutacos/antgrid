import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, filedialog
import random
import threading
import json
import csv
import pickle
import platform
import time
from datetime import datetime
from collections import deque

try:
    import winsound
except ImportError:
    winsound = None

from config import (
    MAX_TILE_CAPACITY, LOGICAL_TILE_SIZE, THEMES, BGM_PATTERNS, PRESET_MAPS,
    AI_PERSONALITIES, blend_hex, load_ini_settings, save_ini_settings
)
from models import MovingGroup, CombatEffect, Tile
from editor import LevelEditorMixin
from network import NetworkMixin
from ai import AIMixin


class AntGridApp(LevelEditorMixin, NetworkMixin, AIMixin):
    def __init__(self, root):
        self.root = root
        self.root.title("antgrid_v_0.9")
        self.root.geometry("1380x880")

        cfg = load_ini_settings()

        # --- SETTINGS VARIABLES (Loaded from settings.ini) ---
        self.grid_rows_var = tk.IntVar(value=cfg.getint("GameRules", "grid_rows", fallback=8))
        self.grid_cols_var = tk.IntVar(value=cfg.getint("GameRules", "grid_cols", fallback=10))
        self.num_players_var = tk.IntVar(value=max(2, min(4, cfg.getint("GameRules", "num_players", fallback=2))))
        self.game_mode_var = tk.StringVar(value=cfg.get("GameRules", "game_mode", fallback="Single Player (vs AI)"))
        self.ai_difficulty_var = tk.StringVar(value=cfg.get("GameRules", "ai_difficulty", fallback="Medium"))
        self.ai_personality_var = tk.StringVar(value=cfg.get("GameRules", "ai_personality", fallback=AI_PERSONALITIES[0]))
        self.victory_mode_var = tk.StringVar(value=cfg.get("GameRules", "victory_mode", fallback="Total Supremacy"))
        self.start_tiles_var = tk.IntVar(value=cfg.getint("GameRules", "start_tiles", fallback=2))
        self.start_units_var = tk.IntVar(value=cfg.getint("GameRules", "start_units", fallback=15))
        self.num_obstacles_var = tk.IntVar(value=cfg.getint("GameRules", "num_obstacles", fallback=8))
        self.turn_duration_var = tk.DoubleVar(value=cfg.getfloat("GameRules", "turn_duration", fallback=7.0))
        self.unit_speed_var = tk.DoubleVar(value=cfg.getfloat("GameRules", "unit_speed", fallback=3.0))
        self.max_move_distance_var = tk.IntVar(value=cfg.getint("GameRules", "max_move_distance", fallback=3))
        self.movement_rule_var = tk.StringVar(value=cfg.get("GameRules", "movement_rule", fallback="Fixed Configurable Distance"))
        self.allow_diagonal_var = tk.BooleanVar(value=cfg.getboolean("GameRules", "allow_diagonal", fallback=True))
        self.fog_of_war_var = tk.BooleanVar(value=cfg.getboolean("GameRules", "fog_of_war", fallback=False))
        self.combat_pause_var = tk.DoubleVar(value=cfg.getfloat("GameRules", "combat_pause_duration", fallback=0.6))

        self.theme_var = tk.StringVar(value=cfg.get("Visuals", "theme", fallback="MS-DOS 90s Retro"))
        self.bgm_track_var = tk.StringVar(value=cfg.get("Visuals", "bgm_track", fallback="Energetic Pulse"))

        # Custom Theme Editor Vars
        self.custom_font_var = tk.StringVar(value=cfg.get("Visuals", "custom_font", fallback="Courier New"))
        self.custom_chunky_var = tk.BooleanVar(value=cfg.getboolean("Visuals", "custom_chunky", fallback=True))
        self.custom_bg_var = tk.StringVar(value=cfg.get("Visuals", "custom_bg", fallback="#0000aa"))
        self.custom_neutral_var = tk.StringVar(value=cfg.get("Visuals", "custom_neutral", fallback="#000055"))
        self.custom_fg_var = tk.StringVar(value=cfg.get("Visuals", "custom_fg", fallback="#ffff55"))

        # Custom Player Colors override dict (1 to 4)
        self.custom_player_colors = {}
        for p in range(1, 5):
            col_val = cfg.get("PlayerColors", f"player_{p}", fallback="").strip()
            if col_val.startswith("#"):
                self.custom_player_colors[p] = col_val

        self.player_color_Setting_Frame = None
        self.num_players_var.trace_add("write", lambda *args: self.refresh_player_color_pickers())

        # Sound Pitch Config Vars
        self.snd_dispatch_freq = tk.IntVar(value=cfg.getint("Sound", "dispatch_freq", fallback=950))
        self.snd_dispatch_dur = tk.IntVar(value=cfg.getint("Sound", "dispatch_dur", fallback=50))
        self.snd_combat_freq = tk.IntVar(value=cfg.getint("Sound", "combat_freq", fallback=220))
        self.snd_combat_dur = tk.IntVar(value=cfg.getint("Sound", "combat_dur", fallback=90))
        self.snd_own_click_freq = tk.IntVar(value=cfg.getint("Sound", "own_click_freq", fallback=600))
        self.snd_neut_click_freq = tk.IntVar(value=cfg.getint("Sound", "neut_click_freq", fallback=440))
        self.snd_enemy_click_freq = tk.IntVar(value=cfg.getint("Sound", "enemy_click_freq", fallback=180))

        # Network Config
        self.net_role = "local"
        self.my_player_id = 1
        self.server_socket = None
        self.client_socket = None
        self.client_connections = []
        self.server_ip_var = tk.StringVar(value=cfg.get("Network", "server_ip", fallback="127.0.0.1"))
        self.server_port_var = tk.IntVar(value=cfg.getint("Network", "server_port", fallback=5555))
        self.discovered_servers = []

        # Dedicated Map Editor State
        self.editor_rows_var = tk.IntVar(value=self.grid_rows_var.get())
        self.editor_cols_var = tk.IntVar(value=self.grid_cols_var.get())
        self.editor_brush_var = tk.StringVar(value="Obstacle (X)")
        self.editor_unit_val_var = tk.IntVar(value=15)
        self.preset_map_var = tk.StringVar(value="Crossfire (2-4P)")
        self.editor_grid = []

        self.load_theme_colors()
        self.root.configure(bg=self.board_bg_color)

        # Runtime Battlefield State
        self.rows, self.cols, self.num_players = 8, 10, 2
        self.grid = []
        self.moving_groups = []
        self.combat_effects = []
        self.game_running = False
        self.is_paused = False
        self.current_turn_player = 1
        self.turn_time_left = 7.0
        self.match_elapsed_seconds = 0.0
        self.selected_tile = None
        self.valid_targets = {}
        self.ai_acted_this_turn = False
        self.ai_action_timer = 0.0
        self.lan_votes = {}
        self.match_event_log = []

        self.hill_hold_timers = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        self.player_tickets = {1: 100, 2: 100, 3: 100, 4: 100}

        # UI Widgets Placeholders
        self.notebook = None
        self.tab_game = None
        self.tab_editor = None
        self.tab_manual = None
        self.tab_customizer = None
        self.tab_settings = None
        self.tab_network = None
        self.lbl_match_timer = None
        self.lbl_turn_indicator = None
        self.lbl_timer = None
        self.turn_bar_canvas = None
        self.btn_end_turn = None
        self.btn_pause = None
        self.canvas = None
        self.editor_canvas = None
        self.lbl_selected_info = None
        self.slider_units = None
        self.lbl_range_hint = None
        self.stats_frame = None
        self.player_stat_labels = {}
        self.lbl_manual = None
        self.server_listbox = None
        self.lbl_net_connection_status = None

        self._build_ui()
        self.init_editor_grid()
        self.start_new_game()

        self.last_tick_ms = 33
        self.root.after(self.last_tick_ms, self.game_loop)
        threading.Thread(target=self._bgm_playback_loop, daemon=True).start()

    # --- SOUND & BGM LOOP ---
    def play_sound(self, sound_type):
        if not winsound or platform.system() != "Windows":
            return
        def _beep_worker():
            try:
                if sound_type == "dispatch":
                    f, d = self.snd_dispatch_freq.get(), self.snd_dispatch_dur.get()
                    winsound.Beep(f, d)
                    winsound.Beep(min(3200, int(f * 1.25)), max(20, int(d * 0.6)))
                elif sound_type == "combat":
                    winsound.Beep(self.snd_combat_freq.get(), self.snd_combat_dur.get())
                elif sound_type == "victory":
                    for freq in [523, 659, 784, 1046]:
                        winsound.Beep(freq, 95)
                elif sound_type == "click_own":
                    winsound.Beep(self.snd_own_click_freq.get(), 35)
                elif sound_type == "click_neutral":
                    winsound.Beep(self.snd_neut_click_freq.get(), 35)
                elif sound_type == "click_enemy":
                    winsound.Beep(self.snd_enemy_click_freq.get(), 55)
                elif sound_type == "click_ui":
                    winsound.Beep(700, 20)
            except Exception:
                pass
        threading.Thread(target=_beep_worker, daemon=True).start()

    def _bgm_playback_loop(self):
        note_idx = 0
        while True:
            track_name = self.bgm_track_var.get()
            pattern = BGM_PATTERNS.get(track_name, [])
            if pattern and self.game_running and not self.is_paused and winsound and platform.system() == "Windows":
                try:
                    freq, dur = pattern[note_idx % len(pattern)]
                    winsound.Beep(freq, dur)
                    note_idx += 1
                    time.sleep(0.35)
                except Exception:
                    time.sleep(0.5)
            else:
                time.sleep(0.5)

    # --- LOGGING & EVENT METHODS ---
    def log_match_event(self, event_type, details):
        self.match_event_log.append({
            "timestamp": datetime.now().isoformat(),
            "match_elapsed_seconds": round(self.match_elapsed_seconds, 2),
            "turn": self.current_turn_player,
            "event_type": event_type,
            "details": details
        })

    def save_match_log_to_disk(self, winner=None):
        if not self.match_event_log:
            return
        try:
            filename = f"antgrid_training_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump({"winner": winner, "events": self.match_event_log}, f, indent=2)
        except Exception:
            pass

    # --- THEME & COLOR CUSTOMIZATION ---
    def load_theme_colors(self):
        theme_name = self.theme_var.get()
        if theme_name == "Custom Theme":
            self.board_bg_color = self.custom_bg_var.get()
            self.neutral_tile_bg = self.custom_neutral_var.get()
            self.foreground_color = self.custom_fg_var.get()
            self.font_family = self.custom_font_var.get()
            self.use_chunky_pixels = self.custom_chunky_var.get()
            self.obstacle_color = "#e056fd"
            self.obstacle_bg = blend_hex(self.board_bg_color, "#000000", 0.5)
            self.player_colors = {0: "#aaaaaa", 1: "#55ffff", 2: "#ff5555", 3: "#55ff55", 4: "#ffff55"}
        else:
            theme = THEMES.get(theme_name, THEMES["MS-DOS 90s Retro"])
            self.player_colors = theme["player_colors"].copy()
            self.board_bg_color = theme["board_bg"]
            self.neutral_tile_bg = theme["neutral_bg"]
            self.foreground_color = theme["foreground"]
            self.obstacle_color = theme["obstacle_color"]
            self.obstacle_bg = theme["obstacle_bg"]
            self.font_family = theme["font_family"]
            self.use_chunky_pixels = theme["use_chunky_pixels"]

        for p, col in self.custom_player_colors.items():
            if p in self.player_colors and col:
                self.player_colors[p] = col

    def apply_theme_selection(self):
        self.load_theme_colors()
        self.root.configure(bg=self.board_bg_color)
        if self.canvas:
            self.canvas.config(bg=self.board_bg_color)
        if self.editor_canvas:
            self.editor_canvas.config(bg=self.board_bg_color)
        self.style.configure("TNotebook", background=self.board_bg_color)
        self.style.configure("TNotebook.Tab", font=(self.font_family, 10, "bold"))
        self.style.configure("TFrame", background=self.board_bg_color)
        self.style.configure("TLabel", background=self.board_bg_color, foreground=self.foreground_color, font=(self.font_family, 9))
        self.style.configure("Header.TLabel", font=(self.font_family, 11, "bold"), foreground=self.foreground_color)
        self.style.configure("TCheckbutton", background=self.board_bg_color, foreground=self.foreground_color, font=(self.font_family, 9, "bold"))
        self.style.configure("TRadiobutton", background=self.board_bg_color, foreground=self.foreground_color, font=(self.font_family, 9, "bold"))
        if self.slider_units:
            self.slider_units.config(bg=self.board_bg_color, fg=self.foreground_color)
        if self.lbl_manual:
            self.lbl_manual.config(bg=self.board_bg_color, fg=self.foreground_color, font=(self.font_family, 8))
        for p in range(1, 5):
            if p in self.player_stat_labels:
                self.player_stat_labels[p].config(bg=self.get_player_bg_tint(p), fg=self.player_colors[p], font=(self.font_family, 9, "bold"))
        self.refresh_player_color_pickers()
        self.update_turn_banner()
        self.render_canvas()
        self.render_editor_canvas()

    def pick_custom_color(self, var_obj):
        color = colorchooser.askcolor(title="Choose Color")[1]
        if color:
            var_obj.set(color)

    def pick_player_color(self, player_id):
        initial = self.player_colors.get(player_id, "#ffffff")
        color = colorchooser.askcolor(color=initial, title=f"Choose Player {player_id} Color")[1]
        if color:
            self.custom_player_colors[player_id] = color
            self.player_colors[player_id] = color
            self.refresh_player_color_pickers()
            self.apply_theme_selection()

    def refresh_player_color_pickers(self):
        if not self.player_color_Setting_Frame:
            return
        for widget in self.player_color_Setting_Frame.winfo_children():
            widget.destroy()

        try:
            count = max(2, min(4, int(self.num_players_var.get())))
        except Exception:
            count = 2

        for p in range(1, count + 1):
            row_f = ttk.Frame(self.player_color_Setting_Frame)
            row_f.pack(fill=tk.X, pady=2)
            ttk.Label(row_f, text=f"Player {p} Color:", font=(self.font_family, 9, "bold"), width=15).pack(side=tk.LEFT)
            cur_col = self.player_colors.get(p, "#ffffff")
            btn = tk.Button(
                row_f, text=cur_col, bg=cur_col,
                fg="#000000" if self.use_chunky_pixels else "#ffffff",
                font=(self.font_family, 8, "bold"), width=12,
                command=lambda pid=p: self.pick_player_color(pid)
            )
            btn.pack(side=tk.LEFT, padx=6)

    def get_player_bg_tint(self, owner: int) -> str:
        if owner == 0:
            return self.neutral_tile_bg
        return blend_hex(self.player_colors.get(owner, "#ffffff"), self.board_bg_color, 0.35)

    def get_obstacle_bg_tint(self) -> str:
        return self.obstacle_bg

    def save_current_settings_to_ini(self):
        try:
            save_ini_settings(self)
            self.play_sound("click_ui")
            messagebox.showinfo("Settings Saved", "All current rules, AI profiles, and colors have been saved to settings.ini!")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save settings.ini: {e}")

    # --- CSV SAVE & LOAD FUNCTIONALITY ---
    def save_game_csv(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Save Files", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["#ANTGRID_SAVE", self.rows, self.cols, self.current_turn_player, self.match_elapsed_seconds, self.victory_mode_var.get()])
                for r in range(self.rows):
                    for c in range(self.cols):
                        t = self.grid[r][c]
                        writer.writerow([r, c, t.owner, t.units, int(t.is_obstacle), t.terrain_type])
            messagebox.showinfo("Success", f"Game successfully saved to {file_path}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save game: {e}")

    def load_game_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Save Files", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
                if not reader or not reader[0][0].startswith("#ANTGRID_SAVE"):
                    messagebox.showerror("Error", "Invalid save file format.")
                    return
                _, r_cnt, c_cnt, turn_p, elapsed, vmode = reader[0]
                self.rows, self.cols = int(r_cnt), int(c_cnt)
                self.current_turn_player = int(turn_p)
                self.match_elapsed_seconds = float(elapsed)
                self.victory_mode_var.set(vmode)

                self.grid = [[Tile(r, c) for c in range(self.cols)] for r in range(self.rows)]
                for row in reader[1:]:
                    if len(row) < 6:
                        continue
                    r, c, own, units, obs, terr = int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]), row[5]
                    tile = self.grid[r][c]
                    tile.owner = own
                    tile.set_units(units)
                    tile.is_obstacle = bool(obs)
                    tile.terrain_type = terr

                self.moving_groups.clear()
                self.combat_effects.clear()
                self.selected_tile = None
                self.valid_targets.clear()
                self.game_running = True
                self.is_paused = False
                self.update_turn_banner()
                self.update_scoreboard()
                self.render_canvas()
                if self.notebook:
                    self.notebook.select(self.tab_game)
                messagebox.showinfo("Success", "Game loaded successfully!")
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load game: {e}")

    # --- GAME LIFECYCLE & TURN MANAGEMENT ---
    def start_new_game(self):
        if self.match_event_log:
            self.save_match_log_to_disk(winner="Reset/Interrupted")
        self.match_event_log.clear()
        self.match_elapsed_seconds = 0.0

        rows = max(4, min(18, self.grid_rows_var.get()))
        cols = max(4, min(22, self.grid_cols_var.get()))
        num_players = max(2, min(4, self.num_players_var.get()))
        start_tiles = max(1, self.start_tiles_var.get())
        start_units = max(1, min(MAX_TILE_CAPACITY, self.start_units_var.get()))
        num_obstacles = max(0, self.num_obstacles_var.get())

        self.rows, self.cols, self.num_players = rows, cols, num_players
        self.grid = [[Tile(r, c) for c in range(cols)] for r in range(rows)]
        self.moving_groups.clear()
        self.combat_effects.clear()
        self.selected_tile = None
        self.valid_targets.clear()
        self.set_pause_state(False)

        self.hill_hold_timers = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        self.player_tickets = {1: 100, 2: 100, 3: 100, 4: 100}

        all_coords = [(r, c) for r in range(rows) for c in range(cols)]
        random.shuffle(all_coords)

        if num_players * start_tiles > len(all_coords):
            start_tiles = max(1, len(all_coords) // num_players)

        coord_idx = 0
        player_owned_tiles = {p: [] for p in range(1, num_players + 1)}
        for p in range(1, num_players + 1):
            for _ in range(start_tiles):
                r, c = all_coords[coord_idx]
                coord_idx += 1
                tile = self.grid[r][c]
                tile.owner = p
                tile.set_units(start_units)
                player_owned_tiles[p].append(tile)

        remaining_coords = all_coords[coord_idx:]
        actual_obstacles = min(num_obstacles, len(remaining_coords))
        for i in range(actual_obstacles):
            r, c = remaining_coords[i]
            self.grid[r][c].is_obstacle = True

        remaining_neutral = [self.grid[r][c] for r, c in remaining_coords[actual_obstacles:] if not self.grid[r][c].is_obstacle]
        random.shuffle(remaining_neutral)

        vmode = self.victory_mode_var.get()
        if "Capture the Flag" in vmode:
            for p in range(1, num_players + 1):
                if player_owned_tiles[p]:
                    player_owned_tiles[p][0].terrain_type = "flag"
        elif "King of the Hill" in vmode:
            if remaining_neutral:
                center_tile = self.grid[rows // 2][cols // 2]
                center_tile.terrain_type = "hill"
        elif "VIP Commander" in vmode:
            for p in range(1, num_players + 1):
                if player_owned_tiles[p]:
                    player_owned_tiles[p][0].terrain_type = "commander"
        elif "Relic Extraction" in vmode:
            if remaining_neutral:
                remaining_neutral[0].terrain_type = "relic"
        elif "Domination" in vmode:
            for i in range(min(3, len(remaining_neutral))):
                remaining_neutral[i].terrain_type = "beacon"

        num_special = min(len(remaining_neutral), max(2, (rows * cols) // 12))
        for i in range(num_special):
            if remaining_neutral[i].terrain_type == "normal":
                remaining_neutral[i].terrain_type = "fortress" if i % 2 == 0 else "factory"

        self.current_turn_player = 1
        self.turn_time_left = float(max(5.0, min(15.0, self.turn_duration_var.get())))
        self.game_running = True
        self.ai_acted_this_turn = False
        self.ai_action_timer = 0.0
        self.apply_theme_selection()
        self.update_scoreboard()
        self.log_match_event("GAME_START", {"rows": rows, "cols": cols, "players": num_players, "victory_mode": vmode})

    def advance_turn(self):
        if not self.game_running or self.is_paused or self.net_role == "client":
            return
        next_p = self.current_turn_player
        for _ in range(self.num_players):
            next_p = (next_p % self.num_players) + 1
            if next_p == 1:
                self.distribute_reinforcements()
            if self.player_is_alive(next_p):
                break
        self.current_turn_player = next_p
        self.turn_time_left = float(max(5.0, min(15.0, self.turn_duration_var.get())))
        self.selected_tile = None
        self.valid_targets.clear()
        if self.lbl_selected_info:
            self.lbl_selected_info.config(text="Selected Territory: None")
        self.ai_action_timer = 0.0
        self.update_turn_banner()
        if self.net_role == "server":
            self.broadcast_game_state()

    def request_pause_toggle(self):
        if not self.game_running:
            return
        target_pause_state = not self.is_paused
        self.play_sound("click_own")
        if self.net_role == "local":
            self.set_pause_state(target_pause_state)
        elif self.net_role == "server":
            data = pickle.dumps({"type": "PAUSE_VOTE_REQUEST", "target_pause": target_pause_state})
            for conn, _ in self.client_connections:
                try:
                    conn.sendall(data)
                except Exception:
                    pass
        elif self.net_role == "client":
            messagebox.showinfo("LAN Vote", "Only the host can initiate a LAN pause.")

    def set_pause_state(self, paused: bool):
        self.is_paused = paused
        if self.btn_pause:
            self.btn_pause.config(text="Resume" if paused else "Pause", bg="#27ae60" if paused else "#e67e22")
        if paused:
            self.selected_tile = None
            self.valid_targets.clear()
        self.render_canvas()
        if self.net_role == "server":
            self.broadcast_game_state()

    def is_human_turn(self) -> bool:
        if self.net_role != "local":
            return self.current_turn_player == self.my_player_id
        mode = self.game_mode_var.get()
        if mode == "Single Player (vs AI)":
            return self.current_turn_player == 1
        return True

    def on_canvas_click(self, event):
        if not self.game_running or self.is_paused:
            return

        r, c = self.pixel_to_grid(event.x, event.y)
        if r is None or c is None:
            return

        if self.net_role != "local":
            local_p = self.my_player_id
        elif self.game_mode_var.get() == "Single Player (vs AI)":
            local_p = 1
        else:
            local_p = self.current_turn_player

        clicked_tile = self.grid[r][c]

        if clicked_tile.owner == local_p:
            self.play_sound("click_own")
        elif clicked_tile.owner == 0:
            self.play_sound("click_neutral")
        else:
            self.play_sound("click_enemy")

        if not self.is_human_turn():
            self.selected_tile = None
            self.valid_targets.clear()
            if self.lbl_selected_info:
                self.lbl_selected_info.config(text=f"Wait for Player {self.current_turn_player}'s turn!")
            self.render_canvas()
            return

        if not self.is_tile_visible_in_fog(r, c, local_p):
            return

        if self.selected_tile and (r, c) in self.valid_targets:
            send_count = min(self.units_to_send_var.get(), self.selected_tile.units)
            if send_count > 0:
                path = self.valid_targets[(r, c)]
                if self.net_role == "client":
                    self.send_packet_to_server({
                        "type": "DISPATCH", "player_id": self.my_player_id,
                        "source": (self.selected_tile.r, self.selected_tile.c),
                        "count": send_count, "path": path
                    })
                else:
                    self.dispatch_units(self.selected_tile, send_count, path)
                    if self.net_role == "server":
                        self.broadcast_game_state()
                self.selected_tile = None
                self.valid_targets.clear()
                if self.lbl_selected_info:
                    self.lbl_selected_info.config(text="Selected Territory: None")
                self.render_canvas()
                return

        if clicked_tile.owner == local_p and clicked_tile.units > 0:
            self.selected_tile = clicked_tile
            if self.slider_units:
                self.slider_units.config(to=max(1, clicked_tile.units))
            self.units_to_send_var.set(max(1, clicked_tile.units // 2))
            if self.lbl_selected_info:
                self.lbl_selected_info.config(text=f"Selected ({r},{c}) | Units: {clicked_tile.units}")
            self.on_unit_slider_change()
            self.render_canvas()
        else:
            self.selected_tile = None
            self.valid_targets.clear()
            if self.lbl_selected_info:
                self.lbl_selected_info.config(text="Selected Territory: None")
            self.render_canvas()

    def on_unit_slider_change(self, _=None):
        if self.selected_tile and not self.is_paused and self.is_human_turn():
            send_count = min(self.units_to_send_var.get(), self.selected_tile.units)
            self.valid_targets = self.compute_reachable_tiles(self.selected_tile, send_count, self.selected_tile.owner)
            if self.lbl_range_hint:
                self.lbl_range_hint.config(text=f"Send {send_count} (Max {self.get_max_steps_allowed(send_count)}t)")

    def set_slider_ratio(self, ratio):
        if not self.selected_tile or self.selected_tile.units <= 0 or self.is_paused or not self.is_human_turn():
            return
        val = 1 if ratio == 0 else max(1, int(round(self.selected_tile.units * ratio)))
        self.units_to_send_var.set(val)
        self.on_unit_slider_change()

    # --- UI BUILDER ---
    def _build_ui(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Game", command=self.start_new_game)
        file_menu.add_separator()
        file_menu.add_command(label="Save Game (CSV)...", command=self.save_game_csv)
        file_menu.add_command(label="Load Game (CSV)...", command=self.load_game_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Save Defaults to settings.ini", command=self.save_current_settings_to_ini)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TNotebook", background=self.board_bg_color, borderwidth=0, tabposition="n")
        self.style.configure("TNotebook.Tab", padding=[16, 6], font=(self.font_family, 10, "bold"), anchor="center")
        self.style.map("TNotebook.Tab", background=[("selected", self.board_bg_color), ("active", "#34495e")])
        self.style.configure("TFrame", background=self.board_bg_color)
        self.style.configure("TLabel", background=self.board_bg_color, foreground=self.foreground_color, font=(self.font_family, 9))
        self.style.configure("Header.TLabel", font=(self.font_family, 11, "bold"), foreground=self.foreground_color)
        self.style.configure("TCheckbutton", background=self.board_bg_color, foreground=self.foreground_color, font=(self.font_family, 9, "bold"))
        self.style.configure("TRadiobutton", background=self.board_bg_color, foreground=self.foreground_color, font=(self.font_family, 9, "bold"))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.tab_game = ttk.Frame(self.notebook)
        self.tab_manual = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_customizer = ttk.Frame(self.notebook)
        self.tab_network = ttk.Frame(self.notebook)
        self.tab_editor = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_game, text="  Battlefield  ")
        self.notebook.add(self.tab_manual, text="  How to Play  ")
        self.notebook.add(self.tab_settings, text="  Settings & Rules  ")
        self.notebook.add(self.tab_customizer, text="  Themes & Styles  ")
        self.notebook.add(self.tab_network, text="  LAN & Multiplayer  ")
        self.notebook.add(self.tab_editor, text="  Level Editor  ")

        self._build_game_tab()
        self._build_editor_tab()
        self._build_manual_tab()
        self._build_customizer_tab()
        self._build_settings_tab()
        self._build_network_tab()

    def _build_game_tab(self):
        # Outer container that centers everything horizontally
        center_wrapper = ttk.Frame(self.tab_game)
        center_wrapper.pack(anchor="center", fill=tk.BOTH, expand=True)

        # Inner dashboard container packed with center alignment
        top_dashboard = ttk.Frame(center_wrapper)
        top_dashboard.pack(anchor="center", padx=4, pady=3)

        # 1. Turn & Match Info Section
        self.lbl_match_timer = tk.Label(
            top_dashboard, text="Time: 00:00", font=(self.font_family, 8, "bold"),
            bg="#2c3e50", fg=self.foreground_color, padx=3, relief=tk.RAISED
        )
        self.lbl_match_timer.pack(side=tk.LEFT, padx=(0, 3))

        self.lbl_turn_indicator = tk.Label(
            top_dashboard, text="Player 1's Turn", font=(self.font_family, 9, "bold"),
            bg=self.player_colors[1], fg="#000000" if self.use_chunky_pixels else "white",
            width=15, anchor="center", padx=1, pady=2
        )
        self.lbl_turn_indicator.pack(side=tk.LEFT, padx=(0, 3))

        self.turn_bar_canvas = tk.Canvas(
            top_dashboard, width=85, height=20, bg="#11171a",
            highlightthickness=1, highlightbackground="#555555"
        )
        self.turn_bar_canvas.pack(side=tk.LEFT, padx=(0, 3))

        self.btn_end_turn = tk.Button(
            top_dashboard, text="End Turn", font=(self.font_family, 8, "bold"),
            bg="#34495e", fg="white", command=self.advance_turn
        )
        self.btn_end_turn.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_pause = tk.Button(
            top_dashboard, text="Pause", font=(self.font_family, 8, "bold"),
            bg="#e67e22", fg="white", command=self.request_pause_toggle
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 2))

        tk.Button(
            top_dashboard, text="New", font=(self.font_family, 8, "bold"),
            bg="#10ac84", fg="white", command=self.start_new_game
        ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Separator(top_dashboard, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)

        # 2. Supremacy Standings Section (Stacked vertically)
        stats_outer = ttk.Frame(top_dashboard)
        stats_outer.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))

        self.stats_frame = ttk.Frame(stats_outer)
        self.stats_frame.pack(anchor="w")

        for p in range(1, 5):
            lbl = tk.Label(
                self.stats_frame, text="", font=(self.font_family, 7, "bold"),
                bg=self.get_player_bg_tint(p), fg=self.player_colors[p], anchor="w", padx=4, pady=1
            )
            lbl.pack(anchor="w", pady=1, fill=tk.X)
            self.player_stat_labels[p] = lbl

        ttk.Separator(top_dashboard, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)

        # 3. Command Panel Section (Tile Selection & Unit Movement Bar)
        cmd_frame = ttk.Frame(top_dashboard)
        cmd_frame.pack(side=tk.LEFT, padx=(0, 4))

        self.lbl_selected_info = tk.Label(
            cmd_frame, text="Selected Territory: None", font=(self.font_family, 8, "bold"),
            bg=self.board_bg_color, fg=self.foreground_color, anchor="w"
        )
        self.lbl_selected_info.pack(anchor="w")

        slider_row = ttk.Frame(cmd_frame)
        slider_row.pack(anchor="w")

        self.units_to_send_var = tk.IntVar(value=1)
        self.slider_units = tk.Scale(
            slider_row, from_=1, to=100, orient=tk.HORIZONTAL, length=90,
            variable=self.units_to_send_var, bg=self.board_bg_color, fg=self.foreground_color,
            highlightthickness=0, troughcolor="#34495e", command=self.on_unit_slider_change
        )
        self.slider_units.pack(side=tk.LEFT, padx=(0, 2))

        pct_frame = ttk.Frame(slider_row)
        pct_frame.pack(side=tk.LEFT)
        for label, ratio in [("1", 0), ("50%", 0.5), ("MAX", 1.0)]:
            tk.Button(
                pct_frame, text=label, bg="#2f3640", fg="white", font=(self.font_family, 8, "bold"), width=4,
                command=lambda r=ratio: [self.set_slider_ratio(r), self.play_sound("click_ui")]
            ).pack(side=tk.LEFT, padx=1)

        self.lbl_range_hint = tk.Label(
            cmd_frame, text="Max reach: 3t", font=(self.font_family, 6),
            bg=self.board_bg_color, fg="#aaaaaa", anchor="w"
        )
        self.lbl_range_hint.pack(anchor="w")

        # 4. Main Battlefield Canvas (Centered inside the wrapper)
        main_pane = ttk.Frame(center_wrapper)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.canvas = tk.Canvas(main_pane, bg=self.board_bg_color, highlightthickness=1, highlightbackground="#555555")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

    def _build_editor_tab(self):
        top_bar = ttk.Frame(self.tab_editor)
        top_bar.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top_bar, text="Rows:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Spinbox(top_bar, from_=4, to=18, textvariable=self.editor_rows_var, width=4).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(top_bar, text="Cols:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Spinbox(top_bar, from_=4, to=22, textvariable=self.editor_cols_var, width=4).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            top_bar, text="Resize / Clear Grid", font=(self.font_family, 8, "bold"),
            bg="#34495e", fg="white", command=self.init_editor_grid
        ).pack(side=tk.LEFT, padx=4)

        ttk.Separator(top_bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Label(top_bar, text="Preset:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Combobox(
            top_bar, textvariable=self.preset_map_var, state="readonly", width=18,
            values=list(PRESET_MAPS.keys())
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            top_bar, text="Load Preset", font=(self.font_family, 8, "bold"),
            bg="#e67e22", fg="white", command=self.load_preset_into_editor
        ).pack(side=tk.LEFT, padx=4)

        ttk.Separator(top_bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        tk.Button(
            top_bar, text="Save CSV", font=(self.font_family, 8, "bold"),
            bg="#2980b9", fg="white", command=self.save_map_to_csv
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            top_bar, text="Load CSV", font=(self.font_family, 8, "bold"),
            bg="#27ae60", fg="white", command=self.load_map_from_csv
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            top_bar, text="Play This Map >>", font=(self.font_family, 9, "bold"),
            bg="#00b894", fg="white", padx=10, command=self.play_editor_map
        ).pack(side=tk.RIGHT, padx=6)

        main_pane = ttk.Frame(self.tab_editor)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.editor_canvas = tk.Canvas(main_pane, bg=self.board_bg_color, highlightthickness=1, highlightbackground="#555555")
        self.editor_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.editor_canvas.bind("<Button-1>", self.on_editor_canvas_paint)
        self.editor_canvas.bind("<B1-Motion>", self.on_editor_canvas_paint)
        self.editor_canvas.bind("<Configure>", lambda e: self.render_editor_canvas())

        brush_bar = ttk.Frame(main_pane, width=275)
        brush_bar.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
        brush_bar.pack_propagate(False)

        ttk.Label(brush_bar, text="PAINT BRUSHES", style="Header.TLabel").pack(anchor="w", pady=(6, 8))

        brushes = [
            "Obstacle (X)", "Fortress (#)", "Factory (^)", "Flag Base (F)",
            "Hill Monolith (*)", "VIP Commander (@)", "Relic Payload ($)",
            "Beacon Node (+)", "Neutral (.)", "Player 1 Base", "Player 2 Base",
            "Player 3 Base", "Player 4 Base"
        ]
        for b in brushes:
            ttk.Radiobutton(brush_bar, text=b, variable=self.editor_brush_var, value=b).pack(anchor="w", pady=2, padx=4)

        ttk.Separator(brush_bar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(brush_bar, text="Starting Units for Player Base:").pack(anchor="w", pady=(0, 2))
        tk.Scale(
            brush_bar, from_=1, to=100, orient=tk.HORIZONTAL,
            variable=self.editor_unit_val_var, bg=self.board_bg_color, fg=self.foreground_color,
            highlightthickness=0, troughcolor="#34495e"
        ).pack(fill=tk.X, pady=2)

    def _build_customizer_tab(self):
        container = ttk.Frame(self.tab_customizer)
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=25)

        ttk.Label(container, text="THEME & STYLE CUSTOMIZER", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(container, text="Select pre-built seasonal/retro themes or build your own custom look!", font=(self.font_family, 9)).pack(anchor="w", pady=(0, 12))

        preset_frame = ttk.Frame(container)
        preset_frame.pack(anchor="w", pady=6)
        ttk.Label(preset_frame, text="Active Theme Preset:", font=(self.font_family, 9, "bold")).pack(side=tk.LEFT, padx=(0, 10))

        theme_list = list(THEMES.keys()) + ["Custom Theme"]
        theme_cb = ttk.Combobox(preset_frame, textvariable=self.theme_var, state="readonly", width=26, values=theme_list)
        theme_cb.pack(side=tk.LEFT, padx=6)
        theme_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_theme_selection())

        ttk.Separator(container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        ttk.Label(container, text="CUSTOM THEME BUILDER", style="Header.TLabel").pack(anchor="w", pady=(0, 8))

        custom_pane = ttk.Frame(container)
        custom_pane.pack(anchor="w", pady=5)

        ttk.Label(custom_pane, text="Font Family:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        ttk.Combobox(custom_pane, textvariable=self.custom_font_var, state="readonly", width=18, values=["Courier New", "Segoe UI", "Consolas", "Terminal", "Arial"]).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(custom_pane, text="Pixel Style:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        ttk.Checkbutton(custom_pane, text="Chunky Pixel Art", variable=self.custom_chunky_var).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(custom_pane, text="Board Background:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 10))
        tk.Button(custom_pane, text="Pick Color", command=lambda: self.pick_custom_color(self.custom_bg_var)).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(custom_pane, text="Neutral Tile Color:").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 10))
        tk.Button(custom_pane, text="Pick Color", command=lambda: self.pick_custom_color(self.custom_neutral_var)).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(custom_pane, text="Foreground Text:").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 10))
        tk.Button(custom_pane, text="Pick Color", command=lambda: self.pick_custom_color(self.custom_fg_var)).grid(row=4, column=1, sticky="w", pady=4)

        tk.Button(
            container, text="Apply Custom Theme", font=(self.font_family, 9, "bold"),
            bg="#00b894", fg="white", padx=12, pady=6,
            command=lambda: [self.theme_var.set("Custom Theme"), self.apply_theme_selection()]
        ).pack(anchor="w", pady=15)

    def _build_settings_tab(self):
        outer = ttk.Frame(self.tab_settings)
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        left_col = ttk.Frame(outer)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))

        ttk.Label(left_col, text="GAME RULES & VICTORY MODES", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        bgm_cb = ttk.Combobox(left_col, textvariable=self.bgm_track_var, state="readonly", width=28, values=list(BGM_PATTERNS.keys()))
        victory_cb = ttk.Combobox(left_col, textvariable=self.victory_mode_var, state="readonly", width=28, values=[
            "Total Supremacy", "Capture the Flag (F)", "King of the Hill (*)", "VIP Commander (@)", "Relic Extraction ($)", "Domination (+)"
        ])
        players_spin = ttk.Spinbox(
            left_col, from_=2, to=4, textvariable=self.num_players_var, width=6,
            command=self.refresh_player_color_pickers
        )

        settings_rows = [
            ("Victory Mode:", victory_cb),
            ("Game Mode:", ttk.Combobox(left_col, textvariable=self.game_mode_var, state="readonly", width=28, values=["Single Player (vs AI)", "Local Hotseat Multiplayer", "LAN Socket Multiplayer"])),
            ("Players (2-4):", players_spin),
            ("AI Difficulty:", ttk.Combobox(left_col, textvariable=self.ai_difficulty_var, state="readonly", width=28, values=["Easy", "Medium", "Hard"])),
            ("AI Personality:", ttk.Combobox(left_col, textvariable=self.ai_personality_var, state="readonly", width=28, values=AI_PERSONALITIES)),
            ("Grid Rows:", ttk.Spinbox(left_col, from_=4, to=16, textvariable=self.grid_rows_var, width=6)),
            ("Grid Cols:", ttk.Spinbox(left_col, from_=4, to=20, textvariable=self.grid_cols_var, width=6)),
            ("Starting Tiles/Player:", ttk.Spinbox(left_col, from_=1, to=6, textvariable=self.start_tiles_var, width=6)),
            ("Start Units:", ttk.Spinbox(left_col, from_=1, to=100, textvariable=self.start_units_var, width=6)),
            ("Obstacles:", ttk.Spinbox(left_col, from_=0, to=40, textvariable=self.num_obstacles_var, width=6)),
            ("Turn Sec:", ttk.Spinbox(left_col, from_=5.0, to=15.0, increment=0.5, textvariable=self.turn_duration_var, width=6)),
            ("Combat Pause Sec:", ttk.Spinbox(left_col, from_=0.1, to=2.0, increment=0.1, textvariable=self.combat_pause_var, width=6)),
            ("Max Move:", ttk.Spinbox(left_col, from_=1, to=20, textvariable=self.max_move_distance_var, width=6)),
            ("Diagonal:", ttk.Checkbutton(left_col, text="Allow", variable=self.allow_diagonal_var)),
            ("Fog of War:", ttk.Checkbutton(left_col, text="Enable", variable=self.fog_of_war_var)),
            ("Music:", bgm_cb),
        ]
        for idx, (lbl_txt, widget) in enumerate(settings_rows, start=1):
            ttk.Label(left_col, text=lbl_txt, font=(self.font_family, 9, "bold")).grid(row=idx, column=0, sticky="w", pady=2, padx=(0, 8))
            widget.grid(row=idx, column=1, sticky="w", pady=2)

        right_col = ttk.Frame(outer)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(15, 0))

        ttk.Label(right_col, text="SOUND CONFIG (Hz)", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        sound_rows = [
            ("Dispatch:", self.snd_dispatch_freq),
            ("Combat:", self.snd_combat_freq),
            ("Own Click:", self.snd_own_click_freq),
            ("Neutral:", self.snd_neut_click_freq),
            ("Enemy:", self.snd_enemy_click_freq),
        ]
        for idx, (lbl_txt, var_obj) in enumerate(sound_rows, start=1):
            ttk.Label(right_col, text=lbl_txt, font=(self.font_family, 9, "bold")).grid(row=idx, column=0, sticky="w", pady=2, padx=(0, 8))
            ttk.Spinbox(right_col, from_=50, to=3000, increment=20, textvariable=var_obj, width=8).grid(row=idx, column=1, sticky="w", pady=2)

        next_row = len(sound_rows) + 1
        ttk.Separator(right_col, orient=tk.HORIZONTAL).grid(row=next_row, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(right_col, text="PLAYER COLORS (2-4P)", style="Header.TLabel").grid(row=next_row + 1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.player_color_Setting_Frame = ttk.Frame(right_col)
        self.player_color_Setting_Frame.grid(row=next_row + 2, column=0, columnspan=2, sticky="w")
        self.refresh_player_color_pickers()

        btn_frame = ttk.Frame(right_col)
        btn_frame.grid(row=next_row + 3, column=0, columnspan=2, sticky="w", pady=18)

        tk.Button(
            btn_frame, text="Apply Settings & Restart", font=(self.font_family, 9, "bold"),
            bg="#00b894", fg="white", padx=12, pady=6,
            command=lambda: [self.apply_theme_selection(), self.start_new_game(), self.notebook.select(self.tab_game)]
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_frame, text="Save Defaults to settings.ini", font=(self.font_family, 9, "bold"),
            bg="#2980b9", fg="white", padx=12, pady=6,
            command=self.save_current_settings_to_ini
        ).pack(side=tk.LEFT)

    def _build_network_tab(self):
        container = ttk.Frame(self.tab_network)
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=25)

        ttk.Label(container, text="AUTOMATED LAN & UDP DISCOVERY", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        info_text = (
            "1. Click 'Host & Broadcast' to host a match.\n"
            "2. Clients click 'Scan Local Network' and double-click a server to join."
        )
        ttk.Label(container, text=info_text, wraplength=550, font=(self.font_family, 9)).pack(anchor="w", pady=(0, 15))

        btn_bar = ttk.Frame(container)
        btn_bar.pack(anchor="w", pady=10)
        tk.Button(btn_bar, text="Host & Broadcast", bg="#00b894", fg="white", padx=12, pady=6, command=self.start_server_with_broadcast).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(btn_bar, text="Scan Network", bg="#2980b9", fg="white", padx=12, pady=6, command=self.scan_lan_for_servers).pack(side=tk.LEFT, padx=10)

        self.server_listbox = tk.Listbox(container, font=(self.font_family, 10), width=48, height=6, bg="#11171a", fg=self.foreground_color)
        self.server_listbox.pack(anchor="w", pady=10)
        self.server_listbox.bind("<Double-Button-1>", self.join_selected_discovered_server)

        self.lbl_net_connection_status = ttk.Label(container, text="Status: Disconnected", font=(self.font_family, 10, "bold"), foreground="#feca57")
        self.lbl_net_connection_status.pack(anchor="w", pady=10)

    # --- PATHFINDING & FOG OF WAR ---
    def is_tile_visible_in_fog(self, r, c, player_p):
        if not self.fog_of_war_var.get():
            return True
        if self.grid[r][c].owner == player_p:
            return True
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc].owner == player_p:
                    return True
        return False

    def _build_manual_tab(self):
        container = ttk.Frame(self.tab_manual)
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=25)

        ttk.Label(container, text="HOW TO PLAY & GAME MODES", style="Header.TLabel").pack(anchor="w", pady=(0, 10))

        manual_text = (
            "• OBJECTIVE: Conquer all rival territories to achieve total supremacy.\n\n"
            "• MOVEMENT & LOGISTICS: Click your colored tile, adjust the dispatch slider, and click a destination.\n"
            "  - Neutral/Enemy Expansion: Capped strictly at 1 tile (adjacent only).\n"
            "  - Friendly Logistics Highway: Slide reserves across contiguous friendly tiles up to your full movement range.\n\n"
            "• AI PERSONALITIES:\n"
            "  - Expansionist: Rushes neutral ground & factories.\n"
            "  - Fortifier: Stacks garrisons inside fortresses (#).\n"
            "  - Blitzkrieg: Aggressively hunts enemy borders & VIPs.\n\n"
            "• TERRAIN & OBJECTIVE ICONS:\n"
            "  # Fortress: Provides +25% defense bonus to garrisons.\n"
            "  ^ Factory: Generates +2 units per turn instead of +1.\n"
            "  X Obstacle: Blocks movement across the map.\n"
            "  F Flag Base: Capture and escort back home (CTF mode).\n"
            "  * Hill Monolith: Hold to accumulate hold time (King of the Hill).\n"
            "  @ VIP Commander: Defend your leader (Regicide mode).\n"
            "  $ Relic Payload: Retrieve and return to factories.\n"
            "  + Beacon Node: Control nodes to drain enemy tickets (Domination).\n\n"
            "• LEVEL EDITOR: Use the Level Editor tab to paint custom tactical maps and save/load them via CSV!"
        )
        
        lbl = tk.Label(
            container, text=manual_text, font=(self.font_family, 10),
            bg=self.board_bg_color, fg=self.foreground_color, justify=tk.LEFT, wraplength=900
        )
        lbl.pack(anchor="w", pady=10)

    def get_max_steps_allowed(self, units_sending):
        rule = self.movement_rule_var.get()
        configured_max = max(1, self.max_move_distance_var.get())
        if rule == "Fixed Configurable Distance":
            return configured_max
        elif rule == "Scaled by Units Sent (Capped at Max Distance)":
            return min(configured_max, units_sending + 1)
        return self.rows * self.cols

    def compute_reachable_tiles(self, start_tile, units_sending, owner_id=None):
        max_steps = self.get_max_steps_allowed(units_sending)
        visited = {(start_tile.r, start_tile.c): [(start_tile.r, start_tile.c)]}
        queue = deque([(start_tile.r, start_tile.c, [(start_tile.r, start_tile.c)])])
        reachable = {}
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if self.allow_diagonal_var.get():
            dirs.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])

        active_p = owner_id if owner_id is not None else start_tile.owner

        while queue:
            r, c, path = queue.popleft()
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    target_tile = self.grid[nr][nc]
                    if (nr, nc) not in visited and not target_tile.is_obstacle:
                        is_friendly = (target_tile.owner == active_p)
                        is_neutral_or_enemy = (target_tile.owner != active_p)
                        steps_so_far = len(path) - 1

                        if is_neutral_or_enemy:
                            if steps_so_far == 0:
                                new_path = path + [(nr, nc)]
                                visited[(nr, nc)] = new_path
                                reachable[(nr, nc)] = new_path
                        elif is_friendly:
                            if steps_so_far < max_steps:
                                new_path = path + [(nr, nc)]
                                visited[(nr, nc)] = new_path
                                reachable[(nr, nc)] = new_path
                                queue.append((nr, nc, new_path))
        return reachable

    def dispatch_units(self, source_tile, count, path_coords):
        count = min(count, source_tile.units)
        if count <= 0 or len(path_coords) < 2:
            return
        owner_id = source_tile.owner
        source_tile.set_units(source_tile.units - count)
        speed = max(0.2, self.unit_speed_var.get() / 2.5)

        carrying_flag = (source_tile.terrain_type == "flag" and source_tile.owner != owner_id and source_tile.owner != 0)
        carrying_relic = (source_tile.terrain_type == "relic")
        if carrying_flag:
            source_tile.terrain_type = "normal"
        if carrying_relic:
            source_tile.terrain_type = "normal"

        self.moving_groups.append(MovingGroup(owner_id, count, path_coords, speed, carrying_flag, carrying_relic))
        self.play_sound("dispatch")
        self.log_match_event("UNIT_DISPATCH", {"player": owner_id, "count": count, "source": [source_tile.r, source_tile.c], "destination": [path_coords[-1][0], path_coords[-1][1]]})

    def distribute_reinforcements(self):
        for p in range(1, self.num_players + 1):
            owned_tiles = [self.grid[r][c] for r in range(self.rows) for c in range(self.cols) if self.grid[r][c].owner == p]
            for _ in range(len(owned_tiles)):
                non_full = [t for t in owned_tiles if t.units < MAX_TILE_CAPACITY]
                if not non_full:
                    break
                chosen = random.choice(non_full)
                chosen.set_units(chosen.units + (2 if chosen.terrain_type == "factory" else 1))

    def player_is_alive(self, p):
        if self.victory_mode_var.get() == "VIP Commander (@)":
            has_commander = any(self.grid[r][c].owner == p and self.grid[r][c].terrain_type == "commander" for r in range(self.rows) for c in range(self.cols))
            if not has_commander:
                return False
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c].owner == p and self.grid[r][c].units > 0:
                    return True
        if any(grp.owner == p for grp in self.moving_groups):
            return True
        return any(eff.grp.owner == p for eff in self.combat_effects)

    def update_turn_banner(self):
        if not self.lbl_turn_indicator:
            return
        p = self.current_turn_player
        self.lbl_turn_indicator.config(text=f"Player {p}'s Turn", bg=self.player_colors[p])

    def update_scoreboard(self):
        alive_players = []
        vmode = self.victory_mode_var.get()

        for p in range(1, 5):
            if p not in self.player_stat_labels:
                continue
            lbl = self.player_stat_labels[p]
            if p > self.num_players:
                lbl.pack_forget()
                continue
            lbl.pack(anchor="w", pady=1, fill=tk.X)
            tiles = sum(1 for r in range(self.rows) for c in range(self.cols) if self.grid[r][c].owner == p)
            units = sum(self.grid[r][c].units for r in range(self.rows) for c in range(self.cols) if self.grid[r][c].owner == p)
            units += sum(grp.count for grp in self.moving_groups if grp.owner == p)
            units += sum(eff.grp.count for eff in self.combat_effects if eff.grp.owner == p and not eff.resolved)
            if tiles > 0 or units > 0:
                alive_players.append(p)

            stat_text = f"Player {p} | Tiles: {tiles} | Units: {units}"
            if "King of the Hill" in vmode:
                stat_text = f"Player {p} | Tiles: {tiles} | Hill: {int(self.hill_hold_timers[p])}s"
            elif "Domination" in vmode:
                stat_text = f"Player {p} | Tiles: {tiles} | Tix: {int(self.player_tickets[p])}"

            if tiles == 0 and units == 0:
                stat_text = f"Player {p} | ELIMINATED"
            lbl.config(text=stat_text, bg=self.get_player_bg_tint(p), fg=self.player_colors[p])

    def update_turn_timer_bar(self):
        if not self.turn_bar_canvas:
            return
        self.turn_bar_canvas.delete("all")
        w = 85
        h = 20
        max_t = max(0.1, float(self.turn_duration_var.get()))
        ratio = max(0.0, min(1.0, self.turn_time_left / max_t))
        fill_w = int(w * ratio)

        bar_col = self.player_colors.get(self.current_turn_player, "#2ecc71")

        if fill_w > 0:
            self.turn_bar_canvas.create_rectangle(0, 0, fill_w, h, fill=bar_col, outline="")

        txt = f"{max(0.0, self.turn_time_left):.1f}s"
        font_cfg = (self.font_family, 8, "bold")
        self.turn_bar_canvas.create_text(w / 2 + 1, h / 2 + 1, text=txt, fill="#000000", font=font_cfg)
        self.turn_bar_canvas.create_text(w / 2, h / 2, text=txt, fill="#ffffff", font=font_cfg)

    def game_loop(self):
        dt = self.last_tick_ms / 1000.0
        if self.game_running and not self.is_paused:
            if self.net_role != "client":
                self.match_elapsed_seconds += dt
                if not self.combat_effects:
                    self.turn_time_left -= dt

                vmode = self.victory_mode_var.get()
                if "King of the Hill" in vmode:
                    for r in range(self.rows):
                        for c in range(self.cols):
                            tile = self.grid[r][c]
                            if tile.terrain_type == "hill" and tile.owner > 0 and tile.units > 0:
                                self.hill_hold_timers[tile.owner] += dt

                elif "Domination" in vmode:
                    beacons = [self.grid[r][c] for r in range(self.rows) for c in range(self.cols) if self.grid[r][c].terrain_type == "beacon" and self.grid[r][c].owner > 0]
                    for b in beacons:
                        for p in range(1, self.num_players + 1):
                            if p != b.owner:
                                self.player_tickets[p] -= dt * 0.5

                if self.game_mode_var.get() == "Single Player (vs AI)" and self.current_turn_player != 1 and not self.combat_effects:
                    self.ai_action_timer += dt
                    if self.ai_action_timer >= 1.5:
                        self.ai_action_timer = 0.0
                        self.execute_ai_point_action()

                if self.turn_time_left <= 0 and not self.combat_effects:
                    self.advance_turn()

            mins, secs = int(self.match_elapsed_seconds // 60), int(self.match_elapsed_seconds % 60)
            if self.lbl_match_timer:
                self.lbl_match_timer.config(text=f"Time: {mins:02d}:{secs:02d}")
            self.update_turn_timer_bar()
            for r in range(self.rows):
                for c in range(self.cols):
                    for ant in self.grid[r][c].ants:
                        ant.update()

            arrived = [grp for grp in self.moving_groups if grp.update(dt)]
            for grp in arrived:
                self.moving_groups.remove(grp)
                dest_r, dest_c = grp.path[-1]
                dest_tile = self.grid[dest_r][dest_c]
                pause_dur = max(0.1, self.combat_pause_var.get())
                eff = CombatEffect(dest_r, dest_c, grp, duration=pause_dur)
                if dest_tile.owner == grp.owner:
                    eff.popup_text = f"+{grp.count}"
                    eff.popup_color = "#55ff55"
                elif dest_tile.owner == 0:
                    eff.popup_text = f"⚑ {grp.count}"
                    eff.popup_color = self.player_colors.get(grp.owner, "#ffffff")
                else:
                    eff.popup_text = f"⚔ -{grp.count}"
                    eff.popup_color = "#ff5555"
                self.combat_effects.append(eff)

            finished_effects = [eff for eff in self.combat_effects if eff.update(dt)]
            for eff in finished_effects:
                self.combat_effects.remove(eff)
                if not eff.resolved and self.net_role != "client":
                    eff.resolved = True
                    self.resolve_arrival(eff.grp)

            self.update_scoreboard()
            if self.net_role == "server":
                self.broadcast_game_state()

        self.render_canvas()
        self.root.after(self.last_tick_ms, self.game_loop)

    def resolve_arrival(self, grp):
        dest_r, dest_c = grp.path[-1]
        tile = self.grid[dest_r][dest_c]
        effective_count = grp.count
        if tile.terrain_type == "fortress" and tile.owner not in (0, grp.owner):
            effective_count = max(1, int(grp.count * 0.75))

        self.play_sound("combat")

        if grp.carrying_flag and tile.terrain_type == "flag" and tile.owner == grp.owner:
            self.game_running = False
            self.play_sound("victory")
            messagebox.showinfo("CTF Victory!", f"Player {grp.owner} successfully captured the enemy flag and won!")
            return

        if grp.carrying_relic and tile.terrain_type == "factory" and tile.owner == grp.owner:
            self.game_running = False
            self.play_sound("victory")
            messagebox.showinfo("Relic Extracted!", f"Player {grp.owner} successfully extracted the relic and won!")
            return

        if tile.owner == grp.owner:
            tile.set_units(min(MAX_TILE_CAPACITY, tile.units + grp.count))
            if grp.carrying_flag:
                tile.terrain_type = "flag"
        elif tile.owner == 0:
            tile.owner = grp.owner
            tile.set_units(min(MAX_TILE_CAPACITY, grp.count))
            if grp.carrying_flag:
                tile.terrain_type = "flag"
        else:
            remaining = tile.units - effective_count
            if remaining > 0:
                tile.set_units(remaining)
            elif remaining < 0:
                tile.owner = grp.owner
                tile.set_units(min(MAX_TILE_CAPACITY, abs(remaining)))
                if grp.carrying_flag:
                    tile.terrain_type = "flag"
                if tile.terrain_type == "commander":
                    tile.owner = 0
                    tile.terrain_type = "normal"
                    self.game_running = False
                    self.play_sound("victory")
                    messagebox.showinfo("Regicide Victory!", f"Player {grp.owner} assassinated the enemy Commander (@) and won!")
                    return
            else:
                tile.owner = 0
                tile.set_units(0)
                if tile.terrain_type == "commander":
                    tile.terrain_type = "normal"

    def get_board_geometry(self):
        cw, ch = max(100, self.canvas.winfo_width()), max(100, self.canvas.winfo_height())
        pad = 15
        tile_px = min((cw - 2 * pad) / self.cols, (ch - 2 * pad) / self.rows)
        return (cw - tile_px * self.cols) / 2, (ch - tile_px * self.rows) / 2, tile_px

    def pixel_to_grid(self, px, py):
        ox, oy, tpx = self.get_board_geometry()
        c, r = int((px - ox) // tpx), int((py - oy) // tpx)
        return (r, c) if 0 <= r < self.rows and 0 <= c < self.cols else (None, None)

    def render_canvas(self):
        if not self.canvas:
            return
        self.canvas.delete("all")
        if not self.grid:
            return
        ox, oy, tpx = self.get_board_geometry()
        px_log = tpx / LOGICAL_TILE_SIZE
        obs_bg = self.get_obstacle_bg_tint()

        if self.net_role != "local":
            active_p = self.my_player_id
        elif self.game_mode_var.get() == "Single Player (vs AI)":
            active_p = 1
        else:
            active_p = self.current_turn_player

        for r in range(self.rows):
            for c in range(self.cols):
                tile = self.grid[r][c]
                x1, y1 = ox + c * tpx, oy + r * tpx
                x2, y2 = x1 + tpx, y1 + tpx

                if not self.is_tile_visible_in_fog(r, c, active_p):
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill="#050505", outline="#222222", width=1)
                    self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="?", fill="#444444", font=(self.font_family, int(tpx * 0.35), "bold"))
                    continue

                bg = obs_bg if tile.is_obstacle else self.get_player_bg_tint(tile.owner)
                border = self.obstacle_color if tile.is_obstacle else ("#ffff55" if self.use_chunky_pixels else "#3d4a55")
                bw = 2 if tile.is_obstacle else 1

                if self.selected_tile == tile:
                    border, bw = "#ffffff", 3
                elif (r, c) in self.valid_targets:
                    border, bw = "#00ffaa", 2

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline=border, width=bw)

                if tile.is_obstacle:
                    self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="X", fill=self.obstacle_color, font=(self.font_family, max(10, int(tpx * 0.45)), "bold"))
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
                    self.canvas.create_text((x1 + x2) / 2, y1 + tpx * 0.25, text=sym, fill=col, font=(self.font_family, max(10, int(tpx * 0.28)), "bold"))

                ant_color = self.player_colors.get(tile.owner, "#ffffff")
                rad = max(1.5, px_log * (0.5 if self.use_chunky_pixels else 0.42))
                for ant in tile.ants:
                    ax, ay = x1 + ant.lx * px_log, y1 + ant.ly * px_log
                    if self.use_chunky_pixels:
                        self.canvas.create_rectangle(ax - rad, ay - rad, ax + rad, ay + rad, fill=ant_color, outline="")
                    else:
                        self.canvas.create_oval(ax - rad, ay - rad, ax + rad, ay + rad, fill=ant_color, outline="")

                if tile.units > 0 or tile.owner != 0:
                    tx, ty = (x1 + x2) / 2, (y1 + y2) / 2 + tpx * 0.12
                    font_cfg = (self.font_family, max(9, int(tpx * 0.30)), "bold")
                    self.canvas.create_text(tx + 1, ty + 1, text=str(tile.units), fill="#000000", font=font_cfg)
                    self.canvas.create_text(tx, ty, text=str(tile.units), fill="#ffffff", font=font_cfg)

        if self.selected_tile and self.valid_targets:
            for _, path in self.valid_targets.items():
                for idx in range(len(path) - 1):
                    r1, c1 = path[idx]
                    r2, c2 = path[idx + 1]
                    self.canvas.create_line(
                        ox + (c1 + 0.5) * tpx, oy + (r1 + 0.5) * tpx,
                        ox + (c2 + 0.5) * tpx, oy + (r2 + 0.5) * tpx,
                        fill="#00ffaa", width=2, dash=(4, 4)
                    )

        for grp in self.moving_groups:
            cr, cc = grp.get_current_logical_pos()
            cx, cy = ox + (cc + 0.5) * tpx, oy + (cr + 0.5) * tpx
            col = self.player_colors.get(grp.owner, "#ffffff")
            for ox_off, oy_off in grp.offsets:
                self.canvas.create_rectangle(cx + ox_off * px_log - 2, cy + oy_off * px_log - 2, cx + ox_off * px_log + 2, cy + oy_off * px_log + 2, fill=col, outline="#ffffff")
            tag_text = f"🏴 {grp.count}" if grp.carrying_flag else (f"💎 {grp.count}" if grp.carrying_relic else str(grp.count))
            self.canvas.create_text(cx, cy - 12, text=tag_text, fill=col, font=(self.font_family, 10, "bold"))

        for eff in self.combat_effects:
            if not self.is_tile_visible_in_fog(eff.r, eff.c, active_p):
                continue
            x1, y1 = ox + eff.c * tpx, oy + eff.r * tpx
            x2, y2 = x1 + tpx, y1 + tpx
            flash_col = "#ffffff" if eff.progress < 0.5 else self.player_colors.get(eff.grp.owner, "#ff5555")
            self.canvas.create_rectangle(x1 + 2, y1 + 2, x2 - 2, y2 - 2, outline=flash_col, width=4)

            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 - (eff.progress * tpx * 0.45)
            font_cfg = (self.font_family, max(10, int(tpx * 0.28)), "bold")
            self.canvas.create_text(cx + 1, cy + 1, text=eff.popup_text, fill="#000000", font=font_cfg)
            self.canvas.create_text(cx, cy, text=eff.popup_text, fill=eff.popup_color, font=font_cfg)


if __name__ == "__main__":
    root = tk.Tk()
    app = AntGridApp(root)
    root.mainloop()