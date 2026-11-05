import os
import configparser

MAX_TILE_CAPACITY = 100
LOGICAL_TILE_SIZE = 10
SETTINGS_FILE = "settings.ini"

AI_PERSONALITIES = [
    "Balanced",
    "Expansionist (Rushes Neutral & Factories)",
    "Fortifier (Stacks Fortresses & Defense)",
    "Blitzkrieg (Hunts Enemy & Commanders)"
]

DEFAULT_INI_CONTENT = """[GameRules]
grid_rows = 8
grid_cols = 10
num_players = 2
game_mode = Single Player (vs AI)
ai_difficulty = Medium
ai_personality = Balanced
victory_mode = Total Supremacy
start_tiles = 2
start_units = 15
num_obstacles = 8
turn_duration = 7.0
unit_speed = 3.0
max_move_distance = 3
movement_rule = Fixed Configurable Distance
allow_diagonal = True
fog_of_war = False
combat_pause_duration = 0.6

[Visuals]
theme = MS-DOS 90s Retro
bgm_track = Energetic Pulse
custom_font = Courier New
custom_chunky = True
custom_bg = #0000aa
custom_neutral = #000055
custom_fg = #ffff55

[PlayerColors]
player_1 = 
player_2 = 
player_3 = 
player_4 = 

[Sound]
dispatch_freq = 950
dispatch_dur = 50
combat_freq = 220
combat_dur = 90
own_click_freq = 600
neut_click_freq = 440
enemy_click_freq = 180

[Network]
server_ip = 127.0.0.1
server_port = 5555
"""

THEMES = {
    "MS-DOS 90s Retro": {
        "board_bg": "#0000aa",
        "neutral_bg": "#000055",
        "foreground": "#ffff55",
        "obstacle_color": "#ff55ff",
        "obstacle_bg": "#550055",
        "font_family": "Courier New",
        "use_chunky_pixels": True,
        "player_colors": {0: "#aaaaaa", 1: "#55ffff", 2: "#ff5555", 3: "#55ff55", 4: "#ffff55"}
    },
    "Modern Dark Mode": {
        "board_bg": "#11171a",
        "neutral_bg": "#2c3e50",
        "foreground": "#ecf0f1",
        "obstacle_color": "#9b59b6",
        "obstacle_bg": "#1a0d21",
        "font_family": "Segoe UI",
        "use_chunky_pixels": False,
        "player_colors": {0: "#888888", 1: "#2980b9", 2: "#c0392b", 3: "#27ae60", 4: "#f39c12"}
    },
    "Modern Light Mode": {
        "board_bg": "#f5f6fa",
        "neutral_bg": "#dcdde1",
        "foreground": "#2f3640",
        "obstacle_color": "#8c7ae6",
        "obstacle_bg": "#e1b12c",
        "font_family": "Segoe UI",
        "use_chunky_pixels": False,
        "player_colors": {0: "#718093", 1: "#0097e6", 2: "#e84118", 3: "#4cd137", 4: "#fbc531"}
    },
    "Autumn Harvest (Seasonal)": {
        "board_bg": "#2d130c",
        "neutral_bg": "#4a2318",
        "foreground": "#ffbe76",
        "obstacle_color": "#e056fd",
        "obstacle_bg": "#220904",
        "font_family": "Courier New",
        "use_chunky_pixels": True,
        "player_colors": {0: "#bdc581", 1: "#ff7979", 2: "#686de0", 3: "#badc58", 4: "#f0932b"}
    },
    "Winter Frost (Seasonal)": {
        "board_bg": "#0c2461",
        "neutral_bg": "#1e3799",
        "foreground": "#82ccdd",
        "obstacle_color": "#e056fd",
        "obstacle_bg": "#06183c",
        "font_family": "Consolas",
        "use_chunky_pixels": False,
        "player_colors": {0: "#78e08f", 1: "#60a3bc", 2: "#fa8231", 3: "#079992", 4: "#e58e26"}
    },
    "Cyberpunk Neon": {
        "board_bg": "#0b0b16",
        "neutral_bg": "#1b1b2f",
        "foreground": "#00ffcc",
        "obstacle_color": "#ff007f",
        "obstacle_bg": "#12021a",
        "font_family": "Courier New",
        "use_chunky_pixels": True,
        "player_colors": {0: "#8888aa", 1: "#00f0ff", 2: "#ff0055", 3: "#39ff14", 4: "#ffe600"}
    }
}

BGM_PATTERNS = {
    "Off": [],
    "Energetic Pulse": [(262, 90), (330, 90), (392, 90), (523, 140), (392, 60), (523, 200)],
    "Ambient Chimes": [(495, 160), (330, 160), (412, 300), (660, 160), (577, 160), (742, 300)],
    "Bass Drone": [(110, 250), (165, 250), (147, 450)]
}

