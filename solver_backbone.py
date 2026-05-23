from models import SolveRequest, SolveResponse, PlacedBuilding, PlacedRoad
import random

def solve_layout(request: SolveRequest) -> SolveResponse:
    random.seed(random.randint(0, 1000000))
    
    grid_w = request.grid.width
    grid_h = request.grid.height
    valid_tiles = request.grid.valid_tiles
    
    # Identify connection hub
    buildings = request.buildings.copy()
    hub = next((b for b in buildings if b.name.lower().startswith('townhall') or b.name.lower().startswith('embassy')), None)
    if not hub:
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

    # Initialize roads and occupied grids
    roads = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
    occupied = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]

    # Mark hub
    for tx, ty in hub_tiles:
        if 0 <= tx < grid_w and 0 <= ty < grid_h:
            occupied[ty][tx] = True
            roads[ty][tx] = 3

    # Generate backbone roads
    backbone = request.backbone_type or "center_spine"
    
    # Determine the maximum road requirement type (to decide 1x1 or 2x2 roads)
    max_road_req = 1
    if any(b.road_type == 2 for b in other_buildings):
        max_road_req = 2
        
    if backbone == "center_spine":
        # Draw a horizontal spine in the center
        spine_y = grid_h // 2
        for x in range(grid_w):
            if is_tile_valid(x, spine_y):
                roads[spine_y][x] = max(roads[spine_y][x], max_road_req)
                occupied[spine_y][x] = True
                if max_road_req == 2 and spine_y + 1 < grid_h and is_tile_valid(x, spine_y + 1):
                    roads[spine_y + 1][x] = max(roads[spine_y + 1][x], 2)
                    occupied[spine_y + 1][x] = True
                    
        # Connect Hub to spine with a vertical road
        min_y = min(hub_y, spine_y)
        max_y = max(hub_y + hub_h - 1, spine_y)
        conn_x = hub_x + hub_w // 2
        for y in range(min_y, max_y + 1):
            if is_tile_valid(conn_x, y):
                roads[y][conn_x] = max(roads[y][conn_x], max_road_req)
                occupied[y][conn_x] = True

    elif backbone == "grid":
        # Draw horizontal lanes every 5 tiles
        lanes = [y for y in range(2, grid_h, 5)]
        for lane_y in lanes:
            for x in range(grid_w):
                if is_tile_valid(x, lane_y):
                    roads[lane_y][x] = max(roads[lane_y][x], max_road_req)
                    occupied[lane_y][x] = True
                    if max_road_req == 2 and lane_y + 1 < grid_h and is_tile_valid(x, lane_y + 1):
                        roads[lane_y + 1][x] = max(roads[lane_y + 1][x], 2)
                        occupied[lane_y + 1][x] = True
                        
        # Draw a vertical spine to link all lanes
        conn_x = hub_x + hub_w // 2
        for y in range(grid_h):
            if is_tile_valid(conn_x, y):
                roads[y][conn_x] = max(roads[y][conn_x], max_road_req)
                occupied[y][conn_x] = True

    elif backbone == "perimeter":
        # Draw perimeter loop around valid outer grid cells
        for y in range(grid_h):
            for x in range(grid_w):
                if is_tile_valid(x, y):
                    # Check if it is a border cell of the valid area
                    is_border = False
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        if not is_tile_valid(x + dx, y + dy):
                            is_border = True
                            break
                    if is_border:
                        roads[y][x] = max(roads[y][x], max_road_req)
                        occupied[y][x] = True
                        
        # Ensure Hub is connected
        conn_x = hub_x + hub_w // 2
        for y in range(grid_h):
            if is_tile_valid(conn_x, y):
                roads[y][conn_x] = max(roads[y][conn_x], max_road_req)
                occupied[y][conn_x] = True

    elif backbone == "custom" and request.custom_roads:
        # Load user-painted roads
        for pr in request.custom_roads:
            if pr.type == 2:
                for dy in range(2):
                    for dx in range(2):
                        rx, ry = pr.x + dx, pr.y + dy
                        if 0 <= rx < grid_w and 0 <= ry < grid_h:
                            roads[ry][rx] = max(roads[ry][rx], 2)
                            occupied[ry][rx] = True
            else:
                if 0 <= pr.x < grid_w and 0 <= pr.y < grid_h:
                    roads[pr.y][pr.x] = max(roads[pr.y][pr.x], 1)
                    occupied[pr.y][pr.x] = True

    # Pack other buildings flush against the road network
    placed_buildings = [PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y)]
    
    # Sort inventory by size descending
    sorted_b = sorted(other_buildings, key=lambda x: x.width * x.height, reverse=True)
    
    def is_adjacent_to_road(cx, cy, cw, ch, req_road_type):
        if req_road_type == 0:
            return True
        for dx in range(cw):
            if cy - 1 >= 0 and (roads[cy-1][cx+dx] >= req_road_type or (cx+dx, cy-1) in hub_tiles): return True
            if cy + ch < grid_h and (roads[cy+ch][cx+dx] >= req_road_type or (cx+dx, cy+ch) in hub_tiles): return True
        for dy in range(ch):
            if cx - 1 >= 0 and (roads[cy+dy][cx-1] >= req_road_type or (cx-1, cy+dy) in hub_tiles): return True
            if cx + cw < grid_w and (roads[cy+dy][cx+cw] >= req_road_type or (cx+cw, cy+dy) in hub_tiles): return True
        return False

    def can_place(x, y, w, h):
        if x < 0 or y < 0 or x + w > grid_w or y + h > grid_h:
            return False
        for dy in range(h):
            for dx in range(w):
                if occupied[y+dy][x+dx]:
                    return False
        return True

    for b in sorted_b:
        best_x, best_y = -1, -1
        # Greedy search for a placement touching the road
        found = False
        for y in range(grid_h):
            for x in range(grid_w):
                if can_place(x, y, b.width, b.height):
                    if is_adjacent_to_road(x, y, b.width, b.height, b.road_type):
                        best_x, best_y = x, y
                        found = True
                        break
            if found: break
            
        if found:
            # Place it!
            for dy in range(b.height):
                for dx in range(b.width):
                    occupied[best_y+dy][best_x+dx] = True
            placed_buildings.append(PlacedBuilding(building_id=b.id, x=best_x, y=best_y))

    # Post-Placement BFS Road Pruning
    # Prune any road tile that is NOT connected or adjacent to a placed building!
    keep_tiles = set()
    
    # Run BFS from the connection hub tiles to find all reachable road cells
    queue = []
    visited = {}
    for th_tx, th_ty in hub_tiles:
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = th_tx + dx, th_ty + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                if roads[ny][nx] > 0 and (nx, ny) not in visited:
                    visited[(nx, ny)] = None
                    queue.append((nx, ny))
                    
    head = 0
    while head < len(queue):
        cx, cy = queue[head]
        head += 1
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                if roads[ny][nx] > 0 and (nx, ny) not in visited:
                    visited[(nx, ny)] = (cx, cy)
                    queue.append((nx, ny))

    # For each placed building requiring roads, find adjacent reachable road tiles
    building_road_types = {b.id: b.road_type for b in buildings}
    for pb in placed_buildings:
        if pb.building_id == hub.id: continue
        req_type = building_road_types[pb.building_id]
        if req_type == 0: continue
        
        b = next(x for x in buildings if x.id == pb.building_id)
        w, h = b.width, b.height
        
        connected_tiles = []
        # Check top/bottom boundaries
        for dx in range(w):
            if pb.y - 1 >= 0 and roads[pb.y - 1][pb.x + dx] >= req_type and (pb.x + dx, pb.y - 1) in visited:
                connected_tiles.append((pb.x + dx, pb.y - 1))
            if pb.y + h < grid_h and roads[pb.y + h][pb.x + dx] >= req_type and (pb.x + dx, pb.y + h) in visited:
                connected_tiles.append((pb.x + dx, pb.y + h))
        # Check left/right boundaries
        for dy in range(h):
            if pb.x - 1 >= 0 and roads[pb.y + dy][pb.x - 1] >= req_type and (pb.x - 1, pb.y + dy) in visited:
                connected_tiles.append((pb.x - 1, pb.y + dy))
            if pb.x + w < grid_w and roads[pb.y + dy][pb.x + w] >= req_type and (pb.x + w, pb.y + dy) in visited:
                connected_tiles.append((pb.x + w, pb.y + dy))
                
        # Trace path back to Hub
        for start_tile in connected_tiles:
            curr = start_tile
            while curr is not None:
                keep_tiles.add(curr)
                curr = visited[curr]

    # Rebuild placed roads using only keep_tiles
    placed_roads = []
    road_tiles_used = set()
    for y in range(grid_h):
        for x in range(grid_w):
            if (x, y) in keep_tiles and (x, y) not in road_tiles_used:
                if roads[y][x] == 2 and x + 1 < grid_w and y + 1 < grid_h:
                    placed_roads.append(PlacedRoad(x=x, y=y, type=2))
                    for dy in range(2):
                        for dx in range(2):
                            road_tiles_used.add((x + dx, y + dy))
                else:
                    placed_roads.append(PlacedRoad(x=x, y=y, type=1))
                    road_tiles_used.add((x, y))

    # Calculate final score
    num_placed = len(placed_buildings)
    road_cost = sum(1 for pr in placed_roads for dy in range(pr.type) for dx in range(pr.type))
    score = num_placed * 10000 - road_cost

    num_1x1 = sum(1 for r in placed_roads if r.type == 1)
    num_2x2 = sum(1 for r in placed_roads if r.type == 2)

    return SolveResponse(
        placed_buildings=placed_buildings,
        placed_roads=placed_roads,
        score=score,
        num_1x1_roads=num_1x1,
        num_2x2_roads=num_2x2
    )
