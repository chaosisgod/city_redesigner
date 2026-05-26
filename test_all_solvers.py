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
        {"id": "b1", "name": "Townhall", "width": 4, "height": 4, "road_type": 0, "color": "#eab308"},
        {"id": "b2", "name": "HouseA", "width": 2, "height": 2, "road_type": 1, "color": "#3b82f6"},
        {"id": "b3", "name": "FactoryA", "width": 3, "height": 3, "road_type": 2, "color": "#10b981"},
        {"id": "b4", "name": "HouseB", "width": 2, "height": 2, "road_type": 1, "color": "#3b82f6"},
        {"id": "b5", "name": "ShrineA", "width": 1, "height": 1, "road_type": 0, "color": "#a855f7"},
        {"id": "b6", "name": "ShrineB", "width": 1, "height": 1, "road_type": 0, "color": "#a855f7"},
        {"id": "b7", "name": "Market", "width": 3, "height": 2, "road_type": 1, "color": "#f97316"},
        {"id": "b8", "name": "Blacksmith", "width": 2, "height": 3, "road_type": 1, "color": "#64748b"},
        {"id": "b9", "name": "Tavern", "width": 2, "height": 2, "road_type": 1, "color": "#db2777"},
        {"id": "b10", "name": "FactoryB", "width": 3, "height": 3, "road_type": 2, "color": "#10b981"},
        {"id": "b11", "name": "StatueA", "width": 1, "height": 1, "road_type": 0, "color": "#a855f7"},
        {"id": "b12", "name": "StatueB", "width": 1, "height": 1, "road_type": 0, "color": "#a855f7"},
        {"id": "b13", "name": "Observatory", "width": 3, "height": 3, "road_type": 1, "color": "#06b6d4"},
        {"id": "b14", "name": "Theatre", "width": 4, "height": 3, "road_type": 2, "color": "#ec4899"},
        {"id": "b15", "name": "Park", "width": 2, "height": 1, "road_type": 0, "color": "#84cc16"}
    ],
    "townhall_fixed": True,
    "townhall_pos": None,
    "optimization_time": 3.0,
    "debug": False
}

solvers = ["random_greedy", "simulated_annealing", "evolutionary", "neural_network", "user_heuristic", "backbone", "constraint_programming"]

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
