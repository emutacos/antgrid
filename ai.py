import random


class AIMixin:
    def get_distance_to_closest_threat_or_border(self, r, c, player_id):
        min_dist = 999
        for tr in range(self.rows):
            for tc in range(self.cols):
                if self.grid[tr][tc].owner != player_id and not self.grid[tr][tc].is_obstacle:
                    d = abs(tr - r) + abs(tc - c)
                    if d < min_dist:
                        min_dist = d
        return min_dist

    def execute_ai_point_action(self):
        p = self.current_turn_player
        my_tiles = [
            self.grid[r][c] for r in range(self.rows) for c in range(self.cols)
            if self.grid[r][c].owner == p and self.grid[r][c].units > 1
        ]
        if not my_tiles:
            return

        difficulty = self.ai_difficulty_var.get()
        personality = self.ai_personality_var.get()

        # Sort candidate source tiles by garrison size (favor larger stacks)
        my_tiles.sort(key=lambda t: t.units, reverse=True)
        candidate_sources = my_tiles[:max(2, len(my_tiles) // 2)]
        tile = random.choice(candidate_sources)

        if "Fortifier" in personality and tile.terrain_type == "fortress" and tile.units < 35:
            # Fortifier holds back in fortresses until a large stack is built
            send_ratio = 0.35
        elif "Blitzkrieg" in personality:
            send_ratio = 0.85
        else:
            send_ratio = 0.55 if difficulty == "Easy" else 0.75

        send_count = max(1, int(tile.units * send_ratio))
        reachable = self.compute_reachable_tiles(tile, send_count, p)
        if not reachable:
            return

        source_border_dist = self.get_distance_to_closest_threat_or_border(tile.r, tile.c, p)
        best_target, best_score = None, -9999

        for (tr, tc), path in reachable.items():
            target_tile = self.grid[tr][tc]
            dist = len(path) - 1
            score = 0.0

            # 1. Objective Tile Priority
            if target_tile.terrain_type in ["hill", "relic", "flag", "beacon"]:
                score += 160 - dist * 4
            elif target_tile.terrain_type == "commander" and target_tile.owner not in (0, p):
                score += 300 if "Blitzkrieg" in personality else 220

            # 2. Unclaimed Neutral Tile Evaluation
            if target_tile.owner == 0:
                base_neutral = 65 - dist * 5
                if "Expansionist" in personality:
                    base_neutral += 95
                    if target_tile.terrain_type == "factory":
                        base_neutral += 85
                elif "Fortifier" in personality:
                    if target_tile.terrain_type == "fortress":
                        base_neutral += 110
                elif "Blitzkrieg" in personality:
                    base_neutral -= 20  # Blitzkrieg prefers attacking enemies over neutral farming

                if target_tile.terrain_type in ["fortress", "factory"]:
                    base_neutral += 35
                score += base_neutral

            # 3. Enemy Tile Evaluation
            elif target_tile.owner != p:
                effective_defense = int(target_tile.units * 1.25) if target_tile.terrain_type == "fortress" else target_tile.units
                can_win = send_count > effective_defense

                if "Blitzkrieg" in personality:
                    score += (190 + target_tile.units) if can_win else 45
                elif "Fortifier" in personality:
                    score += (130 if target_tile.terrain_type == "fortress" else 90) if can_win else -90
                elif "Expansionist" in personality:
                    score += 110 if can_win else -60
                else:  # Balanced
                    score += (145 + target_tile.units - dist * 4) if can_win else (-50 if difficulty == "Hard" else 5)

            # 4. Friendly Territory (Logistics Highway & Fortress Stacking)
            else:
                target_border_dist = self.get_distance_to_closest_threat_or_border(tr, tc, p)
                if "Fortifier" in personality and target_tile.terrain_type == "fortress" and target_tile.units < 60:
                    score += 85 - dist * 2
                elif source_border_dist > 1 and target_border_dist < source_border_dist:
                    # Slide rear reserves toward the frontline along the Friendly Highway
                    score += 45 + (source_border_dist - target_border_dist) * 15
                else:
                    score -= 35

            score += random.uniform(-8, 8)
            if score > best_score:
                best_score, best_target = score, path

        if best_target and (best_score > 0 or difficulty == "Easy"):
            self.dispatch_units(tile, send_count, best_target)