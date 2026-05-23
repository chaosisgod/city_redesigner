import json
import urllib.request
import time

payload_base = {
    "grid": {
        "width": 20,
        "height": 20,
        "valid_tiles": [[True]*20]*20
    },
    "buildings": [
        {"id": "b1", "name": "Townhall", "width": 4, "height": 4, "road_type": 0, "color": "red"},
        {"id": "b2", "name": "House", "width": 2, "height": 2, "road_type": 1, "color": "blue"},
        {"id": "b3", "name": "Factory", "width": 3, "height": 3, "road_type": 2, "color": "green"}
    ],
    "townhall_fixed": True,
    "townhall_pos": None,
    "optimization_time": 2.0,
    "debug": False
}

solvers = ["random_greedy", "simulated_annealing", "backbone", "constraint_programming"]

for solver in solvers:
    payload = payload_base.copy()
    payload["solver_type"] = solver
    
    print(f"\n--- Testing Solver: {solver} ---")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/solve",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        start_time = time.time()
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            elapsed = time.time() - start_time
            print(f"Success! Status: OK. Score: {data.get('score')}. Elapsed time: {elapsed:.2f}s")
            print(f"Placed buildings: {len(data.get('placed_buildings', []))}")
            print(f"Placed roads: {len(data.get('placed_roads', []))}")
    except Exception as e:
        print(f"Failed! Error: {e}")
