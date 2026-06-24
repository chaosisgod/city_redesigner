from models import SolveRequest, SolveResponse, PlacedBuilding, PlacedRoad
import numpy as np
import time
import os

class PolicyNetwork:
    def __init__(self, weights=None):
        if weights is not None:
            W1, b1, W2, b2, W3, b3 = weights
            # Shape checks to support upgrading old 8-feature weights to 9-feature weights
            if W1.shape == (8, 16):
                new_W1 = np.random.randn(9, 16) * 0.1
                new_W1[0:8, :] = W1
                new_W1[8, 4] = 4.0 # Prior weight for road proximity feature
                W1 = new_W1
            self.W1, self.b1, self.W2, self.b2, self.W3, self.b3 = W1, b1, W2, b2, W3, b3
        else:
            # Gaussian initialization with a packing heuristic prior
            self.W1 = np.random.randn(9, 16) * 0.1
            self.b1 = np.zeros(16)
            # Column 0: prefer close to townhall (dist_th is index 0)
            self.W1[0, 0] = -1.0
            # Column 1: prefer close to border X (border_x is index 1)
            self.W1[1, 1] = -1.5
            # Column 2: prefer close to border Y (border_y is index 2)
            self.W1[2, 2] = -1.5
            # Column 3: prefer high occupancy ratio (occ_ratio is index 3)
            self.W1[3, 3] = 2.5
            # Column 8: prefer high road proximity (road_proximity is index 8)
            self.W1[8, 4] = 4.0
            
            self.W2 = np.random.randn(16, 8) * 0.1
            self.b2 = np.zeros(8)
            # Combine the packing features into the first output feature of layer 2
            self.W2[0, 0] = 1.0
            self.W2[1, 0] = 1.0
            self.W2[2, 0] = 1.0
            self.W2[3, 0] = 1.5
            self.W2[4, 0] = 2.5 # weight for hidden neuron 4
            
            self.W3 = np.random.randn(8, 1) * 0.1
            self.b3 = np.zeros(1)
            self.W3[0, 0] = 2.0
            
    def forward(self, X):
        # Vectorized forward pass for N candidate positions
        # X shape: (N, 9)
        h1 = np.maximum(0, np.dot(X, self.W1) + self.b1)  # ReLU
        h2 = np.maximum(0, np.dot(h1, self.W2) + self.b2) # ReLU
        out = np.dot(h2, self.W3) + self.b3
        return out.flatten()

    def get_weights(self):
        return (self.W1, self.b1, self.W2, self.b2, self.W3, self.b3)

def get_features(x, y, w, h, road_type, th_cx, th_cy, grid_w, grid_h, occupied):
    # 1. Normalized Manhattan Distance to Townhall
    dist_th = (abs(x + w/2.0 - th_cx) + abs(y + h/2.0 - th_cy)) / max(1.0, float(grid_w + grid_h))
    
    # 2. Normalized border proximity
    border_x = min(x, grid_w - (x + w)) / max(1.0, float(grid_w))
    border_y = min(y, grid_h - (y + h)) / max(1.0, float(grid_h))
    
    # 3. Local occupancy density in a padded window around candidate
    occ_count = 0
    total_count = (w + 2) * (h + 2)
    
    # Fast path if candidate is fully inside the grid boundary (90%+ of cases)
    if x > 0 and y > 0 and x + w < grid_w and y + h < grid_h:
        occ_count = sum(sum(occupied[dy][x - 1 : x + w + 1]) for dy in range(y - 1, y + h + 1))
    else:
        for dy in range(-1, h + 1):
            ny = y + dy
            if 0 <= ny < grid_h:
                row = occupied[ny]
                for dx in range(-1, w + 1):
                    nx = x + dx
                    if 0 <= nx < grid_w:
                        if row[nx]:
                            occ_count += 1
                    else:
                        occ_count += 1
            else:
                occ_count += (w + 2)
                
    occ_ratio = occ_count / float(total_count)
    
    # 4. Road connection necessity
    is_road_need = road_type / 2.0
    
    # 5. Normalized Dimensions & Aspect ratios
    size_w = w / max(1.0, float(grid_w))
    size_h = h / max(1.0, float(grid_h))
    area = (w * h) / max(1.0, float(grid_w * grid_h))
    
    return [dist_th, border_x, border_y, occ_ratio, is_road_need, size_w, size_h, area]

