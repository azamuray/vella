/**
 * VELLA Terrain Texture Generator
 * Extracts real tiles from artist-made tilesets (Ivan Voirol "Basic Map" v3.1),
 * then pre-renders entire chunks as single textures for optimal performance.
 *
 * Tilesets:
 *   tileset_basic_map.png — 23x29 grid of 32x32 tiles (CC-BY Ivan Voirol)
 *   terrain_base.png — 9x13 grid of 32x32 terrain tiles with transitions
 */

const TILE_SIZE = 32;
const TILES_PER_CHUNK = 32;
const CHUNK_SIZE = TILE_SIZE * TILES_PER_CHUNK;

// Tile types (must match backend)
const T_GRASS = 0;
const T_DIRT = 1;
const T_FOREST = 2;
const T_ROCK = 3;
const T_WATER = 4;
const T_ROAD = 5;

// Seeded RNG (LCG)
function _rng(seed) {
    let s = seed | 0;
    return () => {
        s = (s * 1103515245 + 12345) & 0x7fffffff;
        return s / 0x7fffffff;
    };
}

// Tile coordinates in each spritesheet [col, row]
// 'main' = tileset_basic_map.png, 'base' = terrain_base.png
const TILE_MAP = {
    [T_GRASS]: { src: 'main', coords: [[0,1], [1,1], [2,1], [0,2]] },
    [T_DIRT]:  { src: 'base', coords: [[3,0], [4,0], [5,0]] },
    [T_FOREST]:{ src: 'main', coords: [[0,1], [1,1], [2,1]] },  // same grass base, trees overlaid
    [T_ROCK]:  { src: 'main', coords: [[11,12], [12,12], [11,13]] },
    [T_WATER]: { src: 'main', coords: [[0,16], [1,16], [2,16], [3,16]] },
    [T_ROAD]:  { src: 'main', coords: [[10,8], [11,8]] },
};

// Decoration sprite coordinates in main tileset [col, row, width_tiles, height_tiles]
const DECOR_MAP = {
    tree_canopy:  [[1,12, 1,1]],                          // round green canopy
    tree_full:    [[0,12, 1,1], [0,13, 1,1]],             // top + trunk (combine into 32x64)
    rock:         [[0,14, 1,1], [1,14, 1,1], [2,14, 1,1], [3,14, 1,1], [4,14, 1,1]],
    bush:         [[1,13, 1,1], [2,13, 1,1], [3,13, 1,1]],
    flowers:      [[1,10, 1,1], [2,10, 1,1]],             // red roses, daisies
};


// Building tile sources from main tileset [col, row]
const BUILDING_FILL = {
    'wall_wood':     { tile: [7, 1], border: '#8B6914' },
    'wall_metal':    { tile: [3, 1], border: '#708090' },
    'mine':          { tile: [3, 2], border: '#C0C0C0', icon: '⛏', iconColor: '#e0e0e0' },
    'sawmill':       { tile: [7, 1], border: '#DAA520', icon: '🪵', iconColor: '#daa520' },
    'farm':          { tile: [10, 3], border: '#90EE90', icon: '🌾', iconColor: '#90ee90' },
    'ammo_factory':  { tile: [22, 5], border: '#FF8C00', icon: '🔫', iconColor: '#ff8c00' },
    'med_station':   { tile: [19, 3], border: '#60A5FA', icon: '✚', iconColor: '#ff4444' },
    'bunker':        { tile: [3, 1], border: '#808080', icon: '🏰', iconColor: '#aaa' },
    'barracks':      { tile: [20, 1], border: '#CD853F', icon: '🏠', iconColor: '#cd853f' },
    'arena':         { tile: [11, 3], border: '#FF69B4', icon: '⚔', iconColor: '#ff69b4' },
    'gate_wood':     { tile: [7, 1], border: '#DAA520', icon: '🚪', iconColor: '#daa520' },
    'gate_metal':    { tile: [3, 1], border: '#B0C4DE', icon: '🚪', iconColor: '#b0c4de' },
};

export class TileTextureGenerator {
    constructor() {
        this.tiles = {};   // type -> [HTMLCanvasElement 32x32, ...]
        this.decor = {};   // name -> [HTMLCanvasElement, ...]
        this.buildingSprites = {}; // type_code -> HTMLCanvasElement
        this._mainImg = null;
        this._baseImg = null;
    }

