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
}

function sendReady() {
    if (window.VELLA.ws && window.VELLA.inWaveBreak) {
        window.VELLA.ws.send({ type: 'ready', is_ready: true });

        // Update button states
        const waveReadyBtn = document.getElementById('btn-next-wave');
        waveReadyBtn.textContent = '✓ Ready!';
        waveReadyBtn.classList.add('ready');
        waveReadyBtn.disabled = true;

        const shopReadyBtn = document.getElementById('btn-shop-ready');
        shopReadyBtn.textContent = '✓ Ready!';
        shopReadyBtn.disabled = true;
    }
}

function showRoomsBrowser() {
    showModal('rooms-modal');
    loadPublicRooms();
}

async function loadPublicRooms() {
    const listEl = document.getElementById('rooms-list');
    listEl.innerHTML = '<p class="loading-rooms">Loading...</p>';

    try {
        const response = await fetch('/api/rooms');
        const rooms = await response.json();

        if (rooms.length === 0) {
            listEl.innerHTML = '<p class="no-rooms">No public rooms available.<br>Create your own!</p>';
            return;
        }

        listEl.innerHTML = '';
        for (const room of rooms) {
            const item = document.createElement('div');
            item.className = 'room-item';
            item.innerHTML = `
                <div class="room-info">
                    <div class="room-host">${room.host || 'Unknown'}</div>
                    <div class="room-players">${room.player_count}/${room.max_players} players</div>
                </div>
                <button class="btn btn-primary btn-join-room" data-code="${room.room_code}">Join</button>
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
        listEl.innerHTML = '<p class="no-rooms">Failed to load rooms</p>';
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
        alert(data.message || 'Error');
        hideScreen('lobby-screen');
        showScreen('menu-screen');
        if (window.VELLA.ws) {
            window.VELLA.ws.disconnect();
            window.VELLA.ws = null;
        }
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
    document.getElementById('announce-zombies').textContent = `Starting in ${remaining}...`;
    el.classList.remove('hidden');

    window.VELLA.countdownInterval = setInterval(() => {
        remaining--;
        if (remaining > 0) {
            document.getElementById('announce-zombies').textContent = `Starting in ${remaining}...`;
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
    readyBtn.textContent = '✓ Ready';
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
                        Buy with Stars
                    </button>
                `;
            } else {
                priceSection = `
                    <div class="weapon-price">💰 ${weapon.price_coins}</div>
                    <button class="btn btn-primary buy-coins-btn" ${!canAfford ? 'disabled' : ''} data-code="${weapon.code}">
                        Buy
                    </button>
                `;
            }
        } else if (equipped) {
            priceSection = `<button class="btn btn-secondary" disabled>Equipped</button>`;
        } else {
            priceSection = `<button class="btn btn-primary equip-btn" data-code="${weapon.code}">Equip</button>`;
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
        alert('Telegram WebApp not available');
        return;
    }

    try {
        // Create invoice on backend
        const response = await fetch(`/api/payments/create-invoice?weapon_code=${code}&init_data=${encodeURIComponent(window.VELLA.initData)}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            alert(error.detail || 'Failed to create invoice');
            return;
        }

        const { invoice_url } = await response.json();

        // Open Telegram payment dialog
        tg.openInvoice(invoice_url, async (status) => {
            console.log('[Payment] Status:', status);
            if (status === 'paid') {
                window.playSound('weapon_switch', 0.5);
                alert('Purchase successful! 🎉');
                await loadPlayerData();
                // Refresh shop (keep inGameShop state)
                if (window.VELLA.inGameShop) {
                    showInGameShop();
                } else {
                    showShop();
                }
            } else if (status === 'failed') {
                alert('Payment failed');
            }
            // 'cancelled' - user closed the dialog
        });
    } catch (error) {
        console.error('Failed to buy with Stars:', error);
        alert('Error processing payment');
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
