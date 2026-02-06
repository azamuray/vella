/**
 * VELLA Base Builder
 * Canvas-based renderer for 16x16 clan base grid
 */

const GRID_SIZE = 16;
const CELL_SIZE = 40; // pixels per cell

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

        if (this.canvas) {
            this.canvas.width = GRID_SIZE * CELL_SIZE;
            this.canvas.height = GRID_SIZE * CELL_SIZE;
            this.canvas.addEventListener('click', (e) => this.onClick(e));
        }
    }

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

    render() {
        if (!this.ctx) return;
        const ctx = this.ctx;

        // Clear
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Draw grid
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

        // Draw buildings
        for (const b of this.buildings) {
            const x = b.grid_x * CELL_SIZE;
            const y = b.grid_y * CELL_SIZE;
            const w = b.width * CELL_SIZE;
            const h = b.height * CELL_SIZE;

            // Background
            const color = BUILDING_COLORS[b.category] || '#666';
            const alpha = b.is_built ? 1 : 0.5;
            ctx.globalAlpha = alpha;
            ctx.fillStyle = color;
            ctx.fillRect(x + 2, y + 2, w - 4, h - 4);

            // Border
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);

            ctx.globalAlpha = 1;

            // Label
            ctx.fillStyle = '#fff';
            ctx.font = '10px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(b.type_code, x + w / 2, y + h / 2 - 4);

            // Build progress
            if (!b.is_built) {
                const progress = b.build_progress || 0;
                ctx.fillStyle = 'rgba(255,255,255,0.3)';
                ctx.fillRect(x + 4, y + h - 10, (w - 8) * progress, 6);
            }

            // Production indicator
            if (b.produced_amount > 0) {
                ctx.fillStyle = '#ffd700';
                ctx.font = 'bold 11px Arial';
                ctx.fillText(`+${b.produced_amount}`, x + w / 2, y + h / 2 + 10);
            }
        }
    }

    renderBuildMenu() {
        const container = document.getElementById('build-menu');
        if (!container) return;

        container.innerHTML = '';
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
            btn.addEventListener('click', () => {
                this.selectedType = bt;
                this.renderBuildMenu();
            });
            container.appendChild(btn);
        }
    }

    async onClick(e) {
        if (!this.selectedType) return;

        const rect = this.canvas.getBoundingClientRect();
        const x = Math.floor((e.clientX - rect.left) / CELL_SIZE);
        const y = Math.floor((e.clientY - rect.top) / CELL_SIZE);

        try {
            const res = await fetch(
                `/api/buildings/place?building_type_code=${this.selectedType.code}&grid_x=${x}&grid_y=${y}&init_data=${encodeURIComponent(window.VELLA.initData)}`,
                { method: 'POST' }
            );
            if (res.ok) {
                this.selectedType = null;
                await this.loadBuildings();
                this.renderBuildMenu();
            } else {
                const err = await res.json();
                alert(err.detail || 'Cannot place here');
            }
        } catch (e) {
            console.error('Failed to place building:', e);
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
                alert(`Collected +${data.amount} ${data.resource}`);
                await this.loadBuildings();
            } else {
                const err = await res.json();
                alert(err.detail || 'Cannot collect');
            }
        } catch (e) {
            console.error('Failed to collect:', e);
        }
    }

    destroy() {
        this.buildings = [];
        this.buildingTypes = [];
    }
}
