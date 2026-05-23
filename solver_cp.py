from models import SolveRequest, SolveResponse, PlacedBuilding, PlacedRoad
from ortools.sat.python import cp_model
import random

def solve_layout(request: SolveRequest) -> SolveResponse:
    grid_w = request.grid.width
    grid_h = request.grid.height
    valid_tiles = request.grid.valid_tiles
    
    # Identify connection hub
    buildings = request.buildings.copy()
    hub = next((b for b in buildings if b.name.lower().startswith('townhall') or b.name.lower().startswith('embassy')), None)
    if not hub:
        return SolveResponse(placed_buildings=[], placed_roads=[], score=0.0)
        
    other_buildings = [b for b in buildings if b.id != hub.id]
    
    # Pre-determine Hub placement
    hub_w, hub_h = hub.width, hub.height
    if request.townhall_fixed and request.townhall_pos:
        hub_x, hub_y = request.townhall_pos
    else:
        hub_x = max(0, (grid_w - hub_w) // 2)
        hub_y = max(0, (grid_h - hub_h) // 2)
        
    # Verify hub fits in valid area
    hub_fit = True
    for dy in range(hub_h):
        for dx in range(hub_w):
            if hub_x + dx >= grid_w or hub_y + dy >= grid_h or not valid_tiles[hub_y + dy][hub_x + dx]:
                hub_fit = False
                break
        if not hub_fit: break
        
    if not hub_fit:
        # Search for a valid center-ish placement
        found = False
        for dist in range(1, max(grid_w, grid_h)):
            for sy in range(-dist, dist + 1):
                for sx in range(-dist, dist + 1):
                    cx, cy = hub_x + sx, hub_y + sy
                    if 0 <= cx < grid_w - hub_w and 0 <= cy < grid_h - hub_h:
                        fit = True
                        for hdy in range(hub_h):
                            for hdx in range(hub_w):
                                if not valid_tiles[cy + hdy][cx + hdx]:
                                    fit = False
                                    break
                            if not fit: break
                        if fit:
                            hub_x, hub_y = cx, cy
                            found = True
                            break
                if found: break
            if found: break

    hub_tiles = set((hub_x + dx, hub_y + dy) for dy in range(hub_h) for dx in range(hub_w))

    # Pre-generate road backbone
    roads = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
    
    max_road_req = 1
    if any(b.road_type == 2 for b in other_buildings):
        max_road_req = 2
        
    backbone = request.backbone_type or "center_spine"
    
    if backbone == "center_spine":
        spine_y = grid_h // 2
        for x in range(grid_w):
            if valid_tiles[spine_y][x]:
                roads[spine_y][x] = max(roads[spine_y][x], max_road_req)
                if max_road_req == 2 and spine_y + 1 < grid_h and valid_tiles[spine_y + 1][x]:
                    roads[spine_y + 1][x] = max(roads[spine_y + 1][x], 2)
                    
        # Connect Hub to spine
        min_y = min(hub_y, spine_y)
        max_y = max(hub_y + hub_h - 1, spine_y)
        conn_x = hub_x + hub_w // 2
        for y in range(min_y, max_y + 1):
            if valid_tiles[y][conn_x]:
                roads[y][conn_x] = max(roads[y][conn_x], max_road_req)

    elif backbone == "grid":
        lanes = [y for y in range(2, grid_h, 5)]
        for lane_y in lanes:
            for x in range(grid_w):
                if valid_tiles[lane_y][x]:
                    roads[lane_y][x] = max(roads[lane_y][x], max_road_req)
                    if max_road_req == 2 and lane_y + 1 < grid_h and valid_tiles[lane_y + 1][x]:
                        roads[lane_y + 1][x] = max(roads[lane_y + 1][x], 2)
                        
        conn_x = hub_x + hub_w // 2
        for y in range(grid_h):
            if valid_tiles[y][conn_x]:
                roads[y][conn_x] = max(roads[y][conn_x], max_road_req)

    elif backbone == "perimeter":
        for y in range(grid_h):
            for x in range(grid_w):
                if valid_tiles[y][x]:
                    is_border = False
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        rx, ry = x + dx, y + dy
                        if rx < 0 or ry < 0 or rx >= grid_w or ry >= grid_h or not valid_tiles[ry][rx]:
                            is_border = True
                            break
                    if is_border:
                        roads[y][x] = max(roads[y][x], max_road_req)
                        
        conn_x = hub_x + hub_w // 2
        for y in range(grid_h):
            if valid_tiles[y][conn_x]:
                roads[y][conn_x] = max(roads[y][conn_x], max_road_req)

    elif backbone == "custom" and request.custom_roads:
        for pr in request.custom_roads:
            if pr.type == 2:
                for dy in range(2):
                    for dx in range(2):
                        rx, ry = pr.x + dx, pr.y + dy
                        if 0 <= rx < grid_w and 0 <= ry < grid_h:
                            roads[ry][rx] = max(roads[ry][rx], 2)
            else:
                if 0 <= pr.x < grid_w and 0 <= pr.y < grid_h:
                    roads[pr.y][pr.x] = max(roads[pr.y][pr.x], 1)

    # Initialize CP-SAT Model
    model = cp_model.CpModel()
    
    # Store interval variables for 2D No Overlap constraint
    x_intervals = []
    y_intervals = []
    
    # 1. Place connection Hub (always placed, fixed position)
    hub_x_var = model.NewConstant(hub_x)
    hub_y_var = model.NewConstant(hub_y)
    hub_x_interval = model.NewIntervalVar(hub_x_var, hub_w, hub_x_var + hub_w, "hub_x_interval")
    hub_y_interval = model.NewIntervalVar(hub_y_var, hub_h, hub_y_var + hub_h, "hub_y_interval")
    
    x_intervals.append(hub_x_interval)
    y_intervals.append(hub_y_interval)

    # 2. Add fixed blocks for invalid tiles and road tiles
    # So buildings don't overlap with invalid areas or pre-drawn backbone roads
    for y in range(grid_h):
        for x in range(grid_w):
            if not valid_tiles[y][x] or (roads[y][x] > 0 and (x, y) not in hub_tiles):
                # Fixed 1x1 mandatory block
                fixed_x = model.NewConstant(x)
                fixed_y = model.NewConstant(y)
                fixed_x_int = model.NewIntervalVar(fixed_x, 1, fixed_x + 1, f"fixed_x_{x}_{y}")
                fixed_y_int = model.NewIntervalVar(fixed_y, 1, fixed_y + 1, f"fixed_y_{x}_{y}")
                x_intervals.append(fixed_x_int)
                y_intervals.append(fixed_y_int)

    # Helper: Pre-compute all coordinates (x, y) adjacent to roads
    def get_road_touching_coords(b_w, b_h, req_road_type):
        valid_coords = []
        for y in range(grid_h - b_h + 1):
            for x in range(grid_w - b_w + 1):
                # Verify building fits inside valid grid first
                fits = True
                for dy in range(b_h):
                    for dx in range(b_w):
                        tx, ty = x + dx, y + dy
                        # Must not overlap with hub tiles
                        if (tx, ty) in hub_tiles or not valid_tiles[ty][tx] or roads[ty][tx] > 0:
                            fits = False
                            break
                    if not fits: break
                    
                if fits:
                    # Check if adjacent to road of sufficient type (or adjacent to Hub)
                    is_touching = False
                    for dx in range(b_w):
                        if y - 1 >= 0 and (roads[y - 1][x + dx] >= req_road_type or (x + dx, y - 1) in hub_tiles): is_touching = True
                        if y + b_h < grid_h and (roads[y + b_h][x + dx] >= req_road_type or (x + dx, y + b_h) in hub_tiles): is_touching = True
                    for dy in range(b_h):
                        if x - 1 >= 0 and (roads[y + dy][x - 1] >= req_road_type or (x - 1, y + dy) in hub_tiles): is_touching = True
                        if x + b_w < grid_w and (roads[y + dy][x + b_w] >= req_road_type or (x + b_w, y + dy) in hub_tiles): is_touching = True
                        
                    if is_touching:
                        valid_coords.append((x, y))
        return valid_coords

    # 3. Define placement variables for each inventory building
    building_vars = {}
    for i, b in enumerate(other_buildings):
        placed_var = model.NewBoolVar(f"placed_{b.id}")
        x_var = model.NewIntVar(0, grid_w - b.width, f"x_{b.id}")
        y_var = model.NewIntVar(0, grid_h - b.height, f"y_{b.id}")
        
        x_interval = model.NewOptionalIntervalVar(x_var, b.width, x_var + b.width, placed_var, f"x_interval_{b.id}")
        y_interval = model.NewOptionalIntervalVar(y_var, b.height, y_var + b.height, placed_var, f"y_interval_{b.id}")
        
        x_intervals.append(x_interval)
        y_intervals.append(y_interval)
        
        building_vars[b.id] = (placed_var, x_var, y_var)
        
        # Connectivity: If building requires road, force it to be placed adjacent to roads
        if b.road_type > 0:
            allowed_positions = get_road_touching_coords(b.width, b.height, b.road_type)
            if allowed_positions:
                model.AddAllowedAssignments([x_var, y_var], allowed_positions).OnlyEnforceIf(placed_var)
            else:
                # If no position fits this building adjacent to a road, force placed = False
                model.Add(placed_var == 0)

    # 4. Enforce 2D Non-Overlapping
    model.AddNoOverlap2D(x_intervals, y_intervals)

    # 5. Objective: Maximize total placed building area/count
    # Reward placing buildings, with larger area buildings contributing more to maximize space utilization
    objective_terms = []
    for b in other_buildings:
        placed_var = building_vars[b.id][0]
        area = b.width * b.height
        objective_terms.append(placed_var * (1000 + area))
        
    model.Maximize(sum(objective_terms))

    # 6. Solve
    solver = cp_model.CpSolver()
    # Set solve timeout
    solver.parameters.max_time_in_seconds = request.optimization_time or 10.0
    status = solver.Solve(model)

    # Parse results
    placed_buildings = [PlacedBuilding(building_id=hub.id, x=hub_x, y=hub_y)]
    keep_road_tiles = set()
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for b in other_buildings:
            placed_var, x_var, y_var = building_vars[b.id]
            if solver.BooleanValue(placed_var):
                bx, by = solver.Value(x_var), solver.Value(y_var)
                placed_buildings.append(PlacedBuilding(building_id=b.id, x=bx, y=by))
                
                # Flag the surrounding road tiles we are touching to keep them from pruning
                if b.road_type > 0:
                    for dx in range(b.width):
                        if by - 1 >= 0 and roads[by - 1][bx + dx] >= b.road_type: keep_road_tiles.add((bx + dx, by - 1))
                        if by + b.height < grid_h and roads[by + b.height][bx + dx] >= b.road_type: keep_road_tiles.add((bx + dx, by + b.height))
                    for dy in range(b.height):
                        if bx - 1 >= 0 and roads[by + dy][bx - 1] >= b.road_type: keep_road_tiles.add((bx - 1, by + dy))
                        if bx + b.width < grid_w and roads[by + dy][bx + b.width] >= b.road_type: keep_road_tiles.add((bx + b.width, by + dy))

    # Trace back keeping roads to connect to connection hub
    final_keep_tiles = set()
    if keep_road_tiles:
        # Run BFS from Hub to find all reachable paths
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
                        
        # Trace path back for each target tile
        for target in keep_road_tiles:
            if target in visited:
                curr = target
                while curr is not None:
                    final_keep_tiles.add(curr)
                    curr = visited[curr]

    # Rebuild placed roads
    placed_roads = []
    road_tiles_used = set()
    for y in range(grid_h):
        for x in range(grid_w):
            if (x, y) in final_keep_tiles and (x, y) not in road_tiles_used:
                if roads[y][x] == 2 and x + 1 < grid_w and y + 1 < grid_h:
                    placed_roads.append(PlacedRoad(x=x, y=y, type=2))
                    for dy in range(2):
                        for dx in range(2):
                            road_tiles_used.add((x + dx, y + dy))
                else:
                    placed_roads.append(PlacedRoad(x=x, y=y, type=1))
                    road_tiles_used.add((x, y))

    road_cost = sum(1 for pr in placed_roads for dy in range(pr.type) for dx in range(pr.type))
    score = len(placed_buildings) * 10000 - road_cost
    
    num_1x1 = sum(1 for r in placed_roads if r.type == 1)
    num_2x2 = sum(1 for r in placed_roads if r.type == 2)
    
    return SolveResponse(
        placed_buildings=placed_buildings,
        placed_roads=placed_roads,
        score=score,
        num_1x1_roads=num_1x1,
        num_2x2_roads=num_2x2
    )
