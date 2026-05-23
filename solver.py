from models import SolveRequest, SolveResponse

def solve_layout(request: SolveRequest) -> SolveResponse:
    print(f"Routing request to solver: '{request.solver_type}'")
    
    if request.solver_type == "simulated_annealing":
        import solver_annealing
        return solver_annealing.solve_layout(request)
        
    elif request.solver_type == "backbone":
        import solver_backbone
        return solver_backbone.solve_layout(request)
        
    elif request.solver_type == "constraint_programming":
        try:
            import solver_cp
            return solver_cp.solve_layout(request)
        except ImportError:
            print("ERROR: Google OR-Tools is not installed. Falling back to Simulated Annealing.")
            import solver_annealing
            return solver_annealing.solve_layout(request)
            
    else:
        # Default fallback is the original random_greedy solver
        import solver_greedy
        return solver_greedy.solve_layout(request)
