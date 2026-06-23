from models import SolveRequest, SolveResponse, PlacedBuilding, PlacedRoad
import numpy as np
import time
import os

class PolicyNetwork:
    def __init__(self, weights=None):
        if weights is not None:
            self.W1, self.b1, self.W2, self.b2, self.W3, self.b3 = weights
        else:
            # Gaussian initialization with a packing heuristic prior
            self.W1 = np.random.randn(8, 16) * 0.1
            self.b1 = np.zeros(16)
            # Column 0: prefer close to townhall (dist_th is index 0)
            self.W1[0, 0] = -1.0
            # Column 1: prefer close to border X (border_x is index 1)
            self.W1[1, 1] = -1.5
            # Column 2: prefer close to border Y (border_y is index 2)
            self.W1[2, 2] = -1.5
            # Column 3: prefer high occupancy ratio (occ_ratio is index 3)
            self.W1[3, 3] = 2.5
            
            self.W2 = np.random.randn(16, 8) * 0.1
            self.b2 = np.zeros(8)
            # Combine the packing features into the first output feature of layer 2
            self.W2[0, 0] = 1.0
            self.W2[1, 0] = 1.0
            self.W2[2, 0] = 1.0
            self.W2[3, 0] = 1.5
            
            self.W3 = np.random.randn(8, 1) * 0.1
            self.b3 = np.zeros(1)
            self.W3[0, 0] = 2.0
            
    def forward(self, X):
        # Vectorized forward pass for N candidate positions
        # X shape: (N, 8)
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
    total_count = 0
    for dy in range(-1, h + 1):
        for dx in range(-1, w + 1):
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                if occupied[ny][nx]:
                    occ_count += 1
            else:
                occ_count += 1  # borders count as occupied to encourage internal packing
            total_count += 1
    occ_ratio = occ_count / float(total_count) if total_count > 0 else 0.0
    
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

    # Place other buildings constructively
    # Sort buildings: first those requiring 2x2 roads, then 1x1 roads, then roadless. Within groups, sort by area descending.
    other_buildings = sorted(buildings_orig, key=lambda b: (-b.road_type, -(b.width * b.height)))
    
    placed_b_map = {}
    for b in other_buildings:
        candidates = []
        features_list = []
        
        # Scan grid for valid placement candidates
        for y in range(grid_h - b.height + 1):
            for x in range(grid_w - b.width + 1):
                # Simple check if fits
                fits = True
                for dy in range(b.height):
                    for dx in range(b.width):
                        if occupied[y+dy][x+dx]:
                            fits = False
                            break
                    if not fits: break
                
                if fits:
                    candidates.append((x, y))
                    features_list.append(get_features(x, y, b.width, b.height, b.road_type, hub_cx, hub_cy, grid_w, grid_h, occupied))
                    
        if not candidates:
            # Cannot place building
            continue
            
        # Neural network chooses the candidate
        scores = network.forward(np.array(features_list))
        best_idx = np.argmax(scores)
        best_x, best_y = candidates[best_idx]
        
        # Mark occupied
        placed_b_map[b.id] = (best_x, best_y)
        for dy in range(b.height):
            for dx in range(b.width):
                occupied[best_y+dy][best_x+dx] = True

    # ------------------ BFS Road Routing and Scoring ------------------
    # Re-initialize occupied matrix starting with init_occupied + placed buildings
    eval_occupied = [row[:] for row in init_occupied]
    final_placed_buildings = []
    if hub:
        final_placed_buildings.append(PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y))
        
    for b in other_buildings:
        if b.id in placed_b_map:
            bx, by = placed_b_map[b.id]
            for dy in range(b.height):
                for dx in range(b.width):
                    eval_occupied[by+dy][bx+dx] = True
            final_placed_buildings.append(PlacedBuilding(building_id=b.id, x=bx, y=by))

    roads = [row[:] for row in init_roads]
    
    # Pathfinding routing helper
    def find_shortest_road_path(start_tiles, req_type):
        queue = []
        visited = {}
        for sx, sy in start_tiles:
            if 0 <= sx < grid_w and 0 <= sy < grid_h:
                if (sx, sy) not in hub_tiles:
                    if not eval_occupied[sy][sx] or roads[sy][sx] > 0:
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
                        if not eval_occupied[ny][nx] or roads[ny][nx] > 0:
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

    connected_placed_buildings = []
    if hub:
        connected_placed_buildings.append(PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y))
        
    for pb in final_placed_buildings:
        if hub and pb.building_id == hub.id: continue
        b = next(x for x in other_buildings if x.id == pb.building_id)
        if b.road_type == 0:
            connected_placed_buildings.append(pb)
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
                eval_occupied[ry][rx] = True
            connected_placed_buildings.append(pb)

    # Post-routing BFS road pruning: retain only roads connecting a placed building back to the hub
    keep_tiles = set()
    prune_queue = []
    prune_visited = {}
    if hub:
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
        keep_tiles.add((cx, cy))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                if roads[ny][nx] > 0 and (nx, ny) not in prune_visited:
                    prune_visited[(nx, ny)] = None
                    prune_queue.append((nx, ny))

    # Remove pruned roads
    final_placed_roads = []
    num_1x1 = 0
    num_2x2_tiles = 0
    
    # 2x2 road tracking to prevent duplication
    placed_2x2_tiles = set()
    for y in range(grid_h):
        for x in range(grid_w):
            if (x, y) not in keep_tiles:
                roads[y][x] = 0
            else:
                if roads[y][x] == 2:
                    # Place 2x2 road anchor on bottom-leftmost tile of any 2x2 block
                    if (x, y) not in placed_2x2_tiles:
                        final_placed_roads.append(PlacedRoad(x=x, y=y, type=2))
                        # mark entire 2x2 road grid covered
                        for rdy in range(2):
                            for rdx in range(2):
                                placed_2x2_tiles.add((x + rdx, y + rdy))
                        num_2x2_tiles += 1
                elif roads[y][x] == 1:
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

def solve_layout(request: SolveRequest) -> SolveResponse:
    import json
    # Setup neuro-evolution parameters
    pop_size = 20
    generations = 30
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
    
    for gen in range(generations):
        if time.time() >= end_time:
            break
        if os.path.exists("abort.lock"):
            break
            
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
            
        if request.early_stopping and stagnant_generations >= patience:
            print(f"Early stopping triggered: fitness stagnant for {stagnant_generations} generations.")
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

    # Save the best network checkpoint weights at the end of the run
    if best_network is not None:
        try:
            weights = best_network.get_weights()
            serialized = [w.tolist() for w in weights]
            with open("best_nn_weights.json", "w") as f:
                json.dump(serialized, f)
            print("Successfully saved best neural network weights checkpoint to best_nn_weights.json")
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
