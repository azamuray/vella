/**
 * VELLA - Main Entry Point
 * Initializes Telegram WebApp and game systems
 */

import { WebSocketManager } from './network/WebSocketManager.js';
import { GameManager } from './game.js';
import { UIManager } from './ui/UIManager.js';

// Telegram WebApp
const tg = window.Telegram?.WebApp;

// Global state
window.VELLA = {
    initData: '',
    player: null,
    ws: null,
    game: null,
    ui: null
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
    console.log('VELLA initializing...');

    // Setup Telegram WebApp
    if (tg) {
        tg.ready();
        tg.expand();
        tg.setHeaderColor('#0a0a0f');
        tg.setBackgroundColor('#0a0a0f');

        window.VELLA.initData = tg.initData || '';
        console.log('Telegram WebApp ready');
    } else {
        // Dev mode - create fake init data
        const devUser = {
            id: Math.floor(Math.random() * 1000000),
            username: 'dev_player'
        };
        window.VELLA.initData = `user=${encodeURIComponent(JSON.stringify(devUser))}`;
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
    // Play button
    document.getElementById('btn-play').addEventListener('click', () => {
        joinRoom(null);
    });

    // Join room button
    document.getElementById('btn-join').addEventListener('click', () => {
        showModal('join-modal');
    });

    // Join confirm
    document.getElementById('btn-join-confirm').addEventListener('click', () => {
        const code = document.getElementById('input-room-code').value.toUpperCase().trim();
        if (code.length === 6) {
            hideModal('join-modal');
            joinRoom(code);
        }
    });

    // Join cancel
    document.getElementById('btn-join-cancel').addEventListener('click', () => {
        hideModal('join-modal');
    });

    // Shop button
    document.getElementById('btn-shop').addEventListener('click', () => {
        showShop();
    });

    // Shop back
    document.getElementById('btn-shop-back').addEventListener('click', () => {
        hideScreen('shop-screen');
        showScreen('menu-screen');
    });

    // Ready button
    document.getElementById('btn-ready').addEventListener('click', () => {
        if (window.VELLA.ws) {
            const isReady = document.getElementById('btn-ready').classList.toggle('ready');
            window.VELLA.ws.send({ type: 'ready', is_ready: isReady });
            document.getElementById('ready-text').textContent = isReady ? 'Not Ready' : 'Ready';
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

    window.VELLA.ws.on('room_joined', (data) => {
        document.getElementById('room-code').textContent = data.room_code;
        updateLobbyPlayers(data.players);
    });

    window.VELLA.ws.on('lobby_update', (data) => {
        updateLobbyPlayers(data.players);
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
        showWaveAnnouncement(data.wave, data.zombie_count);
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

    window.VELLA.ws.connect();
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
                ${player.is_ready ? '✓ Ready' : 'Waiting...'}
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
    document.getElementById('announce-zombies').textContent = `${zombieCount} zombies incoming`;

    el.classList.remove('hidden');
    setTimeout(() => {
        el.classList.add('hidden');
    }, 3000);
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
    leaderboard.innerHTML = '<h4>Top Players</h4>';
    data.player_stats.forEach((player, index) => {
        const row = document.createElement('div');
        row.className = 'leaderboard-row';
        row.innerHTML = `
            <span class="rank">#${index + 1}</span>
            <span class="name">${player.username || 'Player'}</span>
            <span class="kills">${player.kills} kills</span>
        `;
        leaderboard.appendChild(row);
    });

    showScreen('gameover-screen');
}

async function showShop() {
    hideScreen('menu-screen');
    showScreen('shop-screen');

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

function renderWeapons(weapons) {
    const grid = document.getElementById('weapons-list');
    grid.innerHTML = '';

    const categoryIcons = {
        pistol: '🔫',
        shotgun: '💥',
        rifle: '🎯',
        sniper: '🎪'
    };

    for (const weapon of weapons) {
        const card = document.createElement('div');
        const equipped = window.VELLA.player?.equipped_weapon === weapon.code;

        let statusClass = '';
        if (equipped) statusClass = 'equipped';
        else if (weapon.owned) statusClass = 'owned';
        else if (!weapon.can_unlock) statusClass = 'locked';

        card.className = `weapon-card ${statusClass}`;
        card.innerHTML = `
            <div class="weapon-icon">${categoryIcons[weapon.category] || '🔫'}</div>
            <div class="weapon-name">${weapon.name}</div>
            <div class="weapon-category">${weapon.category}</div>
            <div class="weapon-stats">
                DMG: ${weapon.damage} | Rate: ${weapon.fire_rate}/s
            </div>
            ${!weapon.owned ? `
                <div class="weapon-price">
                    ${weapon.can_unlock ? `💰 ${weapon.price_coins}` : `🔒 ${weapon.required_kills} kills`}
                </div>
                <button class="btn btn-primary" ${!weapon.can_unlock || weapon.price_coins > (window.VELLA.player?.coins || 0) ? 'disabled' : ''}>
                    Buy
                </button>
            ` : equipped ? `
                <button class="btn btn-secondary" disabled>Equipped</button>
            ` : `
                <button class="btn btn-primary equip-btn" data-code="${weapon.code}">Equip</button>
            `}
        `;

        // Buy button handler
        const buyBtn = card.querySelector('.btn-primary:not(.equip-btn)');
        if (buyBtn && !weapon.owned) {
            buyBtn.addEventListener('click', () => buyWeapon(weapon.code));
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
            await loadPlayerData();
            showShop(); // Refresh
        }
    } catch (error) {
        console.error('Failed to buy weapon:', error);
    }
}

async function equipWeapon(code) {
    try {
        const response = await fetch(`/api/weapons/equip?weapon_code=${code}&init_data=${encodeURIComponent(window.VELLA.initData)}`, {
            method: 'POST'
        });

        if (response.ok) {
            window.VELLA.player.equipped_weapon = code;
            showShop(); // Refresh
        }
    } catch (error) {
        console.error('Failed to equip weapon:', error);
    }
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
