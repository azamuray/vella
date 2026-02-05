/**
 * VELLA Game Manager
 * Manages Phaser game instance and game state
 */

import { DualJoystick } from './ui/Joystick.js';

export class GameManager {
    constructor(initialData) {
        this.initialData = initialData;
        this.myId = window.VELLA.player?.id;
        this.game = null;
        this.scene = null;
        this.joystick = null;

        // Game state
        this.players = {};
        this.zombies = {};
        this.projectiles = {};
        this.currentWave = 0;
        this.kills = 0;
        this.coins = 0;

        // Input state
        this.inputSeq = 0;

        // Asset loading state
        this.assetsLoaded = false;
    }

    start() {
        const config = {
            type: Phaser.AUTO,
            parent: 'game-container',
            width: window.innerWidth,
            height: window.innerHeight,
            backgroundColor: '#1a1a2e',
            physics: {
                default: 'arcade',
                arcade: {
                    debug: false
                }
            },
            scene: {
                preload: this.preload.bind(this),
                create: this.create.bind(this),
                update: this.update.bind(this)
            },
            scale: {
                mode: Phaser.Scale.RESIZE,
                autoCenter: Phaser.Scale.CENTER_BOTH
            }
        };

        this.game = new Phaser.Game(config);
    }

    preload() {
        const scene = this.game.scene.scenes[0];

        // Load SVG sprites
        scene.load.svg('player', '/assets/sprites/player.svg', { width: 48, height: 48 });
        scene.load.svg('zombie_normal', '/assets/sprites/zombie_normal.svg', { width: 40, height: 40 });
        scene.load.svg('zombie_fast', '/assets/sprites/zombie_fast.svg', { width: 32, height: 32 });
        scene.load.svg('zombie_tank', '/assets/sprites/zombie_tank.svg', { width: 56, height: 56 });
        scene.load.svg('zombie_boss', '/assets/sprites/zombie_boss.svg', { width: 72, height: 72 });
        scene.load.svg('bullet', '/assets/sprites/bullet.svg', { width: 16, height: 8 });

        // Fallback: create textures if SVG loading fails
        scene.load.on('loaderror', (file) => {
            console.warn('Failed to load:', file.key, '- creating fallback');
            this.createFallbackTexture(scene, file.key);
        });

        scene.load.on('complete', () => {
            this.assetsLoaded = true;
            // List loaded textures for debugging
            const textures = ['player', 'zombie_normal', 'zombie_fast', 'zombie_tank', 'zombie_boss', 'bullet'];
            for (const key of textures) {
                console.log(`Texture ${key}: ${scene.textures.exists(key) ? 'loaded' : 'MISSING'}`);
            }
        });
    }

    createFallbackTexture(scene, key) {
        const graphics = scene.add.graphics();

        const configs = {
            'player': { color: 0x4ade80, size: 24 },
            'zombie_normal': { color: 0x5a7247, size: 20 },
            'zombie_fast': { color: 0x8a7a5a, size: 16 },
            'zombie_tank': { color: 0x4a5a3a, size: 28 },
            'zombie_boss': { color: 0x3a4a2a, size: 36 },
            'bullet': { color: 0xffd700, size: 4 }
        };

        const config = configs[key] || { color: 0xffffff, size: 16 };

        graphics.fillStyle(config.color);
        graphics.fillCircle(config.size, config.size, config.size);
        graphics.generateTexture(key, config.size * 2, config.size * 2);
        graphics.destroy();
    }

    create() {
        this.scene = this.game.scene.scenes[0];

        // Create sprite groups
        this.playerSprites = this.scene.add.group();
        this.zombieSprites = this.scene.add.group();
        this.projectileSprites = this.scene.add.group();

        // Create arena background
        this.createArena();

        // Setup joysticks
        this.joystick = new DualJoystick();

        // Input sending loop
        this.scene.time.addEvent({
            delay: 50, // 20 times per second
            callback: this.sendInput,
            callbackScope: this,
            loop: true
        });

        // Initialize from initial data
        if (this.initialData?.players) {
            for (const playerData of this.initialData.players) {
                this.createPlayer(playerData);
            }
        }
    }

