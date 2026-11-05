import random
from config import MAX_TILE_CAPACITY

MAX_VISUAL_ANTS = 18
from config import MAX_TILE_CAPACITY


class AntParticle:
    def __init__(self, lx=None, ly=None):
        self.lx = lx if lx is not None else random.uniform(1.5, 8.5)
        self.ly = ly if ly is not None else random.uniform(1.5, 8.5)
        self.vx = random.uniform(-0.18, 0.18)
        self.vy = random.uniform(-0.18, 0.18)

    def update(self):
        self.lx += self.vx
        self.ly += self.vy
        if self.lx < 1.0 or self.lx > 9.0:
            self.vx *= -1
            self.lx = max(1.0, min(9.0, self.lx))
        if self.ly < 1.0 or self.ly > 9.0:
            self.vy *= -1
            self.ly = max(1.0, min(9.0, self.ly))
        if random.random() < 0.15:
            self.vx = max(-0.25, min(0.25, self.vx + random.uniform(-0.06, 0.06)))
            self.vy = max(-0.25, min(0.25, self.vy + random.uniform(-0.06, 0.06)))


class MovingGroup:
    def __init__(self, owner, count, path_coords, speed_tiles_per_sec, carrying_flag=False, carrying_relic=False):
        self.owner = owner
        self.count = count
        self.path = path_coords
        self.speed = speed_tiles_per_sec * 0.5 if carrying_flag else speed_tiles_per_sec
        self.carrying_flag = carrying_flag
        self.carrying_relic = carrying_relic
        self.segment_idx = 0
        self.segment_progress = 0.0
        self.offsets = [
            (random.uniform(-2.2, 2.2), random.uniform(-2.2, 2.2))
            for _ in range(min(count, MAX_VISUAL_ANTS))
        ]

    def update(self, dt):
        if self.segment_idx >= len(self.path) - 1:
            return True
        r1, c1 = self.path[self.segment_idx]
        r2, c2 = self.path[min(self.segment_idx + 1, len(self.path) - 1)]
        step_len = 1.4142 if (r1 != r2 and c1 != c2) else 1.0
        self.segment_progress += (self.speed / step_len) * dt
        while self.segment_progress >= 1.0:
            self.segment_progress -= 1.0
            self.segment_idx += 1
            if self.segment_idx >= len(self.path) - 1:
                return True
        return False

    def get_current_logical_pos(self):
        r1, c1 = self.path[self.segment_idx]
        r2, c2 = self.path[min(self.segment_idx + 1, len(self.path) - 1)]
        return r1 + (r2 - r1) * self.segment_progress, c1 + (c2 - c1) * self.segment_progress


class CombatEffect:
    """Handles Turn-Phase Polish: pauses arriving units on the target tile with a flashing border and floating text."""
    def __init__(self, r, c, grp, duration=0.6):
        self.r = r
        self.c = c
        self.grp = grp
        self.total_duration = max(0.05, float(duration))
        self.timer = self.total_duration
        self.resolved = False
        self.popup_text = f"⚔ {grp.count}"
        self.popup_color = "#ffffff"

    def update(self, dt):
        self.timer -= dt
        return self.timer <= 0.0

    @property
    def progress(self) -> float:
        return max(0.0, min(1.0, 1.0 - (self.timer / self.total_duration)))


class Tile:
    def __init__(self, r, c):
        self.r = r
        self.c = c
        self.owner = 0
        self.units = 0
        self.is_obstacle = False
        self.terrain_type = "normal"
        self.ants = []

    def set_units(self, count):
        self.units = max(0, min(MAX_TILE_CAPACITY, int(count)))
        if self.units == 0 and not self.is_obstacle and self.terrain_type not in ["flag", "hill", "commander", "relic", "beacon"]:
            self.owner = 0
        
        target_visual_ants = min(self.units, MAX_VISUAL_ANTS)
        while len(self.ants) < target_visual_ants:
            self.ants.append(AntParticle())
        while len(self.ants) > target_visual_ants:
            self.ants.pop()