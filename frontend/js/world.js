/**
 * VELLA World Game Manager
 * Manages Phaser game instance for open world mode
 */

import { DualJoystick } from './ui/Joystick.js';

// Tile types (match backend)
const TILE_GRASS = 0;
const TILE_DIRT = 1;
const TILE_FOREST = 2;
const TILE_ROCK = 3;
const TILE_WATER = 4;
const TILE_ROAD = 5;

const TILE_SIZE = 32;
const TILES_PER_CHUNK = 32;
const CHUNK_SIZE = TILE_SIZE * TILES_PER_CHUNK; // 1024

const TILE_COLORS = {
    [TILE_GRASS]: 0x4a7c59,
    [TILE_DIRT]: 0x8b7355,
    [TILE_FOREST]: 0x2d5a1e,
    [TILE_ROCK]: 0x6b6b6b,
    [TILE_WATER]: 0x2a5fa8,
    [TILE_ROAD]: 0x9e9e7a,
};

export class WorldGameManager {
    constructor() {
        this.myId = window.VELLA.player?.id;
        this.game = null;
        this.scene = null;
        this.sceneReady = false;
        this.joystick = null;

        // Game state from server
        this.players = {};
        this.zombies = {};
        this.projectiles = {};

        // Chunks
        this.chunks = {}; // key: "cx,cy" -> { graphics, resources }
        this.pendingChunks = []; // chunks received before scene was ready

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
        // Load sprites
        scene.load.image('zombie_normal', '/assets/sprites/zombie_normal.png');
        scene.load.image('zombie_fast', '/assets/sprites/zombie_fast.png');
        scene.load.image('zombie_tank', '/assets/sprites/zombie_tank.png');
        scene.load.image('zombie_boss', '/assets/sprites/zombie_boss.png');
        scene.load.image('player_sprite', '/assets/sprites/player.png');
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
                if (zombie.healthBar) {
                    const hbWidth = zombie.size * 2;
                    zombie.healthBar.x = zombie.sprite.x - hbWidth / 2;
                    zombie.healthBar.y = zombie.sprite.y - zombie.size - 8;
                }
            }
        }
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
        const aimX = hasKeyboard ? Math.cos(this.aimAngle) : joy.aimX;
        const aimY = hasKeyboard ? Math.sin(this.aimAngle) : joy.aimY;
        const shooting = kbShooting || joy.shooting;

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

        // Draw terrain tiles
        const graphics = this.scene.add.graphics();
        graphics.setDepth(0);

        const terrain = data.terrain;
        for (let ty = 0; ty < TILES_PER_CHUNK; ty++) {
            for (let tx = 0; tx < TILES_PER_CHUNK; tx++) {
                const tileType = terrain[ty][tx];
                const color = TILE_COLORS[tileType] || TILE_COLORS[TILE_GRASS];
                graphics.fillStyle(color, 1);
                graphics.fillRect(
                    offsetX + tx * TILE_SIZE,
                    offsetY + ty * TILE_SIZE,
                    TILE_SIZE, TILE_SIZE
                );
            }
        }

        // Draw grid lines (subtle)
        graphics.lineStyle(1, 0x000000, 0.1);
        for (let i = 0; i <= TILES_PER_CHUNK; i++) {
            graphics.moveTo(offsetX + i * TILE_SIZE, offsetY);
            graphics.lineTo(offsetX + i * TILE_SIZE, offsetY + CHUNK_SIZE);
            graphics.moveTo(offsetX, offsetY + i * TILE_SIZE);
            graphics.lineTo(offsetX + CHUNK_SIZE, offsetY + i * TILE_SIZE);
        }
        graphics.strokePath();

        // Draw resources
        const resourceSprites = [];
        if (data.resources) {
            for (const res of data.resources) {
                const color = res.type === 'metal' ? 0xc0c0c0 : 0x8b4513;
                const circle = this.scene.add.circle(res.x, res.y, 10, color, 0.8);
                circle.setStrokeStyle(2, 0xffffff, 0.5);
                circle.setDepth(2);
                circle.setInteractive();
                circle.resData = res;
                resourceSprites.push(circle);
            }
        }

        this.chunks[key] = { graphics, resourceSprites };
    }

    unloadChunk(chunk_x, chunk_y) {
        const key = `${chunk_x},${chunk_y}`;
        const chunk = this.chunks[key];
        if (!chunk) return;

        chunk.graphics.destroy();
        for (const sprite of chunk.resourceSprites) {
            sprite.destroy();
        }
        delete this.chunks[key];
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

        // Update inventory HUD
        if (state.inventory) {
            this.updateInventoryHUD(state.inventory);
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

        const sprite = this.scene.add.image(data.x, data.y, 'player_sprite');
        sprite.setDisplaySize(36, 36);
        sprite.setDepth(10);
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

        // Rotate sprite to face aim direction
        // SVG faces up (angle=0 is up), Phaser rotation 0 is right
        // aim_angle: 0=right, PI/2=down, -PI/2=up
        if (!data.is_dead && data.aim_angle !== undefined) {
            player.sprite.setRotation(data.aim_angle + Math.PI / 2);
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

        player.data = data;

        // Update HUD for local player
        if (isMe) {
            document.getElementById('hud-health').style.width = `${(data.hp / data.max_hp) * 100}%`;
            document.getElementById('hud-health-text').textContent = `${data.hp}/${data.max_hp}`;
            const ammoEl = document.getElementById('world-weapon-ammo');
            if (ammoEl) ammoEl.textContent = `${data.ammo}/${data.max_ammo}`;
        }
    }

    removePlayer(id) {
        const player = this.players[id];
        if (player) {
            player.sprite.destroy();
            player.nameText.destroy();
            player.healthBar.destroy();
            player.aimLine.destroy();
            delete this.players[id];
        }
    }

    createZombie(data) {
        if (!this.scene) return;

        const zombieConfig = {
            'normal': { texture: 'zombie_normal', displaySize: 32 },
            'fast': { texture: 'zombie_fast', displaySize: 28 },
            'tank': { texture: 'zombie_tank', displaySize: 44 },
            'boss': { texture: 'zombie_boss', displaySize: 60 },
        };
        const config = zombieConfig[data.type] || zombieConfig.normal;

        const sprite = this.scene.add.image(data.x, data.y, config.texture);
        sprite.setDisplaySize(config.displaySize, config.displaySize);
        sprite.setDepth(5);

        let healthBar = null;
        const hbWidth = config.displaySize;
        if (data.type === 'tank' || data.type === 'boss') {
            healthBar = this.scene.add.graphics().setDepth(6);
            this.drawHealthBar(healthBar, data.hp, data.max_hp, hbWidth, 0xff4444);
            healthBar.setPosition(data.x - hbWidth / 2, data.y - config.displaySize / 2 - 8);
        }

        this.zombies[data.id] = {
            sprite, healthBar, data,
            size: config.displaySize / 2,
            targetX: data.x, targetY: data.y,
        };
    }

    updateZombie(data) {
        const zombie = this.zombies[data.id];
        if (!zombie) {
            this.createZombie(data);
            return;
        }

        // Rotate zombie to face movement direction
        if (zombie.data) {
            const dx = data.x - zombie.data.x;
            const dy = data.y - zombie.data.y;
            if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
                zombie.sprite.setRotation(Math.atan2(dy, dx) + Math.PI / 2);
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
        // Clear all chunks
        for (const key of Object.keys(this.chunks)) {
            const chunk = this.chunks[key];
            chunk.graphics.destroy();
            for (const s of chunk.resourceSprites) s.destroy();
        }
        this.chunks = {};
        this.players = {};
        this.zombies = {};
        this.projectiles = {};

        if (this.game) {
            this.game.destroy(true);
            this.game = null;
        }
    }
}
