/**
 * Dual Joystick Controller
 * Left joystick for movement, right for aiming/shooting
 */

export class DualJoystick {
    constructor() {
        this.moveVector = { x: 0, y: 0 };
        this.aimVector = { x: 0, y: -1 }; // Default aim up
        this.shooting = false;

        this.moveJoystick = null;
        this.aimJoystick = null;

        this.createJoysticks();
    }

    createJoysticks() {
        // Left joystick - movement
        this.moveJoystick = nipplejs.create({
            zone: document.getElementById('joystick-left'),
            mode: 'static',
            position: { left: '80px', bottom: '80px' },
            color: 'rgba(74, 222, 128, 0.3)',
            size: 100,
            lockX: false,
            lockY: false,
            dynamicPage: true
        });

        // Right joystick - aim and shoot
        this.aimJoystick = nipplejs.create({
            zone: document.getElementById('joystick-right'),
            mode: 'static',
            position: { right: '80px', bottom: '80px' },
            color: 'rgba(233, 69, 96, 0.3)',
            size: 100,
            lockX: false,
            lockY: false,
            dynamicPage: true
        });

        this.bindEvents();
    }

    bindEvents() {
        // Movement joystick
        this.moveJoystick.on('move', (evt, data) => {
            const force = Math.min(data.force, 1);
            this.moveVector.x = Math.cos(data.angle.radian) * force;
            this.moveVector.y = -Math.sin(data.angle.radian) * force; // Flip Y for screen coords
        });

        this.moveJoystick.on('end', () => {
            this.moveVector.x = 0;
            this.moveVector.y = 0;
        });

        // Aim joystick
        this.aimJoystick.on('move', (evt, data) => {
            const force = Math.min(data.force, 1);
            this.aimVector.x = Math.cos(data.angle.radian);
            this.aimVector.y = -Math.sin(data.angle.radian); // Flip Y

            // Auto-shoot when joystick is moved beyond threshold
            this.shooting = force > 0.3;
        });

        this.aimJoystick.on('end', () => {
            this.shooting = false;
            // Keep last aim direction (don't reset aimVector)
        });
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
        if (this.moveJoystick) {
            this.moveJoystick.destroy();
            this.moveJoystick = null;
        }
        if (this.aimJoystick) {
            this.aimJoystick.destroy();
            this.aimJoystick = null;
        }
    }
}
