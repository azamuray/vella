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

        // Wait for DOM to be ready
        setTimeout(() => this.createJoysticks(), 100);
    }

    createJoysticks() {
        const leftZone = document.getElementById('joystick-left');
        const rightZone = document.getElementById('joystick-right');

        if (!leftZone || !rightZone) {
            console.error('Joystick zones not found!');
            return;
        }

        console.log('Creating joysticks...');

        try {
            // Left joystick - movement (dynamic mode for better touch support)
            this.moveJoystick = nipplejs.create({
                zone: leftZone,
                mode: 'dynamic',
                color: 'rgba(74, 222, 128, 0.5)',
                size: 120,
                multitouch: true,
                maxNumberOfNipples: 1,
                dataOnly: false,
                restOpacity: 0.5
            });

            // Right joystick - aim and shoot
            this.aimJoystick = nipplejs.create({
                zone: rightZone,
                mode: 'dynamic',
                color: 'rgba(233, 69, 96, 0.5)',
                size: 120,
                multitouch: true,
                maxNumberOfNipples: 1,
                dataOnly: false,
                restOpacity: 0.5
            });

            console.log('Joysticks created successfully');
            this.bindEvents();
        } catch (error) {
            console.error('Failed to create joysticks:', error);
        }
    }

    bindEvents() {
        if (!this.moveJoystick || !this.aimJoystick) {
            console.error('Joysticks not initialized');
            return;
        }

        // Movement joystick
        this.moveJoystick.on('move', (evt, data) => {
            if (!data || !data.force) return;
            const force = Math.min(data.force / 50, 1); // Normalize force
            this.moveVector.x = Math.cos(data.angle.radian) * force;
            this.moveVector.y = -Math.sin(data.angle.radian) * force; // Flip Y for screen coords
        });

        this.moveJoystick.on('end', () => {
            this.moveVector.x = 0;
            this.moveVector.y = 0;
        });

        // Aim joystick
        this.aimJoystick.on('move', (evt, data) => {
            if (!data || !data.force) return;
            const force = Math.min(data.force / 50, 1);
            this.aimVector.x = Math.cos(data.angle.radian);
            this.aimVector.y = -Math.sin(data.angle.radian); // Flip Y

            // Auto-shoot when joystick is moved beyond threshold
            this.shooting = force > 0.2;
        });

        this.aimJoystick.on('end', () => {
            this.shooting = false;
            // Keep last aim direction (don't reset aimVector)
        });

        console.log('Joystick events bound');
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
