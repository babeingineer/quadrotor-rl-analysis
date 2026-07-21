"""RateVelAviary — velocity tracking for a heavy quadrotor with domain randomization.

Task
----
Track a random 3-D target velocity. Direction uniform on the unit sphere, speed
Uniform(0, MAX_SPEED) m/s (0 == hover).

Airframe (heavy quad, NOT the CF2X Crazyflie)
---------------------------------------------
* Mass randomized per episode: Uniform(MASS_MIN, MASS_MAX) kg (default 9-11).
* 4 motors, each producing 0 .. MOTOR_MAX_THRUST N (default 40 N -> 160 N total).
* Wind: constant per episode, random direction, speed Uniform(0, WIND_MAX) m/s,
  acting through relative-airspeed (quadratic) drag.

Control architecture
--------------------
The RL policy outputs a normalized CTBR (Collective Thrust + Body Rate) command
[a_T, a_p, a_q, a_r] in [-1,1]^4. A PID inner loop tracks the body-rate set-point.
Per-motor forces are clipped to [0, MOTOR_MAX_THRUST] (motor saturation couples the
achievable thrust and torque), and the *achieved* wrench is applied analytically to
the base link. Mass/inertia are set per episode via ``changeDynamics``; wind drag and
gravity are handled by the real PyBullet integrator (``Physics.PYB``, stepSimulation).

Because the wrench is applied analytically, the drone geometry (arm length, yaw ratio,
inertia) is defined here and does NOT depend on the loaded URDF's link geometry.
"""
import numpy as np
import pybullet as p
from gymnasium import spaces

from gym_pybullet_drones.envs.BaseAviary import BaseAviary
from gym_pybullet_drones.utils.enums import DroneModel, Physics


