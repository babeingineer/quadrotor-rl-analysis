"""Body-rate PI controller + mixer, extracted from RateVelAviary._control_wrench.
Constants are identical to the env. Runs at the 500 Hz inner-loop rate.

Inputs  : roll/pitch/yaw rate set-points + mean throttle, and current BODY-frame
          angular velocity (rad/s).
Output  : the 4 motor FORCE commands (N), clipped to [0, MOTOR_MAX].
"""
import numpy as np


class RatePIController:
    # ---- constants (identical to RateVelAviary) ----
    MOTOR_MAX        = 40.0                          # N per motor
    MAX_TOTAL_THRUST = 4 * MOTOR_MAX                 # 160 N
    NOMINAL_MASS     = 3.5                            # kg
    NOMINAL_HOVER    = NOMINAL_MASS * 9.8            # 34.3 N  (thrust at throttle = 0)
    ARM              = 0.30                           # m (center to motor)
    YAW_RATIO        = 0.02                           # KM/KF (yaw drag-torque per force)
    J_NOMINAL        = np.array([0.06, 0.03, 0.06])   # kg m^2 at NOMINAL_MASS
    MAX_RATE         = np.array([4.0, 4.0, 2.0])      # rad/s (roll, pitch, yaw)
    KP               = np.array([6.0, 6.0, 4.0])      # P gain (ang-accel per rate error)
    KI               = np.array([0.5, 0.5, 0.3])      # I gain
    INT_LIMIT        = 5.0                             # anti-windup clamp on the integral
    DT               = 1.0 / 500.0                     # inner-loop timestep (500 Hz)

    def __init__(self, inertia=None, dt=None):
        a = self.ARM / np.sqrt(2.0)                   # motor moment arm (X-config)
        b = self.YAW_RATIO
        # MIX: [T, tau_x, tau_y, tau_z] = MIX @ [f0, f1, f2, f3]  (CF2X X-config signs)
        self.MIX = np.array([[ 1.0,  1.0,  1.0,  1.0],   # total thrust
                             [-a,   -a,    a,    a  ],   # roll  torque (x)
                             [-a,    a,    a,   -a  ],   # pitch torque (y)
                             [-b,    b,   -b,    b  ]],  # yaw   torque (z)
                            dtype=float)
        self.MIX_INV = np.linalg.inv(self.MIX)
        self.J = np.array(inertia, float) if inertia is not None else self.J_NOMINAL.copy()
        self.dt = self.DT if dt is None else float(dt)
        self.reset()

    def reset(self):
        self.integral = np.zeros(3)                   # per-axis rate-error integral

    @classmethod
    def throttle_to_thrust(cls, a_T):
        """Normalized mean throttle a_T in [-1,1] -> collective thrust (N).
        0 -> nominal hover, +1 -> max total thrust, -1 -> zero."""
        a_T = float(np.clip(a_T, -1.0, 1.0))
        if a_T >= 0.0:
            return cls.NOMINAL_HOVER + a_T * (cls.MAX_TOTAL_THRUST - cls.NOMINAL_HOVER)
        return cls.NOMINAL_HOVER * (1.0 + a_T)

    def update(self, roll_sp, pitch_sp, yaw_sp, throttle, omega_body):
        """roll_sp/pitch_sp/yaw_sp/throttle : normalized in [-1,1]
           omega_body : current body angular velocity [wx,wy,wz] (rad/s)
           returns    : 4 motor force commands (N), clipped to [0, MOTOR_MAX]."""
        omega_body = np.asarray(omega_body, float).reshape(3)
        omega_sp   = np.array([roll_sp, pitch_sp, yaw_sp], float) * self.MAX_RATE   # -> rad/s
        thrust     = self.throttle_to_thrust(throttle)                              # -> N

        # ---- PI on the body-rate error ----
        err = omega_sp - omega_body
        self.integral = np.clip(self.integral + err * self.dt, -self.INT_LIMIT, self.INT_LIMIT)
        ang_acc = self.KP * err + self.KI * self.integral       # desired angular accel (rad/s^2)
        tau = self.J * ang_acc                                  # desired body torque (N m): tau = J*alpha

        # ---- mix (thrust + torques -> 4 motor forces) and saturate ----
        f = self.MIX_INV @ np.array([thrust, tau[0], tau[1], tau[2]])
        return np.clip(f, 0.0, self.MOTOR_MAX)                  # 4 motor force commands (N)


if __name__ == "__main__":
    # example: command +20 deg/s roll from rest, hover throttle
    c = RatePIController()
    omega = np.zeros(3)                                          # current body rate (rad/s)
    roll_sp_norm = np.radians(20.0) / c.MAX_RATE[0]             # 20 deg/s -> normalized
    f = c.update(roll_sp_norm, 0.0, 0.0, 0.0, omega)
    print("motor forces (N):", np.round(f, 3), " normalized:", np.round(f / c.MOTOR_MAX, 3))
