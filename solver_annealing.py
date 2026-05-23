from models import SolveRequest, SolveResponse, PlacedBuilding, PlacedRoad
import random
import time
import math
import copy

def solve_layout(request: SolveRequest) -> SolveResponse:
    # Set seed
    random.seed(random.randint(0, 1000000))
    
    grid_w = request.grid.width
    grid_h = request.grid.height
    valid_tiles = request.grid.valid_tiles
    
    # Identify connection hub
    buildings = request.buildings.copy()
    hub = next((b for b in buildings if b.name.lower().startswith('townhall') or b.name.lower().startswith('embassy')), None)
    if not hub:
        # Fallback if no hub is found
        return SolveResponse(placed_buildings=[], placed_roads=[], score=0.0)
        
    other_buildings = [b for b in buildings if b.id != hub.id]
    
    # Global state helper
    def is_tile_valid(x, y):
        if x < 0 or y < 0 or x >= grid_w or y >= grid_h:
            return False
        return valid_tiles[y][x]

    # Helper: Place hub at center (or fixed position)
    hub_w, hub_h = hub.width, hub.height
    if request.townhall_fixed and request.townhall_pos:
        hub_x, hub_y = request.townhall_pos
    else:
        hub_x = max(0, (grid_w - hub_w) // 2)
        hub_y = max(0, (grid_h - hub_h) // 2)

    # Let's verify hub fits
    for dy in range(hub_h):
        for dx in range(hub_w):
            if not is_tile_valid(hub_x + dx, hub_y + dy):
                # Search for a nearby valid fit
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
        """
        Takes a mapping of building_id -> (x, y) and computes the exact road routing using BFS/Dijkstra,
        returning (placed_buildings, placed_roads, score).
        """
        # Create occupation grid
        occupied = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]
        
        # Mark hub
        for tx, ty in hub_tiles:
            if 0 <= tx < grid_w and 0 <= ty < grid_h:
                occupied[ty][tx] = True
                
        final_placed_b = [PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y)]
        
        # Sort buildings to place (by size, non-road first, or original request)
        b_list = []
        for b in other_buildings:
            if b.id in placed_b_map:
                b_list.append(b)
                
        # First place buildings that fit, keeping track of occupied cells
        valid_placed_b_map = {}
        for b in b_list:
            bx, by = placed_b_map[b.id]
            # Check overlap
            overlap = False
            for dy in range(b.height):
                for dx in range(b.width):
                    rx, ry = bx + dx, by + dy
                    if rx < 0 or ry < 0 or rx >= grid_w or ry >= grid_h or occupied[ry][rx]:
                        overlap = True
                        break
                if overlap: break
                
            if not overlap:
                # Place it!
                for dy in range(b.height):
                    for dx in range(b.width):
                        occupied[by+dy][bx+dx] = True
                final_placed_b.append(PlacedBuilding(building_id=b.id, x=bx, y=by))
                valid_placed_b_map[b.id] = (bx, by)

        # Draw roads for valid placed buildings
        # Road representation: roads[y][x] = road_type (1 or 2)
        roads = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
        for tx, ty in hub_tiles:
            roads[ty][tx] = 3 # Connection hub is a road root
            
        final_placed_roads = []
        
        # Helper: Dijkstra pathfinder from any tile to road network
        def find_shortest_road_path(start_tiles, req_type):
            # start_tiles is a set of coordinates bordering the building
            queue = []
            visited = {}
            for sx, sy in start_tiles:
                if 0 <= sx < grid_w and 0 <= sy < grid_h:
                    queue.append((sx, sy, 0))
                    visited[(sx, sy)] = None
                    
            head = 0
            found_dest = None
            
            while head < len(queue):
                cx, cy, dist = queue[head]
                head += 1
                
                # Check if we touch a road of sufficient type (or hub)
                if roads[cy][cx] >= req_type:
                    found_dest = (cx, cy)
                    break
                    
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < grid_w and 0 <= ny < grid_h:
                        if (nx, ny) not in visited:
                            # We can walk through empty/unoccupied cells or existing roads
                            # We CANNOT walk through other placed buildings
                            if not occupied[ny][nx] or roads[ny][nx] > 0:
                                visited[(nx, ny)] = (cx, cy)
                                queue.append((nx, ny, dist + 1))
                                
            if found_dest:
                # Trace back path
                path = []
                curr = found_dest
                while curr is not None:
                    path.append(curr)
                    curr = visited[curr]
                return path[::-1] # return path from start to dest
            return None

        # Route roads for each building requiring roads
        disconnected_count = 0
        for pb in final_placed_b:
            if pb.building_id == hub.id: continue
            b = next(x for x in other_buildings if x.id == pb.building_id)
            if b.road_type == 0: continue
            
            # Find boundary tiles bordering this building
            boundary = set()
            for dx in range(b.width):
                boundary.add((pb.x + dx, pb.y - 1))
                boundary.add((pb.x + dx, pb.y + b.height))
            for dy in range(b.height):
                boundary.add((pb.x - 1, pb.y + dy))
                boundary.add((pb.x + b.width, pb.y + dy))
                
            path = find_shortest_road_path(boundary, b.road_type)
            if path:
                # Draw the road path!
                for rx, ry in path:
                    roads[ry][rx] = max(roads[ry][rx], b.road_type)
                    occupied[ry][rx] = True
            else:
                # Could not connect this building
                disconnected_count += 1

        # Build final placed roads list based on roads grid
        # To avoid duplicating 2x2 roads, we can trace and output them cleanly
        road_tiles_used = set()
        for y in range(grid_h):
            for x in range(grid_w):
                if roads[y][x] == 2 and (x, y) not in road_tiles_used:
                    # Place 2x2 road if it fits
                    if x + 1 < grid_w and y + 1 < grid_h:
                        final_placed_roads.append(PlacedRoad(x=x, y=y, type=2))
                        for dy in range(2):
                            for dx in range(2):
                                road_tiles_used.add((x + dx, y + dy))
                    else:
                        # Fallback to 1x1 if boundary exceeded
                        final_placed_roads.append(PlacedRoad(x=x, y=y, type=1))
                        road_tiles_used.add((x, y))
                elif roads[y][x] == 1 and (x, y) not in road_tiles_used:
                    final_placed_roads.append(PlacedRoad(x=x, y=y, type=1))
                    road_tiles_used.add((x, y))

        # Scoring
        num_placed = len(final_placed_b)
        road_cost = sum(1 for pr in final_placed_roads for dy in range(pr.type) for dx in range(pr.type))
        
        # Heavy penalty for disconnected critical buildings
        score = num_placed * 10000 - road_cost - (disconnected_count * 15000)
        
        return final_placed_b, final_placed_roads, score, valid_placed_b_map

    # Initialize State: Place as many buildings as possible using a fast greedy pass
    current_b_map = {}
    
    # Try random placements to build the starting layout
    b_order = other_buildings.copy()
    random.shuffle(b_order)
    
    for b in b_order:
        placed = False
        for _ in range(20): # Try 20 random positions
            rx = random.randint(0, grid_w - b.width)
            ry = random.randint(0, grid_h - b.height)
            # Verify basic validity (no overlap with hub)
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

    # Evaluate initial state
    best_placed_b, best_placed_roads, best_score, current_b_map = evaluate_state(current_b_map)
    
    # Simulated Annealing parameters
    temp = 1000.0
    cooling_rate = 0.992
    iterations = request.annealing_iterations or 1500
    
    for i in range(iterations):
        temp *= cooling_rate
        if not other_buildings: break
        
        # Copy current state mapping
        next_b_map = current_b_map.copy()
        
        # Perturbation step
        perturb_type = random.choice(["shift", "swap", "add_remove"])
        
        if perturb_type == "shift" and next_b_map:
            # Shift a random building
            b_id = random.choice(list(next_b_map.keys()))
            b = next(x for x in other_buildings if x.id == b_id)
            nx = random.randint(0, grid_w - b.width)
            ny = random.randint(0, grid_h - b.height)
            next_b_map[b_id] = (nx, ny)
            
        elif perturb_type == "swap" and len(next_b_map) >= 2:
            # Swap positions of two placed buildings
            id1, id2 = random.sample(list(next_b_map.keys()), 2)
            next_b_map[id1], next_b_map[id2] = next_b_map[id2], next_b_map[id1]
            
        else: # add_remove
            b = random.choice(other_buildings)
            if b.id in next_b_map:
                # Remove it
                del next_b_map[b.id]
            else:
                # Add it at a random valid spot
                rx = random.randint(0, grid_w - b.width)
                ry = random.randint(0, grid_h - b.height)
                next_b_map[b.id] = (rx, ry)

        # Evaluate the neighbor state
        next_placed_b, next_placed_roads, next_score, next_valid_b_map = evaluate_state(next_b_map)
        
        # Boltzmann selection
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
