/**
 * VELLA Base Builder
 * Canvas-based renderer for 16x16 clan base grid
 *
 * Interactions:
 * - Tap build-menu button → select type → tap canvas to place
 * - Drag build-menu button → drag onto canvas → release to place
 * - Press & hold existing building on canvas → drag to move it
 */

const GRID_SIZE = 16;
const CELL_SIZE = 40;
const DRAG_THRESHOLD = 8; // px before drag activates

const BUILDING_COLORS = {
    defense: '#4a90d9',
    production: '#d9a04a',
    utility: '#8b5cf6',
};

export class BaseManager {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
        this.buildings = [];
        this.buildingTypes = [];
        this.selectedType = null;
        this.clanId = null;

        // Unified drag state
        // mode: 'menu' (dragging from build menu) | 'move' (dragging existing building)
        this._pending = null;  // { mode, startX, startY, bt?, building? }
        this._active = null;   // { mode, ghost, previewX, previewY, bt?, building? }

        // Bound handlers for document-level pointer tracking
        this._onPointerMove = (e) => this._pointerMove(e);
        this._onPointerUp = (e) => this._pointerUp(e);

        if (this.canvas) {
            this.canvas.width = GRID_SIZE * CELL_SIZE;
            this.canvas.height = GRID_SIZE * CELL_SIZE;

            // Canvas: tap to place selected type, or press-hold to move building
            this.canvas.addEventListener('pointerdown', (e) => this._canvasPointerDown(e));

            // Prevent context menu on long press
            this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
        }
    }

    // ===== Data loading =====

    async loadBuildingTypes() {
        try {
            const res = await fetch(`/api/buildings/types?init_data=${encodeURIComponent(window.VELLA.initData)}`);
            if (res.ok) {
                this.buildingTypes = await res.json();
                this.renderBuildMenu();
            }
        } catch (e) {
            console.error('Failed to load building types:', e);
        }
    }

    async loadBuildings() {
        try {
            const res = await fetch(`/api/buildings?init_data=${encodeURIComponent(window.VELLA.initData)}`);
            if (res.ok) {
                this.buildings = await res.json();
                this.render();
            }
        } catch (e) {
            console.error('Failed to load buildings:', e);
        }
    }

    // ===== Rendering =====

    render(excludeBuildingId = null) {
        if (!this.ctx) return;
        const ctx = this.ctx;

        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Grid lines
        ctx.strokeStyle = 'rgba(255,255,255,0.1)';
        ctx.lineWidth = 1;
        for (let i = 0; i <= GRID_SIZE; i++) {
            ctx.beginPath();
            ctx.moveTo(i * CELL_SIZE, 0);
            ctx.lineTo(i * CELL_SIZE, GRID_SIZE * CELL_SIZE);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(0, i * CELL_SIZE);
            ctx.lineTo(GRID_SIZE * CELL_SIZE, i * CELL_SIZE);
            ctx.stroke();
        }

        // Buildings
        for (const b of this.buildings) {
            if (excludeBuildingId && b.id === excludeBuildingId) continue;

            const x = b.grid_x * CELL_SIZE;
            const y = b.grid_y * CELL_SIZE;
            const w = b.width * CELL_SIZE;
            const h = b.height * CELL_SIZE;

            const color = BUILDING_COLORS[b.category] || '#666';
            ctx.globalAlpha = b.is_built ? 1 : 0.5;
            ctx.fillStyle = color;
            ctx.fillRect(x + 2, y + 2, w - 4, h - 4);

            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);
            ctx.globalAlpha = 1;

            ctx.fillStyle = '#fff';
            ctx.font = '10px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(b.type_name || b.type_code, x + w / 2, y + h / 2 - 4);

            if (!b.is_built) {
                const progress = b.build_progress || 0;
                ctx.fillStyle = 'rgba(255,255,255,0.3)';
                ctx.fillRect(x + 4, y + h - 10, (w - 8) * progress, 6);
            }

            if (b.produced_amount > 0) {
                const cap = b.storage_capacity || 0;
                ctx.fillStyle = (cap > 0 && b.produced_amount >= cap) ? '#ef4444' : '#ffd700';
                ctx.font = 'bold 11px Arial';
                const label = cap > 0 ? `${b.produced_amount}/${cap}` : `+${b.produced_amount}`;
                ctx.fillText(label, x + w / 2, y + h / 2 + 10);
            }
        }
    }

    _drawPreview(gx, gy, w, h, label, excludeBuildingId = null) {
        this.render(excludeBuildingId);
        if (!this.ctx) return;
        const ctx = this.ctx;

        const px = gx * CELL_SIZE;
        const py = gy * CELL_SIZE;
        const pw = w * CELL_SIZE;
        const ph = h * CELL_SIZE;

        const canPlace = !this._checkOverlap(gx, gy, w, h, excludeBuildingId);

        ctx.globalAlpha = 0.45;
        ctx.fillStyle = canPlace ? '#4ade80' : '#ef4444';
        ctx.fillRect(px + 1, py + 1, pw - 2, ph - 2);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = canPlace ? '#4ade80' : '#ef4444';
        ctx.lineWidth = 2;
        ctx.strokeRect(px + 1, py + 1, pw - 2, ph - 2);

        ctx.fillStyle = '#fff';
        ctx.font = 'bold 10px Arial';
        ctx.textAlign = 'center';
        ctx.fillText(label, px + pw / 2, py + ph / 2 + 4);
    }

    _checkOverlap(gx, gy, w, h, excludeId = null) {
        for (const b of this.buildings) {
            if (excludeId && b.id === excludeId) continue;
            if (gx < b.grid_x + b.width && gx + w > b.grid_x &&
                gy < b.grid_y + b.height && gy + h > b.grid_y) {
                return true;
            }
        }
        return false;
    }

    _clientToGrid(clientX, clientY) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        const cx = (clientX - rect.left) * scaleX;
        const cy = (clientY - rect.top) * scaleY;
        return {
            gx: Math.floor(cx / CELL_SIZE),
            gy: Math.floor(cy / CELL_SIZE),
            inside: cx >= 0 && cx < this.canvas.width && cy >= 0 && cy < this.canvas.height,
        };
    }

    _hitBuilding(gx, gy) {
        for (const b of this.buildings) {
            if (gx >= b.grid_x && gx < b.grid_x + b.width &&
                gy >= b.grid_y && gy < b.grid_y + b.height) {
                return b;
            }
        }
        return null;
    }

    // ===== Build Menu =====

    renderBuildMenu() {
        const container = document.getElementById('build-menu');
        if (!container) return;
        container.innerHTML = '';

        // Deselect button
        if (this.selectedType) {
            const deselBtn = document.createElement('button');
            deselBtn.className = 'build-btn';
            deselBtn.style.background = '#555';
            deselBtn.innerHTML = `<span class="build-name">✕ Отмена</span>`;
            deselBtn.addEventListener('click', () => {
                this.selectedType = null;
                this.renderBuildMenu();
            });
            container.appendChild(deselBtn);
        }

        for (const bt of this.buildingTypes) {
            const btn = document.createElement('button');
            btn.className = `build-btn ${this.selectedType?.code === bt.code ? 'selected' : ''}`;
            btn.innerHTML = `
                <span class="build-name">${bt.name}</span>
                <span class="build-cost">
                    ${bt.cost_metal ? `⛏${bt.cost_metal}` : ''}
                    ${bt.cost_wood ? `🪵${bt.cost_wood}` : ''}
                    ${bt.cost_food ? `🍖${bt.cost_food}` : ''}
                </span>
            `;

            // Unified pointer down for drag from menu
            btn.addEventListener('pointerdown', (e) => {
                if (e.button && e.button !== 0) return; // left button / touch only
                e.preventDefault();
                // Capture pointer so we get move/up even outside the button
                btn.setPointerCapture(e.pointerId);
                this._startPending('menu', e.clientX, e.clientY, { bt });
            });

            btn.addEventListener('pointermove', (e) => {
                this._pointerMove(e);
            });

            btn.addEventListener('pointerup', (e) => {
                this._pointerUp(e);
            });

            // Prevent long-press context menu on mobile
            btn.addEventListener('contextmenu', (e) => e.preventDefault());
            // Prevent native drag (ghost image in browsers)
            btn.setAttribute('draggable', 'false');

            container.appendChild(btn);
        }
    }

    // ===== Canvas pointer (for moving existing buildings or placing) =====

    _canvasPointerDown(e) {
        if (e.button && e.button !== 0) return;

        const { gx, gy, inside } = this._clientToGrid(e.clientX, e.clientY);
        if (!inside || gx < 0 || gx >= GRID_SIZE || gy < 0 || gy >= GRID_SIZE) return;

        // Check if clicking on an existing building → start move drag
        const hit = this._hitBuilding(gx, gy);
        if (hit) {
            e.preventDefault();
            this.canvas.setPointerCapture(e.pointerId);
            this._startPending('move', e.clientX, e.clientY, { building: hit });

            // Also listen on canvas for move/up
            this.canvas.addEventListener('pointermove', this._onPointerMove);
            this.canvas.addEventListener('pointerup', this._onPointerUp);
            return;
        }

        // Otherwise if a type is selected, place via tap
        if (this.selectedType) {
            this._placeBuilding(this.selectedType, gx, gy);
        }
    }

    // ===== Unified drag machinery =====

    _startPending(mode, clientX, clientY, extra) {
        this._pending = { mode, startX: clientX, startY: clientY, ...extra };
        this._active = null;
    }

    _pointerMove(e) {
        const clientX = e.clientX;
        const clientY = e.clientY;

        // Check if we should activate drag (threshold)
        if (this._pending && !this._active) {
            const dx = clientX - this._pending.startX;
            const dy = clientY - this._pending.startY;
            if (Math.abs(dx) + Math.abs(dy) < DRAG_THRESHOLD) return;

            // Activate drag — create ghost
            const label = this._pending.mode === 'menu'
                ? this._pending.bt.name
                : (this._pending.building.type_name || this._pending.building.type_code);

            const ghost = document.createElement('div');
            ghost.className = 'drag-ghost';
            ghost.textContent = label;
            ghost.style.left = clientX + 'px';
            ghost.style.top = clientY + 'px';
            document.body.appendChild(ghost);

            this._active = {
                mode: this._pending.mode,
                bt: this._pending.bt || null,
                building: this._pending.building || null,
                ghost,
                previewX: -1,
                previewY: -1,
            };
            this._pending = null;
            return;
        }

        if (!this._active) return;

        // Update ghost position
        this._active.ghost.style.left = clientX + 'px';
        this._active.ghost.style.top = clientY + 'px';

        // Update canvas preview
        const { gx, gy, inside } = this._clientToGrid(clientX, clientY);
        if (inside && gx >= 0 && gx < GRID_SIZE && gy >= 0 && gy < GRID_SIZE) {
            if (gx !== this._active.previewX || gy !== this._active.previewY) {
                this._active.previewX = gx;
                this._active.previewY = gy;

                if (this._active.mode === 'menu') {
                    const bt = this._active.bt;
                    this._drawPreview(gx, gy, bt.width || 1, bt.height || 1, bt.name);
                } else {
                    const b = this._active.building;
                    this._drawPreview(gx, gy, b.width, b.height, b.type_name || b.type_code, b.id);
                }
            }
        } else if (this._active.previewX !== -1) {
            this._active.previewX = -1;
            this._active.previewY = -1;
            this.render();
        }
    }

    _pointerUp(e) {
        // Clean up canvas listeners if we added them for move-mode
        this.canvas.removeEventListener('pointermove', this._onPointerMove);
        this.canvas.removeEventListener('pointerup', this._onPointerUp);

        // If drag was active
        if (this._active) {
            const clientX = e.clientX;
            const clientY = e.clientY;
            this._active.ghost.remove();

            const { gx, gy, inside } = this._clientToGrid(clientX, clientY);
            const validDrop = inside && gx >= 0 && gx < GRID_SIZE && gy >= 0 && gy < GRID_SIZE;

            if (this._active.mode === 'menu') {
                if (validDrop) {
                    this._placeBuilding(this._active.bt, gx, gy);
                }
                // Also select this type for further tap-to-place
                this.selectedType = this._active.bt;
                this.renderBuildMenu();
            } else if (this._active.mode === 'move') {
                if (validDrop) {
                    this._moveBuilding(this._active.building.id, gx, gy);
                }
            }

            this._active = null;
            this.render();
            return;
        }

        // If pending (tap without drag)
        if (this._pending) {
            if (this._pending.mode === 'menu') {
                // Tap on menu button = select type
                this.selectedType = this._pending.bt;
                this.renderBuildMenu();
            }
            // For 'move' mode tap without drag = do nothing (already handled by click)
            this._pending = null;
        }
    }

    // ===== API calls =====

    async _placeBuilding(bt, gx, gy) {
        try {
            const res = await fetch(
                `/api/buildings/place?building_type_code=${bt.code}&grid_x=${gx}&grid_y=${gy}&init_data=${encodeURIComponent(window.VELLA.initData)}`,
                { method: 'POST' }
            );
            if (res.ok) {
                await this.loadBuildings();
                this.renderBuildMenu();
                window.showToast?.('Построено!', 'success');
                this._refreshResources();
            } else {
                const err = await res.json();
                window.showToast?.(err.detail || 'Нельзя разместить здесь', 'error');
            }
        } catch (e) {
            console.error('Failed to place building:', e);
        }
    }

    async _moveBuilding(buildingId, gx, gy) {
        try {
            const res = await fetch(
                `/api/buildings/move?building_id=${buildingId}&grid_x=${gx}&grid_y=${gy}&init_data=${encodeURIComponent(window.VELLA.initData)}`,
                { method: 'POST' }
            );
            if (res.ok) {
                await this.loadBuildings();
                window.showToast?.('Перемещено', 'success');
            } else {
                const err = await res.json();
                window.showToast?.(err.detail || 'Нельзя переместить', 'error');
                this.render(); // redraw at old position
            }
        } catch (e) {
            console.error('Failed to move building:', e);
            this.render();
        }
    }

    async collectFromBuilding(buildingId) {
        try {
            const res = await fetch(
                `/api/buildings/collect?building_id=${buildingId}&init_data=${encodeURIComponent(window.VELLA.initData)}`,
                { method: 'POST' }
            );
            if (res.ok) {
                const data = await res.json();
                window.showToast?.(`+${data.amount} ${data.resource}`, 'success');
                await this.loadBuildings();
            } else {
                const err = await res.json();
                window.showToast?.(err.detail || 'Нечего собирать', 'error');
            }
        } catch (e) {
            console.error('Failed to collect:', e);
        }
    }

    async _refreshResources() {
        try {
            const res = await fetch(`/api/clan?init_data=${encodeURIComponent(window.VELLA.initData)}`);
            if (!res.ok) return;
            const data = await res.json();
            if (!data.clan) return;
            const r = data.clan.resources;
            document.getElementById('base-res-metal').textContent = r.metal;
            document.getElementById('base-res-wood').textContent = r.wood;
            document.getElementById('base-res-food').textContent = r.food;
            document.getElementById('base-res-ammo').textContent = r.ammo;
            document.getElementById('base-res-meds').textContent = r.meds;
        } catch (e) {}
    }

    destroy() {
        if (this._active) {
            this._active.ghost.remove();
            this._active = null;
        }
        this._pending = null;
        this.canvas.removeEventListener('pointermove', this._onPointerMove);
        this.canvas.removeEventListener('pointerup', this._onPointerUp);
        this.buildings = [];
        this.buildingTypes = [];
    }
}
