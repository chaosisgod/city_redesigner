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
def solve(request: SolveRequest):
    # Ensure abort lock is cleared at start
    if os.path.exists("abort.lock"):
        try: os.remove("abort.lock")
        except: pass
        
    try:
        try:
            # Call the solver algorithm
            result = solve_layout(request)
        except Exception as e:
            if os.path.exists("abort.lock"):
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Optimization aborted by user.")
            raise e
            
        if os.path.exists("abort.lock"):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Optimization aborted by user.")
        if result is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Solver failed to produce a layout.")
            
        if len(result.placed_buildings) < len(request.buildings):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Optimization failed: Only {len(result.placed_buildings)} out of {len(request.buildings)} buildings could be placed and connected.")
    finally:
        # Clear abort lock at end
        if os.path.exists("abort.lock"):
            try: os.remove("abort.lock")
            except: pass
            
    return result

@app.post("/api/abort")
async def abort_solve():
    with open("abort.lock", "w") as f:
        f.write("abort requested")
        
    # Instantly terminate all active solver subprocesses to free CPU and prevent hangs
    import multiprocessing
    for p in multiprocessing.active_children():
        try:
            p.terminate()
        except:
            pass
            
    return {"status": "abort requested"}

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
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

