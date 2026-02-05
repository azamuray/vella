/**
 * UI Manager
 * Handles UI state and animations
 */

export class UIManager {
    constructor() {
        this.currentScreen = 'loading';
        this.setupTouchPrevention();
    }

    setupTouchPrevention() {
        // Prevent default touch behaviors that interfere with game
        document.addEventListener('touchmove', (e) => {
            if (e.target.closest('#game-container, .joystick-zone')) {
                e.preventDefault();
            }
        }, { passive: false });

        // Prevent double-tap zoom
        document.addEventListener('dblclick', (e) => {
            e.preventDefault();
        });

        // Prevent context menu
        document.addEventListener('contextmenu', (e) => {
            e.preventDefault();
        });
    }

    showNotification(message, type = 'info') {
        // Could implement toast notifications
        console.log(`[${type}] ${message}`);
    }

    showDamageNumber(x, y, damage) {
        // Floating damage numbers - could be implemented in Phaser scene
    }

    showKillFeed(killerName, victimName, weaponName) {
        // Kill feed in top right corner
    }
}
