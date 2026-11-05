import socket
import threading
import pickle
import time
import csv
import json
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from models import MovingGroup


class NetworkMixin:
    def start_server_with_broadcast(self):
        self.start_server()
        if self.net_role == "server":
            threading.Thread(target=self._udp_broadcast_loop, daemon=True).start()

    def _udp_broadcast_loop(self):
        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            port = self.server_port_var.get()
            while self.net_role == "server":
                msg = pickle.dumps({"magic": "ANTGRID_LOBBY", "port": port})
                udp_sock.sendto(msg, ("<broadcast>", 50005))
                time.sleep(3.0)
        except Exception:
            pass

    def scan_lan_for_servers(self):
        if not self.server_listbox:
            return
        self.server_listbox.delete(0, tk.END)
        self.discovered_servers.clear()
        self.lbl_net_connection_status.config(text="Scanning local network...", foreground="#feca57")

        def _scan():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", 50005))
                sock.settimeout(3.0)
                start_t = datetime.now()
                while (datetime.now() - start_t).total_seconds() < 3.0:
                    try:
                        data, addr = sock.recvfrom(1024)
                        packet = pickle.loads(data)
                        if packet.get("magic") == "ANTGRID_LOBBY":
                            server_info = (addr[0], packet["port"])
                            if server_info not in self.discovered_servers:
                                self.discovered_servers.append(server_info)
                                self.server_listbox.insert(tk.END, f"Host IP: {addr[0]} | Port: {packet['port']}")
                    except socket.timeout:
                        break
                sock.close()
                self.lbl_net_connection_status.config(text=f"Scan complete. Found {len(self.discovered_servers)} lobby(s).", foreground="#2ecc71")
            except Exception as e:
                self.lbl_net_connection_status.config(text=f"Scan error: {e}", foreground="#ff5555")

        threading.Thread(target=_scan, daemon=True).start()

    def join_selected_discovered_server(self, event):
        selection = self.server_listbox.curselection()
        if not selection:
            return
        ip, port = self.discovered_servers[selection[0]]
        self.server_ip_var.set(ip)
        self.server_port_var.set(port)
        self.start_client()

    def export_ml_logs_to_csv(self):
        if not self.match_event_log:
            messagebox.showwarning("Warning", "No match event log recorded yet. Play a game first!")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "ElapsedSec", "Turn", "EventType", "DetailsJSON"])
                for ev in self.match_event_log:
                    writer.writerow([
                        ev["timestamp"], ev["match_elapsed_seconds"],
                        ev["turn"], ev["event_type"], json.dumps(ev["details"])
                    ])
            messagebox.showinfo("Success", f"ML Training logs exported to {file_path}!")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")

    def start_server(self):
        try:
            port = self.server_port_var.get()
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", port))
            self.server_socket.listen(3)
            self.net_role = "server"
            self.my_player_id = 1
            self.game_mode_var.set("LAN Socket Multiplayer")
            self.lbl_net_connection_status.config(text=f"Hosting on port {port} (Player 1)", foreground="#2ecc71")
            self.start_new_game()
            threading.Thread(target=self._server_accept_loop, daemon=True).start()
            messagebox.showinfo("Hosting Started", f"Server running on port {port}!")
            if self.notebook:
                self.notebook.select(self.tab_game)
        except Exception as e:
            messagebox.showerror("Server Error", f"Could not host: {e}")

    def _server_accept_loop(self):
        while self.server_socket and self.net_role == "server":
            try:
                conn, _ = self.server_socket.accept()
                player_id = len(self.client_connections) + 2
                if player_id > self.num_players_var.get():
                    conn.close()
                    continue
                self.client_connections.append((conn, player_id))
                conn.sendall(pickle.dumps({"type": "ASSIGN", "assigned_player_id": player_id}))
                threading.Thread(target=self._server_client_listener, args=(conn, player_id), daemon=True).start()
                self.broadcast_game_state()
            except Exception:
                break

    def _server_client_listener(self, conn, player_id):
        while self.net_role == "server":
            try:
                data = conn.recv(4096)
                if not data:
                    break
                self.handle_network_packet(pickle.loads(data), player_id)
            except Exception:
                break

    def start_client(self):
        try:
            ip, port = self.server_ip_var.get(), self.server_port_var.get()
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            self.net_role = "client"
            self.game_mode_var.set("LAN Socket Multiplayer")
            init_packet = pickle.loads(self.client_socket.recv(4096))
            self.my_player_id = init_packet.get("assigned_player_id", 2)
            self.lbl_net_connection_status.config(text=f"Connected to {ip}:{port} (Player {self.my_player_id})", foreground="#2ecc71")
            threading.Thread(target=self._client_listen_loop, daemon=True).start()
            messagebox.showinfo("Connected", f"Connected as Player {self.my_player_id}!")
            if self.notebook:
                self.notebook.select(self.tab_game)
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect: {e}")

    def _client_listen_loop(self):
        while self.client_socket and self.net_role == "client":
            try:
                data = self.client_socket.recv(8192)
                if not data:
                    break
                self.apply_network_packet(pickle.loads(data))
            except Exception:
                break

    def send_packet_to_server(self, packet):
        if self.client_socket and self.net_role == "client":
            try:
                self.client_socket.sendall(pickle.dumps(packet))
            except Exception:
                pass

    def broadcast_game_state(self):
        if self.net_role != "server":
            return
        state_packet = {
            "type": "STATE_UPDATE",
            "grid_data": [[(t.owner, t.units, t.is_obstacle, t.terrain_type) for t in row] for row in self.grid],
            "current_turn": self.current_turn_player,
            "turn_time": self.turn_time_left,
            "match_time": self.match_elapsed_seconds,
            "is_paused": self.is_paused,
            "moving_groups": [(g.owner, g.count, g.path, g.speed, g.segment_idx, g.segment_progress, g.offsets, g.carrying_flag, g.carrying_relic) for g in self.moving_groups]
        }
        data = pickle.dumps(state_packet)
        for conn, _ in self.client_connections:
            try:
                conn.sendall(data)
            except Exception:
                pass

    def handle_network_packet(self, packet, player_id):
        ptype = packet.get("type")
        if ptype == "DISPATCH" and packet.get("player_id") == self.current_turn_player:
            sr, sc = packet["source"]
            source_tile = self.grid[sr][sc]
            if source_tile.owner == player_id:
                self.dispatch_units(source_tile, packet["count"], packet["path"])
                self.broadcast_game_state()

    def apply_network_packet(self, packet):
        ptype = packet.get("type")
        if ptype == "STATE_UPDATE":
            grid_data = packet["grid_data"]
            for r in range(self.rows):
                for c in range(self.cols):
                    owner, units, is_obs, terr = grid_data[r][c]
                    self.grid[r][c].owner = owner
                    self.grid[r][c].is_obstacle = is_obs
                    self.grid[r][c].terrain_type = terr
                    self.grid[r][c].set_units(units)
            self.current_turn_player = packet["current_turn"]
            self.turn_time_left = packet["turn_time"]
            self.match_elapsed_seconds = packet.get("match_time", self.match_elapsed_seconds)
            self.is_paused = packet["is_paused"]
            self.moving_groups.clear()
            for owner, count, path, speed, s_idx, s_prog, offsets, flag, relic in packet["moving_groups"]:
                g = MovingGroup(owner, count, path, speed, flag, relic)
                g.segment_idx, g.segment_progress, g.offsets = s_idx, s_prog, offsets
                self.moving_groups.append(g)
            self.update_turn_banner()
            self.update_scoreboard()