    createArena() {
        const width = this.scene.scale.width;
        const height = this.scene.scale.height;

        // Grid lines for visual reference
        const graphics = this.scene.add.graphics();
        graphics.lineStyle(1, 0x2a2a4e, 0.3);

        // Vertical lines
        for (let x = 0; x < width; x += 100) {
            graphics.moveTo(x, 0);
            graphics.lineTo(x, height);
        }

        // Horizontal lines
        for (let y = 0; y < height; y += 100) {
            graphics.moveTo(0, y);
            graphics.lineTo(width, y);
        }

        graphics.strokePath();
        graphics.setDepth(0);

        // Safe zone indicator at bottom
        const safeZone = this.scene.add.graphics();
        safeZone.fillStyle(0x2a4a3a, 0.2);
        safeZone.fillRect(0, height - 150, width, 150);
        safeZone.setDepth(1);
    }

    update(time, delta) {
        // Smooth sprite movements
        for (const player of Object.values(this.players)) {
            if (player.targetX !== undefined) {
                player.sprite.x = Phaser.Math.Linear(player.sprite.x, player.targetX, 0.2);
                player.sprite.y = Phaser.Math.Linear(player.sprite.y, player.targetY, 0.2);
                player.nameText.x = player.sprite.x;
                player.nameText.y = player.sprite.y - 35;
                player.healthBar.x = player.sprite.x - 20;
                player.healthBar.y = player.sprite.y - 28;
            }
        }

        for (const zombie of Object.values(this.zombies)) {
            if (zombie.targetX !== undefined) {
                zombie.sprite.x = Phaser.Math.Linear(zombie.sprite.x, zombie.targetX, 0.15);
                zombie.sprite.y = Phaser.Math.Linear(zombie.sprite.y, zombie.targetY, 0.15);
                if (zombie.healthBar) {
                    zombie.healthBar.x = zombie.sprite.x - 15;
                    zombie.healthBar.y = zombie.sprite.y - zombie.sprite.height / 2 - 8;
                }
            }
        }
    }

    sendInput() {
        if (!window.VELLA.ws?.isConnected) return;

        const input = this.joystick.getInput();

        window.VELLA.ws.send({
            type: 'input',
            seq: ++this.inputSeq,
            move_x: input.moveX,
            move_y: input.moveY,
            aim_x: input.aimX,
            aim_y: input.aimY,
            shooting: input.shooting,
            reload: false
        });
    }

