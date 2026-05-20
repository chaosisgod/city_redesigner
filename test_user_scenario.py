from models import SolveRequest, CityGrid, Building
from solver import solve_layout
import time

payload = {
    "grid": {
        "width": 10,
        "height": 10,
        "valid_tiles": [[True]*10 for _ in range(10)]
    },
    "buildings": [
        {"id": "th", "name": "Townhall", "width": 3, "height": 3, "road_type": 0, "color": "red"},
        {"id": "b1", "name": "B1", "width": 2, "height": 2, "road_type": 1, "color": "blue"},
        {"id": "b2", "name": "B2", "width": 2, "height": 2, "road_type": 1, "color": "blue"},
        {"id": "b3", "name": "B3", "width": 2, "height": 2, "road_type": 1, "color": "blue"}
    ],
    "townhall_fixed": True,
    "townhall_pos": [3, 3],
    "optimization_time": 2.0,
    "debug": True
}

if __name__ == '__main__':
    req = SolveRequest(**payload)
    res = solve_layout(req)
    print("Placed buildings:", res.placed_buildings)
    print("Placed roads:", res.placed_roads)
    print("Score:", res.score)
