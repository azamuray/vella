/**
 * VELLA World Game Manager
 * Manages Phaser game instance for open world mode
 */

import { DualJoystick } from './ui/Joystick.js?v=28';
import { TileTextureGenerator } from './terrain.js?v=28';

const TILE_SIZE = 32;
const TILES_PER_CHUNK = 32;
const CHUNK_SIZE = TILE_SIZE * TILES_PER_CHUNK; // 1024

// Building colors by category
const BUILDING_COLORS = {
    'defense': { fill: 0x8b0000, stroke: 0xff4444 },
    'production': { fill: 0x8b6914, stroke: 0xfbbf24 },
    'utility': { fill: 0x1e3a5f, stroke: 0x60a5fa },
};

// Minimap config
const MINIMAP_SIZE = 120;
const MINIMAP_SCALE = 1 / 25; // 1 minimap pixel = 25 world pixels

export class WorldGameManager {
    constructor() {
        this.myId = window.VELLA.player?.id;
        this.game = null;
        this.scene = null;
        this.sceneReady = false;
        this.joystick = null;
        this.terrainGen = new TileTextureGenerator();

        // Clan base info
        this.clanBase = null;
        this.baseMarker = null; // Phaser objects for base marker
        this.baseMarkerText = null;

        // Game state from server
        this.players = {};
        this.zombies = {};
        this.projectiles = {};

        // Chunks
        this.chunks = {}; // key: "cx,cy" -> { sprite, textureKey, resourceSprites, buildingSprites }
        this.pendingChunks = []; // chunks received before scene was ready

        // Ground drops (clothing from zombies)
        this.groundDrops = {}; // drop_id -> { sprite, label }

        // Camera
        this.cameraX = 0;
        this.cameraY = 0;

        // Input
        this.inputSeq = 0;

        // Keyboard state
        this.keys = {};
        this._onKeyDown = (e) => {
            this.keys[e.code] = true;
            // Prevent page scroll on arrow keys / space
            if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space','Slash'].includes(e.code)) {
                e.preventDefault();
            }
        };
        this._onKeyUp = (e) => {
            this.keys[e.code] = false;
        };
        window.addEventListener('keydown', this._onKeyDown);
        window.addEventListener('keyup', this._onKeyUp);

        // Aim angle from arrow keys (radians)
        this.aimAngle = -Math.PI / 2; // default: up