class RateVelAviary(BaseAviary):

    def __init__(self,
                 initial_xyzs=None,
                 initial_rpys=None,
                 pyb_freq: int = 500,
                 ctrl_freq: int = 50,
                 gui: bool = False,
                 record: bool = False,
                 # --- task ---
                 task: str = "velocity",      # "velocity" or "position"
                 episode_len_sec: float = 8.0,
                 max_speed: float = 20.0,
                 pos_range: float = 30.0,     # position task: target radius (m); sets max cruise speed
                 speed_cap: float = 18.0,     # position task: soft speed cap (m/s)
                 # --- airframe / domain randomization ---
                 mass_range=(9.0, 11.0),      # kg, sampled per episode
                 motor_max_thrust: float = 40.0,   # N per motor
                 arm_length: float = 0.35,    # m (center to motor)
                 yaw_ratio: float = 0.02,     # KM/KF, motor drag-torque per thrust (m)
                 inertia_nominal=(0.20, 0.20, 0.35),  # kg m^2 at 10 kg (scales with mass)
                 # --- wind ---
                 wind_max: float = 20.0,      # m/s
                 drag_coeff: float = 0.08,    # F_drag = -drag_coeff*|v_rel|*v_rel (N per (m/s)^2)
                 # --- motor dynamics (first-order lag toward commanded thrust) ---
                 motor_tau_range=(0.10, 0.25),  # s, time constant sampled per episode (0 = ideal)
                 # --- CTBR command limits ---
                 max_rate_rp: float = 4.0,    # rad/s roll & pitch rate range
                 max_rate_yaw: float = 2.0,   # rad/s yaw rate range
                 # --- inner-loop rate PID gains (angular-accel per rate error) ---
                 # NB: gains lowered vs the ideal-motor env — a 0.1-0.25 s actuator lag
                 # in the loop cuts phase margin, so high gains would oscillate.
                 kp_rate=(6.0, 6.0, 4.0),
                 ki_rate=(0.5, 0.5, 0.3),
                 int_limit: float = 5.0,
                 ):
        # ---- config (must be set before super().__init__ -> _housekeeping) ----
        assert task in ("velocity", "position"), task
        self.TASK = task
        self.EPISODE_LEN_SEC = episode_len_sec
        self.MAX_SPEED = float(max_speed)
        self.POS_RANGE = float(pos_range)
        self.SPEED_CAP = float(speed_cap)
        self.MASS_RANGE = (float(mass_range[0]), float(mass_range[1]))
        self.MOTOR_MAX = float(motor_max_thrust)
        self.ARM = float(arm_length)
        self.YAW_RATIO = float(yaw_ratio)
        self.J_NOMINAL = np.array(inertia_nominal, dtype=float)   # at 10 kg
        self.WIND_MAX = float(wind_max)
        self.WIND_DRAG = float(drag_coeff)   # NB: BaseAviary owns self.DRAG_COEFF (URDF)
        self.MOTOR_TAU_RANGE = (float(motor_tau_range[0]), float(motor_tau_range[1]))
        self.MAX_RATE = np.array([max_rate_rp, max_rate_rp, max_rate_yaw], dtype=float)
        self.KP_RATE = np.array(kp_rate, dtype=float)
        self.KI_RATE = np.array(ki_rate, dtype=float)
        self.INT_LIMIT = float(int_limit)

        self.MAX_TOTAL_THRUST = 4.0 * self.MOTOR_MAX             # 160 N
        self.NOMINAL_MASS = 10.0                                 # mass used by onboard estimator
        self.NOMINAL_HOVER = self.NOMINAL_MASS * 9.8             # thrust at a_T=0 (nominal 10 kg)
        self.MOTOR_MAX_RPM = 8000.0                              # for force<->RPM reporting (ESC units)
        self.WIND_EST_ALPHA = 0.5                                # EMA filter on disturbance estimate

        if initial_xyzs is None:
            initial_xyzs = np.array([[0.0, 0.0, 2.0]])

        # runtime state (set in _housekeeping each reset)
        self.M = 10.0
        self.J_DIAG = self.J_NOMINAL.copy()
        self.wind = np.zeros(3)
        self.target_vel = np.zeros(3)
        self.target_pos = np.zeros(3)        # position task
        self.rate_integral = np.zeros(3)
        self.current_action = np.zeros(4)
        self.prev_action = np.zeros(4)
        self.motor_tau = 0.0                 # per-episode motor time constant (s)
        self.motor_alpha = 1.0               # per-substep smoothing = 1-exp(-dt/tau)
        self.motor_forces = np.zeros(4)      # actual (lagged) per-motor thrust (N)
        self.prev_vel = np.zeros(3)          # velocity at previous step (for accel estimate)
        self.wind_est = np.zeros(3)          # disturbance-observer wind force estimate (N, world)

        super().__init__(drone_model=DroneModel.CF2X,  # URDF only for body/visual; dynamics overridden
                         num_drones=1,
                         initial_xyzs=initial_xyzs,
                         initial_rpys=initial_rpys,
                         physics=Physics.PYB,
                         pyb_freq=pyb_freq,
                         ctrl_freq=ctrl_freq,
                         gui=gui,
                         record=record,
                         obstacles=False,
                         user_debug_gui=False)

        # ---- control mixer: [T, tau_x, tau_y, tau_z] = MIX @ [f0,f1,f2,f3] ----
        # X-config, motor moment arm a = ARM/sqrt(2); yaw torque per force = YAW_RATIO.
        # Motor sign convention matches BaseAviary._dynamics CF2X.
        a = self.ARM / np.sqrt(2.0)
        b = self.YAW_RATIO
        self.MIX = np.array([[1.0, 1.0, 1.0, 1.0],
                             [-a,  -a,   a,   a ],
                             [-a,   a,   a,  -a ],
                             [-b,   b,  -b,   b ]], dtype=float)
        self.MIX_INV = np.linalg.inv(self.MIX)

    # ------------------------------------------------------------------ spaces
    def _actionSpace(self):
        return spaces.Box(low=-1.0, high=1.0, shape=(4,), dtype=np.float32)

    def _observationSpace(self):
        # [vel_err(3), target_vel(3), R(9), omega_body(3), last_action(4),
        #  motor_rpm(4), wind_force_est(3)] = 29
        return spaces.Box(low=-np.inf, high=np.inf, shape=(29,), dtype=np.float32)

    # ------------------------------------------------- reset / domain random.
    def _housekeeping(self):
        super()._housekeeping()
        self.rate_integral = np.zeros(3)
        self.current_action = np.zeros(4)
        self.prev_action = np.zeros(4)

        # --- randomize airframe mass + inertia (inertia scales with mass) ---
        self.M = float(self.np_random.uniform(*self.MASS_RANGE))
        self.J_DIAG = self.J_NOMINAL * (self.M / 10.0)
        p.changeDynamics(int(self.DRONE_IDS[0]), -1,
                         mass=self.M,
                         localInertiaDiagonal=self.J_DIAG.tolist(),
                         linearDamping=0.0, angularDamping=0.0,
                         physicsClientId=self.CLIENT)

        # --- randomize wind (constant per episode) ---
        wdir = self.np_random.normal(size=3)
        n = np.linalg.norm(wdir)
        wdir = wdir / n if n > 1e-6 else np.array([1.0, 0.0, 0.0])
        self.wind = wdir * self.np_random.uniform(0.0, self.WIND_MAX)

        # --- randomize motor lag (hidden parameter; per-episode time constant) ---
        self.motor_tau = float(self.np_random.uniform(*self.MOTOR_TAU_RANGE))
        self.motor_alpha = (1.0 if self.motor_tau <= 1e-6
                            else 1.0 - np.exp(-self.PYB_TIMESTEP / self.motor_tau))
        self.motor_forces = np.full(4, self.M * 9.8 / 4.0)   # start at hover equilibrium
        self.prev_vel = np.zeros(3)
        self.wind_est = np.zeros(3)

        self._resample_target()

        # position irrelevant -> fly freely (incl. downward targets / drift in wind)
        p.setCollisionFilterPair(int(self.PLANE_ID), int(self.DRONE_IDS[0]),
                                 -1, -1, enableCollision=0, physicsClientId=self.CLIENT)

    def _resample_target(self):
        d = self.np_random.normal(size=3)
        n = np.linalg.norm(d)
        d = d / n if n > 1e-6 else np.array([1.0, 0.0, 0.0])
        if self.TASK == "velocity":
            self.target_vel = d * self.np_random.uniform(0.0, self.MAX_SPEED)
        else:  # position: target within POS_RANGE of the current position (incl. near 0)
            dist = self.np_random.uniform(0.0, self.POS_RANGE)
            self.target_pos = self.pos[0] + d * dist

    # ------------------------------------------------------- CTBR decode + PID
    def _decode_action(self, action):
        a = np.clip(np.asarray(action, dtype=float).reshape(4), -1.0, 1.0)
        a_T = a[0]
        if a_T >= 0.0:
            thrust = self.NOMINAL_HOVER + a_T * (self.MAX_TOTAL_THRUST - self.NOMINAL_HOVER)
        else:
            thrust = self.NOMINAL_HOVER * (1.0 + a_T)
        omega_des = a[1:4] * self.MAX_RATE
        return float(thrust), omega_des

    def _control_wrench(self, thrust_des, omega_des):
        """PID rate inner loop -> achieved (T, tau_body) after per-motor saturation."""
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        omega_body = R.T @ self.ang_v[0]                      # world -> body rates
        err = omega_des - omega_body
        self.rate_integral = np.clip(self.rate_integral + err * self.PYB_TIMESTEP,
                                     -self.INT_LIMIT, self.INT_LIMIT)
        ang_acc = self.KP_RATE * err + self.KI_RATE * self.rate_integral
        tau_des = self.J_DIAG * ang_acc
        forces_cmd = self.MIX_INV @ np.array([thrust_des, tau_des[0], tau_des[1], tau_des[2]])
        forces_cmd = np.clip(forces_cmd, 0.0, self.MOTOR_MAX)  # motor saturation (0..40 N)
        # first-order motor lag: actual thrust relaxes toward the command each substep
        self.motor_forces += (forces_cmd - self.motor_forces) * self.motor_alpha
        wrench = self.MIX @ self.motor_forces                 # achieved [T, tau_x, tau_y, tau_z]
        return R, wrench[0], wrench[1:]

    def _preprocessAction(self, action):
        # Not used (step() overrides the substep loop); kept for BaseAviary API.
        return np.zeros((1, 4))

    def _apply_wrench_and_wind(self, R, thrust, tau_body):
        did = int(self.DRONE_IDS[0])
        # thrust along body +z, expressed in world
        f_thrust = R[:, 2] * thrust
        # wind drag from relative airspeed (world frame), at COM -> pure force
        v_rel = self.vel[0] - self.wind
        f_wind = -self.WIND_DRAG * np.linalg.norm(v_rel) * v_rel
        p.applyExternalForce(did, -1, (f_thrust + f_wind).tolist(),
                             self.pos[0].tolist(), p.WORLD_FRAME, physicsClientId=self.CLIENT)
        # body torque -> world (avoid pybullet LINK_FRAME torque quirks)
        tau_world = R @ tau_body
        p.applyExternalTorque(did, -1, tau_world.tolist(), p.WORLD_FRAME, physicsClientId=self.CLIENT)

    # ------------------------------------------------------------------- step
    def step(self, action):
        """Hold the policy CTBR set-point constant while the PID inner loop runs every
        physics sub-step (inner loop @ PYB_FREQ); apply achieved wrench + wind + gravity."""
        self.current_action = np.clip(np.asarray(action, dtype=float).reshape(4), -1.0, 1.0)
        thrust_des, omega_des = self._decode_action(self.current_action)
        v_prev = self.vel[0].copy()                       # for the acceleration estimate

        for _ in range(self.PYB_STEPS_PER_CTRL):
            R, thrust, tau_body = self._control_wrench(thrust_des, omega_des)
            self._apply_wrench_and_wind(R, thrust, tau_body)
            p.stepSimulation(physicsClientId=self.CLIENT)
            self._updateAndStoreKinematicInformation()

        self._update_wind_estimate(v_prev)               # disturbance observer
        obs = self._computeObs()
        reward = self._computeReward()
        terminated = self._computeTerminated()
        truncated = self._computeTruncated()
        info = self._computeInfo()
        self.step_counter += self.PYB_STEPS_PER_CTRL
        self.prev_action = self.current_action.copy()
        return obs, reward, terminated, truncated, info

    def _update_wind_estimate(self, v_prev):
        """Disturbance observer: recover external (wind) force from the force balance
        m*a = F_thrust + F_gravity + F_wind, using NOMINAL mass + achieved thrust (i.e.
        exactly what an onboard estimator has). Target-independent -> transfers to
        real-time changing targets. EMA-filtered."""
        a = (self.vel[0] - v_prev) / self.CTRL_TIMESTEP          # finite-difference accel
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        f_thrust = R[:, 2] * float(np.sum(self.motor_forces))    # achieved thrust, world
        f_ext = (self.NOMINAL_MASS * a - f_thrust
                 + np.array([0.0, 0.0, self.NOMINAL_MASS * self.G]))
        self.wind_est = ((1 - self.WIND_EST_ALPHA) * self.wind_est
                         + self.WIND_EST_ALPHA * f_ext)

    # ------------------------------------------------------------------- obs
    def _computeObs(self):
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        omega_body = R.T @ self.ang_v[0]
        # motor RPM from actual (lagged) thrust, normalized to [0,1] (ESC telemetry)
        rpm_norm = np.sqrt(np.clip(self.motor_forces / self.MOTOR_MAX, 0.0, 1.0))
        if self.TASK == "velocity":
            first6 = np.concatenate([(self.target_vel - self.vel[0]) / self.MAX_SPEED,   # vel err
                                     self.target_vel / self.MAX_SPEED])                   # target vel
        else:  # position: relative position (clamped to range) + current velocity
            rel = self.target_pos - self.pos[0]
            n = np.linalg.norm(rel)
            if n > self.POS_RANGE:                            # clamp to range (deployment carrot)
                rel = rel * (self.POS_RANGE / n)
            first6 = np.concatenate([rel / self.POS_RANGE,                                # rel pos
                                     self.vel[0] / self.MAX_SPEED])                        # velocity
        obs = np.concatenate([
            first6,                               # 6
            R.reshape(9),                         # 9
            omega_body / self.MAX_RATE[0],        # 3
            self.current_action,                  # 4
            rpm_norm,                             # 4  <- solves motor delay
            self.wind_est / self.NOMINAL_HOVER,   # 3  <- solves steady wind (target-independent)
        ])
        return obs.astype(np.float32)

    # ---------------------------------------------------------------- reward
    def _computeReward(self):
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        omega_body = R.T @ self.ang_v[0]
        smooth = (- 5e-4 * float(omega_body @ omega_body)
                  - 5e-4 * float((self.current_action - self.prev_action)
                                 @ (self.current_action - self.prev_action)))
        if self.TASK == "velocity":
            d = np.linalg.norm(self.vel[0] - self.target_vel)
            reward = (np.exp(-0.5 * (d / 2.0) ** 2)
                      + 0.5 * np.exp(-0.5 * (d / 8.0) ** 2)
                      - 0.02 * d + smooth)
        else:  # position: reach target AND stop there; soft speed cap
            dp = np.linalg.norm(self.target_pos - self.pos[0])
            speed = np.linalg.norm(self.vel[0])
            # NOTE: reward is kept NON-NEGATIVE while alive so the policy never prefers
            # crashing (which terminates) over flying to a far target. A linear positive
            # baseline gives a dense gradient across the whole range; a sharp Gaussian
            # adds terminal precision.
            reward = (np.clip(1.0 - dp / self.POS_RANGE, 0.0, 1.0)  # positive guidance + survival
                      + np.exp(-0.5 * (dp / 1.5) ** 2)             # sharp precision peak at target
                      - 0.02 * np.exp(-0.5 * dp ** 2) * speed       # brake near target (clean stop)
                      - 0.01 * max(0.0, speed - self.SPEED_CAP) ** 2  # soft speed cap
                      + smooth)
        if self._crashed():
            reward -= 10.0
        return float(reward)

    # --------------------------------------------------------- term / trunc
    def _crashed(self):
        rpy = self.rpy[0]
        if abs(rpy[0]) > np.radians(85) or abs(rpy[1]) > np.radians(85):
            return True
        if not np.all(np.isfinite(self.pos[0])) or np.max(np.abs(self.pos[0])) > 1e4:
            return True
        return False

    def _computeTerminated(self):
        return bool(self._crashed())

    def _computeTruncated(self):
        return bool(self.step_counter / self.PYB_FREQ >= self.EPISODE_LEN_SEC)

    def _computeInfo(self):
        return {"target_vel": self.target_vel.copy(),
                "target_pos": self.target_pos.copy(),
                "pos": self.pos[0].copy(),
                "vel": self.vel[0].copy(),
                "mass": self.M,
                "wind": self.wind.copy(),
                "motor_tau": self.motor_tau,
                "wind_est": self.wind_est.copy(),
                "vel_error": float(np.linalg.norm(self.vel[0] - self.target_vel)),
                "pos_error": float(np.linalg.norm(self.pos[0] - self.target_pos))}
