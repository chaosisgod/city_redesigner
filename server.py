from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from models import SolveRequest, SolveResponse, CatalogBuilding
from solver import solve_layout
from typing import List
import uvicorn
import os
import json

app = FastAPI(title="FoE City Redesigner API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join("static", "index.html"))

@app.post("/api/solve", response_model=SolveResponse)
async def solve(request: SolveRequest):
    # Call the solver algorithm
    result = solve_layout(request)
    return result

@app.get("/api/catalog", response_model=List[CatalogBuilding])
async def get_catalog():
    if not os.path.exists("catalog.json"):
        return []
    with open("catalog.json", "r") as f:
        return json.load(f)

@app.post("/api/catalog")
async def add_to_catalog(building: CatalogBuilding):
    catalog = []
    if os.path.exists("catalog.json"):
        with open("catalog.json", "r") as f:
            catalog = json.load(f)
    
    # Update or add
    for b in catalog:
        if b['name'].lower() == building.name.lower():
            b['width'] = building.width
            b['height'] = building.height
            b['road_type'] = building.road_type
            break
    else:
        catalog.append(building.model_dump())
        
    with open("catalog.json", "w") as f:
        json.dump(catalog, f, indent=4)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
