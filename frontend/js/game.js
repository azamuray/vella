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
        this.coins = window.VELLA.player?.coins || 0;  // Start with saved coins

        // Input state
        this.inputSeq = 0;

        // Asset loading state
        this.assetsLoaded = false;
    }

    start() {
        // Leave 200px at bottom for joystick controls
        const joystickHeight = 200;
        const gameHeight = window.innerHeight - joystickHeight;

        const config = {
            type: Phaser.AUTO,
            parent: 'game-container',
            width: window.innerWidth,
            height: gameHeight,
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
                mode: Phaser.Scale.FIT,
                autoCenter: Phaser.Scale.CENTER_HORIZONTALLY
            }
        };

        this.game = new Phaser.Game(config);
    }

    preload() {
        const scene = this.game.scene.scenes[0];

        // Load animated spritesheets (same as open world)
        scene.load.spritesheet('player_idle', '/assets/sprites/player_idle.png', { frameWidth: 219, frameHeight: 165 });
        scene.load.spritesheet('player_move', '/assets/sprites/player_move.png', { frameWidth: 219, frameHeight: 165 });
        scene.load.spritesheet('player_shoot', '/assets/sprites/player_shoot.png', { frameWidth: 219, frameHeight: 165 });
        scene.load.spritesheet('zombie_idle', '/assets/sprites/zombie_anim_idle.png', { frameWidth: 269, frameHeight: 260 });
        scene.load.spritesheet('zombie_move', '/assets/sprites/zombie_anim_move.png', { frameWidth: 269, frameHeight: 260 });
        scene.load.spritesheet('zombie_attack', '/assets/sprites/zombie_anim_attack.png', { frameWidth: 269, frameHeight: 260 });
        scene.load.image('zombie_tank_img', '/assets/sprites/zombie_tank.png');
        scene.load.image('zombie_boss_img', '/assets/sprites/zombie_boss.png');
        scene.load.svg('bullet', '/assets/sprites/bullet.svg', { width: 16, height: 8 });

        // Load audio
        scene.load.audio('shoot_single', '/assets/audio/shoot_single.ogg');
        scene.load.audio('shoot_auto', '/assets/audio/shoot_auto.ogg');
        scene.load.audio('zombie_death', '/assets/audio/zombie_death.ogg');
        scene.load.audio('zombie_hurt', '/assets/audio/zombie_hurt.ogg');
        scene.load.audio('zombie_attack', '/assets/audio/zombie_attack.ogg');
        scene.load.audio('weapon_switch', '/assets/audio/weapon_switch.ogg');
        scene.load.audio('wave_complete', '/assets/audio/wave_complete.ogg');
        scene.load.audio('player_hurt', '/assets/audio/player_hurt.ogg');

        scene.load.on('complete', () => {
            this.assetsLoaded = true;
        });
    }

    create() {
        this.scene = this.game.scene.scenes[0];

        // Create sprite groups
        this.playerSprites = this.scene.add.group();
        this.zombieSprites = this.scene.add.group();
        this.projectileSprites = this.scene.add.group();

        // Create animations
        this.createAnimations();

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

    createAnimations() {
        // Player animations
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

        // Zombie animations
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
    }

    update(time, delta) {
        // Smooth sprite movements
        for (const player of Object.values(this.players)) {
            if (player.targetX !== undefined) {
                player.sprite.x = Phaser.Math.Linear(player.sprite.x, player.targetX, 0.2);
                player.sprite.y = Phaser.Math.Linear(player.sprite.y, player.targetY, 0.2);
                player.nameText.x = player.sprite.x;
                player.nameText.y = player.sprite.y - 28;
                player.healthBar.x = player.sprite.x - 20;
                player.healthBar.y = player.sprite.y - 22;
            }
        }

        for (const zombie of Object.values(this.zombies)) {
            if (zombie.targetX !== undefined) {
                zombie.sprite.x = Phaser.Math.Linear(zombie.sprite.x, zombie.targetX, 0.15);
                zombie.sprite.y = Phaser.Math.Linear(zombie.sprite.y, zombie.targetY, 0.15);
                if (zombie.indicator) {
                    zombie.indicator.x = zombie.sprite.x;
                    zombie.indicator.y = zombie.sprite.y;
                }
                if (zombie.healthBar) {
                    zombie.healthBar.x = zombie.sprite.x - zombie.size / 2;
                    zombie.healthBar.y = zombie.sprite.y - zombie.size / 2 - 8;
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

        // Update ready status during wave break
        if (state.ready_info) {
            const statusText = `${state.ready_info.ready_count}/${state.ready_info.total_count} players ready`;
            document.getElementById('ready-status').textContent = statusText;
            document.getElementById('shop-ready-status').textContent = statusText;
        }

        // Auto-hide wave complete when countdown/playing starts
        if (state.status === 'countdown' || state.status === 'playing') {
            window.VELLA.inWaveBreak = false;
            document.getElementById('shop-ready-bar').classList.add('hidden');

            const waveCompleteEl = document.getElementById('wave-complete');
            if (!waveCompleteEl.classList.contains('hidden')) {
                waveCompleteEl.classList.add('hidden');
            }
        }
    }

    createPlayer(data) {
        const isMe = data.id === this.myId;

        // Scale positions to screen
        const x = this.scaleX(data.x);
        const y = this.scaleY(data.y);

        const sprite = this.scene.add.sprite(x, y, 'player_idle');
        sprite.setDisplaySize(48, 36);
        sprite.setDepth(10);
        sprite.play('player_idle_anim');

        // Tint other players blue
        if (!isMe) {
            sprite.setTint(0x60a5fa);
        }

        // Aim line
        const aimLine = this.scene.add.graphics().setDepth(9);

        // Name label
        const nameText = this.scene.add.text(x, y - 28, data.username || 'Player', {
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
            aimLine,
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

        const isMe = data.id === this.myId;

        // Save old state for comparison
        const wasReloading = player.data?.reloading || false;
        const oldHp = player.data?.hp;

        // Check if player took damage (for sound)
        if (isMe && oldHp !== undefined && data.hp < oldHp && !data.is_dead) {
            this.playSound('player_hurt', 0.4);
        }

        // Set target for smooth interpolation
        player.targetX = this.scaleX(data.x);
        player.targetY = this.scaleY(data.y);

        // Animation switching
        if (!data.is_dead) {
            const isMoving = player.data && (
                Math.abs(this.scaleX(data.x) - this.scaleX(player.data.x)) > 0.5 ||
                Math.abs(this.scaleY(data.y) - this.scaleY(player.data.y)) > 0.5
            );
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

        // Rotate sprite to face aim direction
        if (!data.is_dead && data.aim_angle !== undefined) {
            player.sprite.setRotation(data.aim_angle);
        }

        // Draw aim line
        player.aimLine.clear();
        if (!data.is_dead) {
            const sx = player.sprite.x;
            const sy = player.sprite.y;
            player.aimLine.lineStyle(2, isMe ? 0x4ade80 : 0x60a5fa, 0.3);
            player.aimLine.moveTo(sx, sy);
            player.aimLine.lineTo(
                sx + Math.cos(data.aim_angle) * 50,
                sy + Math.sin(data.aim_angle) * 50
            );
            player.aimLine.strokePath();
        }

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
                // Play reload sound when reload starts
                if (!wasReloading) {
                    this.playSound('weapon_switch', 0.3);
                }
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
            player.aimLine.destroy();
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

        const x = this.scaleX(data.x);
        const y = this.scaleY(data.y);

        const sizeMap = { 'normal': 48, 'fast': 44, 'tank': 64, 'boss': 80 };
        const displaySize = sizeMap[data.type] || 48;

        // Red ground indicator
        const indicator = this.scene.add.circle(x, y, displaySize * 0.5, 0xff0000, 0.15);
        indicator.setStrokeStyle(2, 0xff0000, 0.35);
        indicator.setDepth(4);

        // Create sprite based on type
        let sprite;
        if (data.type === 'tank') {
            sprite = this.scene.add.image(x, y, 'zombie_tank_img');
        } else if (data.type === 'boss') {
            sprite = this.scene.add.image(x, y, 'zombie_boss_img');
        } else {
            sprite = this.scene.add.sprite(x, y, 'zombie_move');
            sprite.play('zombie_move_anim');
            if (data.type === 'fast') sprite.setTint(0xff6666);
        }
        sprite.setDisplaySize(displaySize, displaySize);
        sprite.setDepth(5);

        // Health bar for tanks and bosses
        let healthBar = null;
        if (data.type === 'tank' || data.type === 'boss') {
            healthBar = this.scene.add.graphics().setDepth(6);
            this.drawHealthBar(healthBar, data.hp, data.max_hp, displaySize, 0xff4444);
            healthBar.setPosition(x - displaySize / 2, y - displaySize / 2 - 8);
        }

        this.zombies[data.id] = {
            sprite,
            indicator,
            healthBar,
            data,
            size: displaySize,
            targetX: x,
            targetY: y
        };
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

        // Rotate zombie to face movement direction
        if (zombie.data) {
            const dx = this.scaleX(data.x) - this.scaleX(zombie.data.x);
            const dy = this.scaleY(data.y) - this.scaleY(zombie.data.y);
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

        // Update health bar
        if (zombie.healthBar) {
            this.drawHealthBar(zombie.healthBar, data.hp, data.max_hp, zombie.size, 0xff4444);
        }

        zombie.data = data;
    }

    removeZombie(id) {
        const zombie = this.zombies[id];
        if (zombie) {
            // Death effect
            this.createDeathEffect(zombie.sprite.x, zombie.sprite.y);

            zombie.sprite.destroy();
            if (zombie.indicator) zombie.indicator.destroy();
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

        // Play shoot sound (only for own projectiles to avoid spam)
        if (data.owner_id === this.myId) {
            this.playSound('shoot_single', 0.3);
        }

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
        // Play death sound for any zombie kill
        this.playSound('zombie_death', 0.4);

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
            this.playSound('zombie_attack', 0.5);
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

    // Scale size from game units to screen pixels
    scaleSize(size) {
        // Use average of X and Y scale factors for size
        const scaleFactorX = this.scene.scale.width / 1920;
        const scaleFactorY = this.scene.scale.height / 1080;
        return size * Math.min(scaleFactorX, scaleFactorY);
    }

    // Play sound effect
    playSound(key, volume = 0.5) {
        if (!this.scene || !this.scene.sound) return;
        try {
            this.scene.sound.play(key, { volume });
        } catch (e) {
            // Ignore audio errors (e.g., user hasn't interacted yet)
        }
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
