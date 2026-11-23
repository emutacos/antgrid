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

    def _find_closest_extraction_goal(self, r, c, player_id, is_flag):
        """Finds the best return target for a captured flag (home flag base) or relic (owned factory)."""
        best_coord = None
        best_dist = 999
        if is_flag:
            home = getattr(self, "flag_home_coords", {}).get(player_id)
            if home:
                return home
        for tr in range(self.rows):
            for tc in range(self.cols):
                t = self.grid[tr][tc]
                if t.owner == player_id and not t.is_obstacle:
                    if (is_flag and t.terrain_type == "flag") or (not is_flag and t.terrain_type == "factory"):
                        d = abs(tr - r) + abs(tc - c)
                        if d < best_dist:
                            best_dist = d
                            best_coord = (tr, tc)
        return best_coord

    def execute_ai_point_action(self):
        p = self.current_turn_player
        difficulty = self.ai_difficulty_var.get()
        personality = self.ai_personality_var.get()

        # Priority 0: Escort any captured enemy Flag or Relic toward extraction point
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.grid[r][c]
                if t.owner == p and t.units > 1:
                    is_enemy_flag = (t.terrain_type == "flag" and getattr(t, "flag_owner", p) not in (0, p))
                    is_relic = (t.terrain_type == "relic")
                    if is_enemy_flag or is_relic:
                        goal = self._find_closest_extraction_goal(r, c, p, is_flag=is_enemy_flag)
                        send_count = max(1, t.units - 1)
                        reachable = self.compute_reachable_tiles(t, send_count, p)
                        if reachable:
                            if goal and goal in reachable:
                                self.dispatch_units(t, send_count, reachable[goal])
                                return
                            best_escort_path = None
                            best_goal_dist = 999
                            for (tr, tc), path in reachable.items():
                                dest_t = self.grid[tr][tc]
                                if dest_t.owner == p or dest_t.owner == 0:
                                    d = (abs(tr - goal[0]) + abs(tc - goal[1])) if goal else len(path)
                                    if d < best_goal_dist:
                                        best_goal_dist = d
                                        best_escort_path = path
                            if best_escort_path:
                                self.dispatch_units(t, send_count, best_escort_path)
                                return

        # Gather owned tiles capable of dispatching units
        raw_tiles = [
            self.grid[r][c] for r in range(self.rows) for c in range(self.cols)
            if self.grid[r][c].owner == p and self.grid[r][c].units > 1
        ]
        if not raw_tiles:
            return

        # Filter to tiles that actually have at least one reachable move
        movable_tiles = []
        for t in raw_tiles:
            if self.compute_reachable_tiles(t, 1, p):
                movable_tiles.append(t)
        if not movable_tiles:
            return

        # Favor larger garrisons
        movable_tiles.sort(key=lambda t: t.units, reverse=True)
        candidate_sources = movable_tiles[:max(2, len(movable_tiles) // 2)]
        tile = random.choice(candidate_sources)

        source_border_dist = self.get_distance_to_closest_threat_or_border(tile.r, tile.c, p)

        # Protect VIP Commander or own Flag Base from over-draining when enemies are close
        is_vital_base = (
            (tile.terrain_type == "commander")
            or (tile.terrain_type == "flag" and getattr(tile, "flag_owner", p) == p)
        )
        if is_vital_base and source_border_dist <= 2:
            send_ratio = 0.35
        elif "Fortifier" in personality and tile.terrain_type == "fortress" and tile.units < 35:
            send_ratio = 0.35
        elif "Blitzkrieg" in personality:
            send_ratio = 0.85
        else:
            send_ratio = 0.55 if difficulty == "Easy" else 0.75

        send_count = max(1, int(tile.units * send_ratio))
        reachable = self.compute_reachable_tiles(tile, send_count, p)
        if not reachable:
            return

        best_target, best_score = None, -9999

        for (tr, tc), path in reachable.items():
            target_tile = self.grid[tr][tc]
            dist = len(path) - 1
            score = 0.0

            # 1. Objective Tile Priority
            if target_tile.terrain_type in ["hill", "relic", "beacon"]:
                score += 160 - dist * 4
            elif target_tile.terrain_type == "flag":
                flag_own = getattr(target_tile, "flag_owner", target_tile.owner)
                if flag_own not in (0, p):
                    score += 210 - dist * 4
                elif target_tile.owner != p:
                    # Reclaim own dropped/stolen flag
                    score += 240 - dist * 4
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
                    base_neutral -= 20

                if target_tile.terrain_type in ["fortress", "factory"]:
                    base_neutral += 35
                score += base_neutral

            # 3. Enemy Tile Evaluation (matches resolve_arrival's 0.75x fortress attack multiplier)
            elif target_tile.owner != p:
                required_to_win = (int(target_tile.units / 0.75) + 1) if target_tile.terrain_type == "fortress" else (target_tile.units + 1)
                can_win = send_count >= required_to_win

                if "Blitzkrieg" in personality:
                    score += (190 + target_tile.units) if can_win else 45
                elif "Fortifier" in personality:
                    score += (130 if target_tile.terrain_type == "fortress" else 90) if can_win else -90
                elif "Expansionist" in personality:
                    score += 110 if can_win else -60
                else:
                    score += (145 + target_tile.units - dist * 4) if can_win else (-50 if difficulty == "Hard" else 5)

            # 4. Friendly Territory (Logistics Highway & Fortress/Base Reinforcement)
            else:
                target_border_dist = self.get_distance_to_closest_threat_or_border(tr, tc, p)
                if "Fortifier" in personality and target_tile.terrain_type == "fortress" and target_tile.units < 60:
                    score += 85 - dist * 2
                elif target_tile.terrain_type in ("commander", "flag") and target_border_dist <= 2 and target_tile.units < 25:
                    score += 75 - dist * 2
                elif source_border_dist > 1 and target_border_dist < source_border_dist:
                    score += 45 + (source_border_dist - target_border_dist) * 15
                else:
                    score -= 35

            score += random.uniform(-8, 8)
            if score > best_score:
                best_score, best_target = score, path

        if best_target and (best_score > 0 or difficulty == "Easy"):
            self.dispatch_units(tile, send_count, best_target)