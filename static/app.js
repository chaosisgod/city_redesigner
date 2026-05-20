document.addEventListener('DOMContentLoaded', () => {
    const gridEl = document.getElementById('city-grid');
    const widthInput = document.getElementById('grid-width');
    const heightInput = document.getElementById('grid-height');
    const btnResize = document.getElementById('btn-resize');
    
    const btnPaint = document.getElementById('btn-mode-paint');
    const btnErase = document.getElementById('btn-mode-erase');
    const btnOptimize = document.getElementById('btn-optimize');
    
    const addBuildingForm = document.getElementById('add-building-form');
    const buildingsList = document.getElementById('buildings-list');
    
    let gridW = parseInt(widthInput.value);
    let gridH = parseInt(heightInput.value);
    let validTiles = [];
    let isPainting = false;
    let paintMode = true; // true = paint valid, false = erase
    
    let buildings = [
        {
            id: 'b_0',
            name: 'Townhall',
            width: 7,
            height: 6,
            road_type: 0,
            color: '#eab308'
        }
    ];
    let buildingIdCounter = 1;
    let catalog = [];

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
        gridEl.style.gridTemplateColumns = `repeat(${gridW}, 24px)`;
        gridEl.innerHTML = '';
        validTiles = Array(gridH).fill().map(() => Array(gridW).fill(true)); // default all valid
        
        for (let y = 0; y < gridH; y++) {
            for (let x = 0; x < gridW; x++) {
                const tile = document.createElement('div');
                tile.className = 'tile valid';
                tile.dataset.x = x;
                tile.dataset.y = y;
                
                tile.addEventListener('mousedown', (e) => {
                    isPainting = true;
                    toggleTile(x, y, tile);
                });
                tile.addEventListener('mouseenter', (e) => {
                    if (isPainting) toggleTile(x, y, tile);
                });
                
                gridEl.appendChild(tile);
            }
        }
    }

    function toggleTile(x, y, tileEl) {
        validTiles[y][x] = paintMode;
        if (paintMode) {
            tileEl.classList.add('valid');
            tileEl.classList.remove('empty');
        } else {
            tileEl.classList.remove('valid');
            tileEl.classList.add('empty');
        }
    }

    document.addEventListener('mouseup', () => { isPainting = false; });

    btnResize.addEventListener('click', () => {
        gridW = parseInt(widthInput.value);
        gridH = parseInt(heightInput.value);
        initGrid();
    });

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

        if (name.toLowerCase().includes('townhall') && buildings.some(b => b.name.toLowerCase().includes('townhall'))) {
            alert("Only one Townhall is allowed!");
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
                <span>${g.count}x ${g.b.name} (${g.b.width}x${g.b.height})</span>
                ${g.b.name.toLowerCase().includes('townhall') ? '' : `<button onclick="removeBuildingGroup('${g.b.name}')">X</button>`}
            `;
            
            li.addEventListener('mouseenter', () => {
                gridEl.classList.add('highlighting');
                Array.from(gridEl.children).forEach(tile => {
                    if (tile.style.backgroundColor === g.b.color || (g.b.name.toLowerCase().includes('townhall') && tile.classList.contains('th'))) {
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
        buildings = buildings.filter(b => b.name !== name);
        renderBuildings();
    };



    btnOptimize.addEventListener('click', async () => {
        const thFixed = document.getElementById('townhall-fixed').checked;
        const optTime = parseFloat(document.getElementById('opt-time').value) || 10;
        const payload = {
            grid: { width: gridW, height: gridH, valid_tiles: validTiles },
            buildings: buildings,
            townhall_fixed: thFixed,
            townhall_pos: null,
            optimization_time: optTime
        };
        
        btnOptimize.textContent = "Solving...";
        try {
            const res = await fetch('/api/solve', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            
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
        } catch (e) {
            console.error(e);
            alert("Error solving layout");
            document.getElementById('debug-output').value = "Error: " + e.message;
        }
        btnOptimize.textContent = "Optimize Layout";
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
        // Reset grid visuals to just valid/invalid
        const tiles = gridEl.children;
        for(let i=0; i<tiles.length; i++) {
            tiles[i].className = validTiles[Math.floor(i/gridW)][i%gridW] ? 'tile valid' : 'tile empty';
            tiles[i].style.backgroundColor = '';
            tiles[i].style.borderTop = '';
            tiles[i].style.borderBottom = '';
            tiles[i].style.borderLeft = '';
            tiles[i].style.borderRight = '';
            delete tiles[i].dataset.name;
        }

        // Draw roads
        data.placed_roads.forEach(r => {
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

        // Draw buildings
        data.placed_buildings.forEach(pb => {
            const b = buildings.find(x => x.id === pb.building_id);
            if(!b) return;
            // if it's townhall, color differently
            const isTH = b.name.toLowerCase().includes('townhall');
            for(let dy=0; dy<b.height; dy++) {
                for(let dx=0; dx<b.width; dx++) {
                    const idx = (pb.y + dy) * gridW + (pb.x + dx);
                    if(tiles[idx]) {
                        tiles[idx].className = isTH ? 'tile th' : 'tile building';
                        tiles[idx].style.backgroundColor = isTH ? '' : b.color;
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
    }

    initGrid();
    fetchCatalog();
    renderBuildings();
});
