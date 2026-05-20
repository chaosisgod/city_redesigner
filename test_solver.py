import json
import urllib.request

payload = {
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
    "townhall_pos": None
}

req = urllib.request.Request("http://127.0.0.1:8000/api/solve", data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode('utf-8'))
    print(json.dumps(data, indent=2))
