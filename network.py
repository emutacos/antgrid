import socket
import struct
import threading
import pickle
import time
import csv
import json
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from models import MovingGroup


def get_local_lan_ip():
    """Finds the actual active Wi-Fi / LAN IP address so Windows broadcasts out the right adapter."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"
    finally:
        s.close()


def send_framed_packet(sock, data_dict):
    """Serializes a dict with pickle and prefixes it with a 4-byte length header."""
    payload = pickle.dumps(data_dict)
    header = struct.pack(">I", len(payload))
    sock.sendall(header + payload)


def recv_exact(sock, num_bytes):
    """Reads exactly num_bytes from a TCP stream, handling split packets."""
    buf = bytearray()
    while len(buf) < num_bytes:
        chunk = sock.recv(num_bytes - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def recv_framed_packet(sock):
    """Reads a complete 4-byte length-prefixed packet from the socket."""
    raw_len = recv_exact(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack(">I", raw_len)[0]
    if msg_len <= 0 or msg_len > 10_000_000:
        return None
    payload = recv_exact(sock, msg_len)
    if not payload:
        return None
    return pickle.loads(payload)


class NetworkMixin:
    def start_server_with_broadcast(self):
        self.start_server()
        if self.net_role == "server":
            threading.Thread(target=self._udp_broadcast_loop, daemon=True).start()

    def _udp_broadcast_loop(self):
        udp_sock = None
        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            local_ip = get_local_lan_ip()
            # Bind specifically to the active Wi-Fi/LAN interface so Windows doesn't route to WSL/VPN
            if local_ip != "0.0.0.0":
                try:
                    udp_sock.bind((local_ip, 0))
                except Exception:
                    pass

            # Calculate directed subnet broadcast (e.g., 192.168.1.255) alongside global broadcast
            broadcast_targets = ["<broadcast>", "255.255.255.255"]
            if local_ip != "0.0.0.0" and "." in local_ip:
                subnet_bcast = local_ip.rsplit(".", 1)[0] + ".255"
                if subnet_bcast not in broadcast_targets:
                    broadcast_targets.append(subnet_bcast)

            port = self.server_port_var.get()
            msg = pickle.dumps({"magic": "ANTGRID_LOBBY", "port": port, "host_ip": local_ip})

            while self.net_role == "server":
                for target in broadcast_targets:
                    try:
                        udp_sock.sendto(msg, (target, 50005))
                    except Exception:
                        pass
                time.sleep(1.0)  # Broadcast every 1s so a 3.5s client scan catches at least 3 beacons
        except Exception:
            pass
        finally:
            if udp_sock:
                try:
                    udp_sock.close()
                except Exception:
                    pass

    def scan_lan_for_servers(self):
        if not self.server_listbox:
            return
        self.server_listbox.delete(0, tk.END)
        self.discovered_servers.clear()
        self.lbl_net_connection_status.config(text="Scanning local network...", foreground="#feca57")

        def _scan():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", 50005))
                sock.settimeout(0.5)
                start_t = time.time()
                while (time.time() - start_t) < 3.5:
                    try:
                        data, addr = sock.recvfrom(1024)
                        packet = pickle.loads(data)
                        if packet.get("magic") == "ANTGRID_LOBBY":
                            host_ip = addr[0]
                            if host_ip in ("0.0.0.0", "127.0.0.1") and packet.get("host_ip"):
                                host_ip = packet["host_ip"]
                            server_info = (host_ip, packet["port"])
                            if server_info not in self.discovered_servers:
                                self.discovered_servers.append(server_info)
                                self.root.after(
                                    0,
                                    lambda ip=host_ip, p=packet["port"]: self.server_listbox.insert(
                                        tk.END, f"Host IP: {ip} | Port: {p}"
                                    )
                                )
                    except socket.timeout:
                        continue
                self.root.after(
                    0,
                    lambda: self.lbl_net_connection_status.config(
                        text=f"Scan complete. Found {len(self.discovered_servers)} lobby(s).",
                        foreground="#2ecc71"
                    )
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda err=e: self.lbl_net_connection_status.config(
                        text=f"Scan error: {err}", foreground="#ff5555"
                    )
                )
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

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
            self.client_connections.clear()
            self._last_broadcast_time = 0.0
            self.game_mode_var.set("LAN Socket Multiplayer")
            local_ip = get_local_lan_ip()
            self.lbl_net_connection_status.config(
                text=f"Hosting on {local_ip}:{port} (Player 1)", foreground="#2ecc71"
            )
            self.start_new_game()
            threading.Thread(target=self._server_accept_loop, daemon=True).start()
            messagebox.showinfo("Hosting Started", f"Server running on {local_ip}:{port}!")
            if self.notebook:
                self.notebook.select(self.tab_game)
        except Exception as e:
            messagebox.showerror("Server Error", f"Could not host: {e}")

    def _server_accept_loop(self):
        while self.server_socket and self.net_role == "server":
            try:
                conn, _ = self.server_socket.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                player_id = len(self.client_connections) + 2
                if player_id > self.num_players_var.get():
                    conn.close()
                    continue
                self.client_connections.append((conn, player_id))
                send_framed_packet(conn, {"type": "ASSIGN", "assigned_player_id": player_id})
                threading.Thread(
                    target=self._server_client_listener, args=(conn, player_id), daemon=True
                ).start()
                self.root.after(0, lambda: self.broadcast_game_state(force=True))
            except Exception:
                break

    def _server_client_listener(self, conn, player_id):
        # Blocking read loop with no timeout for waiting on client actions
        conn.settimeout(None)
        while self.net_role == "server":
            try:
                packet = recv_framed_packet(conn)
                if packet is None:
                    break
                # Schedule packet handling safely on the main Tkinter UI thread
                self.root.after(0, lambda pkt=packet, pid=player_id: self.handle_network_packet(pkt, pid))
            except Exception:
                break

    def start_client(self):
        try:
            ip, port = self.server_ip_var.get(), self.server_port_var.get()
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client_socket.settimeout(5.0)
            self.client_socket.connect((ip, port))
            self.net_role = "client"
            self.game_mode_var.set("LAN Socket Multiplayer")
            init_packet = recv_framed_packet(self.client_socket)
            if not init_packet:
                raise ConnectionError("Did not receive initial assignment from host.")
            self.my_player_id = init_packet.get("assigned_player_id", 2)
            self.client_socket.settimeout(None)
            self.lbl_net_connection_status.config(
                text=f"Connected to {ip}:{port} (Player {self.my_player_id})", foreground="#2ecc71"
            )
            threading.Thread(target=self._client_listen_loop, daemon=True).start()
            messagebox.showinfo("Connected", f"Connected as Player {self.my_player_id}!")
            if self.notebook:
                self.notebook.select(self.tab_game)
        except Exception as e:
            self.net_role = "local"
            messagebox.showerror("Connection Error", f"Could not connect: {e}")

    def _client_listen_loop(self):
        while self.client_socket and self.net_role == "client":
            try:
                packet = recv_framed_packet(self.client_socket)
                if packet is None:
                    break
                # Marshal UI and state updates onto the main Tkinter thread to prevent Tcl/Tk deadlocks
                self.root.after(0, lambda pkt=packet: self.apply_network_packet(pkt))
            except Exception:
                break

    def send_packet_to_server(self, packet):
        if self.client_socket and self.net_role == "client":
            try:
                self.client_socket.settimeout(0.5)
                send_framed_packet(self.client_socket, packet)
                self.client_socket.settimeout(None)
            except Exception:
                pass

    def broadcast_game_state(self, force=False):
        if self.net_role != "server" or not self.client_connections:
            return

        # Built-in rate limiter: cap continuous game_loop broadcasts to ~10 Hz (every 100ms)
        # so the TCP socket isn't flooded 30 times a second, while still allowing immediate forced updates.
        now = time.time()
        last_t = getattr(self, "_last_broadcast_time", 0.0)
        if not force and (now - last_t) < 0.10:
            return
        self._last_broadcast_time = now

        state_packet = {
            "type": "STATE_UPDATE",
            "rows": self.rows,
            "cols": self.cols,
            "num_players": self.num_players,
            "grid_data": [[(t.owner, t.units, t.is_obstacle, t.terrain_type) for t in row] for row in self.grid],
            "current_turn": self.current_turn_player,
            "turn_time": self.turn_time_left,
            "match_time": self.match_elapsed_seconds,
            "is_paused": self.is_paused,
            "moving_groups": [
                (g.owner, g.count, g.path, g.speed, g.segment_idx, g.segment_progress, g.offsets, g.carrying_flag, g.carrying_relic)
                for g in self.moving_groups
            ]
        }

        payload = pickle.dumps(state_packet)
        framed_data = struct.pack(">I", len(payload)) + payload

        dead_clients = []
        for conn, pid in list(self.client_connections):
            try:
                conn.settimeout(0.2)  # Prevent main UI thread from freezing if a client's buffer fills
                conn.sendall(framed_data)
            except socket.timeout:
                # Client is temporarily lagging; skip this frame without disconnecting
                pass
            except Exception:
                dead_clients.append((conn, pid))
            finally:
                try:
                    conn.settimeout(None)
                except Exception:
                    pass

        for dc in dead_clients:
            if dc in self.client_connections:
                self.client_connections.remove(dc)
            try:
                dc[0].close()
            except Exception:
                pass

    def handle_network_packet(self, packet, player_id):
        ptype = packet.get("type")
        if ptype == "DISPATCH" and packet.get("player_id") == self.current_turn_player:
            sr, sc = packet["source"]
            source_tile = self.grid[sr][sc]
            if source_tile.owner == player_id:
                self.dispatch_units(source_tile, packet["count"], packet["path"])
                self.broadcast_game_state(force=True)

    def apply_network_packet(self, packet):
        ptype = packet.get("type")
        if ptype == "STATE_UPDATE":
            grid_data = packet["grid_data"]
            r_cnt = packet.get("rows", len(grid_data))
            c_cnt = packet.get("cols", len(grid_data[0]) if grid_data else 0)
            self.num_players = packet.get("num_players", self.num_players)

            # Rebuild client grid automatically if host has a different map size
            if r_cnt != self.rows or c_cnt != self.cols:
                from models import Tile
                self.rows, self.cols = r_cnt, c_cnt
                self.grid = [[Tile(r, c) for c in range(self.cols)] for r in range(self.rows)]

            for r in range(self.rows):
                for c in range(self.cols):
                    owner, units, is_obs, terr = grid_data[r][c]
                    tile = self.grid[r][c]
                    tile.owner = owner
                    tile.is_obstacle = is_obs
                    tile.terrain_type = terr
                    # Only call set_units when the unit count actually changed to avoid resetting ant positions every tick
                    if tile.units != units:
                        tile.set_units(units)

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