    /**
     * Initialize from Phaser scene (after preload loaded the tileset images).
     * @param {Phaser.Scene} scene
     */
    generateAll(scene) {
        this._mainImg = scene.textures.get('tileset_main').getSourceImage();
        this._baseImg = scene.textures.get('tileset_base').getSourceImage();

        this._extractTiles();
        this._extractDecor();
        this._generateBuildingSprites();
    }

    // ===== Extract tile textures from spritesheets =====

    _extractTiles() {
        for (const type of [T_GRASS, T_DIRT, T_FOREST, T_ROCK, T_WATER, T_ROAD]) {
            const mapping = TILE_MAP[type];
            const srcImg = mapping.src === 'main' ? this._mainImg : this._baseImg;
            this.tiles[type] = [];

            for (const [col, row] of mapping.coords) {
                const c = document.createElement('canvas');
                c.width = TILE_SIZE;
                c.height = TILE_SIZE;
                const ctx = c.getContext('2d');
                ctx.drawImage(srcImg, col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE, 0, 0, TILE_SIZE, TILE_SIZE);

                // Desaturate grass/forest — make less vivid green, more natural
                if (type === T_GRASS || type === T_FOREST) {
                    this._desaturate(ctx, 0.35);
                    // Warm tint — slight yellow/brown to look like real grass
                    ctx.fillStyle = 'rgba(60, 50, 20, 0.15)';
                    ctx.fillRect(0, 0, TILE_SIZE, TILE_SIZE);
                }

                this.tiles[type].push(c);
            }

            // For forest: darken further for forest floor
            if (type === T_FOREST) {
                for (const c of this.tiles[type]) {
                    const ctx = c.getContext('2d');
                    ctx.fillStyle = 'rgba(15, 10, 0, 0.2)';
                    ctx.fillRect(0, 0, TILE_SIZE, TILE_SIZE);
                }
            }
        }
    }

    // ===== Desaturate a canvas context =====

    _desaturate(ctx, amount) {
        const img = ctx.getImageData(0, 0, ctx.canvas.width, ctx.canvas.height);
        const d = img.data;
        for (let i = 0; i < d.length; i += 4) {
            const gray = d[i] * 0.3 + d[i+1] * 0.59 + d[i+2] * 0.11;
            d[i]   = d[i]   + (gray - d[i])   * amount;
            d[i+1] = d[i+1] + (gray - d[i+1]) * amount;
            d[i+2] = d[i+2] + (gray - d[i+2]) * amount;
        }
        ctx.putImageData(img, 0, 0);
    }

    // ===== Extract decoration sprites =====

    _extractDecor() {
        this.decor = {};

        // Single-tile decorations
        for (const [name, coords] of Object.entries(DECOR_MAP)) {
            if (name === 'tree_full') continue; // handled separately
            this.decor[name] = [];
            for (const [col, row, w, h] of coords) {
                const c = document.createElement('canvas');
                c.width = w * TILE_SIZE;
                c.height = h * TILE_SIZE;
                const ctx = c.getContext('2d');
                ctx.drawImage(this._mainImg, col * TILE_SIZE, row * TILE_SIZE, w * TILE_SIZE, h * TILE_SIZE, 0, 0, c.width, c.height);
                // Desaturate green decorations (trees, bushes)
                if (name === 'tree_canopy' || name === 'bush') {
                    this._desaturate(ctx, 0.35);
                    ctx.fillStyle = 'rgba(50, 40, 15, 0.15)';
                    ctx.fillRect(0, 0, c.width, c.height);
                }
                this.decor[name].push(c);
            }
        }

        // Full tree (2 tiles stacked vertically: canopy at row 12, trunk at row 13)
        this.decor.tree_full = [];
        const treeParts = DECOR_MAP.tree_full;
        const c = document.createElement('canvas');
        c.width = TILE_SIZE;
        c.height = TILE_SIZE * 2;
        const ctx = c.getContext('2d');
        // Top part (canopy top)
        ctx.drawImage(this._mainImg, treeParts[0][0] * TILE_SIZE, treeParts[0][1] * TILE_SIZE, TILE_SIZE, TILE_SIZE, 0, 0, TILE_SIZE, TILE_SIZE);
        // Bottom part (trunk)
        ctx.drawImage(this._mainImg, treeParts[1][0] * TILE_SIZE, treeParts[1][1] * TILE_SIZE, TILE_SIZE, TILE_SIZE, 0, TILE_SIZE, TILE_SIZE, TILE_SIZE);
        // Desaturate tree
        this._desaturate(ctx, 0.35);
        ctx.fillStyle = 'rgba(50, 40, 15, 0.15)';
        ctx.fillRect(0, 0, c.width, c.height);
        this.decor.tree_full.push(c);
    }

