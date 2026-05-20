from models import SolveRequest, SolveResponse, PlacedBuilding, PlacedRoad
import math
import time
import random
import os
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

def solve_single_worker(request: SolveRequest, seed: int) -> SolveResponse:
    random.seed(seed)
    
    def dprint(*args, **kwargs):
        if request.debug:
            print(*args, **kwargs)
            
    grid_w = request.grid.width
    grid_h = request.grid.height
    valid_tiles = request.grid.valid_tiles
    
    buildings_orig = request.buildings.copy()
    th_building = next((b for b in buildings_orig if b.name.lower().startswith('townhall')), None)
    if th_building:
        buildings_orig.remove(th_building)
        
    group_2_orig = [b for b in buildings_orig if b.road_type == 2]
    group_1_orig = [b for b in buildings_orig if b.road_type == 1]
    group_0_orig = [b for b in buildings_orig if b.road_type == 0]

    end_time = time.time() + request.optimization_time
    
    best_response = None
    best_score = -float('inf')

    # Ensure at least 1 iteration runs even if time is 0
    iterations = 0
    
    while time.time() < end_time or iterations == 0:
        iterations += 1
        dprint(f"\n--- Starting iteration {iterations} ---")
        
        # 0 = not a road, 1 = 1x1 road, 2 = 2x2 road, 3 = Townhall (highest road type)
        roads = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
        occupied = [[not valid_tiles[y][x] for x in range(grid_w)] for y in range(grid_h)]
        
        placed_buildings = []
        placed_roads = []
        
        # Shuffle within same area size
        def shuffle_group(g):
            g_copy = g.copy()
            # group by area
            by_area = {}
            for b in g_copy:
                a = b.width * b.height
                if a not in by_area: by_area[a] = []
                by_area[a].append(b)
            
            res = []
            for a in sorted(by_area.keys(), reverse=True):
                lst = by_area[a]
                random.shuffle(lst)
                res.extend(lst)
            return res

        group_2 = shuffle_group(group_2_orig)
        group_1 = shuffle_group(group_1_orig)
        group_0 = shuffle_group(group_0_orig)
        
        dprint(f"Initial groups: road_type=2 ({len(group_2)} bldgs), road_type=1 ({len(group_1)} bldgs), road_type=0 ({len(group_0)} bldgs)")
        
        def can_place(x, y, w, h):
            if x < 0 or y < 0 or x + w > grid_w or y + h > grid_h:
                return False
            for dy in range(h):
                for dx in range(w):
                    if occupied[y+dy][x+dx]:
                        return False
            return True

        def mark_occupied(x, y, w, h):
            for dy in range(h):
                for dx in range(w):
                    occupied[y+dy][x+dx] = True

        # Place Townhall
        th_x, th_y, th_w, th_h = 0, 0, 0, 0
        th_tiles = set()
        if th_building:
            if request.townhall_fixed and request.townhall_pos:
                th_x, th_y = request.townhall_pos
                dprint(f"Placing fixed Townhall at ({th_x}, {th_y})")
            else:
                th_x = grid_w // 2 - th_building.width // 2
                th_y = grid_h // 2 - th_building.height // 2
                dprint(f"Placing dynamic Townhall near center ({th_x}, {th_y})")
            
            placed_th = False
            if can_place(th_x, th_y, th_building.width, th_building.height):
                placed_th = True
            else:
                best_dist = float('inf')
                for y in range(grid_h):
                    for x in range(grid_w):
                        if can_place(x, y, th_building.width, th_building.height):
                            dist = abs(x - th_x) + abs(y - th_y)
                            if dist < best_dist:
                                best_dist = dist
                                th_x, th_y = x, y
                                placed_th = True
            if placed_th:
                mark_occupied(th_x, th_y, th_building.width, th_building.height)
                placed_buildings.append(PlacedBuilding(building_id=th_building.id, x=th_x, y=th_y))
                dprint(f"Townhall placed at ({th_x}, {th_y})")
                
                # Define Townhall tiles
                th_tiles = set()
                for dy in range(th_building.height):
                    for dx in range(th_building.width):
                        th_tiles.add((th_x + dx, th_y + dy))
                
                # Try placing seed road
                seed_type = 0
                if len(group_2_orig) > 0:
                    seed_type = 2
                elif len(group_1_orig) > 0:
                    seed_type = 1

                if seed_type > 0:
                    # Randomize seed side - anywhere along the edges
                    seed_candidates = []
                    # Top side
                    for offset in range(th_building.width - seed_type + 1):
                        seed_candidates.append((th_x + offset, th_y - seed_type))
                    # Bottom side
                    for offset in range(th_building.width - seed_type + 1):
                        seed_candidates.append((th_x + offset, th_y + th_building.height))
                    # Left side
                    for offset in range(th_building.height - seed_type + 1):
                        seed_candidates.append((th_x - seed_type, th_y + offset))
                    # Right side
                    for offset in range(th_building.height - seed_type + 1):
                        seed_candidates.append((th_x + th_building.width, th_y + offset))
                    
                    random.shuffle(seed_candidates)
                    
                    for sx, sy in seed_candidates:
                        if sx >= 0 and sy >= 0 and sx + seed_type <= grid_w and sy + seed_type <= grid_h:
                            can_place_seed = True
                            for dy in range(seed_type):
                                for dx in range(seed_type):
                                    if occupied[sy+dy][sx+dx]:
                                        can_place_seed = False
                            
                            if can_place_seed:
                                for dy in range(seed_type):
                                    for dx in range(seed_type):
                                        roads[sy+dy][sx+dx] = seed_type
                                placed_roads.append(PlacedRoad(x=sx, y=sy, type=seed_type))
                                mark_occupied(sx, sy, seed_type, seed_type)
                                dprint(f"Placed seed road of type {seed_type} at ({sx}, {sy})")
                                break
            else:
                dprint("WARNING: Could not place Townhall!")

        # Helper to check if a position has an adjacent road of sufficient type
        def get_touching_score(x, y, w, h, req_road_type):
            if req_road_type == 0:
                return 0
                
            touches_top_bottom = False
            touches_left_right = False
            
            for dx in range(w):
                if y - 1 >= 0 and roads[y-1][x+dx] >= req_road_type: touches_top_bottom = True
                if y + h < grid_h and roads[y+h][x+dx] >= req_road_type: touches_top_bottom = True
                    
            for dy in range(h):
                if x - 1 >= 0 and roads[y+dy][x-1] >= req_road_type: touches_left_right = True
                if x + w < grid_w and roads[y+dy][x+w] >= req_road_type: touches_left_right = True

            if not touches_top_bottom and not touches_left_right:
                return float('inf')
                
            if touches_top_bottom and touches_left_right: return min(w, h)
            if touches_top_bottom: return w
            return h

        def is_adjacent_to_road(cx, cy, cw, ch, req_road_type):
            for dx in range(cw):
                if cy - 1 >= 0 and (roads[cy-1][cx+dx] >= req_road_type or (cx+dx, cy-1) in th_tiles): return True
                if cy + ch < grid_h and (roads[cy+ch][cx+dx] >= req_road_type or (cx+dx, cy+ch) in th_tiles): return True
            for dy in range(ch):
                if cx - 1 >= 0 and (roads[cy+dy][cx-1] >= req_road_type or (cx-1, cy+dy) in th_tiles): return True
                if cx + cw < grid_w and (roads[cy+dy][cx+cw] >= req_road_type or (cx+cw, cy+dy) in th_tiles): return True
            return False

        def place_group(group, req_road_type):
            progress_made = True
            while progress_made and group:
                progress_made = False
                placed_indices_in_step_1 = set()
                
                def count_expansion_candidates(req_type):
                    count = 0
                    r = req_type
                    for ry in range(grid_h - r + 1):
                        for rx in range(grid_w - r + 1):
                            if can_place(rx, ry, r, r) and is_adjacent_to_road(rx, ry, r, r, req_type):
                                count += 1
                    return count

                for i in range(len(group)):
                    if i in placed_indices_in_step_1: continue
                    b = group[i]
                    
                    best_b_score = float('inf')
                    best_x, best_y = -1, -1
                    
                    for y in range(grid_h):
                        for x in range(grid_w):
                            if can_place(x, y, b.width, b.height):
                                score = get_touching_score(x, y, b.width, b.height, req_road_type)
                                if score != float('inf'):
                                    score += random.uniform(0, 1.5) # Add noise
                                    if score < best_b_score:
                                        mark_occupied(x, y, b.width, b.height)
                                        exp_count = count_expansion_candidates(req_road_type)
                                        for dy in range(b.height):
                                            for dx in range(b.width):
                                                occupied[y+dy][x+dx] = False
                                                
                                        if exp_count >= 1 or len(group) == 1:
                                            best_b_score = score
                                            best_x, best_y = x, y
                                    
                    if best_b_score != float('inf'):
                        mark_occupied(best_x, best_y, b.width, b.height)
                        placed_buildings.append(PlacedBuilding(building_id=b.id, x=best_x, y=best_y))
                        placed_indices_in_step_1.add(i)
                        progress_made = True
                        dprint(f"Placed building '{b.name}' ({b.id}) at ({best_x}, {best_y}) (adjacent to road, score={best_b_score:.2f})")
                
                if progress_made:
                    group = [b for i, b in enumerate(group) if i not in placed_indices_in_step_1]
                    continue
                    
                if not group: break
                    
                r = req_road_type
                best_road_score = -float('inf')
                best_rx, best_ry = -1, -1
                
                for ry in range(grid_h - r + 1):
                    for rx in range(grid_w - r + 1):
                        if not can_place(rx, ry, r, r): continue
                        
                        has_any_roads = any(road_type > 0 for row in roads for road_type in row)
                        if has_any_roads and not is_adjacent_to_road(rx, ry, r, r, req_road_type): continue
                            
                        straightness = 0
                        if r == 1:
                            if rx > 0 and roads[ry][rx-1] >= 1:
                                if rx > 1 and roads[ry][rx-2] >= 1: straightness += 1
                            if rx + 1 < grid_w and roads[ry][rx+1] >= 1:
                                if rx + 2 < grid_w and roads[ry][rx+2] >= 1: straightness += 1
                            if ry > 0 and roads[ry-1][rx] >= 1:
                                if ry > 1 and roads[ry-2][rx] >= 1: straightness += 1
                            if ry + 1 < grid_h and roads[ry+1][rx] >= 1:
                                if ry + 2 < grid_h and roads[ry+2][rx] >= 1: straightness += 1
                        else:
                            if rx > 0 and (roads[ry][rx-1] >= 2 or roads[ry+1][rx-1] >= 2):
                                if rx > 1 and (roads[ry][rx-2] >= 2 or roads[ry+1][rx-2] >= 2): straightness += 1
                            if rx + 2 < grid_w and (roads[ry][rx+2] >= 2 or roads[ry+1][rx+2] >= 2):
                                if rx + 3 < grid_w and (roads[ry][rx+3] >= 2 or roads[ry+1][rx+3] >= 2): straightness += 1
                            if ry > 0 and (roads[ry-1][rx] >= 2 or roads[ry-1][rx+1] >= 2):
                                if ry > 1 and (roads[ry-2][rx] >= 2 or roads[ry-2][rx+1] >= 2): straightness += 1
                            if ry + 2 < grid_h and (roads[ry+2][rx] >= 2 or roads[ry+2][rx+1] >= 2):
                                if ry + 3 < grid_h and (roads[ry+3][rx] >= 2 or roads[ry+3][rx+1] >= 2): straightness += 1

                        mark_occupied(rx, ry, r, r)
                        for dy in range(r):
                            for dx in range(r):
                                roads[ry+dy][rx+dx] = r
                        
                        enabled_b_idx = -1
                        min_b_score = float('inf')
                        
                        for i, b in enumerate(group):
                            b_can_place = False
                            b_score = float('inf')
                            search_y_start = max(0, ry - b.height)
                            search_y_end = min(grid_h - b.height + 1, ry + r + 1)
                            search_x_start = max(0, rx - b.width)
                            search_x_end = min(grid_w - b.width + 1, rx + r + 1)
                            
                            for by in range(search_y_start, search_y_end):
                                for bx in range(search_x_start, search_x_end):
                                    if can_place(bx, by, b.width, b.height):
                                        score = get_touching_score(bx, by, b.width, b.height, req_road_type)
                                        if score != float('inf'):
                                            b_can_place = True
                                            if score < b_score: b_score = score
                            
                            if b_can_place:
                                enabled_b_idx = i
                                min_b_score = b_score
                                break 
                                
                        for dy in range(r):
                            for dx in range(r):
                                occupied[ry+dy][rx+dx] = False
                                roads[ry+dy][rx+dx] = 0
                                
                        score = straightness * 10
                        if enabled_b_idx != -1:
                            score += 1000 - min_b_score 
                            
                        dist_to_th = abs(rx - th_x) + abs(ry - th_y)
                        score -= dist_to_th * 0.01
                        
                        score += random.uniform(-5, 5) # Add noise to road placement
                        
                        if score > best_road_score:
                            best_road_score = score
                            best_rx, best_ry = rx, ry
                            
                if best_rx != -1:
                    mark_occupied(best_rx, best_ry, r, r)
                    for dy in range(r):
                        for dx in range(r):
                            roads[best_ry+dy][best_rx+dx] = r
                    placed_roads.append(PlacedRoad(x=best_rx, y=best_ry, type=r))
                    progress_made = True
                    dprint(f"Placed road of type {r} at ({best_rx}, {best_ry}) (score={best_road_score:.2f})")
                    
            return group

        dprint("\n--- Placing group with road_type = 2 ---")
        group_2 = place_group(group_2, 2)
        
        dprint("\n--- Placing group with road_type = 1 ---")
        group_1 = place_group(group_1, 1)
        
        dprint("\n--- Placing group with road_type = 0 ---")
        for b in group_0:
            placed = False
            for y in range(grid_h):
                for x in range(grid_w):
                    if can_place(x, y, b.width, b.height):
                        mark_occupied(x, y, b.width, b.height)
                        placed_buildings.append(PlacedBuilding(building_id=b.id, x=x, y=y))
                        placed = True
                        dprint(f"Placed building '{b.name}' ({b.id}) at ({x}, {y}) (no road required)")
                        break
                if placed: break
        # -------------------------------------------------------------
        # Post-Placement BFS Road Pruning
        # -------------------------------------------------------------
        if placed_roads and th_building:
            # 1. Reuse already-mapped Townhall tiles (th_tiles is defined)
            pass

            # 2. Run BFS starting from the road tiles adjacent to the Townhall
            queue = []
            visited = {} # tile -> parent tile (or None if directly adjacent to Townhall)
            
            for th_tx, th_ty in th_tiles:
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

            # 3. For each placed building that requires a road, find the touching road tiles
            # that are connected to the Townhall (i.e. in visited), and trace the path back.
            keep_tiles = set()
            building_road_types = {b.id: b.road_type for b in request.buildings}
            
            for pb in placed_buildings:
                if pb.building_id == th_building.id:
                    continue
                req_type = building_road_types[pb.building_id]
                if req_type == 0:
                    continue
                
                # Get dimensions of this building
                b_def = next(b for b in request.buildings if b.id == pb.building_id)
                w, h = b_def.width, b_def.height
                
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
                
                # Trace back to the Townhall for each start tile
                for start_tile in connected_tiles:
                    curr = start_tile
                    while curr is not None:
                        keep_tiles.add(curr)
                        curr = visited[curr]

            # 4. Prune the placed_roads list: keep only roads that have at least one tile in keep_tiles
            pruned_placed_roads = []
            for pr in placed_roads:
                keep_road = False
                for dy in range(pr.type):
                    for dx in range(pr.type):
                        if (pr.x + dx, pr.y + dy) in keep_tiles:
                            keep_road = True
                            break
                    if keep_road:
                        break
                if keep_road:
                    pruned_placed_roads.append(pr)
                else:
                    dprint(f"Pruned redundant road of size {pr.type}x{pr.type} at ({pr.x}, {pr.y})")
            
            placed_roads = pruned_placed_roads

        # Calculate score for this iteration
        # Base score on placed buildings
        total_buildings = len(placed_buildings)
        road_cost = 0
        for r in placed_roads:
            if r.type == 2:
                road_cost += 4  # User specifically asked for 2x2 roads to cost higher
            else:
                road_cost += 1
                
        # Objective: Maximize buildings placed, minimize road cost
        iteration_score = total_buildings * 10000 - road_cost
        dprint(f"\nIteration {iterations} finished. Placed {total_buildings} buildings, roads cost {road_cost}. Total score: {iteration_score}")
        
        if iteration_score > best_score:
            best_score = iteration_score
            num_1x1 = sum(1 for r in placed_roads if r.type == 1)
            num_2x2 = sum(1 for r in placed_roads if r.type == 2)
            best_response = SolveResponse(
                placed_buildings=placed_buildings,
                placed_roads=placed_roads,
                score=iteration_score,
                num_1x1_roads=num_1x1,
                num_2x2_roads=num_2x2
            )
            
    dprint(f"\n=== Worker finished: solved using {iterations} iterations. ===")
    if best_response:
        dprint(f"Summary: Placed {len(best_response.placed_buildings)} buildings, used {best_response.num_1x1_roads} 1x1 roads (1-square) and {best_response.num_2x2_roads} 2x2 roads (4-square).")
    return best_response

