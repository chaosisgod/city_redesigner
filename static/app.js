document.addEventListener('DOMContentLoaded', () => {
    const gridEl = document.getElementById('city-grid');
    const widthInput = document.getElementById('grid-width');
    const heightInput = document.getElementById('grid-height');
    const btnResize = document.getElementById('btn-resize');
    
    const btnPaint = document.getElementById('btn-mode-paint');
    const btnErase = document.getElementById('btn-mode-erase');
    const btnOptimize = document.getElementById('btn-optimize');
    const btnAbort = document.getElementById('btn-abort');
    
    const addBuildingForm = document.getElementById('add-building-form');
    const buildingsList = document.getElementById('buildings-list');
    
    // Declare new solver UI elements
    const solverSelect = document.getElementById('solver-select');
    const backboneParams = document.getElementById('backbone-params');
    const backboneSelect = document.getElementById('backbone-select');
    const annealingParams = document.getElementById('annealing-params');
    const annealingIterInput = document.getElementById('annealing-iter');
    const optTimeInput = document.getElementById('opt-time');
    const townhallFixedCheckbox = document.getElementById('townhall-fixed');

    // Restore grid dimensions from localStorage
    const savedGridW = localStorage.getItem('foe_city_grid_w');
    const savedGridH = localStorage.getItem('foe_city_grid_h');
    let gridW = savedGridW ? parseInt(savedGridW) : parseInt(widthInput.value);
    let gridH = savedGridH ? parseInt(savedGridH) : parseInt(heightInput.value);
    widthInput.value = gridW;
    heightInput.value = gridH;

    function adjustTileSize() {
        const container = document.querySelector('.canvas-container');
        if (!container) return;
        
        // Measure other visual elements inside the canvas container to prevent grid overflow
        const banner = document.getElementById('status-banner');
        const dock = document.getElementById('unplaced-dock');
        
        let nonGridHeight = 110; // Top/bottom container padding + gap margins
        
        if (banner && banner.style.display !== 'none' && banner.innerHTML !== '') {
            nonGridHeight += banner.offsetHeight + 20; // height + gap
        }
        if (dock) {
            nonGridHeight += dock.offsetHeight + 20; // height + gap
        }
        
        const containerW = container.clientWidth - 80; // 40px left/right padding
        const containerH = container.clientHeight - nonGridHeight;
        
        const totalW = gridW + 2;
        const totalH = gridH + 2;
        
        let tileSize = Math.floor(Math.min(containerW / totalW, containerH / totalH));
        tileSize = Math.max(8, Math.min(tileSize, 40));
        
        document.documentElement.style.setProperty('--tile-size', `${tileSize}px`);
    }

    window.addEventListener('resize', adjustTileSize);

    function showStatus(message, type = 'info', duration = null) {
        const banner = document.getElementById('status-banner');
        if (!banner) return;
        banner.className = '';
        banner.classList.add(type);
        banner.innerHTML = message;
        banner.style.display = 'block';
        
        if (duration) {
            setTimeout(() => {
                if (banner.innerHTML === message) {
                    banner.style.display = 'none';
                }
            }, duration);
        }
    }
    
    function hideStatus() {
        const banner = document.getElementById('status-banner');
        if (banner) {
            banner.style.display = 'none';
        }
    }

    let validTiles = [];
    let paintedRoads = [];
    let isPainting = false;
    let paintMode = true; // true = paint valid, false = erase
    
    let isDraggingHub = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;
    let rootHubX = null;
    let rootHubY = null;

    // Drag-and-drop layout editor variables
    let isDraggingBuilding = false;
    let draggedBuilding = null;
    let draggedPlacementId = null;
    let dragWidth = 0;
    let dragHeight = 0;
    let dragStartGridX = 0;
    let dragStartGridY = 0;

    function initHubPosition() {
        const rootW = buildings[0].width;
        const rootH = buildings[0].height;
        const savedHubX = localStorage.getItem('foe_city_root_hub_x');
        const savedHubY = localStorage.getItem('foe_city_root_hub_y');
        if (savedHubX !== null && savedHubY !== null) {
            rootHubX = parseInt(savedHubX);
            rootHubY = parseInt(savedHubY);
            if (rootHubX < 0 || rootHubX + rootW > gridW || rootHubY < 0 || rootHubY + rootH > gridH) {
                rootHubX = Math.max(0, Math.floor((gridW - rootW) / 2));
                rootHubY = Math.max(0, Math.floor((gridH - rootH) / 2));
            }
        } else {
            rootHubX = Math.max(0, Math.floor((gridW - rootW) / 2));
            rootHubY = Math.max(0, Math.floor((gridH - rootH) / 2));
        }
    }
    
    // Restore buildings inventory and manual layouts from localStorage
    const savedBuildings = localStorage.getItem('foe_city_buildings');
    let buildings = savedBuildings ? JSON.parse(savedBuildings) : [
        {
            id: 'b_0',
            name: 'Townhall',
            width: 7,
            height: 6,
            road_type: 0,
            color: '#eab308'
        }
    ];

    const savedPlacedBuildings = localStorage.getItem('foe_city_placed_buildings');
    let placedBuildings = savedPlacedBuildings ? JSON.parse(savedPlacedBuildings) : [];

    const savedPlacedRoads = localStorage.getItem('foe_city_placed_roads_result');
    let placedRoads = savedPlacedRoads ? JSON.parse(savedPlacedRoads) : [];
    
    const savedCounter = localStorage.getItem('foe_city_building_counter');
    let buildingIdCounter = savedCounter ? parseInt(savedCounter) : 1;
    let catalog = [];

    const rootSelect = document.getElementById('root-select');
    const embassySizeContainer = document.getElementById('embassy-size-container');
    const embassyWInput = document.getElementById('embassy-w');
    const embassyHInput = document.getElementById('embassy-h');

    // Restore root hub configuration
    const savedRootType = localStorage.getItem('foe_city_root_type') || 'townhall';
    const savedEmbassyW = localStorage.getItem('foe_city_embassy_w') || '4';
    const savedEmbassyH = localStorage.getItem('foe_city_embassy_h') || '4';
    if (rootSelect) {
        rootSelect.value = savedRootType;
        embassyWInput.value = savedEmbassyW;
        embassyHInput.value = savedEmbassyH;
        embassySizeContainer.style.display = savedRootType === 'townhall' ? 'none' : 'flex';
    }

    // Restore solver selections
    if (solverSelect) {
        solverSelect.value = localStorage.getItem('foe_city_solver_type') || 'random_greedy';
        backboneSelect.value = localStorage.getItem('foe_city_backbone_type') || 'center_spine';
        annealingIterInput.value = localStorage.getItem('foe_city_annealing_iter') || '1500';
        optTimeInput.value = localStorage.getItem('foe_city_opt_time') || '10';
        const savedFixed = localStorage.getItem('foe_city_townhall_fixed');
        if (savedFixed !== null) {
            townhallFixedCheckbox.checked = savedFixed === 'true';
        }
    }

    function saveToLocalStorage() {
        localStorage.setItem('foe_city_grid_w', gridW);
        localStorage.setItem('foe_city_grid_h', gridH);
        localStorage.setItem('foe_city_buildings', JSON.stringify(buildings));
        localStorage.setItem('foe_city_placed_buildings', JSON.stringify(placedBuildings));
        localStorage.setItem('foe_city_placed_roads_result', JSON.stringify(placedRoads));
        localStorage.setItem('foe_city_building_counter', buildingIdCounter);
        localStorage.setItem('foe_city_valid_tiles', JSON.stringify(validTiles));
        localStorage.setItem('foe_city_painted_roads', JSON.stringify(paintedRoads));
        localStorage.setItem('foe_city_root_hub_x', rootHubX);
        localStorage.setItem('foe_city_root_hub_y', rootHubY);
        
        if (rootSelect) {
            localStorage.setItem('foe_city_root_type', rootSelect.value);
            localStorage.setItem('foe_city_embassy_w', embassyWInput.value);
            localStorage.setItem('foe_city_embassy_h', embassyHInput.value);
        }
        
        if (solverSelect) {
            localStorage.setItem('foe_city_solver_type', solverSelect.value);
            localStorage.setItem('foe_city_backbone_type', backboneSelect.value);
            localStorage.setItem('foe_city_annealing_iter', annealingIterInput.value);
            localStorage.setItem('foe_city_opt_time', optTimeInput.value);
            localStorage.setItem('foe_city_townhall_fixed', townhallFixedCheckbox.checked);
        }
    }

    function updateSolverParamsVisibility() {
        const solver = solverSelect.value;
        const isCustomActive = (solver === 'backbone' || solver === 'constraint_programming' || solver === 'simulated_annealing' || solver === 'evolutionary' || solver === 'user_heuristic' || solver === 'neural_network') && backboneSelect.value === 'custom';
        
        backboneParams.style.display = (solver === 'backbone' || solver === 'constraint_programming' || solver === 'simulated_annealing' || solver === 'evolutionary' || solver === 'user_heuristic' || solver === 'neural_network') ? 'flex' : 'none';
        annealingParams.style.display = solver === 'simulated_annealing' ? 'flex' : 'none';
        
        const roadTypeContainer = document.getElementById('paint-road-type-container');
        if (roadTypeContainer) {
            roadTypeContainer.style.display = isCustomActive ? 'flex' : 'none';
        }
        
        // Custom labels for custom backbone painted roads
        if (isCustomActive) {
            btnPaint.textContent = "Paint Custom Roads";
            btnErase.textContent = "Erase Roads";
        } else {
            btnPaint.textContent = "Paint Map";
            btnErase.textContent = "Erase Map";
        }
        
        refreshGridVisuals();
    }

    if (solverSelect) {
        solverSelect.addEventListener('change', () => {
            updateSolverParamsVisibility();
            saveToLocalStorage();
        });
        backboneSelect.addEventListener('change', () => {
            updateSolverParamsVisibility();
            saveToLocalStorage();
        });
        annealingIterInput.addEventListener('input', saveToLocalStorage);
        optTimeInput.addEventListener('input', saveToLocalStorage);
        townhallFixedCheckbox.addEventListener('change', () => {
            refreshGridVisuals();
            saveToLocalStorage();
        });
        
        // Initial trigger
        updateSolverParamsVisibility();
    }

    function updateRootBuilding() {
        const rootType = rootSelect.value;
        if (rootType === 'townhall') {
            embassySizeContainer.style.display = 'none';
            buildings[0] = {
                id: 'b_0',
                name: 'Townhall',
                width: 7,
                height: 6,
                road_type: 0,
                color: '#eab308'
            };
        } else {
            embassySizeContainer.style.display = 'flex';
            const w = parseInt(embassyWInput.value) || 4;
            const h = parseInt(embassyHInput.value) || 4;
            buildings[0] = {
                id: 'b_0',
                name: 'Embassy',
                width: w,
                height: h,
                road_type: 0,
                color: '#10b981'
            };
        }
        renderBuildings();
        initHubPosition();
        refreshGridVisuals();
        saveToLocalStorage();
    }

    if (rootSelect) {
        rootSelect.addEventListener('change', updateRootBuilding);
        embassyWInput.addEventListener('input', updateRootBuilding);
        embassyHInput.addEventListener('input', updateRootBuilding);
    }

    async function fetchCatalog() {
        try {
            const res = await fetch('/api/catalog');
            catalog = await res.json();
            const datalist = document.getElementById('catalog-list');
            datalist.innerHTML = '';
            catalog.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.name;
                datalist.appendChild(opt);
            });
        } catch (e) {
            console.error(e);
        }
    }

    function getColorForName(name) {
        if (name.toLowerCase().includes('townhall')) return '#eab308';
        let hash = 0;
        for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
        return `hsl(${Math.abs(hash) % 360}, 70%, 50%)`;
    }

    const nameInput = document.getElementById('b-name');
    nameInput.addEventListener('input', () => {
        const found = catalog.find(b => b.name.toLowerCase() === nameInput.value.toLowerCase());
        if (found) {
            document.getElementById('b-w').value = found.width;
            document.getElementById('b-h').value = found.height;
            document.getElementById('b-road').value = found.road_type;
        }
    });

    function initGrid() {
        adjustTileSize();
        gridEl.style.gridTemplateColumns = `repeat(${gridW}, var(--tile-size))`;
        gridEl.innerHTML = '';
        
        // Generate X-coordinates (Top & Bottom)
        const labelsTop = document.getElementById('grid-labels-top');
        const labelsBottom = document.getElementById('grid-labels-bottom');
        if (labelsTop && labelsBottom) {
            labelsTop.style.gridTemplateColumns = `repeat(${gridW}, var(--tile-size))`;
            labelsBottom.style.gridTemplateColumns = `repeat(${gridW}, var(--tile-size))`;
            labelsTop.innerHTML = '';
            labelsBottom.innerHTML = '';
            for (let x = 0; x < gridW; x++) {
                const labelT = document.createElement('div');
                labelT.className = 'grid-label-x';
                labelT.textContent = x;
                labelsTop.appendChild(labelT);
                
                const labelB = document.createElement('div');
                labelB.className = 'grid-label-x';
                labelB.textContent = x;
                labelsBottom.appendChild(labelB);
            }
        }
        
        // Generate Y-coordinates (Left & Right)
        const labelsLeft = document.getElementById('grid-labels-left');
        const labelsRight = document.getElementById('grid-labels-right');
        if (labelsLeft && labelsRight) {
            labelsLeft.style.gridTemplateRows = `repeat(${gridH}, var(--tile-size))`;
            labelsRight.style.gridTemplateRows = `repeat(${gridH}, var(--tile-size))`;
            labelsLeft.innerHTML = '';
            labelsRight.innerHTML = '';
            for (let y = 0; y < gridH; y++) {
                const labelL = document.createElement('div');
                labelL.className = 'grid-label-y';
                labelL.textContent = y;
                labelsLeft.appendChild(labelL);
                
                const labelR = document.createElement('div');
                labelR.className = 'grid-label-y';
                labelR.textContent = y;
                labelsRight.appendChild(labelR);
            }
        }
        
        // Restore painted map layout if dimensions match
        let savedTiles = localStorage.getItem('foe_city_valid_tiles');
        if (savedTiles) {
            try {
                let parsed = JSON.parse(savedTiles);
                if (parsed.length === gridH && parsed[0].length === gridW) {
                    validTiles = parsed;
                } else {
                    validTiles = Array(gridH).fill().map(() => Array(gridW).fill(true));
                }
            } catch (e) {
                validTiles = Array(gridH).fill().map(() => Array(gridW).fill(true));
            }
        } else {
            validTiles = Array(gridH).fill().map(() => Array(gridW).fill(true));
        }

        // Restore painted roads if dimensions match
        let savedRoads = localStorage.getItem('foe_city_painted_roads');
        if (savedRoads) {
            try {
                let parsed = JSON.parse(savedRoads);
                if (parsed.length === gridH && parsed[0].length === gridW) {
                    paintedRoads = parsed;
                } else {
                    paintedRoads = Array(gridH).fill().map(() => Array(gridW).fill(0));
                }
            } catch (e) {
                paintedRoads = Array(gridH).fill().map(() => Array(gridW).fill(0));
            }
        } else {
            paintedRoads = Array(gridH).fill().map(() => Array(gridW).fill(0));
        }

        initHubPosition();
        
        for (let y = 0; y < gridH; y++) {
            for (let x = 0; x < gridW; x++) {
                const tile = document.createElement('div');
                tile.dataset.x = x;
                tile.dataset.y = y;
                
                tile.addEventListener('mousedown', (e) => {
                    const rootW = buildings[0].width;
                    const rootH = buildings[0].height;
                    const isWithinRootHub = x >= rootHubX && x < rootHubX + rootW && y >= rootHubY && y < rootHubY + rootH;
                    
                    if (isWithinRootHub) {
                        isDraggingHub = true;
                        dragOffsetX = x - rootHubX;
                        dragOffsetY = y - rootHubY;
                    } else {
                        // Check if user clicked on an already placed building (excluding Townhall)
                        const clickedPB = placedBuildings.find(pb => {
                            const b = buildings.find(z => z.id === pb.building_id);
                            if (!b) return false;
                            return x >= pb.x && x < pb.x + b.width && y >= pb.y && y < pb.y + b.height;
                        });
                        
                        if (clickedPB) {
                            const b = buildings.find(z => z.id === clickedPB.building_id);
                            isDraggingBuilding = true;
                            draggedBuilding = b;
                            draggedPlacementId = b.id;
                            dragWidth = b.width;
                            dragHeight = b.height;
                            dragStartGridX = clickedPB.x;
                            dragStartGridY = clickedPB.y;
                            dragOffsetX = x - clickedPB.x;
                            dragOffsetY = y - clickedPB.y;
                        } else {
                            // Otherwise, normal paint mode
                            isPainting = true;
                            refreshGridVisuals();
                            toggleTile(x, y, tile);
                        }
                    }
                });

                tile.addEventListener('mouseenter', (e) => {
                    if (isDraggingHub) {
                        const rootW = buildings[0].width;
                        const rootH = buildings[0].height;
                        
                        const newX = x - dragOffsetX;
                        const newY = y - dragOffsetY;
                        
                        if (newX >= 0 && newX + rootW <= gridW && newY >= 0 && newY + rootH <= gridH) {
                            if (newX !== rootHubX || newY !== rootHubY) {
                                rootHubX = newX;
                                rootHubY = newY;
                                refreshGridVisuals();
                            }
                        }
                    } else if (isDraggingBuilding) {
                        const bx = x - dragOffsetX;
                        const by = y - dragOffsetY;
                        
                        // Check if valid footprint
                        let isValidFootprint = true;
                        const rootW = buildings[0].width;
                        const rootH = buildings[0].height;
                        
                        if (bx < 0 || bx + dragWidth > gridW || by < 0 || by + dragHeight > gridH) {
                            isValidFootprint = false;
                        } else {
                            for (let dy = 0; dy < dragHeight; dy++) {
                                for (let dx = 0; dx < dragWidth; dx++) {
                                    const nx = bx + dx;
                                    const ny = by + dy;
                                    
                                    if (!validTiles[ny][nx]) {
                                        isValidFootprint = false;
                                        break;
                                    }
                                    
                                    if (nx >= rootHubX && nx < rootHubX + rootW && ny >= rootHubY && ny < rootHubY + rootH) {
                                        isValidFootprint = false;
                                        break;
                                    }
                                    
                                    const overlapOther = placedBuildings.some(pb => {
                                        if (pb.building_id === draggedPlacementId) return false;
                                        const ob = buildings.find(z => z.id === pb.building_id);
                                        if (!ob) return false;
                                        return nx >= pb.x && nx < pb.x + ob.width && ny >= pb.y && ny < pb.y + ob.height;
                                    });
                                    if (overlapOther) {
                                        isValidFootprint = false;
                                        break;
                                    }
                                }
                                if (!isValidFootprint) break;
                            }
                        }
                        
                        // Clear previous drag glow classes
                        Array.from(gridEl.children).forEach(tileEl => {
                            tileEl.classList.remove('drag-glow-valid', 'drag-glow-invalid');
                        });
                        
                        // Apply glow classes to candidate tiles
                        for (let dy = 0; dy < dragHeight; dy++) {
                            for (let dx = 0; dx < dragWidth; dx++) {
                                const nx = bx + dx;
                                const ny = by + dy;
                                if (nx >= 0 && nx < gridW && ny >= 0 && ny < gridH) {
                                    const idx = ny * gridW + nx;
                                    const tileEl = gridEl.children[idx];
                                    if (tileEl) {
                                        tileEl.classList.add(isValidFootprint ? 'drag-glow-valid' : 'drag-glow-invalid');
                                    }
                                }
                            }
                        }
                    } else if (isPainting) {
                        toggleTile(x, y, tile);
                    }
                });

                tile.addEventListener('mouseup', (e) => {
                    if (isDraggingBuilding) {
                        const bx = x - dragOffsetX;
                        const by = y - dragOffsetY;
                        
                        let isValidFootprint = true;
                        const rootW = buildings[0].width;
                        const rootH = buildings[0].height;
                        
                        if (bx < 0 || bx + dragWidth > gridW || by < 0 || by + dragHeight > gridH) {
                            isValidFootprint = false;
                        } else {
                            for (let dy = 0; dy < dragHeight; dy++) {
                                for (let dx = 0; dx < dragWidth; dx++) {
                                    const nx = bx + dx;
                                    const ny = by + dy;
                                    if (!validTiles[ny][nx]) { isValidFootprint = false; break; }
                                    if (nx >= rootHubX && nx < rootHubX + rootW && ny >= rootHubY && ny < rootHubY + rootH) { isValidFootprint = false; break; }
                                    const overlapOther = placedBuildings.some(pb => {
                                        if (pb.building_id === draggedPlacementId) return false;
                                        const ob = buildings.find(z => z.id === pb.building_id);
                                        if (!ob) return false;
                                        return nx >= pb.x && nx < pb.x + ob.width && ny >= pb.y && ny < pb.y + ob.height;
                                    });
                                    if (overlapOther) { isValidFootprint = false; break; }
                                }
                                if (!isValidFootprint) break;
                            }
                        }
                        
                        if (isValidFootprint) {
                            let pb = placedBuildings.find(z => z.building_id === draggedPlacementId);
                            if (pb) {
                                pb.x = bx;
                                pb.y = by;
                            } else {
                                placedBuildings.push({ building_id: draggedPlacementId, x: bx, y: by });
                            }
                        } else {
                            // If invalid and already placed, restore original
                            // If from dock, it doesn't get pushed (reverts to dock)
                        }
                        
                        isDraggingBuilding = false;
                        saveToLocalStorage();
                        refreshGridVisuals();
                        renderUnplacedDock();
                    }
                });

                tile.addEventListener('contextmenu', (e) => {
                    e.preventDefault(); // prevent native menu
                    const rootW = buildings[0].width;
                    const rootH = buildings[0].height;
                    const isWithinRootHub = x >= rootHubX && x < rootHubX + rootW && y >= rootHubY && y < rootHubY + rootH;
                    if (isWithinRootHub) return; // Townhall cannot be deleted this way
                    
                    const clickedPBIndex = placedBuildings.findIndex(pb => {
                        const b = buildings.find(z => z.id === pb.building_id);
                        if (!b) return false;
                        return x >= pb.x && x < pb.x + b.width && y >= pb.y && y < pb.y + b.height;
                    });
                    
                    if (clickedPBIndex !== -1) {
                        placedBuildings.splice(clickedPBIndex, 1);
                        saveToLocalStorage();
                        refreshGridVisuals();
                        renderUnplacedDock();
                    }
                });
                
                gridEl.appendChild(tile);
            }
        }
        refreshGridVisuals();
    }

    function refreshGridVisuals() {
        adjustTileSize(); // Dynamic tile scaling on every visual update
        const isCustomRoadsActive = (solverSelect.value === 'backbone' || solverSelect.value === 'constraint_programming' || solverSelect.value === 'simulated_annealing' || solverSelect.value === 'evolutionary' || solverSelect.value === 'user_heuristic' || solverSelect.value === 'neural_network') && backboneSelect.value === 'custom';
        const tiles = gridEl.children;
        if (!tiles || tiles.length === 0) return;
        
        const rootW = buildings[0].width;
        const rootH = buildings[0].height;
        
        if (rootHubX === null || rootHubY === null) {
            initHubPosition();
        }
        
        // Check if root hub overlaps with any invalid tiles
        let hubHasOverlaps = false;
        for (let dy = 0; dy < rootH; dy++) {
            for (let dx = 0; dx < rootW; dx++) {
                const tx = rootHubX + dx;
                const ty = rootHubY + dy;
                if (tx >= 0 && tx < gridW && ty >= 0 && ty < gridH) {
                    if (!validTiles[ty][tx]) {
                        hubHasOverlaps = true;
                        break;
                    }
                }
            }
            if (hubHasOverlaps) break;
        }

        // 1. Reset all tiles to their base valid/empty/painted-road styles
        for (let i = 0; i < tiles.length; i++) {
            const tile = tiles[i];
            const x = parseInt(tile.dataset.x);
            const y = parseInt(tile.dataset.y);
            if (isNaN(x) || isNaN(y)) continue;
            
            tile.style.backgroundColor = '';
            tile.style.borderTop = '';
            tile.style.borderBottom = '';
            tile.style.borderLeft = '';
            tile.style.borderRight = '';
            delete tile.dataset.name;

            const isValid = validTiles[y][x];
            const roadVal = paintedRoads[y][x];
            
            let classNames = ['tile'];
            if (isCustomRoadsActive && roadVal === 1) {
                classNames.push('road-painted-1');
            } else if (isCustomRoadsActive && roadVal === 2) {
                classNames.push('road-painted-2');
            } else {
                classNames.push(isValid ? 'valid' : 'empty');
            }
            
            tile.className = classNames.join(' ');
        }

        // 2. Draw placed roads
        placedRoads.forEach(r => {
            if (r.type === 2) {
                for (let dy = 0; dy < 2; dy++) {
                    for (let dx = 0; dx < 2; dx++) {
                        const idx = (r.y + dy) * gridW + (r.x + dx);
                        if(tiles[idx]) {
                            tiles[idx].className = 'tile road2';
                            tiles[idx].dataset.name = '2x2 Road';
                        }
                    }
                }
            } else {
                const idx = r.y * gridW + r.x;
                if(tiles[idx]) {
                    tiles[idx].className = 'tile road1';
                    tiles[idx].dataset.name = '1x1 Road';
                }
            }
        });

        // 3. Draw Townhall / Embassy
        for (let dy = 0; dy < rootH; dy++) {
            for (let dx = 0; dx < rootW; dx++) {
                const tx = rootHubX + dx;
                const ty = rootHubY + dy;
                const idx = ty * gridW + tx;
                if (tiles[idx]) {
                    tiles[idx].className = 'tile th';
                    tiles[idx].dataset.name = buildings[0].name;
                    
                    const borderStyle = hubHasOverlaps ? '2px solid var(--danger)' : '2px solid var(--tile-th)';
                    
                    tiles[idx].style.borderTop = dy === 0 ? borderStyle : '';
                    tiles[idx].style.borderBottom = dy === rootH - 1 ? borderStyle : '';
                    tiles[idx].style.borderLeft = dx === 0 ? borderStyle : '';
                    tiles[idx].style.borderRight = dx === rootW - 1 ? borderStyle : '';
                }
            }
        }

        // 4. Draw other placed buildings
        placedBuildings.forEach(pb => {
            const b = buildings.find(x => x.id === pb.building_id);
            if(!b) return;
            const isTH = b.name.toLowerCase().includes('townhall') || b.name.toLowerCase().includes('embassy');
            if (isTH) return; // Placed hub drawn separately above
            
            for(let dy=0; dy<b.height; dy++) {
                for(let dx=0; dx<b.width; dx++) {
                    const idx = (pb.y + dy) * gridW + (pb.x + dx);
                    if(tiles[idx]) {
                        tiles[idx].className = 'tile building';
                        tiles[idx].style.backgroundColor = b.color;
                        tiles[idx].dataset.name = b.name;
                        
                        // Draw exterior boundaries
                        tiles[idx].style.borderTop = dy === 0 ? '2px solid white' : '';
                        tiles[idx].style.borderBottom = dy === b.height - 1 ? '2px solid white' : '';
                        tiles[idx].style.borderLeft = dx === 0 ? '2px solid white' : '';
                        tiles[idx].style.borderRight = dx === b.width - 1 ? '2px solid white' : '';
                    }
                }
            }
        });

        const summaryDiv = document.getElementById('solver-summary-stats');
        if (summaryDiv) {
            summaryDiv.innerHTML = '';
        }
    }

    function toggleTile(x, y, tileEl) {
        const isCustomRoadsActive = (solverSelect.value === 'backbone' || solverSelect.value === 'constraint_programming' || solverSelect.value === 'simulated_annealing' || solverSelect.value === 'evolutionary' || solverSelect.value === 'user_heuristic' || solverSelect.value === 'neural_network') && backboneSelect.value === 'custom';
        
        // Don't paint tiles that are occupied by the root hub
        const isWithinRootHub = x >= rootHubX && x < rootHubX + buildings[0].width && y >= rootHubY && y < rootHubY + buildings[0].height;
        if (isWithinRootHub) return;

        if (isCustomRoadsActive) {
            if (paintMode) {
                const roadType = parseInt(document.getElementById('paint-road-type')?.value || '1');
                paintedRoads[y][x] = roadType;
                tileEl.className = 'tile ' + (roadType === 2 ? 'road-painted-2' : 'road-painted-1');
            } else {
                paintedRoads[y][x] = 0;
                const isValid = validTiles[y][x];
                tileEl.className = 'tile ' + (isValid ? 'valid' : 'empty');
            }
        } else {
            validTiles[y][x] = paintMode;
            if (paintMode) {
                tileEl.className = 'tile valid';
            } else {
                tileEl.className = 'tile empty';
            }
        }
        saveToLocalStorage();
    }

    document.addEventListener('mouseup', () => { 
        isPainting = false; 
        if (isDraggingHub) {
            isDraggingHub = false;
            saveToLocalStorage();
        }
    });

    btnResize.addEventListener('click', () => {
        gridW = parseInt(widthInput.value);
        gridH = parseInt(heightInput.value);
        localStorage.removeItem('foe_city_valid_tiles');
        localStorage.removeItem('foe_city_painted_roads');
        initGrid();
        saveToLocalStorage();
    });

    if (btnAbort) {
        btnAbort.addEventListener('click', async () => {
            btnAbort.textContent = "Aborting...";
            btnAbort.disabled = true;
            try {
                await fetch('/api/abort', { method: 'POST' });
            } catch (e) {
                console.error("Abort request failed:", e);
            }
        });
    }

    btnPaint.addEventListener('click', () => {
        paintMode = true;
        btnPaint.classList.add('active');
        btnErase.classList.remove('active');
    });

    btnErase.addEventListener('click', () => {
        paintMode = false;
        btnErase.classList.add('active');
        btnPaint.classList.remove('active');
    });

    addBuildingForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('b-name').value;
        const lowerName = name.toLowerCase();

        if (lowerName.includes('townhall') || lowerName.includes('embassy')) {
            alert("The connection hub (Townhall or Embassy) is managed via the 'Root Hub' panel above!");
            return;
        }

        const w = parseInt(document.getElementById('b-w').value);
        const h = parseInt(document.getElementById('b-h').value);
        const road = parseInt(document.getElementById('b-road').value);
        const qty = parseInt(document.getElementById('b-qty').value) || 1;
        
        const color = getColorForName(name);

        for (let i = 0; i < qty; i++) {
            buildings.push({
                id: `b_${buildingIdCounter++}`,
                name, width: w, height: h, road_type: road,
                color: color
            });
        }

        // Save to catalog
        if (!catalog.find(c => c.name.toLowerCase() === name.toLowerCase() && c.width === w && c.height === h && c.road_type === road)) {
            fetch('/api/catalog', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, width: w, height: h, road_type: road})
            }).then(() => fetchCatalog());
        }

        renderBuildings();
        refreshGridVisuals();
        saveToLocalStorage();
        addBuildingForm.reset();
    });

    function renderBuildings() {
        buildingsList.innerHTML = '';
        // Group by name for display
        const grouped = {};
        buildings.forEach(b => {
            if (!grouped[b.name]) grouped[b.name] = {count: 0, b: b, ids: []};
            grouped[b.name].count++;
            grouped[b.name].ids.push(b.id);
        });

        Object.values(grouped).forEach(g => {
            const li = document.createElement('li');
            li.className = 'building-item';
            li.style.borderLeft = `4px solid ${g.b.color}`;
            li.innerHTML = `
                <span style="cursor: pointer; flex: 1;" title="Click to spawn/drag this building on the map">${g.count}x ${g.b.name} (${g.b.width}x${g.b.height})</span>
                ${(g.b.name.toLowerCase().includes('townhall') || g.b.name.toLowerCase().includes('embassy')) ? '' : `<button onclick="removeBuildingGroup('${g.b.name}')">X</button>`}
            `;
            
            const span = li.querySelector('span');
            span.addEventListener('click', () => {
                spawnBuildingFromInventory(g.b.name);
            });
            
            li.addEventListener('mouseenter', () => {
                gridEl.classList.add('highlighting');
                Array.from(gridEl.children).forEach(tile => {
                    if (tile.dataset.name && tile.dataset.name.toLowerCase() === g.b.name.toLowerCase()) {
                        tile.classList.add('highlight');
                    }
                });
            });
            li.addEventListener('mouseleave', () => {
                gridEl.classList.remove('highlighting');
                Array.from(gridEl.children).forEach(tile => tile.classList.remove('highlight'));
            });

            buildingsList.appendChild(li);
        });
    }

    window.removeBuildingGroup = (name) => {
        const removedIds = new Set(buildings.filter(b => b.name === name).map(b => b.id));
        buildings = buildings.filter(b => b.name !== name);
        placedBuildings = placedBuildings.filter(pb => !removedIds.has(pb.building_id));
        
        renderBuildings();
        renderUnplacedDock();
        refreshGridVisuals();
        saveToLocalStorage();
    };



    btnOptimize.addEventListener('click', async () => {
        const thFixed = townhallFixedCheckbox.checked;
        const optTime = parseFloat(optTimeInput.value) || 10;
        
        // Build custom_roads payload if "Use Painted Roads" is selected
        let customRoads = null;
        if ((solverSelect.value === 'backbone' || solverSelect.value === 'constraint_programming' || solverSelect.value === 'simulated_annealing' || solverSelect.value === 'evolutionary' || solverSelect.value === 'user_heuristic' || solverSelect.value === 'neural_network') && backboneSelect.value === 'custom') {
            customRoads = [];
            for (let y = 0; y < gridH; y++) {
                for (let x = 0; x < gridW; x++) {
                    const roadVal = paintedRoads[y][x];
                    if (roadVal > 0) {
                        customRoads.push({ x: x, y: y, type: roadVal });
                    }
                }
            }
        }

        // For custom roads, we pass a cloned validTiles where all road cells are marked valid (true)
        // so the solver's tile validity checks pass.
        let activeGridTiles = validTiles;
        if (customRoads) {
            activeGridTiles = validTiles.map(row => [...row]);
            customRoads.forEach(r => {
                if (r.type === 2) {
                    for (let dy = 0; dy < 2; dy++) {
                        for (let dx = 0; dx < 2; dx++) {
                            const ny = r.y + dy;
                            const nx = r.x + dx;
                            if (ny < gridH && nx < gridW) {
                                activeGridTiles[ny][nx] = true;
                            }
                        }
                    }
                } else {
                    if (r.y < gridH && r.x < gridW) {
                        activeGridTiles[r.y][r.x] = true;
                    }
                }
            });
        }

        const payload = {
            grid: { width: gridW, height: gridH, valid_tiles: activeGridTiles },
            buildings: buildings,
            townhall_fixed: thFixed,
            townhall_pos: thFixed ? [rootHubX, rootHubY] : null,
            optimization_time: optTime,
            solver_type: solverSelect.value,
            backbone_type: backboneSelect.value,
            annealing_iterations: parseInt(annealingIterInput.value) || 1500,
            custom_roads: customRoads
        };
        
        btnOptimize.textContent = "Solving...";
        let countdownInterval = null;
        const originalTitle = document.title;
        if (btnAbort) {
            btnAbort.disabled = false;
            const endTime = Date.now() + optTime * 1000;
            btnAbort.textContent = `Abort (${optTime.toFixed(1)}s)`;
            
            document.title = `(${Math.ceil(optTime)}s) ${originalTitle}`;
            
            countdownInterval = setInterval(() => {
                const remaining = Math.max(0, (endTime - Date.now()) / 1000);
                btnAbort.textContent = `Abort (${remaining.toFixed(1)}s)`;
                
                document.title = `(${Math.ceil(remaining)}s) ${originalTitle}`;
                
                if (remaining <= 0) {
                    clearInterval(countdownInterval);
                }
            }, 100);
        }
        try {
            showStatus("Optimizing layout... Please wait.", "info");
            const res = await fetch('/api/solve', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            
            if (res.status !== 200) {
                document.getElementById('debug-output').value = data.detail || JSON.stringify(data, null, 2);
                if (data.detail && data.detail.includes("aborted")) {
                    alert("Optimization was aborted successfully.");
                    showStatus("Optimization was aborted successfully.", "warning", 5000);
                } else {
                    alert("Error solving layout: " + (data.detail || "Unknown error"));
                    showStatus("Optimization Failed: " + (data.detail || "Unknown error"), "error");
                }
                return;
            }

            // Populate human-readable summary stats
            const summaryDiv = document.getElementById('solver-summary-stats');
            if (summaryDiv) {
                const num1x1 = data.num_1x1_roads || 0;
                const num2x2 = data.num_2x2_roads || 0;
                const roadCost = num1x1 + num2x2 * 4;
                summaryDiv.innerHTML = `
                    <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 4px; padding: 8px;">
                        <strong>Placed Buildings:</strong> ${data.placed_buildings.length} / ${buildings.length}<br>
                        <strong>1-Square (1x1) Roads Used:</strong> ${num1x1}<br>
                        <strong>4-Square (2x2) Roads Used:</strong> ${num2x2}<br>
                        <strong>Total Road Cost:</strong> ${roadCost} tiles<br>
                        <strong>Solver Score:</strong> ${data.score}
                    </div>
                `;
            }
            
            document.getElementById('debug-output').value = JSON.stringify(data, null, 2);
            drawResult(data);
            
            // Globally check building placement count
            if (data.placed_buildings.length < buildings.length) {
                showStatus(`Optimization Failed: Only ${data.placed_buildings.length} out of ${buildings.length} buildings are placed on the map.`, "error");
            } else {
                showStatus(`Optimization Succeeded: All ${buildings.length} buildings are successfully placed and connected!`, "success", 8000);
            }
        } catch (e) {
            console.error(e);
            alert("Error solving layout");
            showStatus("Optimization Failed: Error solving layout.", "error");
            document.getElementById('debug-output').value = "Error: " + e.message;
        } finally {
            btnOptimize.textContent = "Optimize Layout";
            if (btnAbort) {
                btnAbort.disabled = true;
                btnAbort.textContent = "Abort";
            }
            if (countdownInterval) {
                clearInterval(countdownInterval);
            }
            document.title = originalTitle;
        }
    });

    const tooltip = document.getElementById('tooltip');

    gridEl.addEventListener('mousemove', (e) => {
        if (e.target.classList.contains('tile') && e.target.dataset.name) {
            tooltip.style.display = 'block';
            tooltip.style.left = (e.pageX + 10) + 'px';
            tooltip.style.top = (e.pageY + 10) + 'px';
            tooltip.textContent = e.target.dataset.name;
        } else {
            tooltip.style.display = 'none';
        }
    });

    gridEl.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
    });

    function drawResult(data) {
        placedBuildings = data.placed_buildings || [];
        placedRoads = data.placed_roads || [];
        saveToLocalStorage();
        refreshGridVisuals();
        renderUnplacedDock();
    }

    // Global document mouseup safety listener
    document.addEventListener('mouseup', () => {
        if (isDraggingHub) {
            isDraggingHub = false;
            saveToLocalStorage();
            refreshGridVisuals();
        }
        if (isDraggingBuilding) {
            // Re-render and clear glows if dropped outside the grid
            isDraggingBuilding = false;
            Array.from(gridEl.children).forEach(t => t.classList.remove('drag-glow-valid', 'drag-glow-invalid'));
            refreshGridVisuals();
            renderUnplacedDock();
        }
        isPainting = false;
    });

    // Rotation handler on 'R' keypress while dragging
    window.addEventListener('keydown', (e) => {
        if (isDraggingBuilding && (e.key === 'r' || e.key === 'R')) {
            const b = buildings.find(x => x.id === draggedPlacementId);
            if (b) {
                const temp = b.width;
                b.width = b.height;
                b.height = temp;
                
                const temp2 = dragWidth;
                dragWidth = dragHeight;
                dragHeight = temp2;
                
                const temp3 = dragOffsetX;
                dragOffsetX = dragOffsetY;
                dragOffsetY = temp3;
                
                saveToLocalStorage();
                refreshGridVisuals();
            }
        }
    });

    // Spawn a building constructively on first vacant spot
    function spawnBuildingFromInventory(name) {
        const b = buildings.find(x => x.name.toLowerCase() === name.toLowerCase() && !placedBuildings.some(pb => pb.building_id === x.id));
        if (!b) {
            alert(`All instances of "${name}" are already placed on the map! Add more using the form if needed.`);
            return;
        }
        
        let spawnX = 0;
        let spawnY = 0;
        let foundSpot = false;
        
        const occupied = Array(gridH).fill().map(() => Array(gridW).fill(false));
        for (let y = 0; y < gridH; y++) {
            for (let x = 0; x < gridW; x++) {
                occupied[y][x] = !validTiles[y][x];
            }
        }
        const rootW = buildings[0].width;
        const rootH = buildings[0].height;
        for (let dy = 0; dy < rootH; dy++) {
            for (let dx = 0; dx < rootW; dx++) {
                if (rootHubY + dy < gridH && rootHubX + dx < gridW) {
                    occupied[rootHubY + dy][rootHubX + dx] = true;
                }
            }
        }
        placedBuildings.forEach(pb => {
            const ob = buildings.find(x => x.id === pb.building_id);
            if (ob) {
                for (let dy = 0; dy < ob.height; dy++) {
                    for (let dx = 0; dx < ob.width; dx++) {
                        if (pb.y + dy < gridH && pb.x + dx < gridW) {
                            occupied[pb.y + dy][pb.x + dx] = true;
                        }
                    }
                }
            }
        });
        
        for (let y = 0; y < gridH - b.height + 1; y++) {
            for (let x = 0; x < gridW - b.width + 1; x++) {
                let fits = true;
                for (let dy = 0; dy < b.height; dy++) {
                    for (let dx = 0; dx < b.width; dx++) {
                        if (occupied[y+dy][x+dx]) {
                            fits = false;
                            break;
                        }
                    }
                    if (!fits) break;
                }
                if (fits) {
                    spawnX = x;
                    spawnY = y;
                    foundSpot = true;
                    break;
                }
            }
            if (foundSpot) break;
        }
        
        placedBuildings.push({ building_id: b.id, x: spawnX, y: spawnY });
        saveToLocalStorage();
        refreshGridVisuals();
        renderUnplacedDock();
        
        // Drag instantly
        isDraggingBuilding = true;
        draggedBuilding = b;
        draggedPlacementId = b.id;
        dragWidth = b.width;
        dragHeight = b.height;
        dragStartGridX = spawnX;
        dragStartGridY = spawnY;
        dragOffsetX = 0;
        dragOffsetY = 0;
    }

    // Render the horizontal tray of unplaced buildings
    function renderUnplacedDock() {
        const dockContainer = document.getElementById('unplaced-dock-items');
        if (!dockContainer) return;
        dockContainer.innerHTML = '';
        
        const unplaced = [];
        buildings.forEach((b, idx) => {
            if (idx === 0) return; // Skip Townhall
            
            const isPlaced = placedBuildings.some(pb => pb.building_id === b.id);
            if (!isPlaced) {
                unplaced.push(b);
            }
        });
        
        if (unplaced.length === 0) {
            dockContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem; font-style: italic; width: 100%; text-align: center;">All buildings are placed on the map! Click names to spawn, drag to move, or right-click to return here.</div>';
            return;
        }
        
        unplaced.forEach(b => {
            const card = document.createElement('div');
            card.className = 'dock-item';
            card.style.borderLeft = `4px solid ${b.color}`;
            card.title = "Drag this building onto the grid";
            card.innerHTML = `
                <div class="dock-item-name">${b.name}</div>
                <div class="dock-item-badge" style="background-color: ${b.color};">${b.width}x${b.height}</div>
            `;
            
            card.addEventListener('mousedown', (e) => {
                isDraggingBuilding = true;
                draggedBuilding = b;
                draggedPlacementId = b.id;
                dragWidth = b.width;
                dragHeight = b.height;
                dragOffsetX = Math.floor(b.width / 2);
                dragOffsetY = Math.floor(b.height / 2);
                dragStartGridX = -1;
                dragStartGridY = -1;
            });
            
            dockContainer.appendChild(card);
        });
    }

    initGrid();
    fetchCatalog();
    renderBuildings();
    renderUnplacedDock();
});
