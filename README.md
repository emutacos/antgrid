<img width="1920" height="1080" alt="antgrid_b" src="https://github.com/user-attachments/assets/09efeedb-c96e-4eb0-bca8-ae69c6e29408" />
**AntGrid** is a real-time-animated, turn-based tactical territory game built in Python using `tkinter` and standard library networking. Command ant colonies across a customizable 2D grid, route reinforcements along friendly territory, capture strategic terrain, and outmaneuver AI personalities or LAN opponents.

## Features

* **Asymmetric Movement & Logistics:** Expand into adjacent neutral or enemy tiles (1-tile cap), or slide reserves across connected friendly territories up to your full movement range.
* **Multiple Victory Modes:**
  * **Total Supremacy:** Eliminate all rival colonies.
  * **Capture the Flag (`F`):** Steal an enemy flag and escort it back to your home base.
  * **King of the Hill (`*`):** Hold the central monolith for 30 seconds.
  * **VIP Commander (`@`):** Protect your commander while hunting enemy leaders.
  * **Relic Extraction (`$`):** Retrieve relics and extract them at any owned factory.
  * **Domination (`+`):** Control beacon nodes to drain enemy tickets.
* **Tactical Terrain:** Defend behind **Fortresses (`#`)** (+25% defense), boost unit generation on **Factories (`^`)**, and navigate around **Obstacles (`X`)**.
* **AI Personalities & Difficulty:** Play against *Balanced*, *Expansionist*, *Fortifier*, or *Blitzkrieg* AI profiles across Easy, Medium, and Hard difficulties.
* **Multiplayer & LAN Discovery:** Play solo vs. AI, local hotseat (2–4 players), or over LAN with automatic UDP lobby discovery and TCP state sync.
* **Built-In Level Editor & Themes:** Paint custom maps, export/import layouts via CSV, and switch between 6 retro/modern themes or build your own custom palette.

## Requirements & Running

* **Python 3.8+** (uses standard library modules only—no external `pip` packages required)
* **Tkinter** (included with standard Windows/macOS Python installs; on Linux/Termux, install `python3-tk`)

Project Structure
antgrid.py — Main application window, 30 FPS game loop, combat resolution, and UI tabs.

models.py — Core entities (Tile, AntParticle, MovingGroup, CombatEffect).

ai.py — Heuristic AI decision-making, carrier escort logic, and personality scoring.

network.py — UDP LAN lobby discovery and length-prefixed TCP multiplayer sync.

editor.py — Interactive map editor, preset loader, and CSV import/export.

config.py — Themes, preset map definitions, BGM patterns, and settings.ini persistence.

```bash
python antgrid.py

