from models import SolveRequest, SolveResponse, PlacedBuilding, PlacedRoad
import random
import time
import math
import os
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

def solve_single_worker(request: SolveRequest, seed: int) -> SolveResponse:
    random.seed(seed)
    
    grid_w = request.grid.width
    grid_h = request.grid.height
    valid_tiles = request.grid.valid_tiles
    
    # Identify connection hub
    buildings = request.buildings.copy()
    hub = next((b for b in buildings if b.name.lower().startswith('townhall') or b.name.lower().startswith('embassy')), None)
    if not hub:
        return SolveResponse(placed_buildings=[], placed_roads=[], score=0.0)
        
    other_buildings = [b for b in buildings if b.id != hub.id]
    
    def is_tile_valid(x, y):
        if x < 0 or y < 0 or x >= grid_w or y >= grid_h:
            return False
        return valid_tiles[y][x]

    # Hub placement
    hub_w, hub_h = hub.width, hub.height
    if request.townhall_fixed and request.townhall_pos:
        hub_x, hub_y = request.townhall_pos
    else:
        hub_x = max(0, (grid_w - hub_w) // 2)
        hub_y = max(0, (grid_h - hub_h) // 2)

    for dy in range(hub_h):
        for dx in range(hub_w):
            if not is_tile_valid(hub_x + dx, hub_y + dy):
                found = False
                for dist in range(1, max(grid_w, grid_h)):
                    for sy in range(-dist, dist + 1):
                        for sx in range(-dist, dist + 1):
                            cx, cy = hub_x + sx, hub_y + sy
                            fit = True
                            for hdy in range(hub_h):
                                for hdx in range(hub_w):
                                    if not is_tile_valid(cx + hdx, cy + hdy):
                                        fit = False
                                        break
                                if not fit: break
                            if fit:
                                hub_x, hub_y = cx, cy
                                found = True
                                break
                        if found: break
                    if found: break
                break

    hub_tiles = set((hub_x + dx, hub_y + dy) for dy in range(hub_h) for dx in range(hub_w))

    def evaluate_state(placed_b_map):
        occupied = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]
        
        for tx, ty in hub_tiles:
            if 0 <= tx < grid_w and 0 <= ty < grid_h:
                occupied[ty][tx] = True
                
        final_placed_b = [PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y)]
        
        b_list = []
        for b in other_buildings:
            if b.id in placed_b_map:
                b_list.append(b)
                
        valid_placed_b_map = {}
        for b in b_list:
            bx, by = placed_b_map[b.id]
            overlap = False
            for dy in range(b.height):
                for dx in range(b.width):
                    rx, ry = bx + dx, by + dy
                    if rx < 0 or ry < 0 or rx >= grid_w or ry >= grid_h or occupied[ry][rx]:
                        overlap = True
                        break
                if overlap: break
                
            if not overlap:
                for dy in range(b.height):
                    for dx in range(b.width):
                        occupied[by+dy][bx+dx] = True
                final_placed_b.append(PlacedBuilding(building_id=b.id, x=bx, y=by))
                valid_placed_b_map[b.id] = (bx, by)

        roads = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
        for tx, ty in hub_tiles:
            roads[ty][tx] = 3
            
        final_placed_roads = []
        
        def find_shortest_road_path(start_tiles, req_type):
            queue = []
            visited = {}
            for sx, sy in start_tiles:
                if 0 <= sx < grid_w and 0 <= sy < grid_h:
                    # Only allow starting from tiles that are either free or already roads.
                    # This prevents placing a road on top of a tile occupied by another building.
                    if not occupied[sy][sx] or roads[sy][sx] > 0:
                        queue.append((sx, sy, 0))
                        visited[(sx, sy)] = None
                    
            head = 0
            found_dest = None
            
            while head < len(queue):
                cx, cy, dist = queue[head]
                head += 1
                
                if roads[cy][cx] >= req_type:
                    found_dest = (cx, cy)
                    break
                    
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < grid_w and 0 <= ny < grid_h:
                        if (nx, ny) not in visited:
                            if not occupied[ny][nx] or roads[ny][nx] > 0:
                                visited[(nx, ny)] = (cx, cy)
                                queue.append((nx, ny, dist + 1))
                                
            if found_dest:
                path = []
                curr = found_dest
                while curr is not None:
                    path.append(curr)
                    curr = visited[curr]
                return path[::-1]
            return None

        disconnected_count = 0
        connected_placed_b = [PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y)]
        for pb in final_placed_b:
            if pb.building_id == hub.id: continue
            b = next(x for x in other_buildings if x.id == pb.building_id)
            if b.road_type == 0:
                connected_placed_b.append(pb)
                continue
            
            boundary = set()
            for dx in range(b.width):
                boundary.add((pb.x + dx, pb.y - 1))
                boundary.add((pb.x + dx, pb.y + b.height))
            for dy in range(b.height):
                boundary.add((pb.x - 1, pb.y + dy))
                boundary.add((pb.x + b.width, pb.y + dy))
                
            path = find_shortest_road_path(boundary, b.road_type)
            if path:
                for rx, ry in path:
                    roads[ry][rx] = max(roads[ry][rx], b.road_type)
                    occupied[ry][rx] = True
                connected_placed_b.append(pb)
            else:
                disconnected_count += 1

        road_tiles_used = set()
        for y in range(grid_h):
            for x in range(grid_w):
                if roads[y][x] == 2 and (x, y) not in road_tiles_used:
                    if x + 1 < grid_w and y + 1 < grid_h:
                        final_placed_roads.append(PlacedRoad(x=x, y=y, type=2))
                        for dy in range(2):
                            for dx in range(2):
                                road_tiles_used.add((x + dx, y + dy))
                    else:
                        final_placed_roads.append(PlacedRoad(x=x, y=y, type=1))
                        road_tiles_used.add((x, y))
                elif roads[y][x] == 1 and (x, y) not in road_tiles_used:
                    final_placed_roads.append(PlacedRoad(x=x, y=y, type=1))
                    road_tiles_used.add((x, y))

        num_placed = len(connected_placed_b)
        road_cost = sum(1 for pr in final_placed_roads for dy in range(pr.type) for dx in range(pr.type))
        score = num_placed * 10000 - road_cost - (disconnected_count * 200000)
        
        return connected_placed_b, final_placed_roads, score, valid_placed_b_map

    current_b_map = {}
    b_order = other_buildings.copy()
    random.shuffle(b_order)
    
    for b in b_order:
        placed = False
        for _ in range(20):
            rx = random.randint(0, grid_w - b.width)
            ry = random.randint(0, grid_h - b.height)
            overlap_hub = False
            for dy in range(b.height):
                for dx in range(b.width):
                    if (rx+dx, ry+dy) in hub_tiles or not is_tile_valid(rx+dx, ry+dy):
                        overlap_hub = True
                        break
                if overlap_hub: break
                
            if not overlap_hub:
                current_b_map[b.id] = (rx, ry)
                placed = True
                break

    best_placed_b, best_placed_roads, best_score, current_b_map = evaluate_state(current_b_map)
    
    temp = 1000.0
    cooling_rate = 0.992
    iterations = request.annealing_iterations or 1500
    
    for i in range(iterations):
        if i % 10 == 0 and os.path.exists("abort.lock"):
            break
        temp *= cooling_rate
        if not other_buildings: break
        
        next_b_map = current_b_map.copy()
        perturb_type = random.choice(["shift", "swap", "add_remove"])
        
        if perturb_type == "shift" and next_b_map:
            b_id = random.choice(list(next_b_map.keys()))
            b = next(x for x in other_buildings if x.id == b_id)
            nx = random.randint(0, grid_w - b.width)
            ny = random.randint(0, grid_h - b.height)
            next_b_map[b_id] = (nx, ny)
            
        elif perturb_type == "swap" and len(next_b_map) >= 2:
            id1, id2 = random.sample(list(next_b_map.keys()), 2)
            next_b_map[id1], next_b_map[id2] = next_b_map[id2], next_b_map[id1]
            
        else:
            b = random.choice(other_buildings)
            if b.id in next_b_map:
                del next_b_map[b.id]
            else:
                rx = random.randint(0, grid_w - b.width)
                ry = random.randint(0, grid_h - b.height)
                next_b_map[b.id] = (rx, ry)

        next_placed_b, next_placed_roads, next_score, next_valid_b_map = evaluate_state(next_b_map)
        
        delta = next_score - best_score
        if delta > 0 or (temp > 0.01 and random.uniform(0, 1) < math.exp(delta / temp)):
            current_b_map = next_valid_b_map
            best_placed_b = next_placed_b
            best_placed_roads = next_placed_roads
            best_score = next_score

    num_1x1 = sum(1 for r in best_placed_roads if r.type == 1)
    num_2x2 = sum(1 for r in best_placed_roads if r.type == 2)
    
    return SolveResponse(
        placed_buildings=best_placed_b,
        placed_roads=best_placed_roads,
        score=best_score,
        num_1x1_roads=num_1x1,
        num_2x2_roads=num_2x2
    )

def solve_layout(request: SolveRequest) -> SolveResponse:
    num_workers = max(1, (os.cpu_count() or 4) - 1)
    
    if request.optimization_time <= 0.1 or num_workers <= 1 or request.debug:
        return solve_single_worker(request, random.randint(0, 1000000))
        
    best_response = None
    best_score = -float('inf')
    
    seeds = [random.randint(0, 1000000) for _ in range(num_workers)]
    
    ctx = multiprocessing.get_context('spawn')
    
    with ProcessPoolExecutor(max_workers=num_workers, mp_context=ctx) as executor:
        futures = [executor.submit(solve_single_worker, request, seed) for seed in seeds]
        for future in as_completed(futures):
            if os.path.exists("abort.lock"):
                break
            try:
                res = future.result()
                if res and res.score > best_score:
                    best_score = res.score
                    best_response = res
            except Exception as e:
                print(f"Annealing worker process failed: {e}")
                
    return best_response
