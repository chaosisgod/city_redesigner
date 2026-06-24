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

    # Pre-generate road backbone
    init_roads = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
    init_occupied = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]

    # Seed the hub / Townhall tiles in both roads and occupied grids
    for tx, ty in hub_tiles:
        if 0 <= tx < grid_w and 0 <= ty < grid_h:
            init_occupied[ty][tx] = True
            init_roads[ty][tx] = 3

    backbone = request.backbone_type or "none"
    
    if backbone != "none":
        max_road_req = 1
        if any(b.road_type == 2 for b in other_buildings):
            max_road_req = 2
            
        if backbone == "center_spine":
            spine_y = grid_h // 2
            for x in range(grid_w):
                if is_tile_valid(x, spine_y):
                    init_roads[spine_y][x] = max(init_roads[spine_y][x], max_road_req)
                    init_occupied[spine_y][x] = True
                    if max_road_req == 2 and spine_y + 1 < grid_h and is_tile_valid(x, spine_y + 1):
                        init_roads[spine_y + 1][x] = max(init_roads[spine_y + 1][x], 2)
                        init_occupied[spine_y + 1][x] = True
                        
            min_y = min(hub_y, spine_y)
            max_y = max(hub_y + hub_h - 1, spine_y)
            conn_x = hub_x + hub_w // 2
            for y in range(min_y, max_y + 1):
                if is_tile_valid(conn_x, y):
                    init_roads[y][conn_x] = max(init_roads[y][conn_x], max_road_req)
                    init_occupied[y][conn_x] = True

        elif backbone == "center_cross":
            spine_y = grid_h // 2
            spine_x = grid_w // 2
            
            # Horizontal Spine
            for x in range(grid_w):
                if is_tile_valid(x, spine_y):
                    init_roads[spine_y][x] = max(init_roads[spine_y][x], max_road_req)
                    init_occupied[spine_y][x] = True
                    if max_road_req == 2 and spine_y + 1 < grid_h and is_tile_valid(x, spine_y + 1):
                        init_roads[spine_y + 1][x] = max(init_roads[spine_y + 1][x], 2)
                        init_occupied[spine_y + 1][x] = True
                        
            # Vertical Spine
            for y in range(grid_h):
                if is_tile_valid(spine_x, y):
                    init_roads[y][spine_x] = max(init_roads[y][spine_x], max_road_req)
                    init_occupied[y][spine_x] = True
                    if max_road_req == 2 and spine_x + 1 < grid_w and is_tile_valid(spine_x + 1, y):
                        init_roads[y][spine_x + 1] = max(init_roads[y][spine_x + 1], 2)
                        init_occupied[y][spine_x + 1] = True
                        
            # Connect Hub to horizontal & vertical cross-spines
            min_y = min(hub_y, spine_y)
            max_y = max(hub_y + hub_h - 1, spine_y)
            conn_x = hub_x + hub_w // 2
            for y in range(min_y, max_y + 1):
                if is_tile_valid(conn_x, y):
                    init_roads[y][conn_x] = max(init_roads[y][conn_x], max_road_req)
                    init_occupied[y][conn_x] = True
                    
            min_x = min(hub_x, spine_x)
            max_x = max(hub_x + hub_w - 1, spine_x)
            conn_y = hub_y + hub_h // 2
            for x in range(min_x, max_x + 1):
                if is_tile_valid(x, conn_y):
                    init_roads[conn_y][x] = max(init_roads[conn_y][x], max_road_req)
                    init_occupied[conn_y][x] = True

        elif backbone == "grid":
            lanes = [y for y in range(2, grid_h, 5)]
            for lane_y in lanes:
                for x in range(grid_w):
                    if is_tile_valid(x, lane_y):
                        init_roads[lane_y][x] = max(init_roads[lane_y][x], max_road_req)
                        init_occupied[lane_y][x] = True
                        if max_road_req == 2 and lane_y + 1 < grid_h and is_tile_valid(x, lane_y + 1):
                            init_roads[lane_y + 1][x] = max(init_roads[lane_y + 1][x], 2)
                            init_occupied[lane_y + 1][x] = True
                            
            conn_x = hub_x + hub_w // 2
            for y in range(grid_h):
                if is_tile_valid(conn_x, y):
                    init_roads[y][conn_x] = max(init_roads[y][conn_x], max_road_req)
                    init_occupied[y][conn_x] = True

        elif backbone == "perimeter":
            for y in range(grid_h):
                for x in range(grid_w):
                    if is_tile_valid(x, y):
                        is_border = False
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            if not is_tile_valid(x + dx, y + dy):
                                is_border = True
                                break
                        if is_border:
                            init_roads[y][x] = max(init_roads[y][x], max_road_req)
                            init_occupied[y][x] = True
                            
            conn_x = hub_x + hub_w // 2
            for y in range(grid_h):
                if is_tile_valid(conn_x, y):
                    init_roads[y][conn_x] = max(init_roads[y][conn_x], max_road_req)
                    init_occupied[y][conn_x] = True

        elif backbone == "custom" and request.custom_roads:
            for pr in request.custom_roads:
                if pr.type == 2:
                    for dy in range(2):
                        for dx in range(2):
                            rx, ry = pr.x + dx, pr.y + dy
                            if 0 <= rx < grid_w and 0 <= ry < grid_h:
                                init_roads[ry][rx] = max(init_roads[ry][rx], 2)
                                init_occupied[ry][rx] = True
                else:
                    if 0 <= pr.x < grid_w and 0 <= pr.y < grid_h:
                        init_roads[pr.y][pr.x] = max(init_roads[pr.y][pr.x], 1)
                        init_occupied[pr.y][pr.x] = True

        # Pre-placement Backbone Pruning: Ensure only fully connected road segments are kept
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
                        
        # Discard any disconnected backbone tiles and free their space for building placement
        for y in range(grid_h):
            for x in range(grid_w):
                if (x, y) not in hub_tiles:
                    if init_roads[y][x] > 0 and (x, y) not in connected_backbone:
                        init_roads[y][x] = 0
                        init_occupied[y][x] = not valid_tiles[y][x]

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

    # GA Configuration
    pop_size = 40
    elitism_count = 4  # Keep top 10%
    mutation_rate = 0.25
    
    # Helper to generate a single random individual
    def create_random_individual():
        placed_b_map = {}
        for b in other_buildings:
            for _ in range(50):
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
                    placed_b_map[b.id] = (rx, ry)
                    break
        return placed_b_map

    # Initialize Population
    population = []
    for _ in range(pop_size):
        chromosome = create_random_individual()
        connected_placed_b, final_placed_roads, score, valid_placed_b_map = evaluate_state(chromosome)
        population.append((score, valid_placed_b_map, connected_placed_b, final_placed_roads))

    start_time = time.time()
    end_time = start_time + request.optimization_time
    
    best_overall = max(population, key=lambda ind: ind[0])
    
    generation = 0
    stagnant_generations = 0
    patience = 8
    
    while time.time() < end_time:
        if os.path.exists("abort.lock"):
            break
        generation += 1
        
        # Sort current population by score (descending)
        population.sort(key=lambda ind: ind[0], reverse=True)
        
        # Keep track of the absolute best
        if population[0][0] > best_overall[0]:
            best_overall = population[0]
            stagnant_generations = 0
        else:
            stagnant_generations += 1
            
        placed_count = len(best_overall[2]) if best_overall else 0
        best_unplaced = len(request.buildings) - placed_count
        
        if request.early_stopping and stagnant_generations >= patience and best_unplaced == 0:
            print(f"Early stopping triggered: fitness stagnant for {stagnant_generations} generations (at generation {generation}).")
            break
            
        next_population = []
        
        # Elitism: Directly retain the top individuals
        for i in range(elitism_count):
            next_population.append(population[i])
            
        # Breeding offspring
        while len(next_population) < pop_size:
            # Tournament Selection for Parent A
            tournament_a = random.sample(population, 3)
            parent_a = max(tournament_a, key=lambda ind: ind[0])
            
            # Tournament Selection for Parent B
            tournament_b = random.sample(population, 3)
            parent_b = max(tournament_b, key=lambda ind: ind[0])
            
            # Crossover: Uniform crossover
            offspring_chromosome = {}
            for b in other_buildings:
                inherit_from_a = random.choice([True, False])
                if inherit_from_a and b.id in parent_a[1]:
                    offspring_chromosome[b.id] = parent_a[1][b.id]
                elif b.id in parent_b[1]:
                    offspring_chromosome[b.id] = parent_b[1][b.id]
                else:
                    # Fallback to random position if building wasn't valid in parent
                    rx = random.randint(0, grid_w - b.width)
                    ry = random.randint(0, grid_h - b.height)
                    offspring_chromosome[b.id] = (rx, ry)
                    
            # Mutation
            if random.random() < mutation_rate and other_buildings:
                mut_b = random.choice(other_buildings)
                mut_type = random.choice(["shift", "swap", "randomize"])
                
                if mut_type == "shift" and mut_b.id in offspring_chromosome:
                    cx, cy = offspring_chromosome[mut_b.id]
                    dx = random.randint(-3, 3)
                    dy = random.randint(-3, 3)
                    nx = max(0, min(grid_w - mut_b.width, cx + dx))
                    ny = max(0, min(grid_h - mut_b.height, cy + dy))
                    offspring_chromosome[mut_b.id] = (nx, ny)
                    
                elif mut_type == "swap" and len(offspring_chromosome) >= 2:
                    swap_target = random.choice([ob for ob in other_buildings if ob.id != mut_b.id])
                    if mut_b.id in offspring_chromosome and swap_target.id in offspring_chromosome:
                        offspring_chromosome[mut_b.id], offspring_chromosome[swap_target.id] = offspring_chromosome[swap_target.id], offspring_chromosome[mut_b.id]
                        
                else:
                    # Randomize location
                    for _ in range(10):
                        rx = random.randint(0, grid_w - mut_b.width)
                        ry = random.randint(0, grid_h - mut_b.height)
                        overlap = False
                        for dy in range(mut_b.height):
                            for dx in range(mut_b.width):
                                if init_occupied[ry+dy][rx+dx]:
                                    overlap = True
                                    break
                            if overlap: break
                        if not overlap:
                            offspring_chromosome[mut_b.id] = (rx, ry)
                            break
                            
            # Evaluate new offspring
            connected_placed_b, final_placed_roads, score, valid_placed_b_map = evaluate_state(offspring_chromosome)
            next_population.append((score, valid_placed_b_map, connected_placed_b, final_placed_roads))
            
        population = next_population

    # Take the absolute best out of final population and historically best
    population.sort(key=lambda ind: ind[0], reverse=True)
    best_ind = population[0]
    if best_overall[0] > best_ind[0]:
        best_ind = best_overall
        
    best_placed_b = best_ind[2]
    best_placed_roads = best_ind[3]
    best_score = best_ind[0]
    
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
                for p in multiprocessing.active_children():
                    try: p.terminate()
                    except: pass
                break
            try:
                res = future.result()
                if res and res.score > best_score:
                    best_score = res.score
                    best_response = res
            except Exception as e:
                print(f"Evolutionary worker process failed: {e}")
                
    return best_response