def run_constructive_placement(network, request):
    grid_w = request.grid.width
    grid_h = request.grid.height
    valid_tiles = request.grid.valid_tiles
    
    buildings_orig = request.buildings.copy()
    hub = next((b for b in buildings_orig if b.name.lower().startswith('townhall') or b.name.lower().startswith('embassy')), None)
    if hub:
        buildings_orig.remove(hub)
        
    def is_tile_valid(x, y):
        if x < 0 or y < 0 or x >= grid_w or y >= grid_h:
            return False
        return valid_tiles[y][x]

    # Pre-occupied matrix base
    occupied_base = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]
    
    # Place Townhall
    hub_x, hub_y = 0, 0
    if hub:
        if request.townhall_fixed and request.townhall_pos:
            hub_x, hub_y = request.townhall_pos
        else:
            hub_x = max(0, (grid_w - hub.width) // 2)
            hub_y = max(0, (grid_h - hub.height) // 2)
            
        # Overlap validation helper
        def check_fits(cx, cy, cw, ch):
            if cx < 0 or cy < 0 or cx + cw > grid_w or cy + ch > grid_h:
                return False
            for dy in range(ch):
                for dx in range(cw):
                    if occupied_base[cy+dy][cx+dx]:
                        return False
            return True
            
        if not check_fits(hub_x, hub_y, hub.width, hub.height):
            # Fallback to nearest open space
            best_d = float('inf')
            placed_hub = False
            for y in range(grid_h - hub.height + 1):
                for x in range(grid_w - hub.width + 1):
                    if check_fits(x, y, hub.width, hub.height):
                        d = abs(x - hub_x) + abs(y - hub_y)
                        if d < best_d:
                            best_d = d
                            hub_x, hub_y = x, y
                            placed_hub = True
            if not placed_hub:
                # Absolute failure to place Townhall
                return None
                
        # Mark Townhall occupied in occupied_base
        for dy in range(hub.height):
            for dx in range(hub.width):
                occupied_base[hub_y+dy][hub_x+dx] = True

    hub_cx = hub_x + (hub.width / 2.0) if hub else grid_w / 2.0
    hub_cy = hub_y + (hub.height / 2.0) if hub else grid_h / 2.0
    hub_tiles = set()
    if hub:
        for dy in range(hub.height):
            for dx in range(hub.width):
                hub_tiles.add((hub_x + dx, hub_y + dy))

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
        if any(b.road_type == 2 for b in buildings_orig):
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
            max_y = max(hub_y + hub.height - 1, spine_y)
            conn_x = hub_x + hub.width // 2
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
            max_y = max(hub_y + hub.height - 1, spine_y)
            conn_x = hub_x + hub.width // 2
            for y in range(min_y, max_y + 1):
                if is_tile_valid(conn_x, y):
                    init_roads[y][conn_x] = max(init_roads[y][conn_x], max_road_req)
                    init_occupied[y][conn_x] = True
                    
            min_x = min(hub_x, spine_x)
            max_x = max(hub_x + hub.width - 1, spine_x)
            conn_y = hub_y + hub.height // 2
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
                            
            conn_x = hub_x + hub.width // 2
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
                            
            conn_x = hub_x + hub.width // 2
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

    # Initialize constructive placement occupied map using the generated init_occupied
    occupied = [row[:] for row in init_occupied]
    current_roads = [row[:] for row in init_roads]

    # Place other buildings constructively
    # Sort buildings: first those requiring 2x2 roads, then 1x1 roads, then roadless. Within groups, sort by area descending.
    other_buildings = sorted(buildings_orig, key=lambda b: (-b.road_type, -(b.width * b.height)))
    
    placed_b_map = {}
    for b in other_buildings:
        # Multi-source BFS to calculate road distance to all empty tiles
        dist_grid = [[float('inf') for _ in range(grid_w)] for _ in range(grid_h)]
        parent_grid = [[None for _ in range(grid_w)] for _ in range(grid_h)]
        
        # Only run BFS if the building requires a road
        if b.road_type > 0:
            queue = []
            req_road_type = b.road_type
            
            # 1. Existing road tiles (type 1 or 2) meeting the requirement are sources (distance 0)
            for y in range(grid_h):
                for x in range(grid_w):
                    if current_roads[y][x] == 1 or current_roads[y][x] == 2:
                        if current_roads[y][x] >= req_road_type:
                            dist_grid[y][x] = 0
                            queue.append((x, y))
                            
            # 2. Empty tiles adjacent to the Townhall (type 3) are sources (distance 1)
            # This ensures that a real road tile (type 1 or 2) is always placed to connect to the Townhall.
            for y in range(grid_h):
                for x in range(grid_w):
                    if current_roads[y][x] == 3: # Townhall tile
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                                if not occupied[ny][nx] and current_roads[ny][nx] == 0:
                                    if dist_grid[ny][nx] == float('inf'):
                                        dist_grid[ny][nx] = 1
                                        queue.append((nx, ny))
                        
            head = 0
            while head < len(queue):
                cx, cy = queue[head]
                head += 1
                curr_dist = dist_grid[cy][cx]
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < grid_w and 0 <= ny < grid_h:
                        if not occupied[ny][nx] and dist_grid[ny][nx] == float('inf'):
                            dist_grid[ny][nx] = curr_dist + 1
                            parent_grid[ny][nx] = (cx, cy)
                            queue.append((nx, ny))

        candidates = []
        features_list = []
        road_connect_info = [] # Store (min_dist, best_boundary_tile) for each candidate
        
        # Scan grid for valid placement candidates
        for y in range(grid_h - b.height + 1):
            for x in range(grid_w - b.width + 1):
                # Simple check if fits
                fits = True
                for dy in range(b.height):
                    if any(occupied[y+dy][x : x + b.width]):
                        fits = False
                        break
                        
                if fits:
                    # Calculate road connection feature
                    if b.road_type == 0:
                        road_proximity = 1.0
                        best_boundary = None
                        min_dist = 0
                    else:
                        # Find minimum distance to road network from building boundary
                        min_dist = float('inf')
                        best_boundary = None
                        
                        # Boundary check
                        # Top / Bottom
                        for dx in range(b.width):
                            for ty, tx in [(y - 1, x + dx), (y + b.height, x + dx)]:
                                if 0 <= tx < grid_w and 0 <= ty < grid_h:
                                    d = dist_grid[ty][tx]
                                    if d < min_dist:
                                        min_dist = d
                                        best_boundary = (tx, ty)
                        # Left / Right
                        for dy in range(b.height):
                            for ty, tx in [(y + dy, x - 1), (y + dy, x + b.width)]:
                                if 0 <= tx < grid_w and 0 <= ty < grid_h:
                                    d = dist_grid[ty][tx]
                                    if d < min_dist:
                                        min_dist = d
                                        best_boundary = (tx, ty)
                                        
                        if min_dist != float('inf'):
                            road_proximity = 1.0 / (1.0 + min_dist)
                        else:
                            road_proximity = 0.0
                            
                    # If the building requires a road, but cannot be connected, we should NOT place it here
                    if b.road_type > 0 and road_proximity == 0.0:
                        continue
                        
                    candidates.append((x, y))
                    road_connect_info.append((min_dist, best_boundary))
                    
                    feats = get_features(x, y, b.width, b.height, b.road_type, hub_cx, hub_cy, grid_w, grid_h, occupied)
                    feats.append(road_proximity)
                    features_list.append(feats)
                    
        if not candidates:
            # Cannot place building
            continue
            
        # Neural network chooses the candidate
        scores = network.forward(np.array(features_list))
        best_idx = np.argmax(scores)
        best_x, best_y = candidates[best_idx]
        best_min_dist, best_boundary = road_connect_info[best_idx]
        
        # Mark occupied
        placed_b_map[b.id] = (best_x, best_y)
        for dy in range(b.height):
            for dx in range(b.width):
                occupied[best_y+dy][best_x+dx] = True
                
        # Draw road path if needed
        if b.road_type > 0 and best_boundary is not None and best_min_dist > 0:
            curr = best_boundary
            while curr is not None:
                cx, cy = curr
                current_roads[cy][cx] = max(current_roads[cy][cx], b.road_type)
                occupied[cy][cx] = True
                curr = parent_grid[cy][cx]

    connected_placed_buildings = []
    if hub:
        connected_placed_buildings.append(PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y))
    for b_id, pos in placed_b_map.items():
        bx, by = pos
        connected_placed_buildings.append(PlacedBuilding(building_id=b_id, x=bx, y=by))

    final_placed_roads = []
    num_1x1 = 0
    num_2x2_tiles = 0
    
    # 2x2 road tracking to prevent duplication
    placed_2x2_tiles = set()
    for y in range(grid_h):
        for x in range(grid_w):
            if (x, y) not in hub_tiles:
                if current_roads[y][x] == 2:
                    if (x, y) not in placed_2x2_tiles:
                        final_placed_roads.append(PlacedRoad(x=x, y=y, type=2))
                        for rdy in range(2):
                            for rdx in range(2):
                                placed_2x2_tiles.add((x + rdx, y + rdy))
                        num_2x2_tiles += 1
                elif current_roads[y][x] == 1:
                    final_placed_roads.append(PlacedRoad(x=x, y=y, type=1))
                    num_1x1 += 1

    # Scoring Calculation
    placed_set = {pb.building_id for pb in connected_placed_buildings}
    unplaced_count = len(request.buildings) - len(placed_set)
    road_cost = num_1x1 + num_2x2_tiles * 4
    
    score = 30000.0 - road_cost - 200000.0 * unplaced_count
    
    response = SolveResponse(
        placed_buildings=connected_placed_buildings,
        placed_roads=final_placed_roads,
        score=score,
        num_1x1_roads=num_1x1,
        num_2x2_roads=num_2x2_tiles
    )
    return response

def solve_single_worker(request: SolveRequest, seed: int) -> tuple:
    import json
    import random
    np.random.seed(seed)
    random.seed(seed)
    
    # Setup neuro-evolution parameters
    pop_size = 20
    mutation_rate = 0.2
    mutation_scale = 0.15
    elitism = 4
    
    # Initialize random population of network weights or warm-start from checkpoint
    best_weights = None
    if getattr(request, "resume_weights", False) and os.path.exists("best_nn_weights.json"):
        try:
            with open("best_nn_weights.json", "r") as f:
                serialized = json.load(f)
                best_weights = tuple(np.array(w) for w in serialized)
            print("Successfully loaded best neural network weights to warm start the population!")
        except Exception as e:
            print(f"Error loading best_nn_weights.json: {e}")

    population = []
    if best_weights is not None:
        # Seed 5 exact copies of the best network, and 15 mutated versions of it
        for _ in range(5):
            population.append(PolicyNetwork(weights=best_weights))
        for _ in range(pop_size - 5):
            mutated = mutate(best_weights, rate=0.3, scale=0.1)
            population.append(PolicyNetwork(weights=mutated))
    else:
        population = [PolicyNetwork() for _ in range(pop_size)]

    best_response = None
    best_score = -float('inf')
    best_network = None
    
    stagnant_generations = 0
    patience = 8
    
    end_time = time.time() + request.optimization_time
    generation = 0
    
    while time.time() < end_time:
        if os.path.exists("abort.lock"):
            break
        generation += 1
            
        fitness_scores = []
        layouts = []
        
        for i in range(pop_size):
            res = run_constructive_placement(population[i], request)
            if res is not None:
                fitness_scores.append(res.score)
                layouts.append(res)
            else:
                fitness_scores.append(-999999.0)
                layouts.append(None)
                
        # Sort by fitness descending
        indices = np.argsort(fitness_scores)[::-1]
        
        # Track best layout
        gen_best_idx = indices[0]
        gen_best_score = fitness_scores[gen_best_idx]
        if gen_best_score > best_score and layouts[gen_best_idx] is not None:
            best_score = gen_best_score
            best_response = layouts[gen_best_idx]
            best_network = population[gen_best_idx]
            stagnant_generations = 0
        else:
            stagnant_generations += 1
            
        placed_set = {pb.building_id for pb in best_response.placed_buildings} if best_response else set()
        best_unplaced = len(request.buildings) - len(placed_set)
        
        if request.early_stopping and stagnant_generations >= patience and best_unplaced == 0:
            print(f"Early stopping triggered: fitness stagnant for {stagnant_generations} generations (at generation {generation}).")
            break
            
        # Form new population (Elitism + Selection + Mutation)
        new_population = []
        
        # 1. Elitism
        for e in range(min(elitism, pop_size)):
            new_population.append(population[indices[e]])
            
        # 2. Crossover & Mutation for offspring
        while len(new_population) < pop_size:
            # Tournament selection (select 2 parents)
            p1_idx = tournament_select(indices, fitness_scores)
            p2_idx = tournament_select(indices, fitness_scores)
            
            parent1 = population[p1_idx]
            parent2 = population[p2_idx]
            
            # Crossover weights
            offspring_weights = crossover(parent1.get_weights(), parent2.get_weights())
            
            # Mutate offspring weights
            mutated_weights = mutate(offspring_weights, mutation_rate, mutation_scale)
            
            new_population.append(PolicyNetwork(weights=mutated_weights))
            
        population = new_population

    best_weights_serialized = None
    if best_network is not None:
        try:
            weights = best_network.get_weights()
            best_weights_serialized = [w.tolist() for w in weights]
        except Exception as e:
            print(f"Error serializing best network weights: {e}")

    return best_response, best_weights_serialized

def solve_layout(request: SolveRequest) -> SolveResponse:
    import random
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor, as_completed

    num_workers = max(1, (os.cpu_count() or 4) - 1)
    
    # If single-process or debug, execute directly
    if request.optimization_time <= 0.1 or num_workers <= 1 or request.debug:
        res, weights_serialized = solve_single_worker(request, random.randint(0, 1000000))
        if weights_serialized is not None:
            try:
                import json
                with open("best_nn_weights.json", "w") as f:
                    json.dump(weights_serialized, f)
                print("Successfully saved best neural network weights checkpoint to best_nn_weights.json")
            except Exception as e:
                print(f"Error saving best_nn_weights.json: {e}")
        return res

    best_response = None
    best_score = -float('inf')
    best_weights_serialized = None
    
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
                res, weights_serialized = future.result()
                if res and res.score > best_score:
                    best_score = res.score
                    best_response = res
                    best_weights_serialized = weights_serialized
            except Exception as e:
                print(f"Neuro-evolutionary worker process failed: {e}")
                
    # Save the best weights found across all processes
    if best_weights_serialized is not None:
        try:
            import json
            with open("best_nn_weights.json", "w") as f:
                json.dump(best_weights_serialized, f)
            print("Successfully saved best neural network weights checkpoint from the best worker process to best_nn_weights.json")
        except Exception as e:
            print(f"Error saving best_nn_weights.json: {e}")
            
    return best_response

def tournament_select(indices, fitness_scores, k=3):
    selected_indices = np.random.choice(indices, size=min(k, len(indices)), replace=False)
    best_idx = selected_indices[0]
    best_fit = fitness_scores[best_idx]
    for idx in selected_indices[1:]:
        if fitness_scores[idx] > best_fit:
            best_fit = fitness_scores[idx]
            best_idx = idx
    return best_idx

def crossover(weights1, weights2):
    # Perform uniform crossover on weight matrices and bias vectors
    child_weights = []
    for w1, w2 in zip(weights1, weights2):
        mask = np.random.rand(*w1.shape) < 0.5
        child_w = np.where(mask, w1, w2)
        child_weights.append(child_w)
    return tuple(child_weights)

def mutate(weights, rate, scale):
    # Apply Gaussian mutations with probability rate and strength scale
    mutated_weights = []
    for w in weights:
        mutation_mask = np.random.rand(*w.shape) < rate
        noise = np.random.randn(*w.shape) * scale
        mutated_w = w + np.where(mutation_mask, noise, 0.0)
        mutated_weights.append(mutated_w)
    return tuple(mutated_weights)
