/**
 * VELLA - Main Entry Point
 * Initializes Telegram WebApp and game systems
 */

import { WebSocketManager } from './network/WebSocketManager.js?v=28';
import { GameManager } from './game.js?v=28';
import { WorldGameManager } from './world.js?v=28';
import { BaseManager } from './base.js?v=28';
import { UIManager } from './ui/UIManager.js?v=28';

// Telegram WebApp
const tg = window.Telegram?.WebApp;

// Global state
window.VELLA = {
    initData: '',
    player: null,
    ws: null,
    game: null,
    worldGame: null,
    baseManager: null,
    ui: null,
    mode: null, // 'room' or 'world'
};

// Global audio player (works without Phaser game)
window.playSound = function(name, volume = 0.5) {
    // Try Phaser first
    if (window.VELLA.game) {
        window.VELLA.game.playSound(name, volume);
        return;
    }
    // Fallback to HTML5 Audio
    try {
        const audio = new Audio(`/assets/audio/${name}.ogg`);
        audio.volume = volume;
        audio.play().catch(() => {}); // Ignore autoplay errors
    } catch (e) {}
};

// Global toast notification
window.showToast = function(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    // Remove after animation ends (~2.8s)
    setTimeout(() => toast.remove(), 3000);
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
    console.log('VELLA initializing...');

    // Setup Telegram WebApp
    if (tg && tg.initData) {
        tg.ready();
        tg.expand();
        tg.setHeaderColor('#0a0a0f');
        tg.setBackgroundColor('#0a0a0f');

        window.VELLA.initData = tg.initData;
        console.log('Telegram WebApp ready');
    } else {
        // Dev mode - create fake init data
        if (tg) {
            try { tg.ready(); tg.expand(); } catch(e) {}
        }
        const devUser = {
            id: 999999,
            username: 'dev_player',
            first_name: 'Dev'
        };
        window.VELLA.initData = `user=${JSON.stringify(devUser)}`;
        console.log('Dev mode - using fake init data');
    }

    // Initialize UI Manager
    window.VELLA.ui = new UIManager();

    // Load player data
    await loadPlayerData();

    // Show menu
    hideScreen('loading-screen');
    showScreen('menu-screen');

    // Setup event listeners
    setupEventListeners();
});

async function loadPlayerData() {
    try {
        const response = await fetch(`/api/player?init_data=${encodeURIComponent(window.VELLA.initData)}`);
        if (response.ok) {
            window.VELLA.player = await response.json();
            updatePlayerUI();
        }
    } catch (error) {
        console.error('Failed to load player data:', error);
    }
}

function updatePlayerUI() {
    const player = window.VELLA.player;
    if (!player) return;

    document.getElementById('player-coins').textContent = player.coins;
    document.getElementById('player-kills').textContent = player.total_kills;
    document.getElementById('player-wave').textContent = player.highest_wave;
    document.getElementById('equipped-weapon-name').textContent = getWeaponDisplayName(player.equipped_weapon);
}

