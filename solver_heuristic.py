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

    # =========================================================================
    # HEURISTIC SEEDING PHASE
    # =========================================================================
    
    init_roads = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
    init_occupied = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]
    
    for tx, ty in hub_tiles:
        if 0 <= tx < grid_w and 0 <= ty < grid_h:
            init_occupied[ty][tx] = True
            init_roads[ty][tx] = 3

    # Partition other buildings
    needs_2 = [b for b in other_buildings if b.road_type == 2]
    needs_1 = [b for b in other_buildings if b.road_type == 1]
    needs_0 = [b for b in other_buildings if b.road_type == 0]

    # Subdivide needs_2 into squares and rectangles
    needs_2_squares = [b for b in needs_2 if b.width == b.height]
    needs_2_rects = [b for b in needs_2 if b.width != b.height]
    # Sort by area descending
    needs_2_rects.sort(key=lambda b: b.width * b.height, reverse=True)
    needs_2_squares.sort(key=lambda b: b.width * b.height, reverse=True)
    needs_2_sorted = needs_2_rects + needs_2_squares

    # Subdivide needs_1 into wider and taller
    needs_1_wider = [b for b in needs_1 if b.width > b.height]
    needs_1_taller = [b for b in needs_1 if b.width <= b.height]
    # Sort by area descending
    needs_1_wider.sort(key=lambda b: b.width * b.height, reverse=True)
    needs_1_taller.sort(key=lambda b: b.width * b.height, reverse=True)
    needs_1_sorted = needs_1_wider + needs_1_taller

    # Seeding tracking
    seeded_b_map = {}
    
    # 1. Place the largest 2x2 building in a corner (Top-Left is a natural choice)
    placed_largest_2 = False
    largest_2_b = None
    if needs_2_sorted:
        largest_2_b = needs_2_sorted[0]
        # Search for valid slot in top-left region (0, 0)
        for cy in range(grid_h - largest_2_b.height + 1):
            for cx in range(grid_w - largest_2_b.width + 1):
                if cx <= 3 and cy <= 3:
                    fit = True
                    for dy in range(largest_2_b.height):
                        for dx in range(largest_2_b.width):
                            if init_occupied[cy+dy][cx+dx]:
                                fit = False
                                break
                        if not fit: break
                    if fit:
                        seeded_b_map[largest_2_b.id] = (cx, cy)
                        for dy in range(largest_2_b.height):
                            for dx in range(largest_2_b.width):
                                init_occupied[cy+dy][cx+dx] = True
                        placed_largest_2 = True
                        break
            if placed_largest_2: break

    # 2. Build the straight 2-lane road from corner towards Townhall
    # We will lay a straight 2-lane horizontal or vertical backbone
    if placed_largest_2 and largest_2_b:
        c_x, c_y = seeded_b_map[largest_2_b.id]
        
        # Decide straight backbone direction (prefer horizontal or vertical to reach Townhall)
        if abs(hub_x - c_x) > abs(hub_y - c_y):
            # Run horizontal straight road at row y = c_y + largest_2_b.height (or nearby)
            ry = min(grid_h - 2, c_y + largest_2_b.height)
            for rx in range(grid_w):
                if is_tile_valid(rx, ry):
                    init_roads[ry][rx] = max(init_roads[ry][rx], 2)
                    init_occupied[ry][rx] = True
                    if ry + 1 < grid_h and is_tile_valid(rx, ry + 1):
                        init_roads[ry + 1][rx] = max(init_roads[ry + 1][rx], 2)
                        init_occupied[ry + 1][rx] = True
                        
            # Populate remaining 2x2 rectangles on both sides, oriented on shorter side
            for b in needs_2_sorted:
                if b.id in seeded_b_map: continue
                
                placed = False
                # Shorter side alignment: for horizontal road, we touch along width, so we prefer width < height
                # Try placing above/below the road
                for cx in range(grid_w - b.width + 1):
                    for cy in [ry - b.height, ry + 2]:
                        if 0 <= cy < grid_h - b.height + 1:
                            fit = True
                            for dy in range(b.height):
                                for dx in range(b.width):
                                    if init_occupied[cy+dy][cx+dx]:
                                        fit = False
                                        break
                                if not fit: break
                            if fit:
                                # Prioritize width < height
                                if b.width <= b.height or random.random() < 0.2:
                                    seeded_b_map[b.id] = (cx, cy)
                                    for dy in range(b.height):
                                        for dx in range(b.width):
                                            init_occupied[cy+dy][cx+dx] = True
                                    placed = True
                                    break
                    if placed: break
        else:
            # Run vertical straight road at column x = c_x + largest_2_b.width
            rx = min(grid_w - 2, c_x + largest_2_b.width)
            for ry in range(grid_h):
                if is_tile_valid(rx, ry):
                    init_roads[ry][rx] = max(init_roads[ry][rx], 2)
                    init_occupied[ry][rx] = True
                    if rx + 1 < grid_w and is_tile_valid(rx + 1, ry):
                        init_roads[ry][rx + 1] = max(init_roads[ry][rx + 1], 2)
                        init_occupied[ry][rx + 1] = True
                        
            # Populate remaining 2x2 rectangles on both sides
            for b in needs_2_sorted:
                if b.id in seeded_b_map: continue
                
                placed = False
                # Shorter side alignment: for vertical road, we touch along height, so we prefer height < width
                for cy in range(grid_h - b.height + 1):
                    for cx in [rx - b.width, rx + 2]:
                        if 0 <= cx < grid_w - b.width + 1:
                            fit = True
                            for dy in range(b.height):
                                for dx in range(b.width):
                                    if init_occupied[cy+dy][cx+dx]:
                                        fit = False
                                        break
                                if not fit: break
                            if fit:
                                if b.height <= b.width or random.random() < 0.2:
                                    seeded_b_map[b.id] = (cx, cy)
                                    for dy in range(b.height):
                                        for dx in range(b.width):
                                            init_occupied[cy+dy][cx+dx] = True
                                    placed = True
                                    break
                    if placed: break

    # 3. Place largest 1x1 building in another corner (Bottom-Right is a natural choice)
    placed_largest_1 = False
    largest_1_b = None
    if needs_1_sorted:
        largest_1_b = needs_1_sorted[0]
        # Search for valid slot in bottom-right region
        for cy in range(grid_h - largest_1_b.height, -1, -1):
            for cx in range(grid_w - largest_1_b.width, -1, -1):
                if cx >= grid_w - 4 and cy >= grid_h - 4:
                    fit = True
                    for dy in range(largest_1_b.height):
                        for dx in range(largest_1_b.width):
                            if init_occupied[cy+dy][cx+dx]:
                                fit = False
                                break
                        if not fit: break
                    if fit:
                        seeded_b_map[largest_1_b.id] = (cx, cy)
                        for dy in range(largest_1_b.height):
                            for dx in range(largest_1_b.width):
                                init_occupied[cy+dy][cx+dx] = True
                        placed_largest_1 = True
                        break
            if placed_largest_1: break

    # 4. Build 1-lane road along side walls of the map and align 1x1 buildings
    if placed_largest_1 and largest_1_b:
        c1_x, c1_y = seeded_b_map[largest_1_b.id]
        
        # Lay a 1-lane road along the bottom edge
        bottom_y = grid_h - 1
        for rx in range(grid_w):
            if is_tile_valid(rx, bottom_y):
                init_roads[bottom_y][rx] = max(init_roads[bottom_y][rx], 1)
                init_occupied[bottom_y][rx] = True
                
        # Populate 1-lane buildings along this bottom perimeter road, shorter side touching (width < height)
        for b in needs_1_sorted:
            if b.id in seeded_b_map: continue
            
            placed = False
            for cx in range(grid_w - b.width + 1):
                cy = bottom_y - b.height
                if cy >= 0:
                    fit = True
                    for dy in range(b.height):
                        for dx in range(b.width):
                            if init_occupied[cy+dy][cx+dx]:
                                fit = False
                                break
                        if not fit: break
                    if fit:
                        seeded_b_map[b.id] = (cx, cy)
                        for dy in range(b.height):
                            for dx in range(b.width):
                                init_occupied[cy+dy][cx+dx] = True
                        placed = True
                        break

    # 5. Fallback constructive placement for any remaining road-requiring buildings
    for b in other_buildings:
        if b.road_type > 0 and b.id not in seeded_b_map:
            placed = False
            # Find any valid slot adjacent to existing roads
            for cy in range(grid_h - b.height + 1):
                for cx in range(grid_w - b.width + 1):
                    fit = True
                    for dy in range(b.height):
                        for dx in range(b.width):
                            if init_occupied[cy+dy][cx+dx]:
                                fit = False
                                break
                        if not fit: break
                    if fit:
                        seeded_b_map[b.id] = (cx, cy)
                        for dy in range(b.height):
                            for dx in range(b.width):
                                init_occupied[cy+dy][cx+dx] = True
                        placed = True
                        break
                if placed: break

    # 6. Seed roadless buildings in the remaining empty holes
    for b in needs_0:
        if b.id not in seeded_b_map:
            placed = False
            for cy in range(grid_h - b.height + 1):
                for cx in range(grid_w - b.width + 1):
                    fit = True
                    for dy in range(b.height):
                        for dx in range(b.width):
                            if init_occupied[cy+dy][cx+dx]:
                                fit = False
                                break
                        if not fit: break
                    if fit:
                        seeded_b_map[b.id] = (cx, cy)
                        for dy in range(b.height):
                            for dx in range(b.width):
                                init_occupied[cy+dy][cx+dx] = True
                        placed = True
                        break
                if placed: break

    # Prune any disconnected seed backbone tiles to start clean
    connected_backbone = set()
    queue = []
    visited = {}
    for th_tx, th_ty in hub_tiles:
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = th_tx + dx, th_ty + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                if init_roads[ny][nx] > 0 and (nx, ny) not in visited:
                    visited[(nx, ny)] = None
                    queue.append((nx, ny))
                    
    head = 0
    while head < len(queue):
        cx, cy = queue[head]
        head += 1
        connected_backbone.add((cx, cy))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                if init_roads[ny][nx] > 0 and (nx, ny) not in visited:
                    visited[(nx, ny)] = (cx, cy)
                    queue.append((nx, ny))
                    
    for y in range(grid_h):
        for x in range(grid_w):
            if (x, y) not in hub_tiles:
                if init_roads[y][x] > 0 and (x, y) not in connected_backbone:
                    init_roads[y][x] = 0
                    init_occupied[y][x] = not valid_tiles[y][x]

    # Clean up the placeholder seeding occupied list, we will let evaluate_state handle true overlap detection
    # but keep init_occupied for mutation and placement validation!
    # Update init_occupied to only contain invalid tiles, Townhall tiles, and seeded roads
    init_occupied = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]
    for tx, ty in hub_tiles:
        if 0 <= tx < grid_w and 0 <= ty < grid_h:
            init_occupied[ty][tx] = True
    for y in range(grid_h):
        for x in range(grid_w):
            if init_roads[y][x] > 0:
                init_occupied[y][x] = True

    # =========================================================================
    # REFINEMENT & LOCAL SEARCH PHASE
    # =========================================================================

    def evaluate_state(placed_b_map):
        occupied = [row[:] for row in init_occupied]
        
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

        roads = [row[:] for row in init_roads]
        final_placed_roads = []
        
        def find_shortest_road_path(start_tiles, req_type):
            queue = []
            visited = {}
            for sx, sy in start_tiles:
                if 0 <= sx < grid_w and 0 <= sy < grid_h:
                    if (sx, sy) not in hub_tiles:
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

        # Post-placement BFS road pruning
        keep_tiles = set()
        prune_queue = []
        prune_visited = {}
        for th_tx, th_ty in hub_tiles:
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = th_tx + dx, th_ty + dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h:
                    if roads[ny][nx] > 0 and (nx, ny) not in prune_visited:
                        prune_visited[(nx, ny)] = None
                        prune_queue.append((nx, ny))
                        
        head = 0
        while head < len(prune_queue):
            cx, cy = prune_queue[head]
            head += 1
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h:
                    if roads[ny][nx] > 0 and (nx, ny) not in prune_visited:
                        prune_visited[(nx, ny)] = (cx, cy)
                        prune_queue.append((nx, ny))

        building_road_types = {b.id: b.road_type for b in buildings}
        for pb in connected_placed_b:
            if pb.building_id == hub.id: continue
            req_type = building_road_types[pb.building_id]
            if req_type == 0: continue
            
            b = next(x for x in buildings if x.id == pb.building_id)
            w, h = b.width, b.height
            
            connected_tiles = []
            for dx in range(w):
                if pb.y - 1 >= 0 and roads[pb.y - 1][pb.x + dx] >= req_type and (pb.x + dx, pb.y - 1) in prune_visited:
                    connected_tiles.append((pb.x + dx, pb.y - 1))
                if pb.y + h < grid_h and roads[pb.y + h][pb.x + dx] >= req_type and (pb.x + dx, pb.y + h) in prune_visited:
                    connected_tiles.append((pb.x + dx, pb.y + h))
            for dy in range(h):
                if pb.x - 1 >= 0 and roads[pb.y + dy][pb.x - 1] >= req_type and (pb.x - 1, pb.y + dy) in prune_visited:
                    connected_tiles.append((pb.x - 1, pb.y + dy))
                if pb.x + w < grid_w and roads[pb.y + dy][pb.x + w] >= req_type and (pb.x + w, pb.y + dy) in prune_visited:
                    connected_tiles.append((pb.x + w, pb.y + dy))
                    
            for start_tile in connected_tiles:
                curr = start_tile
                while curr is not None:
                    keep_tiles.add(curr)
                    curr = prune_visited[curr]

        # Clean/prune all unused roads
        for y in range(grid_h):
            for x in range(grid_w):
                if (x, y) not in hub_tiles and (x, y) not in keep_tiles:
                    roads[y][x] = 0

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
        missing_count = len(buildings) - num_placed
        road_cost = sum(1 for pr in final_placed_roads for dy in range(pr.type) for dx in range(pr.type))
        score = num_placed * 10000 - road_cost - (missing_count * 200000)
        
        return connected_placed_b, final_placed_roads, score, valid_placed_b_map

    # Evaluate the initial constructive layout
    best_placed_b, best_placed_roads, best_score, current_b_map = evaluate_state(seeded_b_map)
    
    # Run a localized refinement search to pack any leftover buildings securely
    temp = 800.0
    cooling_rate = 0.99
    iterations = min(1200, request.annealing_iterations or 1000)
    
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
            for _ in range(10):
                nx = random.randint(0, grid_w - b.width)
                ny = random.randint(0, grid_h - b.height)
                overlap = False
                for dy in range(b.height):
                    for dx in range(b.width):
                        if init_occupied[ny+dy][nx+dx]:
                            overlap = True
                            break
                    if overlap: break
                if not overlap:
                    next_b_map[b_id] = (nx, ny)
                    break
            
        elif perturb_type == "swap" and len(next_b_map) >= 2:
            id1, id2 = random.sample(list(next_b_map.keys()), 2)
            next_b_map[id1], next_b_map[id2] = next_b_map[id2], next_b_map[id1]
            
        else:
            b = random.choice(other_buildings)
            if b.id in next_b_map:
                del next_b_map[b.id]
            else:
                for _ in range(10):
                    rx = random.randint(0, grid_w - b.width)
                    ry = random.randint(0, grid_h - b.height)
                    overlap = False
                    for dy in range(b.height):
                        for dx in range(b.width):
                            if init_occupied[ry+dy][rx+dx]:
                                overlap = True
                                break
                        if overlap: break
                    if not overlap:
                        next_b_map[b.id] = (rx, ry)
                        break

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
                print(f"Heuristic worker process failed: {e}")
                
    return best_response