        // Minimap
        this.minimapCanvas = document.getElementById('world-minimap');
        this.minimapCtx = this.minimapCanvas ? this.minimapCanvas.getContext('2d') : null;
    }

    setClanBase(baseData) {
        this.clanBase = baseData;
    }

    start() {
        const joystickHeight = 200;
        const gameHeight = window.innerHeight - joystickHeight;

        const config = {
            type: Phaser.AUTO,
            parent: 'game-container',
            width: window.innerWidth,
            height: gameHeight,
            backgroundColor: '#1a1a2e',
            scene: {
                preload: this.preload.bind(this),
                create: this.create.bind(this),
                update: this.update.bind(this),
            },
            scale: {
                mode: Phaser.Scale.FIT,
                autoCenter: Phaser.Scale.CENTER_HORIZONTALLY,
            },
        };

        this.game = new Phaser.Game(config);
    }

    preload() {
        const scene = this.game.scene.scenes[0];
        // Load animated spritesheets
        scene.load.spritesheet('player_idle', '/assets/sprites/player_idle.png', { frameWidth: 219, frameHeight: 165 });
        scene.load.spritesheet('player_move', '/assets/sprites/player_move.png', { frameWidth: 219, frameHeight: 165 });
        scene.load.spritesheet('player_shoot', '/assets/sprites/player_shoot.png', { frameWidth: 219, frameHeight: 165 });
        scene.load.spritesheet('zombie_idle', '/assets/sprites/zombie_anim_idle.png', { frameWidth: 269, frameHeight: 260 });
        scene.load.spritesheet('zombie_move', '/assets/sprites/zombie_anim_move.png', { frameWidth: 269, frameHeight: 260 });
        scene.load.spritesheet('zombie_attack', '/assets/sprites/zombie_anim_attack.png', { frameWidth: 269, frameHeight: 260 });
        // Fallback static sprites for special zombie types
        scene.load.image('zombie_tank_img', '/assets/sprites/zombie_tank.png');
        scene.load.image('zombie_boss_img', '/assets/sprites/zombie_boss.png');
        // Load tilesets
        scene.load.image('tileset_main', '/assets/tilesets/tileset_basic_map.png');
        scene.load.image('tileset_base', '/assets/tilesets/terrain_base.png');
        // Load audio
        scene.load.audio('shoot_single', '/assets/audio/shoot_single.ogg');
        scene.load.audio('zombie_death', '/assets/audio/zombie_death.ogg');
        scene.load.audio('zombie_hurt', '/assets/audio/zombie_hurt.ogg');
        scene.load.audio('zombie_attack', '/assets/audio/zombie_attack.ogg');
        scene.load.audio('player_hurt', '/assets/audio/player_hurt.ogg');
    }

    create() {
        this.scene = this.game.scene.scenes[0];
        this.sceneReady = true;

        // Extract terrain textures from tilesets (one-time cost)
        this.terrainGen.generateAll(this.scene);

        // Track gate sprites for animation
        this._gateSprites = {}; // building_id -> { sprite, isOpen }

        // Register building sprite textures
        for (const code of ['wall_wood', 'wall_metal', 'gate_wood', 'gate_metal',
            'mine', 'sawmill', 'farm',
            'ammo_factory', 'med_station', 'bunker', 'barracks', 'arena']) {
            const canvas = this.terrainGen.getBuildingSprite(code);
            if (canvas) {
                this.scene.textures.addCanvas(`bldg_${code}`, canvas);
            }
        }

        // Create player animations
        this.scene.anims.create({
            key: 'player_idle_anim',
            frames: this.scene.anims.generateFrameNumbers('player_idle', { start: 0, end: 4 }),
            frameRate: 6,
            repeat: -1,
        });
        this.scene.anims.create({
            key: 'player_move_anim',
            frames: this.scene.anims.generateFrameNumbers('player_move', { start: 0, end: 7 }),
            frameRate: 12,
            repeat: -1,
        });
        this.scene.anims.create({
            key: 'player_shoot_anim',
            frames: this.scene.anims.generateFrameNumbers('player_shoot', { start: 0, end: 2 }),
            frameRate: 10,
            repeat: 0,
        });

        // Create zombie animations
        this.scene.anims.create({
            key: 'zombie_idle_anim',
            frames: this.scene.anims.generateFrameNumbers('zombie_idle', { start: 0, end: 3 }),
            frameRate: 4,
            repeat: -1,
        });
        this.scene.anims.create({
            key: 'zombie_move_anim',
            frames: this.scene.anims.generateFrameNumbers('zombie_move', { start: 0, end: 7 }),
            frameRate: 8,
            repeat: -1,
        });
        this.scene.anims.create({
            key: 'zombie_attack_anim',
            frames: this.scene.anims.generateFrameNumbers('zombie_attack', { start: 0, end: 5 }),
            frameRate: 10,
            repeat: 0,
        });

        // Setup camera (world is larger than screen)
        this.scene.cameras.main.setBounds(-100000, -100000, 200000, 200000);

        // Setup joysticks
        this.joystick = new DualJoystick();

        // Input sending loop
        this.scene.time.addEvent({
            delay: 50,
            callback: this.sendInput,
            callbackScope: this,
            loop: true,
        });

        // Create base marker if clan base is set
        if (this.clanBase) {
            this._createBaseMarker();
        }

        // Click/tap on buildings
        this.scene.input.on('pointerdown', (pointer) => {
            const worldX = pointer.worldX;
            const worldY = pointer.worldY;
            this._handleBuildingClick(worldX, worldY);
        });

        // Building panel buttons
        this._setupBuildingPanel();

        // Process any chunks that arrived before scene was ready
        for (const data of this.pendingChunks) {
            this.loadChunk(data);
        }
        this.pendingChunks = [];
    }

    update(time, delta) {
        // Smooth camera follow on my player
        const me = this.players[this.myId];
        if (me && me.targetX !== undefined) {
            // Smooth interpolation for player sprites
            for (const player of Object.values(this.players)) {
                if (player.targetX !== undefined) {
                    player.sprite.x = Phaser.Math.Linear(player.sprite.x, player.targetX, 0.2);
                    player.sprite.y = Phaser.Math.Linear(player.sprite.y, player.targetY, 0.2);
                    if (player.nameText) {
                        player.nameText.x = player.sprite.x;
                        player.nameText.y = player.sprite.y - 30;
                    }
                    if (player.healthBar) {
                        player.healthBar.x = player.sprite.x - 20;
                        player.healthBar.y = player.sprite.y - 24;
                    }
                    if (player.armorRing) {
                        player.armorRing.setPosition(player.sprite.x, player.sprite.y);
                    }
                }
            }

            // Camera follows my player
            this.scene.cameras.main.scrollX = me.sprite.x - this.scene.scale.width / 2;
            this.scene.cameras.main.scrollY = me.sprite.y - this.scene.scale.height / 2;
        }

        // Smooth zombie interpolation
        for (const zombie of Object.values(this.zombies)) {
            if (zombie.targetX !== undefined) {
                zombie.sprite.x = Phaser.Math.Linear(zombie.sprite.x, zombie.targetX, 0.15);
                zombie.sprite.y = Phaser.Math.Linear(zombie.sprite.y, zombie.targetY, 0.15);
                if (zombie.indicator) {
                    zombie.indicator.x = zombie.sprite.x;
                    zombie.indicator.y = zombie.sprite.y;
                }
                if (zombie.healthBar) {
                    const hbWidth = zombie.size * 2;
                    zombie.healthBar.x = zombie.sprite.x - hbWidth / 2;
                    zombie.healthBar.y = zombie.sprite.y - zombie.size - 8;
                }
            }
        }

        // Update minimap
        this.updateMinimap();

        // Update base distance HUD
        this._updateBaseDistance();
    }

    sendInput() {
        if (!window.VELLA.ws?.isConnected) return;

        // Get joystick input (mobile)
        const joy = this.joystick ? this.joystick.getInput() : { moveX: 0, moveY: 0, aimX: 0, aimY: 0, shooting: false };

        // Keyboard movement: WASD
        let kbMoveX = 0, kbMoveY = 0;
        if (this.keys['KeyW'] || this.keys['KeyW']) kbMoveY -= 1;
        if (this.keys['KeyS']) kbMoveY += 1;
        if (this.keys['KeyA']) kbMoveX -= 1;
        if (this.keys['KeyD']) kbMoveX += 1;
        // Normalize diagonal
        if (kbMoveX !== 0 && kbMoveY !== 0) {
            const len = Math.sqrt(kbMoveX * kbMoveX + kbMoveY * kbMoveY);
            kbMoveX /= len;
            kbMoveY /= len;
        }

        // Keyboard aim: Arrow keys (rotate aim angle)
        const aimSpeed = 0.06; // radians per tick
        if (this.keys['ArrowLeft']) this.aimAngle -= aimSpeed;
        if (this.keys['ArrowRight']) this.aimAngle += aimSpeed;
        if (this.keys['ArrowUp']) this.aimAngle = -Math.PI / 2;
        if (this.keys['ArrowDown']) this.aimAngle = Math.PI / 2;

        // Keyboard shoot: / or ? key (Slash)
        const kbShooting = !!this.keys['Slash'];

        // Combine: keyboard takes priority if active
        const hasKeyboard = kbMoveX !== 0 || kbMoveY !== 0 || kbShooting ||
            this.keys['ArrowLeft'] || this.keys['ArrowRight'] ||
            this.keys['ArrowUp'] || this.keys['ArrowDown'];

        const moveX = hasKeyboard ? kbMoveX : joy.moveX;
        const moveY = hasKeyboard ? kbMoveY : joy.moveY;
        const shooting = kbShooting || joy.shooting;

        // Aim: keyboard arrows > right joystick > movement direction > last known
        let aimX, aimY;
        if (hasKeyboard) {
            aimX = Math.cos(this.aimAngle);
            aimY = Math.sin(this.aimAngle);
        } else if (this.joystick?.rightTouch !== null) {
            // Right joystick is actively held
            aimX = joy.aimX;
            aimY = joy.aimY;
            this._lastAimX = aimX;
            this._lastAimY = aimY;
        } else if (Math.abs(moveX) > 0.1 || Math.abs(moveY) > 0.1) {
            // No aim input — face movement direction
            const len = Math.sqrt(moveX * moveX + moveY * moveY);
            aimX = moveX / len;
            aimY = moveY / len;
            this._lastAimX = aimX;
            this._lastAimY = aimY;
        } else if (this._lastAimX !== undefined) {
            // Nothing pressed — keep last direction
            aimX = this._lastAimX;
            aimY = this._lastAimY;
        } else {
            aimX = 0;
            aimY = 0;
        }

        window.VELLA.ws.send({
            type: 'world_input',
            seq: ++this.inputSeq,
            move_x: moveX,
            move_y: moveY,
            aim_x: aimX,
            aim_y: aimY,
            shooting: shooting,
            reload: false,
        });
    }

    // ===== Base marker =====

    _createBaseMarker() {
        if (!this.clanBase || !this.scene) return;

        const bx = this.clanBase.base_x;
        const by = this.clanBase.base_y;
        const platformSize = 120;
        const halfPlatform = platformSize / 2;

        // Safe zone boundary (450px radius, matching backend SAFE_ZONE_RADIUS)
        const safeZone = this.scene.add.circle(bx, by, 450, 0x4488ff, 0.04);
        safeZone.setStrokeStyle(1, 0x4488ff, 0.15);
        safeZone.setDepth(1);

        // Platform
        const platform = this.scene.add.graphics().setDepth(2);
        platform.fillStyle(0x2a1a3a, 0.5);
        platform.fillRect(bx - halfPlatform, by - halfPlatform, platformSize, platformSize);
        platform.lineStyle(2, 0xffd700, 0.6);
        platform.strokeRect(bx - halfPlatform, by - halfPlatform, platformSize, platformSize);

        // Base flag icon (triangle) in center
        const flag = this.scene.add.graphics().setDepth(15);
        flag.fillStyle(0xffd700, 0.9);
        flag.fillRect(bx - 1, by - 20, 2, 26); // pole
        flag.fillStyle(0xe94560, 1);
        flag.fillTriangle(bx + 1, by - 20, bx + 1, by - 8, bx + 14, by - 14); // flag

        // Clan name text above base
        const nameText = this.scene.add.text(bx, by - halfPlatform - 10, this.clanBase.name, {
            fontSize: '12px',
            fontFamily: 'Arial',
            color: '#ffd700',
            stroke: '#000',
            strokeThickness: 3,
        }).setOrigin(0.5).setDepth(15);

        // Store all member sprites for cleanup
        const memberSprites = [];

        // Render clan members on the platform
        const members = this.clanBase.members || [];
        // Filter out the current player — they're shown as their normal sprite
        const otherMembers = members.filter(m => m.player_id !== this.myId);

        // Position members in a grid around center, avoiding the flag area
        const positions = [
            { dx: -35, dy: -30 },
            { dx: 35, dy: -30 },
            { dx: -35, dy: 30 },
            { dx: 35, dy: 30 },
            { dx: 0, dy: 40 },
            { dx: -35, dy: 0 },
            { dx: 35, dy: 0 },
            { dx: 0, dy: -40 },
        ];

        for (let i = 0; i < otherMembers.length && i < positions.length; i++) {
            const m = otherMembers[i];
            const pos = positions[i];
            const mx = bx + pos.dx;
            const my = by + pos.dy;

            // Circle for member (green = online, gray = offline)
            const color = m.is_online ? 0x4ade80 : 0x888888;
            const circle = this.scene.add.circle(mx, my, 8, color, 0.9);
            circle.setStrokeStyle(1, 0xffffff, 0.4);
            circle.setDepth(14);
            memberSprites.push(circle);

            // Username text above circle
            const memberName = this.scene.add.text(mx, my - 14, m.username, {
                fontSize: '7px',
                fontFamily: 'Arial',
                color: m.is_online ? '#4ade80' : '#aaaaaa',
                stroke: '#000',
                strokeThickness: 2,
            }).setOrigin(0.5).setDepth(14);
            memberSprites.push(memberName);

            // Zzz animation for offline members
            if (!m.is_online) {
                const zzz = this.scene.add.text(mx + 10, my - 8, 'zzz', {
                    fontSize: '8px',
                    fontFamily: 'Arial',
                    color: '#aaaaaa',
                    stroke: '#000',
                    strokeThickness: 2,
                }).setOrigin(0, 1).setDepth(15);
                memberSprites.push(zzz);

                // Float up and repeat
                this.scene.tweens.add({
                    targets: zzz,
                    y: my - 24,
                    alpha: 0,
                    duration: 2000,
                    delay: i * 300,
                    repeat: -1,
                    onRepeat: () => {
                        zzz.y = my - 8;
                        zzz.alpha = 1;
                    },
                });
            }
        }

        this.baseMarker = { platform, flag, nameText, safeZone, memberSprites };
    }

    _updateBaseDistance() {
        const distEl = document.getElementById('base-distance');
        if (!distEl || !this.clanBase) return;

        const me = this.players[this.myId];
        if (!me) return;

        const dx = this.clanBase.base_x - me.sprite.x;
        const dy = this.clanBase.base_y - me.sprite.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 100) {
            distEl.textContent = 'на базе';
        } else if (dist < 1000) {
            distEl.textContent = `${Math.round(dist)}м`;
        } else {
            distEl.textContent = `${(dist / 1000).toFixed(1)}км`;
        }

        // Show/hide base actions dropdown wrapper based on proximity (450 = SAFE_ZONE_RADIUS)
        const actionsWrap = document.getElementById('base-actions-wrap');
        if (actionsWrap) {
            const shouldHide = dist > 450;
            actionsWrap.classList.toggle('hidden', shouldHide);
            // Close dropdown when leaving base area
            if (shouldHide) {
                const dd = document.getElementById('base-actions-dropdown');
                if (dd) dd.classList.add('hidden');
            }
        }
    }

    // ===== Chunk management =====

    loadChunk(data) {
        // If scene isn't ready yet, buffer for later
        if (!this.sceneReady) {
            this.pendingChunks.push(data);
            return;
        }

        const key = `${data.chunk_x},${data.chunk_y}`;
        if (this.chunks[key]) return; // Already loaded

        const offsetX = data.chunk_x * CHUNK_SIZE;
        const offsetY = data.chunk_y * CHUNK_SIZE;

        // Pre-render chunk to a single canvas texture
        const chunkSeed = data.seed || (data.chunk_x * 7919 + data.chunk_y * 6271);
        const chunkCanvas = this.terrainGen.renderChunk(data.terrain, chunkSeed);

        const textureKey = `chunk_${data.chunk_x}_${data.chunk_y}`;
        this.scene.textures.addCanvas(textureKey, chunkCanvas);
        const sprite = this.scene.add.image(offsetX + CHUNK_SIZE / 2, offsetY + CHUNK_SIZE / 2, textureKey);
        sprite.setDepth(0);

        // Draw resources
        const resourceSprites = [];
        if (data.resources) {
            for (const res of data.resources) {
                if (res.type === 'trash') {
                    // Trash can — cylindrical shape
                    const g = this.scene.add.graphics().setDepth(2);
                    // Body
                    g.fillStyle(0x666655, 0.9);
                    g.fillRect(res.x - 7, res.y - 6, 14, 14);
                    // Lid
                    g.fillStyle(0x888877, 1);
                    g.fillRoundedRect(res.x - 8, res.y - 9, 16, 4, 2);
                    // Handle on lid
                    g.fillStyle(0xaaaaaa, 1);
                    g.fillRect(res.x - 2, res.y - 11, 4, 2);
                    // Bottom rim
                    g.fillStyle(0x555544, 1);
                    g.fillRect(res.x - 7, res.y + 7, 14, 2);
                    // Outline
                    g.lineStyle(1, 0x888877, 0.6);
                    g.strokeRect(res.x - 7, res.y - 6, 14, 14);
                    // ? mark
                    const label = this.scene.add.text(res.x, res.y + 1, '?', {
                        fontSize: '10px', fontFamily: 'Arial',
                        color: '#ccccaa', fontStyle: 'bold',
                        stroke: '#333', strokeThickness: 1,
                    }).setOrigin(0.5).setDepth(3);
                    g.resData = res;
                    resourceSprites.push(g);
                    resourceSprites.push(label);
                } else {
                    const color = res.type === 'metal' ? 0xc0c0c0 : 0x8b4513;
                    const circle = this.scene.add.circle(res.x, res.y, 10, color, 0.8);
                    circle.setStrokeStyle(2, 0xffffff, 0.5);
                    circle.setDepth(2);
                    circle.setInteractive();
                    circle.resData = res;
                    resourceSprites.push(circle);
                }
            }
        }

        // Draw buildings
        const buildingSprites = [];
        if (data.buildings && data.buildings.length > 0) {
            for (const b of data.buildings) {
                const sprites = this._createBuildingSprite(b);
                buildingSprites.push(...sprites);
            }
        }

        this.chunks[key] = { sprite, textureKey, resourceSprites, buildingSprites, _buildings: data.buildings || [] };
    }

    _createBuildingSprite(b) {
        const sprites = [];
        const alpha = b.is_built ? 1 : 0.4;
        const cx = b.x + b.width / 2;
        const cy = b.y + b.height / 2;

        // Gates — special handling (hinge rotation for open/close animation)
        if (b.type_code === 'gate_wood' || b.type_code === 'gate_metal') {
            const textureKey = `bldg_${b.type_code}`;
            const hasTexture = this.scene.textures.exists(textureKey);

            if (hasTexture) {
                // Gate sprite with origin at left edge (hinge point)
                const gateSprite = this.scene.add.image(b.x, cy, textureKey);
                gateSprite.setOrigin(0, 0.5);
                gateSprite.setDepth(3);
                gateSprite.setAlpha(alpha);
                sprites.push(gateSprite);

                // Track for open/close animation
                this._gateSprites[b.id] = { sprite: gateSprite, isOpen: false };
            } else {
                // Fallback
                const rect = this.scene.add.graphics().setDepth(3);
                rect.fillStyle(0x8b6914, alpha * 0.85);
                rect.fillRect(b.x, b.y, b.width, b.height);
                rect.lineStyle(2, 0xdaa520, alpha);
                rect.strokeRect(b.x, b.y, b.width, b.height);
                sprites.push(rect);
            }

            // Name label
            const name = b.type_code === 'gate_wood' ? 'Ворота' : 'Мет. ворота';
            const label = this.scene.add.text(cx, b.y + b.height + 6, name, {
                fontSize: '7px', fontFamily: 'Arial', color: '#ddd',
                stroke: '#000', strokeThickness: 2,
            }).setOrigin(0.5).setDepth(4);
            sprites.push(label);

            return sprites;
        }

        // Turrets — special handling (base + rotating barrel)
        if (b.type_code === 'turret_basic' || b.type_code === 'turret_heavy') {
            const isHeavy = b.type_code === 'turret_heavy';
            const radius = isHeavy ? 28 : 16;

            // Range circle
            const range = isHeavy ? 400 : 300;
            const rangeCircle = this.scene.add.circle(cx, cy, range, 0xff4444, 0.03);
            rangeCircle.setStrokeStyle(1, 0xff4444, 0.12);
            rangeCircle.setDepth(1);
            sprites.push(rangeCircle);

            // Base platform (dark circle)
            const base = this.scene.add.circle(cx, cy, radius + 4, 0x333333, alpha * 0.9);
            base.setStrokeStyle(2, 0x666666, alpha);
            base.setDepth(3);
            sprites.push(base);

            // Turret body (lighter circle)
            const body = this.scene.add.circle(cx, cy, radius, isHeavy ? 0x8b0000 : 0x555555, alpha);
            body.setStrokeStyle(isHeavy ? 2 : 1.5, isHeavy ? 0xff4444 : 0xaaaaaa, alpha);
            body.setDepth(3.5);
            sprites.push(body);

            // Barrel (graphics that we'll rotate)
            const barrel = this.scene.add.graphics().setDepth(4);
            const barrelLen = isHeavy ? 30 : 20;
            const barrelW = isHeavy ? 8 : 5;
            barrel.fillStyle(isHeavy ? 0xcc2222 : 0x888888, alpha);
            barrel.fillRect(0, -barrelW / 2, barrelLen, barrelW);
            barrel.fillStyle(0x222222, alpha);
            barrel.fillRect(barrelLen - 4, -barrelW / 2 - 1, 4, barrelW + 2);
            barrel.setPosition(cx, cy);
            sprites.push(barrel);

            if (!this._turretBarrels) this._turretBarrels = {};
            this._turretBarrels[b.id] = barrel;

            const label = this.scene.add.text(cx, cy + radius + 10, isHeavy ? 'Тяж. турель' : 'Турель', {
                fontSize: '8px', fontFamily: 'Arial', color: '#ff6666',
                stroke: '#000', strokeThickness: 2,
            }).setOrigin(0.5).setDepth(4);
            sprites.push(label);

        } else {
            // All other buildings — use tileset-based sprite
            const textureKey = `bldg_${b.type_code}`;
            const hasTexture = this.scene.textures.exists(textureKey);

            if (hasTexture) {
                const img = this.scene.add.image(cx, cy, textureKey);
                img.setDepth(3);
                img.setAlpha(alpha);
                sprites.push(img);
            } else {
                // Fallback for unknown types
                const rect = this.scene.add.graphics().setDepth(3);
                rect.fillStyle(0x333333, alpha * 0.85);
                rect.fillRect(b.x, b.y, b.width, b.height);
                rect.lineStyle(2, 0x888888, alpha);
                rect.strokeRect(b.x, b.y, b.width, b.height);
                sprites.push(rect);
            }

            // Name label
            const BLDG_NAMES = {
                'wall_wood': 'Дерев. стена', 'wall_metal': 'Мет. стена',
                'gate_wood': 'Ворота', 'gate_metal': 'Мет. ворота',
                'mine': 'Шахта', 'sawmill': 'Лесопилка', 'farm': 'Ферма',
                'ammo_factory': 'Оружейная', 'med_station': 'Медпункт',
                'bunker': 'Бункер', 'barracks': 'Казарма', 'arena': 'Арена',
            };
            const name = BLDG_NAMES[b.type_code] || b.type_name || b.type_code;
            // Only show label for non-wall buildings
            if (!b.type_code.startsWith('wall_')) {
                const label = this.scene.add.text(cx, b.y + b.height + 6, name, {
                    fontSize: '7px', fontFamily: 'Arial', color: '#ddd',
                    stroke: '#000', strokeThickness: 2,
                }).setOrigin(0.5).setDepth(4);
                sprites.push(label);
            }
        }

        // Health bar for damaged buildings
        if (b.hp < b.max_hp) {
            const hb = this.scene.add.graphics().setDepth(4);
            const hbWidth = b.width;
            const percent = b.hp / b.max_hp;
            hb.fillStyle(0x000000, 0.5);
            hb.fillRect(b.x, b.y - 6, hbWidth, 3);
            const hpColor = percent > 0.5 ? 0x4ade80 : (percent > 0.25 ? 0xfbbf24 : 0xef4444);
            hb.fillStyle(hpColor, 1);
            hb.fillRect(b.x, b.y - 6, hbWidth * percent, 3);
            sprites.push(hb);
        }

        return sprites;
    }

    _cleanupChunkTurretBarrels(buildings) {
        if (!buildings) return;
        for (const b of buildings) {
            if (this._turretBarrels && b.type_code?.startsWith('turret')) {
                delete this._turretBarrels[b.id];
            }
            if (this._gateSprites && b.type_code?.startsWith('gate_')) {
                delete this._gateSprites[b.id];
            }
        }
    }

    updateChunkBuildings(data) {
        const key = `${data.chunk_x},${data.chunk_y}`;
        const chunk = this.chunks[key];
        if (!chunk) return;

        // Cleanup old turret barrel references
        this._cleanupChunkTurretBarrels(chunk._buildings);

        // Destroy old building sprites
        if (chunk.buildingSprites) {
            for (const sprite of chunk.buildingSprites) {
                sprite.destroy();
            }
        }

        // Create new building sprites
        const buildingSprites = [];
        if (data.buildings && data.buildings.length > 0) {
            for (const b of data.buildings) {
                const sprites = this._createBuildingSprite(b);
                buildingSprites.push(...sprites);
            }
        }

        chunk.buildingSprites = buildingSprites;
        chunk._buildings = data.buildings || [];
    }

    unloadChunk(chunk_x, chunk_y) {
        const key = `${chunk_x},${chunk_y}`;
        const chunk = this.chunks[key];
        if (!chunk) return;

        this._cleanupChunkTurretBarrels(chunk._buildings);
        chunk.sprite.destroy();
        this.scene.textures.remove(chunk.textureKey);

        for (const sprite of chunk.resourceSprites) {
            sprite.destroy();
        }
        if (chunk.buildingSprites) {
            for (const sprite of chunk.buildingSprites) {
                sprite.destroy();
            }
        }
        delete this.chunks[key];
    }

    // ===== Minimap =====

    updateMinimap() {
        if (!this.minimapCtx) return;
        const ctx = this.minimapCtx;
        const me = this.players[this.myId];
        if (!me) return;

        const myX = me.sprite.x;
        const myY = me.sprite.y;
        const half = MINIMAP_SIZE / 2;
        // World range visible on minimap
        const worldRange = MINIMAP_SIZE / MINIMAP_SCALE;

        // Clear
        ctx.fillStyle = 'rgba(10, 10, 15, 0.85)';
        ctx.fillRect(0, 0, MINIMAP_SIZE, MINIMAP_SIZE);

        // Helper: world coords to minimap coords
        const toMini = (wx, wy) => ({
            x: half + (wx - myX) * MINIMAP_SCALE,
            y: half + (wy - myY) * MINIMAP_SCALE,
        });

        // Draw loaded chunk boundaries
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
        ctx.lineWidth = 0.5;
        for (const key of Object.keys(this.chunks)) {
            const [cx, cy] = key.split(',').map(Number);
            const p = toMini(cx * CHUNK_SIZE, cy * CHUNK_SIZE);
            const size = CHUNK_SIZE * MINIMAP_SCALE;
            ctx.strokeRect(p.x, p.y, size, size);
        }

        // Draw buildings on minimap
        for (const key of Object.keys(this.chunks)) {
            const chunk = this.chunks[key];
            if (!chunk._buildings) continue;
            for (const b of chunk._buildings) {
                const p = toMini(b.x + b.width / 2, b.y + b.height / 2);
                if (p.x < 0 || p.x >= MINIMAP_SIZE || p.y < 0 || p.y >= MINIMAP_SIZE) continue;
                ctx.fillStyle = b.category === 'defense' ? '#ff4444' : (b.category === 'production' ? '#fbbf24' : '#60a5fa');
                ctx.fillRect(p.x - 1, p.y - 1, 3, 3);
            }
        }

        // Draw zombies (red dots)
        ctx.fillStyle = '#ef4444';
        for (const zombie of Object.values(this.zombies)) {
            const p = toMini(zombie.sprite.x, zombie.sprite.y);
            if (p.x < 0 || p.x >= MINIMAP_SIZE || p.y < 0 || p.y >= MINIMAP_SIZE) continue;
            ctx.fillRect(p.x - 1, p.y - 1, 2, 2);
        }

        // Draw other players (blue dots)
        ctx.fillStyle = '#60a5fa';
        for (const player of Object.values(this.players)) {
            if (player.data?.id === this.myId) continue;
            const p = toMini(player.sprite.x, player.sprite.y);
            if (p.x < 0 || p.x >= MINIMAP_SIZE || p.y < 0 || p.y >= MINIMAP_SIZE) continue;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
            ctx.fill();
        }

        // Draw base marker
        if (this.clanBase) {
            const bp = toMini(this.clanBase.base_x, this.clanBase.base_y);

            if (bp.x >= 0 && bp.x < MINIMAP_SIZE && bp.y >= 0 && bp.y < MINIMAP_SIZE) {
                // Base is visible on minimap — draw a gold diamond
                ctx.fillStyle = '#ffd700';
                ctx.beginPath();
                ctx.moveTo(bp.x, bp.y - 4);
                ctx.lineTo(bp.x + 4, bp.y);
                ctx.lineTo(bp.x, bp.y + 4);
                ctx.lineTo(bp.x - 4, bp.y);
                ctx.closePath();
                ctx.fill();
            } else {
                // Base is off-screen — draw arrow at edge pointing to base
                const angle = Math.atan2(this.clanBase.base_y - myY, this.clanBase.base_x - myX);
                const edgeX = Math.max(4, Math.min(MINIMAP_SIZE - 4, half + Math.cos(angle) * (half - 6)));
                const edgeY = Math.max(4, Math.min(MINIMAP_SIZE - 4, half + Math.sin(angle) * (half - 6)));

                ctx.fillStyle = '#ffd700';
                ctx.beginPath();
                ctx.arc(edgeX, edgeY, 3, 0, Math.PI * 2);
                ctx.fill();

                // Arrow head pointing outward
                ctx.strokeStyle = '#ffd700';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(edgeX, edgeY);
                ctx.lineTo(edgeX + Math.cos(angle) * 5, edgeY + Math.sin(angle) * 5);
                ctx.stroke();
            }
        }

        // Draw my player (green dot, always center)
        ctx.fillStyle = '#4ade80';
        ctx.beginPath();
        ctx.arc(half, half, 3, 0, Math.PI * 2);
        ctx.fill();

        // Minimap border
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.lineWidth = 1;
        ctx.strokeRect(0, 0, MINIMAP_SIZE, MINIMAP_SIZE);
    }

    // ===== State updates from server =====

    updateState(state) {
        if (!this.scene) return;

        // Update players
        for (const pd of state.players) {
            if (this.players[pd.id]) {
                this.updatePlayer(pd);
            } else {
                this.createPlayer(pd);
            }
        }

        // Remove disconnected players
        const activeIds = new Set(state.players.map(p => p.id));
        for (const id of Object.keys(this.players)) {
            if (!activeIds.has(parseInt(id))) {
                this.removePlayer(parseInt(id));
            }
        }

        // Update zombies
        for (const zd of state.zombies) {
            if (this.zombies[zd.id]) {
                this.updateZombie(zd);
            } else {
                this.createZombie(zd);
            }
        }

        const activeZombieIds = new Set(state.zombies.map(z => z.id));
        for (const id of Object.keys(this.zombies)) {
            if (!activeZombieIds.has(parseInt(id))) {
                this.removeZombie(parseInt(id));
            }
        }

        // Update projectiles
        for (const pd of state.projectiles) {
            if (this.projectiles[pd.id]) {
                this.updateProjectile(pd);
            } else {
                this.createProjectile(pd);
            }
        }

        const activeProjIds = new Set(state.projectiles.map(p => p.id));
        for (const id of Object.keys(this.projectiles)) {
            if (!activeProjIds.has(parseInt(id))) {
                this.removeProjectile(parseInt(id));
            }
        }

        // Update turret rotations
        if (state.turrets && this._turretBarrels) {
            for (const td of state.turrets) {
                const barrel = this._turretBarrels[td.id];
                if (barrel) {
                    barrel.setRotation(td.aim_angle);
                }
            }
        }

        // Update gate open/close states with animation
        if (state.open_gates && this._gateSprites) {
            const openSet = new Set(state.open_gates);
            for (const [idStr, gate] of Object.entries(this._gateSprites)) {
                const id = parseInt(idStr);
                const shouldBeOpen = openSet.has(id);
                if (shouldBeOpen && !gate.isOpen) {
                    // Animate open (swing 90 degrees)
                    gate.isOpen = true;
                    this.scene.tweens.add({
                        targets: gate.sprite,
                        rotation: -Math.PI / 2,
                        duration: 300,
                        ease: 'Power2',
                    });
                } else if (!shouldBeOpen && gate.isOpen) {
                    // Animate close
                    gate.isOpen = false;
                    this.scene.tweens.add({
                        targets: gate.sprite,
                        rotation: 0,
                        duration: 300,
                        ease: 'Power2',
                    });
                }
            }
        }

        // Update ground drops
        if (state.ground_drops) {
            this._updateGroundDrops(state.ground_drops);
        }

        // Update inventory HUD
        if (state.inventory) {
            this.updateInventoryHUD(state.inventory);
        }

        // Update clothing/equipment HUD
        if (state.clothing) {
            this._updateClothingHUD(state.clothing);
        }

        // Process events
        if (state.events) {
            for (const event of state.events) {
                this.handleEvent(event);
            }
        }
    }

    handleEvent(event) {
        switch (event.type) {
            case 'world_zombie_killed':
                this.playSound('zombie_death', 0.4);
                if (event.killer_id === this.myId) {
                    // Show loot
                    if (event.loot) {
                        const parts = [];
                        for (const [res, amt] of Object.entries(event.loot)) {
                            parts.push(`+${amt} ${res}`);
                        }
                        if (parts.length > 0) {
                            this.showFloatingText(parts.join(' '), 0xffd700);
                        }
                    }
                }
                break;
            case 'world_player_died':
                if (event.player_id === this.myId) {
                    this.playSound('zombie_attack', 0.5);
                    this.showFloatingText('YOU DIED!', 0xff0000, true);
                }
                break;
            case 'clothing_broken':
                if (event.items) {
                    for (const item of event.items) {
                        if (window.showToast) window.showToast(`Сломалось: ${item.name}`, 'warning');
                    }
                }
                break;
        }
    }

    updateInventoryHUD(inv) {
        const el = (id, val) => {
            const e = document.getElementById(id);
            if (e) e.textContent = val;
        };
        el('world-metal', inv.metal);
        el('world-wood', inv.wood);
        el('world-food', inv.food);
        el('world-ammo', inv.ammo);
        el('world-meds', inv.meds);
    }

    // ===== Entity management =====

    createPlayer(data) {
        const isMe = data.id === this.myId;

        const sprite = this.scene.add.sprite(data.x, data.y, 'player_idle');
        sprite.setDisplaySize(48, 36);
        sprite.setDepth(10);
        sprite.play('player_idle_anim');
        if (!isMe) sprite.setTint(0x60a5fa);

        // Aim indicator
        const aimLine = this.scene.add.graphics().setDepth(9);

        const nameText = this.scene.add.text(data.x, data.y - 28, data.username || 'Player', {
            fontSize: '11px',
            fontFamily: 'Arial',
            color: isMe ? '#4ade80' : '#60a5fa',
            stroke: '#000',
            strokeThickness: 2,
        }).setOrigin(0.5).setDepth(11);

        const healthBar = this.scene.add.graphics().setDepth(11);
        this.drawHealthBar(healthBar, data.hp, data.max_hp, 40);

        this.players[data.id] = {
            sprite, nameText, healthBar, aimLine, data,
            targetX: data.x, targetY: data.y,
        };
    }

    updatePlayer(data) {
        const player = this.players[data.id];
        if (!player) return;

        const isMe = data.id === this.myId;
        const oldHp = player.data?.hp;

        if (isMe && oldHp !== undefined && data.hp < oldHp && !data.is_dead) {
            this.playSound('player_hurt', 0.4);
        }

        player.targetX = data.x;
        player.targetY = data.y;

        this.drawHealthBar(player.healthBar, data.hp, data.max_hp, 40);
        player.sprite.alpha = data.is_dead ? 0.3 : 1;
        player.nameText.alpha = data.is_dead ? 0.3 : 1;

        // Switch animation based on state
        if (!data.is_dead) {
            const isMoving = player.data && (Math.abs(data.x - player.data.x) > 0.5 || Math.abs(data.y - player.data.y) > 0.5);
            const isShooting = data.shooting;

            if (isShooting) {
                if (player.sprite.anims.currentAnim?.key !== 'player_shoot_anim') {
                    player.sprite.play('player_shoot_anim');
                }
            } else if (isMoving) {
                if (player.sprite.anims.currentAnim?.key !== 'player_move_anim') {
                    player.sprite.play('player_move_anim');
                }
            } else {
                if (player.sprite.anims.currentAnim?.key !== 'player_idle_anim') {
                    player.sprite.play('player_idle_anim');
                }
            }
        }

        // Rotate sprite to face aim direction (survivor sprite faces right at rotation=0)
        if (!data.is_dead && data.aim_angle !== undefined) {
            player.sprite.setRotation(data.aim_angle);
        }

        // Draw aim line
        player.aimLine.clear();
        if (!data.is_dead) {
            player.aimLine.lineStyle(2, isMe ? 0x4ade80 : 0x60a5fa, 0.3);
            player.aimLine.moveTo(data.x, data.y);
            player.aimLine.lineTo(
                data.x + Math.cos(data.aim_angle) * 50,
                data.y + Math.sin(data.aim_angle) * 50
            );
            player.aimLine.strokePath();
        }

        // Armor visual (colored ring around player)
        if (data.armor > 0 && !data.is_dead) {
            if (!player.armorRing) {
                player.armorRing = this.scene.add.circle(data.x, data.y, 22, 0x000000, 0);
                player.armorRing.setDepth(9);
            }
            const armorColor = data.armor >= 0.2 ? 0xfbbf24 : (data.armor >= 0.1 ? 0x4ade80 : 0x60a5fa);
            player.armorRing.setStrokeStyle(2, armorColor, 0.5);
            player.armorRing.setPosition(player.sprite.x, player.sprite.y);
            player.armorRing.setVisible(true);
        } else if (player.armorRing) {
            player.armorRing.setVisible(false);
        }

        player.data = data;

        // Update HUD for local player
        if (isMe) {
            document.getElementById('hud-health').style.width = `${(data.hp / data.max_hp) * 100}%`;
            document.getElementById('hud-health-text').textContent = `${data.hp}/${data.max_hp}`;
            const ammoEl = document.getElementById('world-weapon-ammo');
            if (ammoEl) {
                const reserve = data.ammo_reserve !== undefined ? data.ammo_reserve : '?';
                ammoEl.textContent = `${data.ammo}/${data.max_ammo} [${reserve}]`;
            }
        }
    }

    removePlayer(id) {
        const player = this.players[id];
        if (player) {
            player.sprite.destroy();
            player.nameText.destroy();
            player.healthBar.destroy();
            player.aimLine.destroy();
            if (player.armorRing) player.armorRing.destroy();
            delete this.players[id];
        }
    }

    createZombie(data) {
        if (!this.scene) return;

        const sizeMap = { 'normal': 48, 'fast': 44, 'tank': 64, 'boss': 80 };
        const displaySize = sizeMap[data.type] || 48;

        // Red ground indicator under zombie
        const indicator = this.scene.add.circle(data.x, data.y, displaySize * 0.7, 0xff0000, 0.15);
        indicator.setStrokeStyle(2, 0xff0000, 0.35);
        indicator.setDepth(4);

        let sprite;
        if (data.type === 'tank') {
            sprite = this.scene.add.image(data.x, data.y, 'zombie_tank_img');
        } else if (data.type === 'boss') {
            sprite = this.scene.add.image(data.x, data.y, 'zombie_boss_img');
        } else {
            sprite = this.scene.add.sprite(data.x, data.y, 'zombie_move');
            sprite.play('zombie_move_anim');
            if (data.type === 'fast') sprite.setTint(0xff6666);
        }
        sprite.setDisplaySize(displaySize, displaySize);
        sprite.setDepth(5);

        let healthBar = null;
        if (data.type === 'tank' || data.type === 'boss') {
            healthBar = this.scene.add.graphics().setDepth(6);
            this.drawHealthBar(healthBar, data.hp, data.max_hp, displaySize, 0xff4444);
            healthBar.setPosition(data.x - displaySize / 2, data.y - displaySize / 2 - 8);
        }

        this.zombies[data.id] = {
            sprite, indicator, healthBar, data,
            size: displaySize / 2,
            targetX: data.x, targetY: data.y,
        };
    }

    updateZombie(data) {
        const zombie = this.zombies[data.id];
        if (!zombie) {
            this.createZombie(data);
            return;
        }

        // Rotate zombie to face movement direction (sprite faces right at rotation=0)
        if (zombie.data) {
            const dx = data.x - zombie.data.x;
            const dy = data.y - zombie.data.y;
            const isMoving = Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5;
            if (isMoving) {
                zombie.sprite.setRotation(Math.atan2(dy, dx));
            }

            // Switch animation (only for animated zombies)
            if (zombie.sprite.anims) {
                if (isMoving) {
                    if (zombie.sprite.anims.currentAnim?.key !== 'zombie_move_anim') {
                        zombie.sprite.play('zombie_move_anim');
                    }
                } else {
                    if (zombie.sprite.anims.currentAnim?.key !== 'zombie_idle_anim') {
                        zombie.sprite.play('zombie_idle_anim');
                    }
                }
            }
        }

        zombie.targetX = data.x;
        zombie.targetY = data.y;

        if (zombie.healthBar) {
            const hbWidth = zombie.size * 2;
            this.drawHealthBar(zombie.healthBar, data.hp, data.max_hp, hbWidth, 0xff4444);
        }

        zombie.data = data;
    }

    removeZombie(id) {
        const zombie = this.zombies[id];
        if (zombie) {
            zombie.sprite.destroy();
            if (zombie.indicator) zombie.indicator.destroy();
            if (zombie.healthBar) zombie.healthBar.destroy();
            delete this.zombies[id];
        }
    }

    createProjectile(data) {
        const sprite = this.scene.add.circle(data.x, data.y, 3, 0xffd700);
        sprite.setDepth(8);

        if (data.owner_id === this.myId) {
            this.playSound('shoot_single', 0.2);
        }

        this.projectiles[data.id] = { sprite, data };
    }

    updateProjectile(data) {
        const proj = this.projectiles[data.id];
        if (!proj) return;
        proj.sprite.x = data.x;
        proj.sprite.y = data.y;
        proj.data = data;
    }

    removeProjectile(id) {
        const proj = this.projectiles[id];
        if (proj) {
            proj.sprite.destroy();
            delete this.projectiles[id];
        }
    }

    // ===== Building interaction =====

    _handleBuildingClick(worldX, worldY) {
        if (!this.clanBase) return;

        // Check if player is near the base
        const me = this.players[this.myId];
        if (!me) return;
        const dx = this.clanBase.base_x - me.sprite.x;
        const dy = this.clanBase.base_y - me.sprite.y;
        if (Math.sqrt(dx * dx + dy * dy) > 500) return;

        // If in move mode — place building at clicked grid position
        if (this._movingBuilding) {
            const baseX = this.clanBase.base_x - 8 * TILE_SIZE;
            const baseY = this.clanBase.base_y - 8 * TILE_SIZE;
            const gridX = Math.floor((worldX - baseX) / TILE_SIZE);
            const gridY = Math.floor((worldY - baseY) / TILE_SIZE);

            if (gridX < 0 || gridX >= 16 || gridY < 0 || gridY >= 16) {
                this.showFloatingText('За пределами базы', 0xff4444);
            } else {
                window.VELLA.ws.send({
                    type: 'move_building',
                    building_id: this._movingBuilding.id,
                    grid_x: gridX,
                    grid_y: gridY,
                });
            }
            this._movingBuilding = null;
            return;
        }

        // Find clicked building
        for (const key of Object.keys(this.chunks)) {
            const chunk = this.chunks[key];
            if (!chunk._buildings) continue;
            for (const b of chunk._buildings) {
                if (worldX >= b.x && worldX <= b.x + b.width &&
                    worldY >= b.y && worldY <= b.y + b.height) {
                    this._showBuildingPanel(b);
                    return;
                }
            }
        }
    }

    _showBuildingPanel(b) {
        this._selectedBuilding = b;
        const panel = document.getElementById('building-panel');
        const title = document.getElementById('bp-title');
        const info = document.getElementById('bp-info');
        const collectRow = document.getElementById('bp-collect-row');
        const collectAmount = document.getElementById('bp-collect-amount');

        title.textContent = b.type_name || b.type_code;
        info.textContent = `HP: ${Math.round(b.hp)}/${b.max_hp}`;

        // Show collect button for production buildings
        if (b.category === 'production' && b.is_built) {
            collectRow.classList.remove('hidden');
            collectAmount.textContent = '...';
        } else {
            collectRow.classList.add('hidden');
        }

        panel.classList.remove('hidden');
    }

    _setupBuildingPanel() {
        const close = document.getElementById('bp-close');
        const collect = document.getElementById('bp-collect');
        const move = document.getElementById('bp-move');
        const demolish = document.getElementById('bp-demolish');

        if (close) close.addEventListener('click', () => {
            document.getElementById('building-panel').classList.add('hidden');
            this._selectedBuilding = null;
        });

        if (collect) collect.addEventListener('click', () => {
            if (!this._selectedBuilding) return;
            window.VELLA.ws.send({
                type: 'collect_building',
                building_id: this._selectedBuilding.id,
            });
            document.getElementById('building-panel').classList.add('hidden');
        });

        if (demolish) demolish.addEventListener('click', () => {
            if (!this._selectedBuilding) return;
            if (confirm(`Снести ${this._selectedBuilding.type_name || this._selectedBuilding.type_code}?`)) {
                window.VELLA.ws.send({
                    type: 'demolish_building',
                    building_id: this._selectedBuilding.id,
                });
                document.getElementById('building-panel').classList.add('hidden');
                this._selectedBuilding = null;
            }
        });

        if (move) move.addEventListener('click', () => {
            if (!this._selectedBuilding || !this.clanBase) return;
            document.getElementById('building-panel').classList.add('hidden');
            this._startBuildingMove(this._selectedBuilding);
        });

        // Listen for server responses
        window.VELLA.ws.on('building_collected', (data) => {
            if (data.success) {
                this.showFloatingText(`+${data.amount} ${data.resource}`, 0x4ade80);
            } else {
                this.showFloatingText(data.reason || 'Нечего собирать', 0xff4444);
            }
        });

        window.VELLA.ws.on('building_demolished', (data) => {
            if (data.success) {
                this.showFloatingText('Здание снесено', 0xfbbf24);
            }
        });

        window.VELLA.ws.on('building_moved', (data) => {
            if (data.success) {
                this.showFloatingText('Здание перемещено', 0x60a5fa);
            } else {
                this.showFloatingText(data.reason || 'Ошибка', 0xff4444);
            }
            this._movingBuilding = null;
        });
    }

    _startBuildingMove(b) {
        this._movingBuilding = b;
        this.showFloatingText('Нажмите на новое место на базе', 0x60a5fa);
    }

    // ===== Ground Drops =====

    _updateGroundDrops(drops) {
        const RARITY_COLORS = { common: 0xaaaaaa, uncommon: 0x4ade80, rare: 0xfbbf24 };
        const activeIds = new Set(drops.map(d => d.id));

        // Remove old drops
        for (const id of Object.keys(this.groundDrops)) {
            if (!activeIds.has(parseInt(id))) {
                const drop = this.groundDrops[id];
                drop.sprite.destroy();
                if (drop.label) drop.label.destroy();
                if (drop.glow) drop.glow.destroy();
                delete this.groundDrops[id];
            }
        }

        // Create or update drops
        const t = Date.now() / 1000;
        for (const d of drops) {
            if (this.groundDrops[d.id]) {
                // Update float animation
                const drop = this.groundDrops[d.id];
                const floatY = Math.sin(t * 3 + d.id) * 3;
                drop.sprite.y = d.y - 4 + floatY;
                if (drop.label) drop.label.y = d.y - 14 + floatY;
                if (drop.glow) {
                    drop.glow.y = d.y + floatY;
                    drop.glow.setAlpha(0.15 + Math.sin(t * 2) * 0.1);
                }
            } else {
                // Create new drop
                const color = RARITY_COLORS[d.rarity] || 0xaaaaaa;
                const glow = this.scene.add.circle(d.x, d.y, 12, color, 0.2);
                glow.setDepth(3);
                const sprite = this.scene.add.rectangle(d.x, d.y - 4, 10, 10, color, 0.9);
                sprite.setStrokeStyle(1, 0xffffff, 0.7);
                sprite.setDepth(4);
                const label = this.scene.add.text(d.x, d.y - 14, d.name, {
                    fontSize: '8px', fontFamily: 'Arial',
                    color: `#${color.toString(16).padStart(6, '0')}`,
                    stroke: '#000', strokeThickness: 2,
                }).setOrigin(0.5).setDepth(4);
                this.groundDrops[d.id] = { sprite, label, glow };
            }
        }
    }

    // ===== Clothing HUD =====

    _updateClothingHUD(clothing) {
        const eqHud = document.getElementById('equipment-hud');
        if (!eqHud) return;

        let totalArmor = 0;
        let hasAny = false;

        for (const slot of ['head', 'body', 'legs']) {
            const el = eqHud.querySelector(`[data-slot="${slot}"]`);
            if (!el) continue;
            const item = clothing[slot];
            if (item) {
                hasAny = true;
                totalArmor += this._getItemArmor(item.code);
                const pct = Math.round((item.durability / item.max_durability) * 100);
                const durColor = pct > 50 ? '#4ade80' : (pct > 25 ? '#fbbf24' : '#ef4444');
                el.innerHTML = `<span class="eq-name">${item.name}</span><span class="eq-dur" style="color:${durColor}">${pct}%</span>`;
            } else {
                el.innerHTML = '--';
            }
        }

        const armorEl = eqHud.querySelector('.armor-value');
        if (armorEl) armorEl.textContent = `${Math.round(totalArmor * 100)}%`;

        eqHud.style.display = hasAny ? '' : 'none';
    }

    _getItemArmor(code) {
        const ARMOR_MAP = {
            cap: 0.03, helmet: 0.06, riot_helmet: 0.10,
            tshirt: 0.04, jacket: 0.08, kevlar: 0.15,
            jeans: 0.03, cargo: 0.06, military_pants: 0.10,
        };
        return ARMOR_MAP[code] || 0;
    }

    // ===== Utils =====

    drawHealthBar(graphics, hp, maxHp, width, color = 0x4ade80) {
        graphics.clear();
        const height = 4;
        const percent = hp / maxHp;
        graphics.fillStyle(0x000000, 0.5);
        graphics.fillRect(0, 0, width, height);
        const healthColor = percent > 0.5 ? color : (percent > 0.25 ? 0xfbbf24 : 0xef4444);
        graphics.fillStyle(healthColor, 1);
        graphics.fillRect(0, 0, width * percent, height);
    }

    showFloatingText(text, color, large = false) {
        if (!this.scene) return;
        const me = this.players[this.myId];
        const x = me ? me.sprite.x : 0;
        const y = me ? me.sprite.y - 50 : 0;

        const textObj = this.scene.add.text(x, y, text, {
            fontSize: large ? '28px' : '14px',
            fontFamily: 'Arial',
            color: `#${color.toString(16).padStart(6, '0')}`,
            stroke: '#000',
            strokeThickness: large ? 4 : 2,
        }).setOrigin(0.5).setDepth(100);

        this.scene.tweens.add({
            targets: textObj,
            y: y - 40,
            alpha: 0,
            duration: 1500,
            onComplete: () => textObj.destroy(),
        });
    }

    playSound(key, volume = 0.5) {
        if (!this.scene?.sound) return;
        try {
            this.scene.sound.play(key, { volume });
        } catch (e) {}
    }

    destroy() {
        // Remove keyboard listeners
        window.removeEventListener('keydown', this._onKeyDown);
        window.removeEventListener('keyup', this._onKeyUp);

        if (this.joystick) {
            this.joystick.destroy();
            this.joystick = null;
        }
        // Clear base marker
        if (this.baseMarker) {
            if (this.baseMarker.platform) this.baseMarker.platform.destroy();
            if (this.baseMarker.flag) this.baseMarker.flag.destroy();
            if (this.baseMarker.nameText) this.baseMarker.nameText.destroy();
            if (this.baseMarker.safeZone) this.baseMarker.safeZone.destroy();
            if (this.baseMarker.memberSprites) {
                for (const s of this.baseMarker.memberSprites) s.destroy();
            }
            this.baseMarker = null;
        }
        // Clear all chunks
        for (const key of Object.keys(this.chunks)) {
            const chunk = this.chunks[key];
            chunk.sprite.destroy();
            if (this.scene) {
                this.scene.textures.remove(chunk.textureKey);
            }
            for (const s of chunk.resourceSprites) s.destroy();
            if (chunk.buildingSprites) {
                for (const s of chunk.buildingSprites) s.destroy();
            }
        }
        this.chunks = {};
        this.players = {};
        this.zombies = {};
        this.projectiles = {};
        // Clean up ground drops
        for (const drop of Object.values(this.groundDrops)) {
            drop.sprite.destroy();
            if (drop.label) drop.label.destroy();
            if (drop.glow) drop.glow.destroy();
        }
        this.groundDrops = {};

        // Clear minimap
        if (this.minimapCtx) {
            this.minimapCtx.clearRect(0, 0, MINIMAP_SIZE, MINIMAP_SIZE);
        }

        if (this.game) {
            this.game.destroy(true);
            this.game = null;
        }
    }
}