function getWeaponDisplayName(code) {
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

function setupEventListeners() {
    // Create room button
    document.getElementById('btn-create-room').addEventListener('click', () => {
        createRoom();
    });

    // Browse rooms button
    document.getElementById('btn-browse-rooms').addEventListener('click', () => {
        showRoomsBrowser();
    });

    // Rooms refresh
    document.getElementById('btn-rooms-refresh').addEventListener('click', () => {
        loadPublicRooms();
    });

    // Rooms cancel
    document.getElementById('btn-rooms-cancel').addEventListener('click', () => {
        hideModal('rooms-modal');
    });

    // Open World button
    document.getElementById('btn-open-world').addEventListener('click', () => {
        enterWorld();
    });

    // Clan button
    document.getElementById('btn-clan').addEventListener('click', () => {
        showClanScreen();
    });

    // Clan back
    document.getElementById('btn-clan-back').addEventListener('click', () => {
        hideScreen('clan-screen');
        showScreen('menu-screen');
    });

    // Clan create
    document.getElementById('btn-clan-create').addEventListener('click', () => {
        createClan();
    });

    // Clan join
    document.getElementById('btn-clan-join').addEventListener('click', () => {
        joinClan();
    });

    // Clan leave
    document.getElementById('btn-clan-leave').addEventListener('click', () => {
        leaveClan();
    });

    // Clan base
    document.getElementById('btn-clan-base').addEventListener('click', () => {
        showBaseScreen();
    });

    // Clan deposit
    document.getElementById('btn-clan-deposit').addEventListener('click', () => {
        depositResources();
    });

    // Base back — return to clan screen or world depending on where we came from
    document.getElementById('btn-base-back').addEventListener('click', () => {
        hideScreen('base-screen');
        if (window.VELLA._baseOpenedFromWorld) {
            window.VELLA._baseOpenedFromWorld = false;
            // Return to world
            document.getElementById('game-container').classList.remove('hidden');
            document.getElementById('world-hud').classList.remove('hidden');
            document.getElementById('joystick-left').classList.remove('hidden');
            document.getElementById('joystick-right').classList.remove('hidden');
        } else {
            showScreen('clan-screen');
        }
    });

    // World buttons
    document.getElementById('btn-use-medkit').addEventListener('click', () => {
        if (window.VELLA.ws) {
            window.VELLA.ws.send({ type: 'use_medkit' });
        }
    });

    document.getElementById('btn-collect-resource').addEventListener('click', () => {
        if (window.VELLA.ws) {
            window.VELLA.ws.send({ type: 'collect_resource' });
        }
    });

    document.getElementById('btn-deposit-base').addEventListener('click', () => {
        if (window.VELLA.ws) {
            window.VELLA.ws.send({ type: 'deposit_to_base' });
        }
    });

    // Base actions dropdown toggle
    document.getElementById('base-actions-toggle').addEventListener('click', () => {
        const dd = document.getElementById('base-actions-dropdown');
        dd.classList.toggle('hidden');
    });

    // Build on base directly from world
    document.getElementById('btn-world-build').addEventListener('click', () => {
        openBaseBuildFromWorld();
    });

    document.getElementById('btn-world-pause').addEventListener('click', () => {
        showModal('world-exit-modal');
    });

    document.getElementById('btn-world-exit-confirm').addEventListener('click', () => {
        hideModal('world-exit-modal');
        leaveWorld();
    });

    document.getElementById('btn-world-exit-cancel').addEventListener('click', () => {
        hideModal('world-exit-modal');
    });

    // Shop button
    document.getElementById('btn-shop').addEventListener('click', () => {
        showShop();
    });

    // Shop back
    document.getElementById('btn-shop-back').addEventListener('click', () => {
        hideScreen('shop-screen');
        if (window.VELLA.inGameShop) {
            // Show joysticks again
            document.getElementById('joystick-left').classList.remove('hidden');
            document.getElementById('joystick-right').classList.remove('hidden');
            showScreen('wave-complete');
        } else {
            showScreen('menu-screen');
        }
    });

    // Ready button
    document.getElementById('btn-ready').addEventListener('click', () => {
        if (window.VELLA.ws) {
            const isReady = document.getElementById('btn-ready').classList.toggle('ready');
            window.VELLA.ws.send({ type: 'ready', is_ready: isReady });
            document.getElementById('ready-text').textContent = isReady ? 'Не готов' : 'Готов';
        }
    });

    // Leave button
    document.getElementById('btn-leave').addEventListener('click', () => {
        leaveRoom();
    });

    // Copy room code
    document.getElementById('btn-copy-code').addEventListener('click', () => {
        const code = document.getElementById('room-code').textContent;
        navigator.clipboard?.writeText(code);
    });

    // Game over buttons
    document.getElementById('btn-play-again').addEventListener('click', () => {
        hideScreen('gameover-screen');
        joinRoom(null);
    });

    document.getElementById('btn-back-menu').addEventListener('click', () => {
        hideScreen('gameover-screen');
        showScreen('menu-screen');
        loadPlayerData();
    });

    // Debug: Kill all zombies
    document.getElementById('btn-kill-all').addEventListener('click', () => {
        if (window.VELLA.ws) {
            window.VELLA.ws.send({ type: 'kill_all' });
        }
    });

    document.getElementById('btn-wave-shop').addEventListener('click', () => {
        // Hide wave complete, show shop (can still ready from shop)
        hideScreen('wave-complete');
        showInGameShop();
    });

    // Ready button on wave complete screen
    document.getElementById('btn-next-wave').addEventListener('click', () => {
        sendReady();
    });

    // Ready button in shop
    document.getElementById('btn-shop-ready').addEventListener('click', () => {
        sendReady();
    });

    // Pause button - show exit confirmation
    document.getElementById('btn-pause').addEventListener('click', () => {
        showModal('exit-modal');
    });

    // Exit confirm
    document.getElementById('btn-exit-confirm').addEventListener('click', () => {
        hideModal('exit-modal');
        leaveRoom();
    });

    // Exit cancel
    document.getElementById('btn-exit-cancel').addEventListener('click', () => {
        hideModal('exit-modal');
    });
}

function sendReady() {
    if (window.VELLA.ws && window.VELLA.inWaveBreak) {
        window.VELLA.ws.send({ type: 'ready', is_ready: true });

        // Update button states
        const waveReadyBtn = document.getElementById('btn-next-wave');
        waveReadyBtn.textContent = '✓ Готов!';
        waveReadyBtn.classList.add('ready');
        waveReadyBtn.disabled = true;

        const shopReadyBtn = document.getElementById('btn-shop-ready');
        shopReadyBtn.textContent = '✓ Готов!';
        shopReadyBtn.disabled = true;
    }
}

function showRoomsBrowser() {
    showModal('rooms-modal');
    loadPublicRooms();
}

async function loadPublicRooms() {
    const listEl = document.getElementById('rooms-list');
    listEl.innerHTML = '<p class="loading-rooms">Загрузка...</p>';

    try {
        const response = await fetch('/api/rooms');
        const rooms = await response.json();

        if (rooms.length === 0) {
            listEl.innerHTML = '<p class="no-rooms">Нет доступных комнат.<br>Создай свою!</p>';
            return;
        }

        listEl.innerHTML = '';
        for (const room of rooms) {
            const item = document.createElement('div');
            item.className = 'room-item';
            item.innerHTML = `
                <div class="room-info">
                    <div class="room-host">${room.host || 'Unknown'}</div>
                    <div class="room-players">${room.player_count}/${room.max_players} игроков</div>
                </div>
                <button class="btn btn-primary btn-join-room" data-code="${room.room_code}">Войти</button>
            `;
            listEl.appendChild(item);
        }

        // Add click handlers
        listEl.querySelectorAll('.btn-join-room').forEach(btn => {
            btn.addEventListener('click', () => {
                hideModal('rooms-modal');
                joinRoom(btn.dataset.code);
            });
        });
    } catch (error) {
        listEl.innerHTML = '<p class="no-rooms">Ошибка загрузки</p>';
        console.error('Failed to load rooms:', error);
    }
}

async function createRoom() {
    hideScreen('menu-screen');
    showScreen('lobby-screen');

    // Connect WebSocket
    const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws?init_data=${encodeURIComponent(window.VELLA.initData)}`;

    window.VELLA.ws = new WebSocketManager(wsUrl);

    window.VELLA.ws.on('open', () => {
        window.VELLA.ws.send({ type: 'create_room', is_public: true });
    });

    setupRoomHandlers();
    window.VELLA.ws.connect();
}

async function joinRoom(roomCode) {
    hideScreen('menu-screen');
    showScreen('lobby-screen');

    // Connect WebSocket
    const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws?init_data=${encodeURIComponent(window.VELLA.initData)}`;

    window.VELLA.ws = new WebSocketManager(wsUrl);

    window.VELLA.ws.on('open', () => {
        window.VELLA.ws.send({ type: 'join_room', room_code: roomCode });
    });

    setupRoomHandlers();
    window.VELLA.ws.connect();
}

function setupRoomHandlers() {
    window.VELLA.ws.on('room_created', (data) => {
        document.getElementById('room-code').textContent = data.room_code;
        updateLobbyPlayers(data.players);
    });

    window.VELLA.ws.on('room_joined', (data) => {
        document.getElementById('room-code').textContent = data.room_code;
        updateLobbyPlayers(data.players);
    });

    window.VELLA.ws.on('error', (data) => {
        window.showToast(data.message || 'Ошибка', 'error');
        hideScreen('lobby-screen');
        showScreen('menu-screen');
        if (window.VELLA.ws) {
            window.VELLA.ws.disconnect();
            window.VELLA.ws = null;
        }
    });

    window.VELLA.ws.on('lobby_update', (data) => {
        updateLobbyPlayers(data.players);

        // Update ready status during wave break
        if (window.VELLA.inWaveBreak && data.players) {
            const readyCount = data.players.filter(p => p.is_ready).length;
            const totalCount = data.players.length;
            const statusText = `${readyCount}/${totalCount} готовы`;
            document.getElementById('ready-status').textContent = statusText;
            document.getElementById('shop-ready-status').textContent = statusText;
        }
    });

    window.VELLA.ws.on('game_start', (data) => {
        startGame(data);
    });

    window.VELLA.ws.on('state', (data) => {
        // Debug: log zombie count every 20 state updates
        if (window.VELLA._stateCount === undefined) window.VELLA._stateCount = 0;
        window.VELLA._stateCount++;
        if (window.VELLA._stateCount % 20 === 1) {
            console.log(`[State] tick=${data.tick} zombies=${data.zombies?.length || 0} players=${data.players?.length || 0}`);
        }

        if (window.VELLA.game) {
            window.VELLA.game.updateState(data);
        }
    });

    window.VELLA.ws.on('wave_start', (data) => {
        hideScreen('wave-complete');
        hideScreen('shop-screen');
        window.VELLA.inWaveBreak = false;
        window.VELLA.inGameShop = false;
        document.getElementById('shop-ready-bar').classList.add('hidden');

        // Show joysticks for gameplay
        document.getElementById('joystick-left').classList.remove('hidden');
        document.getElementById('joystick-right').classList.remove('hidden');

        // Clear countdowns if still running
        if (window.VELLA.countdownInterval) {
            clearInterval(window.VELLA.countdownInterval);
            window.VELLA.countdownInterval = null;
        }
        showWaveAnnouncement(data.wave, data.zombie_count);
    });

    window.VELLA.ws.on('wave_complete', (data) => {
        console.log('[WAVE COMPLETE]', data);
        showWaveComplete(data);
    });

    window.VELLA.ws.on('wave_countdown', (data) => {
        hideScreen('wave-complete');
        showWaveCountdown(data.next_wave, data.countdown || 5);
    });

    window.VELLA.ws.on('zombie_killed', (data) => {
        if (window.VELLA.game) {
            window.VELLA.game.onZombieKilled(data);
        }
    });

    window.VELLA.ws.on('player_died', (data) => {
        if (window.VELLA.game) {
            window.VELLA.game.onPlayerDied(data);
        }
    });

    window.VELLA.ws.on('game_over', (data) => {
        endGame(data);
    });

    window.VELLA.ws.on('close', () => {
        console.log('WebSocket closed');
    });
}

function leaveRoom() {
    if (window.VELLA.ws) {
        window.VELLA.ws.send({ type: 'leave_room' });
        window.VELLA.ws.disconnect();
        window.VELLA.ws = null;
    }

    if (window.VELLA.game) {
        window.VELLA.game.destroy();
        window.VELLA.game = null;
    }

    hideScreen('lobby-screen');
    hideScreen('game-container');
    document.getElementById('hud').classList.add('hidden');
    document.getElementById('joystick-left').classList.add('hidden');
    document.getElementById('joystick-right').classList.add('hidden');

    showScreen('menu-screen');
    loadPlayerData();
}

function updateLobbyPlayers(players) {
    const container = document.getElementById('lobby-players');
    container.innerHTML = '';

    for (const player of players) {
        const row = document.createElement('div');
        row.className = `player-row ${player.is_ready ? 'ready' : 'not-ready'}`;
        row.innerHTML = `
            <span class="player-name">${player.username || 'Player'}</span>
            <span class="player-status ${player.is_ready ? 'ready' : 'not-ready'}">
                ${player.is_ready ? '✓ Готов' : 'Ожидание...'}
            </span>
        `;
        container.appendChild(row);
    }
}

function startGame(data) {
    hideScreen('lobby-screen');

    // Create game
    window.VELLA.game = new GameManager(data);

    // Show game elements
    document.getElementById('game-container').classList.remove('hidden');
    document.getElementById('hud').classList.remove('hidden');
    document.getElementById('joystick-left').classList.remove('hidden');
    document.getElementById('joystick-right').classList.remove('hidden');

    // Start game
    window.VELLA.game.start();
}

function showWaveAnnouncement(wave, zombieCount) {
    const el = document.getElementById('wave-announcement');
    document.getElementById('announce-wave').textContent = wave;
    document.getElementById('announce-zombies').textContent = `${zombieCount} зомби приближаются`;

    // Play wave start sound (zombie growl)
    window.playSound('zombie_attack', 0.6);

    el.classList.remove('hidden');
    setTimeout(() => {
        el.classList.add('hidden');
    }, 3000);
}

function showWaveCountdown(wave, seconds) {
    const el = document.getElementById('wave-announcement');
    document.getElementById('announce-wave').textContent = wave;

    // Clear any existing countdown
    if (window.VELLA.countdownInterval) {
        clearInterval(window.VELLA.countdownInterval);
    }

    let remaining = seconds;
    document.getElementById('announce-zombies').textContent = `Начало через ${remaining}...`;
    el.classList.remove('hidden');

    window.VELLA.countdownInterval = setInterval(() => {
        remaining--;
        if (remaining > 0) {
            document.getElementById('announce-zombies').textContent = `Начало через ${remaining}...`;
        } else {
            clearInterval(window.VELLA.countdownInterval);
            window.VELLA.countdownInterval = null;
            // Will be hidden by wave_start event
        }
    }, 1000);
}

function showWaveComplete(data) {
    document.getElementById('complete-wave').textContent = data.wave;
    document.getElementById('wave-bonus').textContent = data.bonus_coins;
    document.getElementById('next-wave-num').textContent = data.next_wave;

    // Play wave complete sound
    window.playSound('wave_complete', 0.5);

    // Update player coins display
    if (window.VELLA.game) {
        window.VELLA.game.coins += data.bonus_coins;
        document.getElementById('hud-coins').textContent = window.VELLA.game.coins;
    }

    // Reset ready button state
    const readyBtn = document.getElementById('btn-next-wave');
    readyBtn.textContent = '✓ Готов';
    readyBtn.classList.remove('ready');
    readyBtn.disabled = false;

    // Show shop ready bar
    document.getElementById('shop-ready-bar').classList.remove('hidden');

    // Mark that we're in wave break
    window.VELLA.inWaveBreak = true;

    showScreen('wave-complete');
}

function endGame(data) {
    // Hide game elements
    document.getElementById('game-container').classList.add('hidden');
    document.getElementById('hud').classList.add('hidden');
    document.getElementById('joystick-left').classList.add('hidden');
    document.getElementById('joystick-right').classList.add('hidden');

    // Destroy game
    if (window.VELLA.game) {
        window.VELLA.game.destroy();
        window.VELLA.game = null;
    }

    // Update game over screen
    document.getElementById('final-wave').textContent = data.wave_reached;
    document.getElementById('final-kills').textContent = data.total_kills;
    document.getElementById('final-coins').textContent = data.coins_earned;

    // Leaderboard
    const leaderboard = document.getElementById('final-leaderboard');
    leaderboard.innerHTML = '<h4>Лучшие игроки</h4>';
    data.player_stats.forEach((player, index) => {
        const row = document.createElement('div');
        row.className = 'leaderboard-row';
        row.innerHTML = `
            <span class="rank">#${index + 1}</span>
            <span class="name">${player.username || 'Игрок'}</span>
            <span class="kills">${player.kills} 💀</span>
        `;
        leaderboard.appendChild(row);
    });

    showScreen('gameover-screen');
}

async function showShop() {
    hideScreen('menu-screen');
    showScreen('shop-screen');
    window.VELLA.inGameShop = false;

    document.getElementById('shop-coins').textContent = window.VELLA.player?.coins || 0;

    try {
        const response = await fetch(`/api/weapons?init_data=${encodeURIComponent(window.VELLA.initData)}`);
        if (response.ok) {
            const weapons = await response.json();
            renderWeapons(weapons);
        }
    } catch (error) {
        console.error('Failed to load weapons:', error);
    }
}

async function showInGameShop() {
    showScreen('shop-screen');
    window.VELLA.inGameShop = true;

    // Hide joysticks while in shop
    document.getElementById('joystick-left').classList.add('hidden');
    document.getElementById('joystick-right').classList.add('hidden');

    // Use in-game coins if available
    const coins = window.VELLA.game?.coins || window.VELLA.player?.coins || 0;
    document.getElementById('shop-coins').textContent = coins;

    try {
        const response = await fetch(`/api/weapons?init_data=${encodeURIComponent(window.VELLA.initData)}`);
        if (response.ok) {
            const weapons = await response.json();
            renderWeapons(weapons);
        }
    } catch (error) {
        console.error('Failed to load weapons:', error);
    }
}

function renderWeapons(weapons) {
    const grid = document.getElementById('weapons-list');
    grid.innerHTML = '';

    const categoryIcons = {
        pistol: '🔫',
        shotgun: '💥',
        rifle: '🎯',
        sniper: '🎪',
        heavy: '⚙️'
    };

    // Use in-game coins if in game, otherwise saved coins
    const playerCoins = window.VELLA.game?.coins ?? window.VELLA.player?.coins ?? 0;

    for (const weapon of weapons) {
        const card = document.createElement('div');
        const equipped = window.VELLA.player?.equipped_weapon === weapon.code;
        const isPremium = weapon.premium || false;
        const canAfford = isPremium ? true : playerCoins >= weapon.price_coins;

        let statusClass = '';
        if (equipped) statusClass = 'equipped';
        else if (weapon.owned) statusClass = 'owned';
        else if (isPremium) statusClass = 'premium';
        else if (!canAfford) statusClass = 'locked';

        card.className = `weapon-card ${statusClass}`;

        // Build price/button section
        let priceSection = '';
        if (!weapon.owned) {
            if (isPremium) {
                priceSection = `
                    <div class="weapon-price premium-price">⭐ ${weapon.price_stars} Stars</div>
                    <div class="weapon-desc">${weapon.description || ''}</div>
                    <button class="btn btn-premium buy-stars-btn" data-code="${weapon.code}">
                        Купить за Stars
                    </button>
                `;
            } else {
                priceSection = `
                    <div class="weapon-price">💰 ${weapon.price_coins}</div>
                    <button class="btn btn-primary buy-coins-btn" ${!canAfford ? 'disabled' : ''} data-code="${weapon.code}">
                        Купить
                    </button>
                `;
            }
        } else if (equipped) {
            priceSection = `<button class="btn btn-secondary" disabled>Выбрано</button>`;
        } else {
            priceSection = `<button class="btn btn-primary equip-btn" data-code="${weapon.code}">Выбрать</button>`;
        }

        card.innerHTML = `
            <div class="weapon-icon">${categoryIcons[weapon.category] || '🔫'}</div>
            <div class="weapon-name">${weapon.name}</div>
            <div class="weapon-category">${weapon.category}${isPremium ? ' ⭐' : ''}</div>
            <div class="weapon-stats">
                DMG: ${weapon.damage} | Rate: ${weapon.fire_rate}/s
            </div>
            ${priceSection}
        `;

        // Buy with coins button handler
        const buyCoinsBtn = card.querySelector('.buy-coins-btn');
        if (buyCoinsBtn) {
            buyCoinsBtn.addEventListener('click', () => buyWeapon(weapon.code));
        }

        // Buy with Stars button handler
        const buyStarsBtn = card.querySelector('.buy-stars-btn');
        if (buyStarsBtn) {
            buyStarsBtn.addEventListener('click', () => buyWithStars(weapon.code));
        }

        // Equip button handler
        const equipBtn = card.querySelector('.equip-btn');
        if (equipBtn) {
            equipBtn.addEventListener('click', () => equipWeapon(weapon.code));
        }

        grid.appendChild(card);
    }
}

async function buyWeapon(code) {
    try {
        const response = await fetch(`/api/weapons/buy?weapon_code=${code}&init_data=${encodeURIComponent(window.VELLA.initData)}`, {
            method: 'POST'
        });

        if (response.ok) {
            const result = await response.json();
            window.VELLA.player.coins = result.coins;

            // Update in-game coins too
            if (window.VELLA.game) {
                window.VELLA.game.coins = result.coins;
            }

            // Play purchase sound
            window.playSound('weapon_switch', 0.5);

            await loadPlayerData();

            // Refresh shop (keep inGameShop state)
            if (window.VELLA.inGameShop) {
                showInGameShop();
            } else {
                showShop();
            }
        }
    } catch (error) {
        console.error('Failed to buy weapon:', error);
    }
}

async function buyWithStars(code) {
    const tg = window.Telegram?.WebApp;
    if (!tg) {
        window.showToast('Telegram WebApp недоступен', 'error');
        return;
    }

    try {
        // Create invoice on backend
        const response = await fetch(`/api/payments/create-invoice?weapon_code=${code}&init_data=${encodeURIComponent(window.VELLA.initData)}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            window.showToast(error.detail || 'Ошибка создания счёта', 'error');
            return;
        }

        const { invoice_url } = await response.json();

        // Open Telegram payment dialog
        tg.openInvoice(invoice_url, async (status) => {
            console.log('[Payment] Status:', status);
            if (status === 'paid') {
                window.playSound('weapon_switch', 0.5);
                window.showToast('Покупка успешна!', 'success');
                await loadPlayerData();
                // Refresh shop (keep inGameShop state)
                if (window.VELLA.inGameShop) {
                    showInGameShop();
                } else {
                    showShop();
                }
            } else if (status === 'failed') {
                window.showToast('Оплата не прошла', 'error');
            }
            // 'cancelled' - user closed the dialog
        });
    } catch (error) {
        console.error('Failed to buy with Stars:', error);
        window.showToast('Ошибка обработки платежа', 'error');
    }
}

async function equipWeapon(code) {
    try {
        const response = await fetch(`/api/weapons/equip?weapon_code=${code}&init_data=${encodeURIComponent(window.VELLA.initData)}`, {
            method: 'POST'
        });

        if (response.ok) {
            window.VELLA.player.equipped_weapon = code;

            // Play weapon switch sound
            window.playSound('weapon_switch', 0.4);

            // Also switch weapon in active game session
            if (window.VELLA.ws?.isConnected) {
                window.VELLA.ws.send({ type: 'switch_weapon', weapon_code: code });
            }

            // Refresh shop (keep inGameShop state)
            if (window.VELLA.inGameShop) {
                showInGameShop();
            } else {
                showShop();
            }
        }
    } catch (error) {
        console.error('Failed to equip weapon:', error);
    }
}

// ============== OPEN WORLD ==============

async function enterWorld() {
    hideScreen('menu-screen');

    // Connect WebSocket
    const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws?init_data=${encodeURIComponent(window.VELLA.initData)}`;
    window.VELLA.ws = new WebSocketManager(wsUrl);

    window.VELLA.ws.on('open', () => {
        window.VELLA.ws.send({ type: 'enter_world' });
    });

    setupWorldHandlers();
    window.VELLA.ws.connect();
}

function setupWorldHandlers() {
    window.VELLA.ws.on('world_entered', (data) => {
        console.log('[World] Entered at', data.x, data.y);
        window.VELLA.mode = 'world';

        // Create world game manager
        window.VELLA.worldGame = new WorldGameManager();

        // Pass clan base info
        if (data.clan_base) {
            window.VELLA.worldGame.setClanBase(data.clan_base);
        }

        // Show game elements
        document.getElementById('game-container').classList.remove('hidden');
        document.getElementById('world-hud').classList.remove('hidden');
        document.getElementById('joystick-left').classList.remove('hidden');
        document.getElementById('joystick-right').classList.remove('hidden');

        // Show "to base" button if in clan
        const baseBtn = document.getElementById('btn-goto-base');
        if (baseBtn) {
            baseBtn.classList.toggle('hidden', !data.clan_base);
        }

        window.VELLA.worldGame.start();

        // Process any chunks that arrived before worldGame was created
        if (window.VELLA._pendingWorldChunks) {
            for (const chunk of window.VELLA._pendingWorldChunks) {
                window.VELLA.worldGame.loadChunk(chunk);
            }
            window.VELLA._pendingWorldChunks = null;
        }
    });

    window.VELLA.ws.on('world_chunk_load', (data) => {
        if (window.VELLA.worldGame) {
            window.VELLA.worldGame.loadChunk(data);
        } else {
            // Buffer chunks that arrive before worldGame is created
            if (!window.VELLA._pendingWorldChunks) window.VELLA._pendingWorldChunks = [];
            window.VELLA._pendingWorldChunks.push(data);
        }
    });

    window.VELLA.ws.on('world_chunk_unload', (data) => {
        if (window.VELLA.worldGame) {
            window.VELLA.worldGame.unloadChunk(data.chunk_x, data.chunk_y);
        }
    });

    window.VELLA.ws.on('world_chunk_buildings_update', (data) => {
        if (window.VELLA.worldGame) {
            window.VELLA.worldGame.updateChunkBuildings(data);
        }
    });

    window.VELLA.ws.on('world_state', (data) => {
        if (window.VELLA.worldGame) {
            window.VELLA.worldGame.updateState(data);
        }
    });

    window.VELLA.ws.on('world_resource_collected', (data) => {
        console.log('[World] Collected', data.amount, data.resource_type);
        window.playSound('weapon_switch', 0.3);
    });

    window.VELLA.ws.on('world_medkit_used', (data) => {
        console.log('[World] Medkit used, HP:', data.hp);
        window.playSound('wave_complete', 0.3);
    });

    window.VELLA.ws.on('deposit_result', (data) => {
        if (data.success) {
            const d = data.deposited;
            const parts = [];
            if (d.metal) parts.push(`${d.metal} металла`);
            if (d.wood) parts.push(`${d.wood} дерева`);
            if (d.food) parts.push(`${d.food} еды`);
            if (d.ammo) parts.push(`${d.ammo} патронов`);
            if (d.meds) parts.push(`${d.meds} аптечек`);
            if (window.VELLA.worldGame) {
                window.VELLA.worldGame.showFloatingText('Сдано: ' + parts.join(', '), 0x4ade80);
            }
            window.playSound('wave_complete', 0.3);
            console.log('[World] Deposited:', d);
        } else {
            if (data.reason === 'empty') {
                if (window.VELLA.worldGame) window.VELLA.worldGame.showFloatingText('Нечего сдавать', 0xff4444);
            } else {
                if (window.VELLA.worldGame) window.VELLA.worldGame.showFloatingText('Подойди к базе', 0xff4444);
            }
        }
    });

    window.VELLA.ws.on('world_player_respawn', (data) => {
        console.log('[World] Respawned at', data.x, data.y);
    });

    window.VELLA.ws.on('clothing_equipped', (data) => {
        if (data.name) {
            window.showToast(`Экипировано: ${data.name}`, 'success');
        }
    });

    window.VELLA.ws.on('clothing_unequipped', (data) => {
        if (data.name) {
            window.showToast(`Снято: ${data.name}`, 'info');
        }
    });

    window.VELLA.ws.on('world_left', () => {
        console.log('[World] Left world');
    });

    window.VELLA.ws.on('close', () => {
        console.log('WebSocket closed');
    });

    window.VELLA.ws.on('error', (data) => {
        console.error('WebSocket error:', data);
    });
}

function leaveWorld() {
    if (window.VELLA.ws) {
        window.VELLA.ws.send({ type: 'leave_world' });
        window.VELLA.ws.disconnect();
        window.VELLA.ws = null;
    }

    if (window.VELLA.worldGame) {
        window.VELLA.worldGame.destroy();
        window.VELLA.worldGame = null;
    }

    window.VELLA.mode = null;

    document.getElementById('game-container').classList.add('hidden');
    document.getElementById('world-hud').classList.add('hidden');
    document.getElementById('joystick-left').classList.add('hidden');
    document.getElementById('joystick-right').classList.add('hidden');

    showScreen('menu-screen');
    loadPlayerData();
}

// ============== CLAN ==============

async function showClanScreen() {
    hideScreen('menu-screen');
    showScreen('clan-screen');
    await loadClanData();
}

async function loadClanData() {
    try {
        const res = await fetch(`/api/clan?init_data=${encodeURIComponent(window.VELLA.initData)}`);
        if (!res.ok) return;
        const data = await res.json();

        if (!data.clan) {
            document.getElementById('clan-no-clan').classList.remove('hidden');
            document.getElementById('clan-info').classList.add('hidden');
            return;
        }

        document.getElementById('clan-no-clan').classList.add('hidden');
        document.getElementById('clan-info').classList.remove('hidden');

        const clan = data.clan;
        document.getElementById('clan-name-display').textContent = clan.name;
        document.getElementById('clan-metal').textContent = clan.resources.metal;
        document.getElementById('clan-wood').textContent = clan.resources.wood;
        document.getElementById('clan-food').textContent = clan.resources.food;
        document.getElementById('clan-ammo').textContent = clan.resources.ammo;
        document.getElementById('clan-meds').textContent = clan.resources.meds;

        // Members
        const listEl = document.getElementById('clan-members-list');
        listEl.innerHTML = '';
        for (const m of clan.members) {
            const row = document.createElement('div');
            row.className = 'clan-member-row';
            const roleIcon = m.role === 'leader' ? '👑' : m.role === 'officer' ? '⭐' : '';
            row.innerHTML = `
                <span class="member-name">${roleIcon} ${m.username || 'Player'}</span>
                <span class="member-role">${m.role}</span>
            `;
            listEl.appendChild(row);
        }
    } catch (e) {
        console.error('Failed to load clan:', e);
    }
}

async function createClan() {
    const name = document.getElementById('clan-name-input').value.trim();
    const chatId = document.getElementById('clan-chat-id-input').value.trim();
    if (!name || !chatId) return window.showToast('Заполни все поля', 'warning');

    try {
        const res = await fetch(
            `/api/clan/create?name=${encodeURIComponent(name)}&telegram_chat_id=${chatId}&init_data=${encodeURIComponent(window.VELLA.initData)}`,
            { method: 'POST' }
        );
        if (res.ok) {
            await loadClanData();
        } else {
            const err = await res.json();
            window.showToast(err.detail || 'Ошибка', 'error');
        }
    } catch (e) {
        console.error('Failed to create clan:', e);
    }
}

async function joinClan() {
    const clanId = document.getElementById('clan-join-id-input').value.trim();
    if (!clanId) return window.showToast('Введи ID клана', 'warning');

    try {
        const res = await fetch(
            `/api/clan/join?clan_id=${clanId}&init_data=${encodeURIComponent(window.VELLA.initData)}`,
            { method: 'POST' }
        );
        if (res.ok) {
            await loadClanData();
        } else {
            const err = await res.json();
            window.showToast(err.detail || 'Ошибка', 'error');
        }
    } catch (e) {
        console.error('Failed to join clan:', e);
    }
}

async function leaveClan() {
    if (!confirm('Leave clan?')) return;

    try {
        const res = await fetch(
            `/api/clan/leave?init_data=${encodeURIComponent(window.VELLA.initData)}`,
            { method: 'DELETE' }
        );
        if (res.ok) {
            await loadClanData();
        }
    } catch (e) {
        console.error('Failed to leave clan:', e);
    }
}

async function depositResources() {
    // Simple deposit: deposit all resources
    const amounts = prompt('Deposit all resources? (metal,wood,food,ammo,meds)', '10,10,5,5,1');
    if (!amounts) return;
    const [metal, wood, food, ammo, meds] = amounts.split(',').map(Number);

    try {
        const res = await fetch(
            `/api/clan/deposit?metal=${metal || 0}&wood=${wood || 0}&food=${food || 0}&ammo=${ammo || 0}&meds=${meds || 0}&init_data=${encodeURIComponent(window.VELLA.initData)}`,
            { method: 'POST' }
        );
        if (res.ok) {
            await loadClanData();
        } else {
            const err = await res.json();
            window.showToast(err.detail || 'Ошибка', 'error');
        }
    } catch (e) {
        console.error('Failed to deposit:', e);
    }
}

// ============== BASE ==============

async function showBaseScreen() {
    hideScreen('clan-screen');
    showScreen('base-screen');

    if (!window.VELLA.baseManager) {
        window.VELLA.baseManager = new BaseManager('base-canvas');
    }

    // Load clan resources into base screen header
    loadBaseResources();

    await window.VELLA.baseManager.loadBuildingTypes();
    await window.VELLA.baseManager.loadBuildings();
}

async function loadBaseResources() {
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
    } catch (e) {
        console.error('Failed to load base resources:', e);
    }
}

// Open base screen directly from world (shortcut)
function openBaseBuildFromWorld() {
    window.VELLA._baseOpenedFromWorld = true;
    document.getElementById('game-container').classList.add('hidden');
    document.getElementById('world-hud').classList.add('hidden');
    document.getElementById('joystick-left').classList.add('hidden');
    document.getElementById('joystick-right').classList.add('hidden');
    showBaseScreen();
}

// Helper functions
function showScreen(id) {
    document.getElementById(id).classList.remove('hidden');
}

function hideScreen(id) {
    document.getElementById(id).classList.add('hidden');
}

function showModal(id) {
    document.getElementById(id).classList.remove('hidden');
}

function hideModal(id) {
    document.getElementById(id).classList.add('hidden');
}

// Export for modules
window.showScreen = showScreen;
window.hideScreen = hideScreen;