PRESET_MAPS = {
    "Crossfire (2-4P)": [
        "P1 . . X X X X . . P2",
        ". . ^ . X X . ^ . .",
        ". ^ . . # # . . ^ .",
        "X X . . . . . . X X",
        "X X . . . . . . X X",
        ". ^ . . # # . . ^ .",
        ". . ^ . X X . ^ . .",
        "P4 . . X X X X . . P3"
    ],
    "King of the Hill Arena": [
        "P1 . . X . . X . . P2",
        ". . . . . . . . . .",
        ". . # . ^ ^ . # . .",
        "X . . . . * . . . X",
        "X . . . * * . . . X",
        ". . # . ^ ^ . # . .",
        ". . . . . . . . . .",
        "P4 . . X . . X . . P3"
    ],
    "CTF & Relic Vault": [
        "P1 F . . X . $ . X . . F P2",
        ". . . . X . . . X . . .",
        ". ^ . . . + + . . . ^ .",
        "X X X . @ . . @ . X X X",
        "X X X . @ . . @ . X X X",
        ". ^ . . . + + . . . ^ .",
        ". . . . X . . . X . . .",
        "P4 F . . X . $ . X . . F P3"
    ]
}


def blend_hex(hex1: str, hex2: str, ratio: float = 0.32) -> str:
    try:
        h1, h2 = hex1.lstrip("#"), hex2.lstrip("#")
        r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
        r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
        r = int(r1 * ratio + r2 * (1.0 - ratio))
        g = int(g1 * ratio + g2 * (1.0 - ratio))
        b = int(b1 * ratio + b2 * (1.0 - ratio))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#2c3e50"


def ensure_settings_file():
    if not os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                f.write(DEFAULT_INI_CONTENT)
        except Exception:
            pass


def load_ini_settings() -> configparser.ConfigParser:
    ensure_settings_file()
    cfg = configparser.ConfigParser()
    cfg.read_string(DEFAULT_INI_CONTENT)
    try:
        cfg.read(SETTINGS_FILE, encoding="utf-8")
    except Exception:
        pass
    return cfg


def save_ini_settings(app):
    cfg = configparser.ConfigParser()
    cfg["GameRules"] = {
        "grid_rows": str(app.grid_rows_var.get()),
        "grid_cols": str(app.grid_cols_var.get()),
        "num_players": str(app.num_players_var.get()),
        "game_mode": app.game_mode_var.get(),
        "ai_difficulty": app.ai_difficulty_var.get(),
        "ai_personality": app.ai_personality_var.get(),
        "victory_mode": app.victory_mode_var.get(),
        "start_tiles": str(app.start_tiles_var.get()),
        "start_units": str(app.start_units_var.get()),
        "num_obstacles": str(app.num_obstacles_var.get()),
        "turn_duration": str(app.turn_duration_var.get()),
        "unit_speed": str(app.unit_speed_var.get()),
        "max_move_distance": str(app.max_move_distance_var.get()),
        "movement_rule": app.movement_rule_var.get(),
        "allow_diagonal": str(app.allow_diagonal_var.get()),
        "fog_of_war": str(app.fog_of_war_var.get()),
        "combat_pause_duration": str(app.combat_pause_var.get())
    }
    cfg["Visuals"] = {
        "theme": app.theme_var.get(),
        "bgm_track": app.bgm_track_var.get(),
        "custom_font": app.custom_font_var.get(),
        "custom_chunky": str(app.custom_chunky_var.get()),
        "custom_bg": app.custom_bg_var.get(),
        "custom_neutral": app.custom_neutral_var.get(),
        "custom_fg": app.custom_fg_var.get()
    }
    cfg["PlayerColors"] = {
        f"player_{p}": app.custom_player_colors.get(p, "") for p in range(1, 5)
    }
    cfg["Sound"] = {
        "dispatch_freq": str(app.snd_dispatch_freq.get()),
        "dispatch_dur": str(app.snd_dispatch_dur.get()),
        "combat_freq": str(app.snd_combat_freq.get()),
        "combat_dur": str(app.snd_combat_dur.get()),
        "own_click_freq": str(app.snd_own_click_freq.get()),
        "neut_click_freq": str(app.snd_neut_click_freq.get()),
        "enemy_click_freq": str(app.snd_enemy_click_freq.get())
    }
    cfg["Network"] = {
        "server_ip": app.server_ip_var.get(),
        "server_port": str(app.server_port_var.get())
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)