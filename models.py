from pydantic import BaseModel
from typing import List, Optional, Tuple

class Building(BaseModel):
    id: str
    name: str
    width: int
    height: int
    road_type: int  # 0=none, 1=1x1, 2=2x2
    color: str

class CatalogBuilding(BaseModel):
    name: str
    width: int
    height: int
    road_type: int

class CityGrid(BaseModel):
    width: int
    height: int
    valid_tiles: List[List[bool]]

class PlacedBuilding(BaseModel):
    building_id: str
    x: int
    y: int

class PlacedRoad(BaseModel):
    x: int
    y: int
    type: int

class SolveRequest(BaseModel):
    grid: CityGrid
    buildings: List[Building]
    townhall_fixed: bool
    townhall_pos: Optional[Tuple[int, int]] = None
    optimization_time: float = 60.0
    debug: bool = False
    solver_type: str = "random_greedy"  # random_greedy, simulated_annealing, backbone, constraint_programming
    backbone_type: Optional[str] = "center_spine"  # center_spine, grid, perimeter, custom
    annealing_iterations: int = 1500
    custom_roads: Optional[List[PlacedRoad]] = None

class SolveResponse(BaseModel):
    placed_buildings: List[PlacedBuilding]
    placed_roads: List[PlacedRoad]
    score: float
    num_1x1_roads: Optional[int] = None
    num_2x2_roads: Optional[int] = None
