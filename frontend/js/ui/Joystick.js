/**
 * Simple Touch Joysticks (no external library)
 * Works reliably on iOS Telegram WebView
 */

export class DualJoystick {
    constructor() {
        this.moveVector = { x: 0, y: 0 };
        this.aimVector = { x: 0, y: -1 };
        this.shooting = false;

        this.leftTouch = null;
        this.rightTouch = null;

        this.leftCenter = null;
        this.rightCenter = null;

        this.leftStick = null;
        this.rightStick = null;
        this.leftBase = null;
        this.rightBase = null;

        this.maxDistance = 50;

        this.init();
    }

    init() {
        // Create joystick elements
        this.createJoystickElements('joystick-left', 'left');
        this.createJoystickElements('joystick-right', 'right');

        // Bind touch events
        const leftZone = document.getElementById('joystick-left');
        const rightZone = document.getElementById('joystick-right');

        if (leftZone) {
            leftZone.addEventListener('touchstart', (e) => this.onTouchStart(e, 'left'), { passive: false });
            leftZone.addEventListener('touchmove', (e) => this.onTouchMove(e, 'left'), { passive: false });
            leftZone.addEventListener('touchend', (e) => this.onTouchEnd(e, 'left'), { passive: false });
            leftZone.addEventListener('touchcancel', (e) => this.onTouchEnd(e, 'left'), { passive: false });
        }

        if (rightZone) {
            rightZone.addEventListener('touchstart', (e) => this.onTouchStart(e, 'right'), { passive: false });
            rightZone.addEventListener('touchmove', (e) => this.onTouchMove(e, 'right'), { passive: false });
            rightZone.addEventListener('touchend', (e) => this.onTouchEnd(e, 'right'), { passive: false });
            rightZone.addEventListener('touchcancel', (e) => this.onTouchEnd(e, 'right'), { passive: false });
        }

        console.log('Custom joysticks initialized');
    }

    createJoystickElements(zoneId, side) {
        const zone = document.getElementById(zoneId);
        if (!zone) return;

        // Base circle (outer ring)
        const base = document.createElement('div');
        base.className = 'joystick-base';
        base.style.cssText = `
            position: absolute;
            width: 100px;
            height: 100px;
            border-radius: 50%;
            border: 3px solid ${side === 'left' ? 'rgba(74, 222, 128, 0.6)' : 'rgba(233, 69, 96, 0.6)'};
            background: ${side === 'left' ? 'rgba(74, 222, 128, 0.15)' : 'rgba(233, 69, 96, 0.15)'};
            display: none;
            pointer-events: none;
        `;
        zone.appendChild(base);

        // Stick (inner circle)
        const stick = document.createElement('div');
        stick.className = 'joystick-stick';
        stick.style.cssText = `
            position: absolute;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: ${side === 'left' ? 'rgba(74, 222, 128, 0.8)' : 'rgba(233, 69, 96, 0.8)'};
            display: none;
            pointer-events: none;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        `;
        zone.appendChild(stick);

        if (side === 'left') {
            this.leftBase = base;
            this.leftStick = stick;
        } else {
            this.rightBase = base;
            this.rightStick = stick;
        }
    }

    onTouchStart(e, side) {
        e.preventDefault();

        const touch = e.changedTouches[0];
        if (!touch) return;

        const zone = e.currentTarget;
        const rect = zone.getBoundingClientRect();
        const x = touch.clientX - rect.left;
        const y = touch.clientY - rect.top;

        if (side === 'left') {
            this.leftTouch = touch.identifier;
            this.leftCenter = { x, y };
            this.showJoystick(this.leftBase, this.leftStick, x, y);
        } else {
            this.rightTouch = touch.identifier;
            this.rightCenter = { x, y };
            this.showJoystick(this.rightBase, this.rightStick, x, y);
            this.shooting = true;
        }
    }

    onTouchMove(e, side) {
        e.preventDefault();

        for (const touch of e.changedTouches) {
            if (side === 'left' && touch.identifier === this.leftTouch) {
                this.updateJoystick(touch, e.currentTarget, 'left');
            } else if (side === 'right' && touch.identifier === this.rightTouch) {
                this.updateJoystick(touch, e.currentTarget, 'right');
            }
        }
    }

    onTouchEnd(e, side) {
        e.preventDefault();

        for (const touch of e.changedTouches) {
            if (side === 'left' && touch.identifier === this.leftTouch) {
                this.leftTouch = null;
                this.leftCenter = null;
                this.hideJoystick(this.leftBase, this.leftStick);
                this.moveVector = { x: 0, y: 0 };
            } else if (side === 'right' && touch.identifier === this.rightTouch) {
                this.rightTouch = null;
                this.rightCenter = null;
                this.hideJoystick(this.rightBase, this.rightStick);
                this.shooting = false;
            }
        }
    }

    updateJoystick(touch, zone, side) {
        const rect = zone.getBoundingClientRect();
        const x = touch.clientX - rect.left;
        const y = touch.clientY - rect.top;

        const center = side === 'left' ? this.leftCenter : this.rightCenter;
        const stick = side === 'left' ? this.leftStick : this.rightStick;

        if (!center || !stick) return;

        let dx = x - center.x;
        let dy = y - center.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        // Clamp to max distance
        if (distance > this.maxDistance) {
            dx = (dx / distance) * this.maxDistance;
            dy = (dy / distance) * this.maxDistance;
        }

        // Update stick position
        stick.style.left = `${center.x + dx - 25}px`;
        stick.style.top = `${center.y + dy - 25}px`;

        // Normalize to -1 to 1
        const normX = dx / this.maxDistance;
        const normY = dy / this.maxDistance;

        if (side === 'left') {
            this.moveVector = { x: normX, y: normY };
        } else {
            // For aim, we want direction even at small movements
            if (distance > 5) {
                this.aimVector = { x: dx / distance, y: dy / distance };
            }
            this.shooting = distance > 10;
        }
    }

    showJoystick(base, stick, x, y) {
        if (base) {
            base.style.display = 'block';
            base.style.left = `${x - 50}px`;
            base.style.top = `${y - 50}px`;
        }
        if (stick) {
            stick.style.display = 'block';
            stick.style.left = `${x - 25}px`;
            stick.style.top = `${y - 25}px`;
        }
    }

    hideJoystick(base, stick) {
        if (base) base.style.display = 'none';
        if (stick) stick.style.display = 'none';
    }

    getInput() {
        return {
            moveX: this.moveVector.x,
            moveY: this.moveVector.y,
            aimX: this.aimVector.x,
            aimY: this.aimVector.y,
            shooting: this.shooting
        };
    }

    destroy() {
        // Remove event listeners would go here if needed
    }
}