    updateState(state) {
        if (!this.scene) {
            console.warn('Scene not ready, skipping state update');
            return;
        }

        this.currentWave = state.wave;

        // Update players
        for (const playerData of state.players) {
            if (this.players[playerData.id]) {
                this.updatePlayer(playerData);
            } else {
                this.createPlayer(playerData);
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
        if (state.zombies.length > 0 && Object.keys(this.zombies).length === 0) {
            console.log(`Received ${state.zombies.length} zombies from server`);
        }
        for (const zombieData of state.zombies) {
            if (this.zombies[zombieData.id]) {
                this.updateZombie(zombieData);
            } else {
                this.createZombie(zombieData);
            }
        }

        // Remove dead zombies
        const activeZombieIds = new Set(state.zombies.map(z => z.id));
        for (const id of Object.keys(this.zombies)) {
            if (!activeZombieIds.has(parseInt(id))) {
                this.removeZombie(parseInt(id));
            }
        }

        // Update projectiles
        for (const projData of state.projectiles) {
            if (this.projectiles[projData.id]) {
                this.updateProjectile(projData);
            } else {
                this.createProjectile(projData);
            }
        }

        // Remove old projectiles
        const activeProjIds = new Set(state.projectiles.map(p => p.id));
        for (const id of Object.keys(this.projectiles)) {
            if (!activeProjIds.has(parseInt(id))) {
                this.removeProjectile(parseInt(id));
            }
        }

        // Update HUD
        document.getElementById('hud-wave').textContent = state.wave;
        document.getElementById('hud-zombies').textContent = state.zombies_remaining;
    }

    createPlayer(data) {
        const isMe = data.id === this.myId;

        // Scale positions to screen
        const x = this.scaleX(data.x);
        const y = this.scaleY(data.y);

        const sprite = this.scene.add.sprite(x, y, 'player');
        sprite.setScale(isMe ? 1.0 : 0.9);
        sprite.setDepth(10);

        // Tint other players blue
        if (!isMe) {
            sprite.setTint(0x60a5fa);
        }

        // Name label
        const nameText = this.scene.add.text(x, y - 35, data.username || 'Player', {
            fontSize: '11px',
            fontFamily: 'Arial',
            color: isMe ? '#4ade80' : '#60a5fa',
            stroke: '#000',
            strokeThickness: 2
        }).setOrigin(0.5).setDepth(11);

        // Health bar
        const healthBar = this.scene.add.graphics().setDepth(11);
        this.drawHealthBar(healthBar, data.hp, data.max_hp, 40);

        this.players[data.id] = {
            sprite,
            nameText,
            healthBar,
            data,
            targetX: x,
            targetY: y
        };
        this.playerSprites.add(sprite);
    }

    updatePlayer(data) {
        const player = this.players[data.id];
        if (!player) return;

        // Set target for smooth interpolation
        player.targetX = this.scaleX(data.x);
        player.targetY = this.scaleY(data.y);

        // Update rotation based on aim
        player.sprite.rotation = data.aim_angle + Math.PI / 2; // Adjust for sprite orientation

        // Update health bar
        this.drawHealthBar(player.healthBar, data.hp, data.max_hp, 40);

        // Dead state
        player.sprite.alpha = data.is_dead ? 0.3 : 1;
        player.nameText.alpha = data.is_dead ? 0.3 : 1;

        // Update data
        player.data = data;

        // Update HUD for local player
        if (data.id === this.myId) {
            document.getElementById('hud-health').style.width = `${(data.hp / data.max_hp) * 100}%`;
            document.getElementById('hud-health-text').textContent = `${data.hp}/${data.max_hp}`;
            document.getElementById('hud-ammo').textContent = data.ammo;
            document.getElementById('hud-max-ammo').textContent = data.max_ammo;
            document.getElementById('hud-weapon-name').textContent = this.getWeaponName(data.weapon);

            // Reload bar
            const reloadBar = document.getElementById('reload-bar');
            const reloadFill = document.getElementById('reload-fill');
            if (data.reloading) {
                reloadBar.classList.remove('hidden');
                reloadFill.style.width = `${data.reload_progress * 100}%`;
            } else {
                reloadBar.classList.add('hidden');
            }
        }
    }

    removePlayer(id) {
        const player = this.players[id];
        if (player) {
            player.sprite.destroy();
            player.nameText.destroy();
            player.healthBar.destroy();
            delete this.players[id];
        }
    }

    createZombie(data) {
        if (!this.scene) {
            console.warn('Scene not ready, cannot create zombie');
            return;
        }

        const textureKey = `zombie_${data.type}`;
        const x = this.scaleX(data.x);
        const y = this.scaleY(data.y);

        const textureExists = this.scene.textures.exists(textureKey);
        console.log(`Creating zombie ${data.id} type=${data.type} at screen(${x.toFixed(0)}, ${y.toFixed(0)}) game(${data.x}, ${data.y}) texture=${textureKey} exists=${textureExists}`);

        // Check if texture exists, use fallback if not
        let sprite;
        if (this.scene.textures.exists(textureKey)) {
            sprite = this.scene.add.sprite(x, y, textureKey);
        } else {
            // Create fallback circle
            const colors = {
                'normal': 0x5a7247,
                'fast': 0x8a7a5a,
                'tank': 0x4a5a3a,
                'boss': 0x7c2a2a
            };
            const sizes = {
                'normal': 20,
                'fast': 16,
                'tank': 28,
                'boss': 36
            };
            const size = sizes[data.type] || 20;
            sprite = this.scene.add.circle(x, y, size, colors[data.type] || 0x5a7247);
        }
        sprite.setDepth(5);

        // Health bar for tanks and bosses
        let healthBar = null;
        if (data.type === 'tank' || data.type === 'boss') {
            healthBar = this.scene.add.graphics().setDepth(6);
            this.drawHealthBar(healthBar, data.hp, data.max_hp, 30, 0xff4444);
        }

        this.zombies[data.id] = {
            sprite,
            healthBar,
            data,
            targetX: x,
            targetY: y
        };
        this.zombieSprites.add(sprite);
    }

    updateZombie(data) {
        const zombie = this.zombies[data.id];
        if (!zombie) {
            console.warn(`Zombie ${data.id} not found for update, creating...`);
            this.createZombie(data);
            return;
        }

        // Set target for smooth interpolation
        zombie.targetX = this.scaleX(data.x);
        zombie.targetY = this.scaleY(data.y);

        // Update health bar
        if (zombie.healthBar) {
            this.drawHealthBar(zombie.healthBar, data.hp, data.max_hp, 30, 0xff4444);
        }

        zombie.data = data;
    }

    removeZombie(id) {
        const zombie = this.zombies[id];
        if (zombie) {
            // Death effect
            this.createDeathEffect(zombie.sprite.x, zombie.sprite.y);

            zombie.sprite.destroy();
            if (zombie.healthBar) zombie.healthBar.destroy();
            delete this.zombies[id];
        }
    }

    createDeathEffect(x, y) {
        // Blood splatter particles
        const particles = this.scene.add.particles(x, y, 'bullet', {
            speed: { min: 50, max: 150 },
            scale: { start: 1, end: 0 },
            lifespan: 300,
            quantity: 8,
            tint: 0x8b0000,
            blendMode: 'ADD'
        });

        this.scene.time.delayedCall(500, () => {
            particles.destroy();
        });
    }

    createProjectile(data) {
        const x = this.scaleX(data.x);
        const y = this.scaleY(data.y);

        const sprite = this.scene.add.sprite(x, y, 'bullet');
        sprite.setRotation(data.angle);
        sprite.setDepth(8);
        sprite.setScale(1.5);

        // Muzzle flash effect
        const flash = this.scene.add.circle(x, y, 8, 0xffff00, 0.8);
        flash.setDepth(9);
        this.scene.tweens.add({
            targets: flash,
            alpha: 0,
            scale: 2,
            duration: 100,
            onComplete: () => flash.destroy()
        });

        this.projectiles[data.id] = { sprite, data };
        this.projectileSprites.add(sprite);
    }

    updateProjectile(data) {
        const proj = this.projectiles[data.id];
        if (!proj) return;

        proj.sprite.x = this.scaleX(data.x);
        proj.sprite.y = this.scaleY(data.y);
        proj.sprite.rotation = data.angle;
        proj.data = data;
    }

    removeProjectile(id) {
        const proj = this.projectiles[id];
        if (proj) {
            proj.sprite.destroy();
            delete this.projectiles[id];
        }
    }

    onZombieKilled(data) {
        if (data.killer_id === this.myId) {
            this.kills++;
            this.coins += data.coins;
            document.getElementById('hud-kills').textContent = this.kills;
            document.getElementById('hud-coins').textContent = this.coins;

            // Show floating coin text
            this.showFloatingText(`+${data.coins}`, 0xffd700);
        }
    }

    onPlayerDied(data) {
        if (data.player_id === this.myId) {
            this.showFloatingText('YOU DIED!', 0xff0000, true);
        }
    }

    showFloatingText(text, color, large = false) {
        const x = this.scene.scale.width / 2;
        const y = this.scene.scale.height / 2;

        const textObj = this.scene.add.text(x, y, text, {
            fontSize: large ? '32px' : '18px',
            fontFamily: 'Arial',
            color: `#${color.toString(16).padStart(6, '0')}`,
            stroke: '#000',
            strokeThickness: large ? 4 : 2
        }).setOrigin(0.5).setDepth(100);

        this.scene.tweens.add({
            targets: textObj,
            y: y - 50,
            alpha: 0,
            duration: 1500,
            onComplete: () => textObj.destroy()
        });
    }

    drawHealthBar(graphics, hp, maxHp, width, color = 0x4ade80) {
        graphics.clear();

        const height = 4;
        const percent = hp / maxHp;

        // Background
        graphics.fillStyle(0x000000, 0.5);
        graphics.fillRect(0, 0, width, height);

        // Health
        const healthColor = percent > 0.5 ? color : (percent > 0.25 ? 0xfbbf24 : 0xef4444);
        graphics.fillStyle(healthColor, 1);
        graphics.fillRect(0, 0, width * percent, height);
    }

    getWeaponName(code) {
        const names = {
            'glock_17': 'Glock 17',
            'beretta_m9': 'Beretta M9',
            'desert_eagle': 'Desert Eagle',
            'remington_870': 'Remington 870',
            'benelli_m4': 'Benelli M4',
            'ak_47': 'AK-47',
            'm4a1': 'M4A1',
            'scar_h': 'SCAR-H',
            'remington_700': 'Remington 700',
            'barrett_m82': 'Barrett M82'
        };
        return names[code] || code;
    }

    // Scale game coordinates to screen
    scaleX(x) {
        return (x / 1920) * this.scene.scale.width;
    }

    scaleY(y) {
        return (y / 1080) * this.scene.scale.height;
    }

    destroy() {
        if (this.joystick) {
            this.joystick.destroy();
            this.joystick = null;
        }

        if (this.game) {
            this.game.destroy(true);
            this.game = null;
        }
    }
}