def solve_layout(request: SolveRequest) -> SolveResponse:
    num_workers = max(1, (os.cpu_count() or 4) - 1)
    
    # If optimization time is extremely short, we only have 1 core, or debug is requested, run sequentially
    if request.optimization_time <= 0.1 or num_workers <= 1 or request.debug:
        if request.debug:
            request.optimization_time = 0.0
        best_response = solve_single_worker(request, random.randint(0, 1000000))
    else:
        best_response = None
        best_score = -float('inf')
        
        seeds = [random.randint(0, 1000000) for _ in range(num_workers)]
        
        ctx = multiprocessing.get_context('spawn')
        
        with ProcessPoolExecutor(max_workers=num_workers, mp_context=ctx) as executor:
            futures = [executor.submit(solve_single_worker, request, seed) for seed in seeds]
            
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res and res.score > best_score:
                        best_score = res.score
                        best_response = res
                except Exception as e:
                    print(f"Worker process failed with exception: {e}")
                
    if best_response:
        num_1x1 = best_response.num_1x1_roads or 0
        num_2x2 = best_response.num_2x2_roads or 0
        print(f"\n=======================================================")
        print(f"SOLVER SUMMARY:")
        print(f"  - Placed buildings: {len(best_response.placed_buildings)}")
        print(f"  - 1-square (1x1) roads used: {num_1x1}")
        print(f"  - 4-square (2x2) roads used: {num_2x2}")
        print(f"  - Total road cost: {num_1x1 + num_2x2 * 4}")
        print(f"  - Final score: {best_response.score}")
        print(f"=======================================================")
        
    return best_response
