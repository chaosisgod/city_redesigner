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
        {"id": "b1", "name": "Townhall", "width": 4, "height": 4, "road_type": 0, "color": "red"}
    ] + [
        {"id": f"b{i}", "name": "House", "width": 2, "height": 2, "road_type": 1, "color": "blue"} for i in range(2, 40)
    ],
    "townhall_fixed": True,
    "townhall_pos": None
}

req = SolveRequest(**payload)
t0 = time.time()
res = solve_layout(req)
t1 = time.time()

print(f"Time: {t1-t0:.4f}s")
print(f"Placed buildings: {len(res.placed_buildings)} / {len(payload['buildings'])}")
print(f"Placed roads: {len(res.placed_roads)}")

grid = [['.' for _ in range(20)] for _ in range(20)]
for r in res.placed_roads:
    grid[r.y][r.x] = '+'
for b in res.placed_buildings:
    char = 'T' if b.building_id == 'b1' else 'H'
    for dy in range(4 if char == 'T' else 2):
        for dx in range(4 if char == 'T' else 2):
            if 0 <= b.y+dy < 20 and 0 <= b.x+dx < 20:
                grid[b.y+dy][b.x+dx] = char
for row in grid:
    print(''.join(row))