    // ===== Chunk rendering =====

    renderChunk(terrain, seed) {
        const canvas = document.createElement('canvas');
        canvas.width = CHUNK_SIZE;
        canvas.height = CHUNK_SIZE;
        const ctx = canvas.getContext('2d');

        // Pass 1: stamp base terrain tiles
        for (let ty = 0; ty < TILES_PER_CHUNK; ty++) {
            for (let tx = 0; tx < TILES_PER_CHUNK; tx++) {
                const tileType = terrain[ty][tx];
                const px = tx * TILE_SIZE;
                const py = ty * TILE_SIZE;

                const variants = this.tiles[tileType];
                if (!variants || variants.length === 0) continue;

                // Pick variant deterministically
                const r = _rng(seed + ty * TILES_PER_CHUNK + tx);
                const variant = Math.floor(r() * variants.length);
                ctx.drawImage(variants[variant], px, py);
            }
        }

        // Pass 2: stamp decorations on top
        for (let ty = 0; ty < TILES_PER_CHUNK; ty++) {
            for (let tx = 0; tx < TILES_PER_CHUNK; tx++) {
                const tileType = terrain[ty][tx];
                const px = tx * TILE_SIZE;
                const py = ty * TILE_SIZE;

                const r = _rng(seed * 31 + ty * TILES_PER_CHUNK + tx);
                this._stampDecor(ctx, tileType, px, py, r);
            }
        }

        return canvas;
    }

    _stampDecor(ctx, type, px, py, r) {
        switch (type) {
            case T_GRASS:
                // Flowers (rare)
                if (r() < 0.06 && this.decor.flowers?.length) {
                    const flower = this.decor.flowers[Math.floor(r() * this.decor.flowers.length)];
                    const scale = 0.5 + r() * 0.3;
                    const dw = flower.width * scale;
                    const dh = flower.height * scale;
                    ctx.drawImage(flower,
                        px + r() * (TILE_SIZE - dw),
                        py + r() * (TILE_SIZE - dh),
                        dw, dh
                    );
                }
                // Small rock (rare)
                if (r() < 0.02 && this.decor.rock?.length) {
                    const rock = this.decor.rock[3] || this.decor.rock[this.decor.rock.length - 1]; // smallest
                    const scale = 0.3 + r() * 0.2;
                    ctx.drawImage(rock,
                        px + 4 + r() * (TILE_SIZE - 12),
                        py + 4 + r() * (TILE_SIZE - 12),
                        rock.width * scale, rock.height * scale
                    );
                }
                break;

            case T_FOREST:
                // Full tree (common)
                if (r() < 0.55 && this.decor.tree_full?.length) {
                    const tree = this.decor.tree_full[0];
                    const scale = 0.6 + r() * 0.4;
                    const dw = tree.width * scale;
                    const dh = tree.height * scale;
                    // Tree base at bottom of tile, canopy extends upward
                    ctx.drawImage(tree,
                        px + (TILE_SIZE - dw) * r(),
                        py + TILE_SIZE - dh,
                        dw, dh
                    );
                }
                // Bush
                if (r() < 0.25 && this.decor.bush?.length) {
                    const bush = this.decor.bush[Math.floor(r() * this.decor.bush.length)];
                    const scale = 0.4 + r() * 0.3;
                    ctx.drawImage(bush,
                        px + r() * (TILE_SIZE - bush.width * scale),
                        py + r() * (TILE_SIZE - bush.height * scale),
                        bush.width * scale, bush.height * scale
                    );
                }
                // Round canopy (extra density)
                if (r() < 0.3 && this.decor.tree_canopy?.length) {
                    const canopy = this.decor.tree_canopy[0];
                    const scale = 0.5 + r() * 0.5;
                    ctx.drawImage(canopy,
                        px + r() * (TILE_SIZE - canopy.width * scale),
                        py + r() * (TILE_SIZE - canopy.height * scale),
                        canopy.width * scale, canopy.height * scale
                    );
                }
                break;

            case T_ROCK:
                // Rock decorations
                if (r() < 0.4 && this.decor.rock?.length) {
                    const idx = Math.floor(r() * this.decor.rock.length);
                    const rock = this.decor.rock[idx];
                    const scale = 0.4 + r() * 0.4;
                    ctx.drawImage(rock,
                        px + 2 + r() * (TILE_SIZE - rock.width * scale - 4),
                        py + 2 + r() * (TILE_SIZE - rock.height * scale - 4),
                        rock.width * scale, rock.height * scale
                    );
                }
                break;

            case T_DIRT:
                // Occasional small rock
                if (r() < 0.15 && this.decor.rock?.length) {
                    const rock = this.decor.rock[Math.min(3, this.decor.rock.length - 1)];
                    const scale = 0.25 + r() * 0.2;
                    ctx.drawImage(rock,
                        px + r() * (TILE_SIZE - rock.width * scale),
                        py + r() * (TILE_SIZE - rock.height * scale),
                        rock.width * scale, rock.height * scale
                    );
                }
                break;

            // WATER and ROAD: no decorations (clean look)
        }
    }

