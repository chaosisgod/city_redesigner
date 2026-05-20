# Forge of Empires (FoE) City Redesigner

An intelligent, interactive tool designed to plan and optimize layouts for Forge of Empires cities. With a backend optimization engine and a simple browser interface, you can lay out your townhall, buildings, and roads to maximize space efficiency.

---

## 🚀 Key Features

* **Interactive Grid Painter**: Paint and erase valid city tiles directly on a configurable grid to match your actual Forge of Empires expansion layout.
* **Building Catalog & Custom Inventory**: Add custom buildings with precise dimensions (Width × Height), road connection requirements (No Road, 1x1 Road, or 2x2 Road), and quantities.
* **Intelligent Layout Optimizer**: A parallelized, random-restart heuristic engine designed to maximize the number of placed buildings while minimizing the cost and total length of connected roads.
* **Smart BFS Road Pruning**: Post-placement pathfinding (Breadth-First Search) traces connections back to the Townhall and automatically prunes redundant or unnecessary road tiles.
* **FastAPI Backend**: Built with standard python concurrency, FastAPI, and Uvicorn for extremely low-latency communication and rapid optimizations.

---

## 🛠️ Architecture

* **Frontend**: HTML5 Canvas / Grid, Vanilla CSS (harmonious, modern dark mode palette), and clean interactive Javascript (`static/app.js`, `static/index.html`, `static/style.css`).
* **Backend**: FastAPI web server (`server.py`) wrapping a highly optimized Python-based layout solver (`solver.py`).
* **Multi-core Optimization**: Uses `ProcessPoolExecutor` to spawn multiple background optimization workers to run diverse random seeds in parallel, returning the globally best layout found.

---

## 📦 Getting Started

### 1. Prerequisites
Ensure you have Python 3.8+ installed on your system.

### 2. Install Dependencies
You'll need `fastapi`, `uvicorn`, and `pydantic` to run the web server. Install them via your favorite package manager:

```bash
pip install fastapi uvicorn pydantic
```

*(Optional)* If you are running inside a virtual environment (`venv`), make sure it is activated before installing.

### 3. Running the Server
Launch the server using:

```bash
python server.py
```

The server will spin up a local development environment. Open your browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 💡 How it Works

1. **Configure Grid**: Set your grid size (e.g., 20x20 or 40x40) and click **Apply Size**.
2. **Paint/Erase Map**: Mark which tiles on the grid are valid (available for placement) and which are blocked.
3. **Inventory Management**: Enter your buildings, including the **Townhall** (which serves as the root for all road paths).
4. **Optimize**: Hit **Optimize Layout**. The server spawns background solver threads to find the ideal layout, then streams the placed buildings and roads back to the visual interface.
