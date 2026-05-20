from models import SolveRequest, CityGrid, Building
from solver import solve_layout
import time

payload = {
    "grid": {
        "width": 20,
        "height": 20,
        "valid_tiles": [[True]*20]*20
    },
    "buildings": [
        {"id": "th1", "name": "Townhall", "width": 4, "height": 4, "road_type": 0, "color": "red"},
        {"id": "h1", "name": "House", "width": 2, "height": 2, "road_type": 1, "color": "blue"},
        {"id": "h2", "name": "House2", "width": 2, "height": 2, "road_type": 1, "color": "blue"},
        {"id": "f1", "name": "Factory", "width": 3, "height": 3, "road_type": 2, "color": "green"},
        {"id": "f2", "name": "Factory2", "width": 3, "height": 3, "road_type": 2, "color": "green"}
    ],
    "townhall_fixed": True,
    "townhall_pos": None,
    "optimization_time": 1.0,
    "debug": False
}

if __name__ == '__main__':
    req = SolveRequest(**payload)
    t0 = time.time()
    res = solve_layout(req)
    t1 = time.time()

    print(f"Time: {t1-t0:.4f}s")
    print(f"Placed {len(res.placed_buildings)} / {len(payload['buildings'])} buildings")
    print(f"Placed {len(res.placed_roads)} roads")
    print("Buildings:", res.placed_buildings)