    // ===== Building sprite generation =====

    _generateBuildingSprites() {
        // Building sizes in tiles [width, height]
        const BUILDING_SIZES = {
            'wall_wood': [1, 1], 'wall_metal': [1, 1],
            'turret_basic': [1, 1], 'turret_heavy': [2, 2],
            'mine': [2, 2], 'sawmill': [2, 2],
            'farm': [3, 2], 'ammo_factory': [2, 2],
            'med_station': [2, 2], 'bunker': [3, 3],
            'barracks': [2, 2], 'arena': [4, 4],
            'gate_wood': [1, 1], 'gate_metal': [1, 1],
        };

        for (const [code, fill] of Object.entries(BUILDING_FILL)) {
            const size = BUILDING_SIZES[code];
            if (!size) continue;
            const [tw, th] = size;
            const pw = tw * TILE_SIZE;
            const ph = th * TILE_SIZE;

            const c = document.createElement('canvas');
            c.width = pw;
            c.height = ph;
            const ctx = c.getContext('2d');

            // Fill with tiled texture from tileset
            const [col, row] = fill.tile;
            for (let ty = 0; ty < th; ty++) {
                for (let tx = 0; tx < tw; tx++) {
                    ctx.drawImage(this._mainImg,
                        col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE,
                        tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE);
                }
            }

            // Slight darkening overlay for depth
            ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
            ctx.fillRect(0, 0, pw, ph);

            // Border
            ctx.strokeStyle = fill.border;
            ctx.lineWidth = 2;
            ctx.strokeRect(1, 1, pw - 2, ph - 2);

            // Inner highlight (top-left light)
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(2, ph - 2);
            ctx.lineTo(2, 2);
            ctx.lineTo(pw - 2, 2);
            ctx.stroke();

            // Shadow (bottom-right)
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.3)';
            ctx.beginPath();
            ctx.moveTo(pw - 2, 2);
            ctx.lineTo(pw - 2, ph - 2);
            ctx.lineTo(2, ph - 2);
            ctx.stroke();

            // Icon in center
            if (fill.icon) {
                const iconSize = Math.min(pw, ph) > 48 ? 22 : 16;
                ctx.font = `${iconSize}px Arial`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                // Shadow behind icon
                ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
                ctx.fillText(fill.icon, pw / 2 + 1, ph / 2 - 2 + 1);
                ctx.fillText(fill.icon, pw / 2, ph / 2 - 2);
            }

            this.buildingSprites[code] = c;
        }
    }

    /**
     * Get a pre-rendered building sprite canvas.
     * @param {string} typeCode
     * @returns {HTMLCanvasElement|null}
     */
    getBuildingSprite(typeCode) {
        return this.buildingSprites[typeCode] || null;
    }
}
