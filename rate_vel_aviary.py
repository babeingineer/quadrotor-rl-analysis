"""RateVelAviary — velocity + heading tracking for a quadrotor TAILSITTER VTOL.

Task (velyaw)
-------------
Two objectives held for the whole episode:
  1. match current 3-D velocity to a target (random direction, 0..MAX_SPEED m/s);
  2. match current heading (yaw) to a commanded desired_yaw.
under domain randomization (mass, wind, wing area, motor lag, yaw-torque bias).

Airframe (small tailsitter VTOL — 4 motors + 2 fixed wings, no control surfaces)
--------------------------------------------------------------------------------
* Mass Uniform(MASS_MIN, MASS_MAX) kg per episode; 4 motors, 0..MOTOR_MAX_THRUST N each.
* 2 fixed wings: flat-plate aero valid across the full 0-90 deg AoA a tailsitter sweeps:
  CL = 2 sin a cos a, CD = CD0 + 2 sin^2 a. Force at the COM, no aero moment.
* Wind: constant per episode; enters through the air-relative velocity that drives the wings.

Control
-------
Policy outputs normalized CTBR [a_T, a_p, a_q, a_r] in [-1,1]^4. A PID inner loop tracks the
body-rate set-point at PYB_FREQ; per-motor forces are clipped (saturation couples thrust and
torque) and the achieved wrench is applied analytically (drone geometry is defined here, not
from the URDF). Mass/inertia set per episode; wing aero + gravity applied to the PYB integrator.
"""
import numpy as np
import pybullet as p
from gymnasium import spaces

from gym_pybullet_drones.envs.BaseAviary import BaseAviary
from gym_pybullet_drones.utils.enums import DroneModel, Physics
from aero_xwing import func_aero_model


class RateVelAviary(BaseAviary):

    def __init__(self,
                 initial_xyzs=None,
                 initial_rpys=None,
                 pyb_freq: int = 500,
                 ctrl_freq: int = 50,
                 gui: bool = False,
                 record: bool = False,
                 # --- task ---
                 episode_len_sec: float = 8.0,
                 max_speed: float = 25.0,
                 speed_min: float = 0.0,          # min target speed (band-limited training)
                 target_speed_max=None,           # optional target upper bound independent of
                                                  # MAX_SPEED obs/integral normalization
                 # --- airframe / domain randomization (small tailsitter VTOL) ---
                 mass_range=(2.0, 5.0),
                 motor_max_thrust: float = 40.0,   # N per motor (4 -> 160 N total)
                 arm_length: float = 0.30,
                 yaw_ratio: float = 0.02,          # KM/KF, motor drag-torque per thrust (m)
                 inertia_nominal=(0.06, 0.03, 0.06),  # kg m^2 at NOMINAL_MASS (scales w/ mass)
                 randomize_init: bool = False,     # gentle +-40 deg tilt + random vel/heading start
                 tough_init_frac: float = 0.0,     # fraction of episodes started in FAILURE states
                 trim_init_frac: float = 0.0,      # fraction started AT the target in near-trim attitude
                 priv_obs: bool = False,           # append the hidden episode draw to obs
                 #                                   (CRITIC-ONLY consumption via priv_policy.py)
                 att_cmd: bool = False,            # action = attitude setpoint (thrust + desired
                 #                                   body-z + yaw rate) -> inner attitude P ->
                 #                                   rate PID
                 katt: float = 1.5,                # attitude-P gain for att_cmd mode
                 att_rel: bool = False,            # att_cmd variant: the commanded thrust
                 #                                   direction is BODY-RELATIVE
                 #                                   (unit[k*ax, k*ay, 1] rotated by R).
                 #                                   The world-frame form's sensitivity is
                 #                                   1/sqrt(1-|xy|^2) -> blows up at the high
                 #                                   tilts trim requires at speed; this form
                 #                                   has constant conditioning and a neutral
                 #                                   "hold attitude" action at a=0.
                 att_rel_k: float = 0.5,           # max per-step tilt correction = atan(k)
                 trim_ff: bool = False,            # TRIM FEEDFORWARD: the episode's trim
                 #                                   (attitude, elevator, thrust) is solved once
                 #                                   at reset and the policy commands only the
                 #                                   DEVIATION from it. a=0 holds trim, which is
                 #                                   an absolute reference (unlike att_rel).
                 trim_ff_k: float = 0.4,           # tilt deviation scale: max atan(k) ~ 22 deg
                 trim_ff_thrust: float = 0.4,      # thrust deviation span, x NOMINAL_HOVER
                 trim_ff_fin: float = 0.5,         # elevon deviation span, x FIN_MAX
                 trim_ff_true_wind: bool = True,   # index the trim with the TRUE wind
                 #                                   (privileged: ceiling test). False = use the
                 #                                   observer's wind estimate (deployable).
                 fin_assist: float = 0.0,          # att_cmd: elevator follows the pitch-rate
                 #                                   command (fin authority scales with V^2,
                 #                                   motor torque does not); policy fin action
                 #                                   adds on top
                 wind_oversample: float = 0.0,     # fraction of TRAINING episodes whose wind
                 #                                   magnitude is drawn U(8, WIND_MAX) instead
                 #                                   of U(0, WIND_MAX) (strong-wind tail focus)
                 air_obs: bool = False,            # DIAGNOSTIC: actor sees true body-frame
                 #                                   air-relative velocity (3 dims); deployment
                 #                                   would need an observer for this
                 # --- observation features ---
                 use_wind_est: bool = True,        # disturbance-observer external-force estimate
                 use_vel_integral: bool = True,    # leaky+clamped velocity-error integral
                 use_yaw_integral: bool = True,    # leaky+clamped yaw-error integral
                 integral_tau: float = 3.0,        # leak time constant (s): anti-windup + forgets old
                 yaw_integral_tau=None,            # separate leak for the yaw integral
                 #                                   (None = same as integral_tau)
                 # --- heading objective ---
                 yaw_reward_width: float = 0.35,   # rad; sharp-peak width of the heading reward
                 yaw_weight: float = 1.0,          # weight of the heading objective in the reward
                 yaw_bias_max: float = 0.0,        # N*m; per-episode constant yaw-torque disturbance
                 yaw_gate: bool = False,           # gate the yaw reward by velocity success
                 yaw_gate_floor: float = 0.2,      # fraction of the yaw reward that always pays
                 #                                   (higher -> more yaw pressure at high vel error)
                 vel_precision: float = 0.0,       # weight of an extra NARROW velocity peak
                 att_tilt_max: float = 0.0,        # >0: full-sphere thrust axis, max tilt (deg)
                 att_tilt_ext: float = 0.0,        # >0: legacy map to 64 deg then extend to this
                 rel_obs: bool = False,            # add command-scaled velocity error to obs
                 rel_approach: float = 0.0,        # legacy alias: basin + command-keyed linear
                 rel_basin: float = 0.0,           # scale-invariant approach-basin weight only
                 cmd_linear: bool = False,         # key far-field linear pull to command speed
                 rel_width: float = 0.5,           # basin width as a fraction of commanded speed
                 rel_floor: float = 8.0,           # m/s commanded-speed floor (hover/low)
                 #                                   (1 - tanh(d/0.5)): gradient below ~1 m/s, where
                 #                                   the d/2 peak is already ~flat
                 cov_width: float = 0.0,           # wide-coverage Gaussian width (m/s);
                 #                                   0 = default 10*(MAX_SPEED/20)
                 yaw_att_gate: bool = False,       # scale yaw reward by clip(R22,0,1): yaw enforced in
                 #                                   hover (controllable) and released in wing-borne
                 #                                   cruise, where the nose must follow the velocity
                 #                                   vector and a random desired_yaw is unsatisfiable
                 velyaw_heading_frame: bool = False,  # express vel error in the current-heading frame
                 # --- wind / aero ---
                 wind_max: float = 20.0,
                 wing_area: float = 0.40,
                 wing_area_jitter: float = 0.20,
                 air_density: float = 1.225,
                 cd0: float = 0.05,
                 pitot_noise: float = 0.0,
                 # --- aerodynamic MOMENT (static weathervane stability + rate damping) ---
                 use_aero_moment: bool = False,  # off -> force-only aero (legacy); on -> realistic moment
                 cp_offset: float = 0.06,        # m, aero center-of-pressure aft of COM (static stiffness)
                 aero_damp: float = 0.6,         # aerodynamic rate-damping coefficient
                 chord: float = 0.5,             # m, aerodynamic chord (moment-arm scale)
                 # --- XWing aero model (full funcAeroModel port) + XWing mass/motor power ---
                 use_xwing_aero: bool = False,   # replace aero with the ported XWing model + XWing airframe
                 aero_dr: bool = True,           # per-episode aero randomization (17 coeffs +/-20% + Xg
                 #                                 jitter); False = fixed NOMINAL aircraft (ablation)
                 aero_s: float = 1.0, aero_c: float = 1.0, aero_b: float = 1.0,  # aero reference dims
                 # --- motor dynamics (first-order lag) ---
                 motor_tau_range=(0.10, 0.25),
                 # --- CTBR command limits ---
                 max_rate_rp: float = 4.0,
                 max_rate_yaw: float = 2.0,
                 # --- inner-loop rate PID gains (lowered vs ideal-motor: lag cuts phase margin) ---
                 kp_rate=(6.0, 6.0, 4.0),
                 ki_rate=(0.5, 0.5, 0.3),
                 int_limit: float = 5.0,
                 ):
        # ---- config (must be set before super().__init__ -> _housekeeping) ----
        self.EPISODE_LEN_SEC = episode_len_sec
        self.MAX_SPEED = float(max_speed)
        self.SPEED_MIN = float(speed_min)
        self.TARGET_SPEED_MAX = float(max_speed if target_speed_max is None
                                      else target_speed_max)
        if not 0.0 <= self.SPEED_MIN <= self.TARGET_SPEED_MAX <= self.MAX_SPEED:
            raise ValueError("target speed range must satisfy 0 <= speed_min <= "
                             "target_speed_max <= max_speed")
        self.MASS_RANGE = (float(mass_range[0]), float(mass_range[1]))
        self.MOTOR_MAX = float(motor_max_thrust)
        self.ARM = float(arm_length)
        self.YAW_RATIO = float(yaw_ratio)
        self.J_NOMINAL = np.array(inertia_nominal, dtype=float)
        self.RANDOMIZE_INIT = bool(randomize_init)
        self.TOUGH_INIT_FRAC = float(tough_init_frac)
        self.TRIM_INIT_FRAC = float(trim_init_frac)
        self._trim_table = None                    # lazy-loaded trim_table.npz
        self.PRIV_OBS = bool(priv_obs)
        self.ATT_CMD = bool(att_cmd)
        self.KATT = float(katt)
        self.ATT_REL = bool(att_rel)
        self.ATT_REL_K = float(att_rel_k)
        self.TRIM_FF = bool(trim_ff)
        self.TRIM_FF_K = float(trim_ff_k)
        self.TRIM_FF_THRUST = float(trim_ff_thrust)
        self.TRIM_FF_FIN = float(trim_ff_fin)
        self.TRIM_FF_TRUE_WIND = bool(trim_ff_true_wind)
        self._ff = None                            # (R_trim, de_trim, T_trim) or None
        self.FIN_ASSIST = float(fin_assist)
        self.WIND_OVERSAMPLE = float(wind_oversample)
        self.AIR_OBS = bool(air_obs)
        self._bz_des = None
        self._yaw_rate_des = 0.0
        self._omega_des_last = np.zeros(3)
        self.USE_WIND_EST = bool(use_wind_est)
        self.USE_VEL_INTEGRAL = bool(use_vel_integral)
        self.USE_YAW_INTEGRAL = bool(use_yaw_integral)
        self.INTEGRAL_TAU = float(integral_tau)
        # separate leak for the YAW integral: at speed the heading error is unsatisfiable by
        # design (nose follows the velocity vector), so a long-memory yaw integral rails at
        # +-pi and becomes a saturated, misleading input. None -> share INTEGRAL_TAU (legacy).
        self.YAW_INTEGRAL_TAU = float(integral_tau if yaw_integral_tau is None
                                      else yaw_integral_tau)
        self.YAW_REWARD_WIDTH = float(yaw_reward_width)
        self.YAW_WEIGHT = float(yaw_weight)
        self.YAW_BIAS_MAX = float(yaw_bias_max)
        self.YAW_GATE = bool(yaw_gate)
        self.YAW_GATE_FLOOR = float(yaw_gate_floor)
        self.VEL_PRECISION = float(vel_precision)
        if rel_approach > 0.0 and (rel_basin != 0.0 or cmd_linear):
            raise ValueError("rel_approach is the legacy combined alias; do not combine it with "
                             "rel_basin or cmd_linear")
        self.ATT_TILT_MAX = float(att_tilt_max)
        self.ATT_TILT_EXT = float(att_tilt_ext)
        self.REL_OBS = bool(rel_obs)
        self.REL_APPROACH = float(rel_approach)     # retained for old configs/introspection
        self.REL_BASIN = float(rel_approach if rel_approach > 0.0 else rel_basin)
        self.CMD_LINEAR = bool(rel_approach > 0.0 or cmd_linear)
        self.REL_WIDTH = float(rel_width)
        self.REL_FLOOR = float(rel_floor)
        self.COV_WIDTH = float(cov_width)
        self.YAW_ATT_GATE = bool(yaw_att_gate)
        self.VELYAW_HEADING_FRAME = bool(velyaw_heading_frame)
        self.WIND_MAX = float(wind_max)
        self.MOTOR_TAU_RANGE = (float(motor_tau_range[0]), float(motor_tau_range[1]))
        self.MAX_RATE = np.array([max_rate_rp, max_rate_rp, max_rate_yaw], dtype=float)
        self.KP_RATE = np.array(kp_rate, dtype=float)
        self.KI_RATE = np.array(ki_rate, dtype=float)
        self.INT_LIMIT = float(int_limit)

        self.MAX_TOTAL_THRUST = 4.0 * self.MOTOR_MAX             # 160 N
        self.NOMINAL_MASS = 3.5                                  # mass used by onboard estimator/hover
        self.NOMINAL_HOVER = self.NOMINAL_MASS * 9.8            # thrust at a_T=0
        self.MOTOR_MAX_RPM = 8000.0
        self.WIND_EST_ALPHA = 0.5                               # EMA on disturbance estimate
        self.WING_AREA_NOM = float(wing_area)
        self.WING_JITTER = float(wing_area_jitter)
        self.RHO = float(air_density)
        self.CD0 = float(cd0)
        self.PITOT_NOISE = float(pitot_noise)
        self.wing_area = self.WING_AREA_NOM
        self.USE_AERO_MOMENT = bool(use_aero_moment)
        self.CP_OFFSET = float(cp_offset)
        self.AERO_DAMP = float(aero_damp)
        self.CHORD = float(chord)
        # --- XWing aero model + XWing airframe (mass / inertia / motor power) ---
        self.USE_XWING_AERO = bool(use_xwing_aero)
        self.AERO_DR = bool(aero_dr)
        self.AERO_S = float(aero_s); self.AERO_C = float(aero_c); self.AERO_B = float(aero_b)
        self.XG, self.YG, self.ZG = 0.4045, -0.00062, 0.0  # XWing aero CoM (drives the moment coeffs;
        #                                                    randomized +/-0.02 per episode like the DLL —
        #                                                    the stability coeffs are hypersensitive to Xg)
        self.aero_rand = np.ones(17)                       # per-episode aero DR (set in _housekeeping)
        if self.USE_XWING_AERO:
            self.MASS_RANGE = (13.6, 14.1)                 # heavy XWing airframe
            self.NOMINAL_MASS = 13.85
            self.J_NOMINAL = np.array([1.47, 0.46, 1.39])  # XWing nominal inertia (Ixx, Iyy, Izz)
            self.MOTOR_MAX = 110.0                         # N per motor (11 kgf class) -> T/W ~3.2
            self.MAX_TOTAL_THRUST = 4.0 * self.MOTOR_MAX
            self.NOMINAL_HOVER = self.NOMINAL_MASS * 9.8
            self.MOTOR_TAU_RANGE = (0.025, 0.16)           # real XWing motor time constants (from DLL)
            if tuple(np.asarray(kp_rate, dtype=float)) == (6.0, 6.0, 4.0):   # caller used old default
                self.KP_RATE = np.array([25.0, 25.0, 15.0])    # stiffer rate loop for the strong aero
                self.KI_RATE = np.array([6.0, 6.0, 3.0])       #   (stable at the faster XWing lag)
            self.INT_LIMIT = max(self.INT_LIMIT, 15.0)
        # --- elevons (XWing only): action[0:2] = left/right fin, aero via de/da terms.
        # Motor torque is ~constant with airspeed but the weathervane moment grows with V^2;
        # elevon authority also grows with V^2 — the only actuator that keeps pace at speed.
        self.USE_ELEVONS = self.USE_XWING_AERO
        self.ACT_DIM = 6 if self.USE_ELEVONS else 4
        self.FIN_MAX = np.radians(20.0)                     # rad; real elevon limit -20..+20 deg
        self.FIN_TAU = 0.03                                 # s, servo first-order lag
        self.fin_angles = np.zeros(2)                       # actual (lagged) deflections (rad)
        self.fin_gain = np.ones(2)                          # per-episode servo gain DR (DLL: 1 +/- 0.1)
        self.fin_offset = np.zeros(2)                       # per-episode mounting offset (rad)

        if initial_xyzs is None:
            initial_xyzs = np.array([[0.0, 0.0, 2.0]])

        # runtime state (set in _housekeeping each reset)
        self.M = 10.0
        self.J_DIAG = self.J_NOMINAL.copy()
        self.wind = np.zeros(3)
        self.target_vel = np.zeros(3)
        self.desired_yaw = 0.0
        self.yaw_bias = 0.0
        self.rate_integral = np.zeros(3)
        self.current_action = np.zeros(self.ACT_DIM)
        self.prev_action = np.zeros(self.ACT_DIM)
        self.motor_tau = 0.0
        self.motor_alpha = 1.0
        self.motor_forces = np.zeros(4)
        self.prev_vel = np.zeros(3)
        self.wind_est = np.zeros(3)
        self.vel_integral = np.zeros(3)
        self.yaw_integral = 0.0

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

        # ---- control mixer: [T, tau_x, tau_y, tau_z] = MIX @ [f0,f1,f2,f3] (X-config, CF2X signs)
        a = self.ARM / np.sqrt(2.0)
        b = self.YAW_RATIO
        self.MIX = np.array([[1.0, 1.0, 1.0, 1.0],
                             [-a,  -a,   a,   a ],
                             [-a,   a,   a,  -a ],
                             [-b,   b,  -b,   b ]], dtype=float)
        self.MIX_INV = np.linalg.inv(self.MIX)

    # ------------------------------------------------------------------ spaces
    def _actionSpace(self):
        return spaces.Box(low=-1.0, high=1.0, shape=(self.ACT_DIM,), dtype=np.float32)

    def _observationSpace(self):
        # 27 = vel_err(3) + target_vel(3) + R(9) + omega_body(3) + last_action(4) + motor_rpm(4)
        #    + pitot(1); + wind_est(3), + vel_integral(3), + [sin,cos dpsi](2), + yaw_integral(1)
        # elevons add: last_action grows 4->6 (+2) and actual fin deflections (+2, servo state —
        # same "sense the actuator" rationale as motor RPM)
        dim = 27 + (3 if self.USE_WIND_EST else 0) + (3 if self.USE_VEL_INTEGRAL else 0) \
              + 2 + (1 if self.USE_YAW_INTEGRAL else 0) + (4 if self.USE_ELEVONS else 0)
        if self.REL_OBS:
            dim += 3                      # command-scaled velocity error
        if self.AIR_OBS:
            dim += 3
        # privileged tail (CRITIC-ONLY): hidden episode draw appended so an asymmetric
        # critic can predict returns; the actor slices it off (priv_policy.py)
        if self.PRIV_OBS:
            dim += 27
        return spaces.Box(low=-np.inf, high=np.inf, shape=(dim,), dtype=np.float32)

    # ---------------------------------------------------------------- heading
    def _current_yaw(self, R):
        """Heading = azimuth of body-x (nose) in the world horizontal plane. Well-conditioned
        except near body-x vertical (extreme tilt)."""
        nose = R[:, 0]
        return float(np.arctan2(nose[1], nose[0]))

    def _yaw_error(self, R):
        """Signed, wrap-safe heading error dpsi = wrap(psi - desired_yaw) in [-pi, pi]."""
        dpsi = self._current_yaw(R) - self.desired_yaw
        return float(np.arctan2(np.sin(dpsi), np.cos(dpsi)))

    # -------------------------------------------------- curriculum / tough init
    def set_wind_max(self, w):
        """Curriculum knob (called via env_method): per-episode wind is U(0, WIND_MAX)."""
        self.WIND_MAX = float(w)

    def _quat_z_along(self, d, roll=0.0, scatter_deg=0.0):
        """Quaternion whose body-z (prop/cruise axis) points along unit vector d, with a given
        roll about that axis and optional random angular scatter."""
        z = np.array([0.0, 0.0, 1.0])
        axis = np.cross(z, d)
        n = np.linalg.norm(axis)
        if n < 1e-8:
            q = [0.0, 0.0, 0.0, 1.0] if d[2] > 0 else [1.0, 0.0, 0.0, 0.0]
        else:
            q = p.getQuaternionFromAxisAngle((axis / n).tolist(),
                                             float(np.arccos(np.clip(z @ d, -1.0, 1.0))))
        q_roll = p.getQuaternionFromAxisAngle(d.tolist(), float(roll))
        _, q = p.multiplyTransforms([0, 0, 0], q_roll, [0, 0, 0], q)
        if scatter_deg > 0.0:
            ax = self.np_random.normal(size=3); ax /= (np.linalg.norm(ax) + 1e-9)
            qs = p.getQuaternionFromAxisAngle(ax.tolist(), float(np.radians(scatter_deg)))
            _, q = p.multiplyTransforms([0, 0, 0], qs, [0, 0, 0], list(q))
        return np.array(q)

    def _sample_tough_init(self):
        """Failure-state starts: 50% developed dive (30-50 m/s steeply down, nose
        near-aligned with the flow), 50% botched transition (60-120 deg tilt at
        15-30 m/s, tumbling)."""
        if self.np_random.uniform() < 0.5:
            az = self.np_random.uniform(-np.pi, np.pi)
            elev = np.radians(self.np_random.uniform(40.0, 90.0))
            d = np.array([np.cos(elev) * np.cos(az), np.cos(elev) * np.sin(az), -np.sin(elev)])
            v = d * self.np_random.uniform(30.0, 50.0)
            quat = self._quat_z_along(d, roll=self.np_random.uniform(-np.pi, np.pi),
                                      scatter_deg=self.np_random.uniform(0.0, 25.0))
            w = self.np_random.uniform(-1.0, 1.0, size=3)
        else:
            a0 = self.np_random.uniform(-np.pi, np.pi)
            tilt = np.radians(self.np_random.uniform(60.0, 120.0))
            q1 = p.getQuaternionFromAxisAngle([np.cos(a0), np.sin(a0), 0.0], float(tilt))
            qy = p.getQuaternionFromAxisAngle([0.0, 0.0, 1.0],
                                              float(self.np_random.uniform(-np.pi, np.pi)))
            _, quat = p.multiplyTransforms([0, 0, 0], qy, [0, 0, 0], q1)
            quat = np.array(quat)
            dv = self.np_random.normal(size=3)
            dv[2] = -abs(dv[2]) * 0.5                       # horizontal-ish, slightly sinking
            dv /= (np.linalg.norm(dv) + 1e-9)
            v = dv * self.np_random.uniform(15.0, 30.0)
            w = self.np_random.uniform(-2.0, 2.0, size=3)
        return quat, v, w

    # ------------------------------------------------- reset / domain random.
    def _housekeeping(self):
        super()._housekeeping()
        self.rate_integral = np.zeros(3)
        self.current_action = np.zeros(self.ACT_DIM)
        self.prev_action = np.zeros(self.ACT_DIM)

        # mass + inertia (inertia scales with mass)
        self.M = float(self.np_random.uniform(*self.MASS_RANGE))
        self.J_DIAG = self.J_NOMINAL * (self.M / self.NOMINAL_MASS)
        p.changeDynamics(int(self.DRONE_IDS[0]), -1, mass=self.M,
                         localInertiaDiagonal=self.J_DIAG.tolist(),
                         linearDamping=0.0, angularDamping=0.0, physicsClientId=self.CLIENT)

        # wind (constant per episode)
        wdir = self.np_random.normal(size=3)
        n = np.linalg.norm(wdir)
        wdir = wdir / n if n > 1e-6 else np.array([1.0, 0.0, 0.0])
        w_lo = 0.0
        if self.WIND_OVERSAMPLE > 0.0 and self.np_random.uniform() < self.WIND_OVERSAMPLE:
            w_lo = min(8.0, self.WIND_MAX)
        self.wind = wdir * self.np_random.uniform(w_lo, self.WIND_MAX)

        # wing area + motor lag (hidden per-episode parameters)
        self.wing_area = self.WING_AREA_NOM * (
            1.0 + self.np_random.uniform(-self.WING_JITTER, self.WING_JITTER))
        # XWing aero coefficient randomization (17 multipliers, +/-20% per episode, as in the DLL),
        # and aero-CoM Xg = 0.4045 +/- 0.02 (DLL's dXg) — MYB/MZA stability coeffs are near their
        # Xg zero-crossings, so this randomization meaningfully varies static stability.
        if self.USE_XWING_AERO and self.AERO_DR:
            self.aero_rand = 1.0 + self.np_random.uniform(-0.20, 0.20, size=17)
            self.XG = 0.4045 + self.np_random.uniform(-0.02, 0.02)
        else:
            self.aero_rand = np.ones(17)
            self.XG = 0.4045
        # elevon servo DR (DLL: Fin gain 1 +/- 0.1, small mounting offset) + reset servo state
        self.fin_angles = np.zeros(2)
        self.fin_gain = 1.0 + self.np_random.uniform(-0.10, 0.10, size=2)
        self.fin_offset = self.np_random.uniform(-0.02, 0.02, size=2)   # rad (~1 deg)
        self.motor_tau = float(self.np_random.uniform(*self.MOTOR_TAU_RANGE))
        self.motor_alpha = (1.0 if self.motor_tau <= 1e-6
                            else 1.0 - np.exp(-self.PYB_TIMESTEP / self.motor_tau))
        self.motor_forces = np.full(4, self.M * 9.8 / 4.0)

        # reset estimators/integrals; sample heading target + yaw-torque disturbance
        self.prev_vel = np.zeros(3)
        self.wind_est = np.zeros(3)
        self.vel_integral = np.zeros(3)
        self.yaw_integral = 0.0
        self.desired_yaw = float(self.np_random.uniform(-np.pi, np.pi))
        self.yaw_bias = float(self.np_random.uniform(-self.YAW_BIAS_MAX, self.YAW_BIAS_MAX))

        # gentle VTOL init: roll/pitch +-40 deg (never inverted -> no gimbal lock), yaw 360 deg,
        # velocity any direction up to MAX_SPEED, gentle body rates.
        if self.RANDOMIZE_INIT:
            did = int(self.DRONE_IDS[0])
            if self.np_random.uniform() < self.TOUGH_INIT_FRAC:
                quat, v, w = self._sample_tough_init()      # dive / botched-transition start
            else:
                rr = self.np_random.uniform(np.radians(-40.0), np.radians(40.0))
                pp = self.np_random.uniform(np.radians(-40.0), np.radians(40.0))
                yy = self.np_random.uniform(-np.pi, np.pi)
                quat = np.array(p.getQuaternionFromEuler([rr, pp, yy]))
                dv = self.np_random.normal(size=3); dv /= (np.linalg.norm(dv) + 1e-9)
                v = dv * self.np_random.uniform(0.0, self.MAX_SPEED)
                w = self.np_random.uniform(-1.0, 1.0, size=3)
            p.resetBasePositionAndOrientation(did, self.pos[0].tolist(), quat.tolist(),
                                              physicsClientId=self.CLIENT)
            p.resetBaseVelocity(did, v.tolist(), w.tolist(), physicsClientId=self.CLIENT)
            self._updateAndStoreKinematicInformation()
            self.prev_vel = self.vel[0].copy()

        self._resample_target()

        # trim init: start this episode AT the target velocity in near-trim attitude
        # (table trim for the episode's v_rel, plus angular scatter)
        if self.TRIM_INIT_FRAC > 0.0 and self.np_random.uniform() < self.TRIM_INIT_FRAC:
            self._apply_trim_init()

        # TRIM FEEDFORWARD: target and wind are constant per episode, so the trim is solved
        # ONCE here (~0.04 s) and reused every step as the action's reference point.
        self._ff = self._solve_ff_trim() if self.TRIM_FF else None

        # position irrelevant -> fly freely (incl. downward targets / drift in wind)
        p.setCollisionFilterPair(int(self.PLANE_ID), int(self.DRONE_IDS[0]),
                                 -1, -1, enableCollision=0, physicsClientId=self.CLIENT)

    def _apply_trim_init(self):
        from scipy.spatial.transform import Rotation as _Rot
        if self._trim_table is None:
            import os
            self._trim_table = dict(np.load(os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "trim_table.npz")))
        t = self._trim_table
        v_rel = self.target_vel - self.wind
        s = float(np.linalg.norm(v_rel))
        if s < 2.0:
            return                                             # hover-ish: keep normal init
        g = float(np.arcsin(np.clip(v_rel[2] / s, -1.0, 1.0)))
        i = int(np.argmin(np.abs(t["speeds"] - s)))
        j = int(np.argmin(np.abs(t["gammas"] - g)))
        R_can = _Rot.from_rotvec(t["rotvecs"][i, j])
        psi = float(np.arctan2(v_rel[1], v_rel[0]))            # rotate canonical x -> heading
        R_tab = _Rot.from_euler("z", psi) * R_can
        de_tab = float(t["des"][i, j])
        # refine against THIS episode's DR draw (table is nominal-coeff; its residual grows
        # with Q — ~3 m/s^2 at Va 40-55, degrading the goal-state exposure at top bands)
        R_ref, de_ref, T_ref = self._refine_trim(R_tab, de_tab, v_rel)
        scatter = _Rot.from_rotvec(self.np_random.normal(size=3) * np.radians(10.0) / 1.732)
        R = R_ref * scatter
        v0 = self.target_vel + self.np_random.normal(size=3) * 1.0
        did = int(self.DRONE_IDS[0])
        p.resetBasePositionAndOrientation(did, self.pos[0].tolist(), R.as_quat().tolist(),
                                          physicsClientId=self.CLIENT)
        p.resetBaseVelocity(did, v0.tolist(),
                            (self.np_random.uniform(-0.3, 0.3, size=3)).tolist(),
                            physicsClientId=self.CLIENT)
        self.fin_angles = np.array([de_ref, de_ref])
        self.motor_forces = np.full(4, T_ref / 4.0)
        self._updateAndStoreKinematicInformation()
        self.prev_vel = self.vel[0].copy()

    def _solve_ff_trim(self):
        """Trim (R, elevator, thrust) for this episode's target and wind, from the table +
        a short refinement against the actual aero draw. Returns None below ~2 m/s, where
        the hover solution is trivial and the feedforward adds nothing."""
        from scipy.spatial.transform import Rotation as _Rot
        import os
        wind = self.wind if self.TRIM_FF_TRUE_WIND else self._wind_vel_estimate()
        v_rel = self.target_vel - wind
        s = float(np.linalg.norm(v_rel))
        if s < 2.0:
            return None
        if self._trim_table is None:
            self._trim_table = dict(np.load(os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "trim_table.npz")))
        t = self._trim_table
        g = float(np.arcsin(np.clip(v_rel[2] / s, -1.0, 1.0)))
        i = int(np.argmin(np.abs(t["speeds"] - s)))
        j = int(np.argmin(np.abs(t["gammas"] - g)))
        psi = float(np.arctan2(v_rel[1], v_rel[0]))
        R_tab = _Rot.from_euler("z", psi) * _Rot.from_rotvec(t["rotvecs"][i, j])
        sol = self._refine_trim(R_tab, float(t["des"][i, j]), v_rel)
        # a feedforward REFERENCE must be right: ~8% of draws leave the table warm-start in a
        # poor basin, so re-scan those (once per episode, only when needed).
        if self._ff_residual(sol, v_rel) > 0.5:
            best = sol
            best_r = self._ff_residual(sol, v_rel)
            for _ in range(12):
                R0 = _Rot.from_rotvec(self.np_random.normal(size=3) * 1.2) * R_tab
                cand = self._refine_trim(R0, float(t["des"][i, j]), v_rel)
                r = self._ff_residual(cand, v_rel)
                if r < best_r:
                    best, best_r = cand, r
                if best_r <= 0.05:
                    break
            sol = best
        return sol

    def _ff_residual(self, sol, v_rel):
        """Residual acceleration (m/s^2) left by a candidate trim under THIS episode's draw."""
        R, de, T = sol
        Rm = R.as_matrix()
        v_xw = self._P_XW @ (Rm.T @ v_rel)
        Va = float(np.linalg.norm(v_xw))
        if Va < 1e-4:
            return 0.0
        u, vv, w = v_xw
        al = float(np.arctan2(-vv, u))
        be = float(np.arcsin(np.clip(w / Va, -1.0, 1.0)))
        F, _ = func_aero_model(al, be, Va, np.zeros(3), self.RHO, self.AERO_S, self.AERO_C,
                               self.AERO_B, (self.XG, self.YG, self.ZG), de, de, self.aero_rand)
        Fw = Rm @ (self._P_XW.T @ F) + np.array([0.0, 0.0, -self.M * 9.8]) + Rm[:, 2] * T
        return float(np.linalg.norm(Fw)) / self.M

    def _wind_vel_estimate(self):
        """Deployable stand-in for the wind VELOCITY: the disturbance observer estimates an
        external force; at quasi-steady flight the wind-induced part is recovered by
        differencing ground velocity against the axial air-relative speed the pitot sees."""
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        axial = R[:, 2]
        pitot = float(axial @ (self.vel[0] - self.wind))    # sensor reading (axial airspeed)
        return self.vel[0] - pitot * axial

    def _refine_trim(self, R_tab, de_tab, v_rel):
        """Short warm-started solve of (attitude, elevator) against THIS episode's actual
        aero draw and mass; returns (R, de, total thrust)."""
        from scipy.spatial.transform import Rotation as _Rot
        from scipy.optimize import minimize as _min
        G = np.array([0.0, 0.0, -self.M * 9.8])

        def resid(x):
            R = _Rot.from_rotvec(x[:3]).as_matrix()
            de = float(np.clip(x[3], -self.FIN_MAX, self.FIN_MAX))
            v_xw = self._P_XW @ (R.T @ v_rel)
            Va = float(np.linalg.norm(v_xw))
            if Va < 1e-4:
                Fw = G
            else:
                u, vv, w = v_xw
                al = float(np.arctan2(-vv, u))
                be = float(np.arcsin(np.clip(w / Va, -1.0, 1.0)))
                F, _ = func_aero_model(al, be, Va, np.zeros(3), self.RHO, self.AERO_S,
                                       self.AERO_C, self.AERO_B, (self.XG, self.YG, self.ZG),
                                       de, de, self.aero_rand)
                Fw = R @ (self._P_XW.T @ F) + G
            bz = R[:, 2]
            T = float(np.clip(-(Fw @ bz), 0.0, self.MAX_TOTAL_THRUST))
            return float(np.linalg.norm(Fw + T * bz)), T

        x0 = np.concatenate([R_tab.as_rotvec(), [de_tab]])
        try:
            res = _min(lambda x: resid(x)[0], x0, method="Nelder-Mead",
                       options={"maxiter": 150, "xatol": 1e-4, "fatol": 1e-3})
            x = res.x
        except Exception:
            x = x0
        _, T = resid(x)
        return (_Rot.from_rotvec(x[:3]),
                float(np.clip(x[3], -self.FIN_MAX, self.FIN_MAX)), T)

    def _resample_target(self):
        d = self.np_random.normal(size=3)
        n = np.linalg.norm(d)
        d = d / n if n > 1e-6 else np.array([1.0, 0.0, 0.0])
        self.target_vel = d * self.np_random.uniform(self.SPEED_MIN, self.TARGET_SPEED_MAX)

    def set_target_speed_range(self, lo, hi):
        """Change target sampling without changing policy observation/integral scaling."""
        lo, hi = float(lo), float(hi)
        if not 0.0 <= lo <= hi <= self.MAX_SPEED:
            raise ValueError("target speed range must stay inside [0, MAX_SPEED]")
        self.SPEED_MIN, self.TARGET_SPEED_MAX = lo, hi

    # ------------------------------------------------------- CTBR decode + PID
    def _decode_action(self, action):
        a = np.clip(np.asarray(action, dtype=float).reshape(-1)[-4:], -1.0, 1.0)
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
        if self.ATT_CMD and self._bz_des is not None:
            # attitude P (classical-cascade style, runs every physics substep): rotate body-z
            # toward the commanded direction; yaw rate passes through about body z.
            bz = R[:, 2]
            axis = np.cross(bz, self._bz_des)
            n = float(np.linalg.norm(axis))
            ang = float(np.arccos(np.clip(bz @ self._bz_des, -1.0, 1.0)))
            omega_w = self.KATT * (axis / n) * ang if n > 1e-8 else np.zeros(3)
            omega_des = R.T @ omega_w
            omega_des[2] = self._yaw_rate_des
            omega_des = np.clip(omega_des, -self.MAX_RATE, self.MAX_RATE)
            self._omega_des_last = omega_des
        omega_body = R.T @ self.ang_v[0]
        err = omega_des - omega_body
        self.rate_integral = np.clip(self.rate_integral + err * self.PYB_TIMESTEP,
                                     -self.INT_LIMIT, self.INT_LIMIT)
        ang_acc = self.KP_RATE * err + self.KI_RATE * self.rate_integral
        tau_des = self.J_DIAG * ang_acc
        forces_cmd = self.MIX_INV @ np.array([thrust_des, tau_des[0], tau_des[1], tau_des[2]])
        forces_cmd = np.clip(forces_cmd, 0.0, self.MOTOR_MAX)  # motor saturation
        self.motor_forces += (forces_cmd - self.motor_forces) * self.motor_alpha  # first-order lag
        wrench = self.MIX @ self.motor_forces
        return R, wrench[0], wrench[1:]

    def _preprocessAction(self, action):
        return np.zeros((1, 4))   # unused (step() overrides the substep loop); kept for BaseAviary API

    def _wing_aero(self, R):
        """Flat-plate wing FORCE (world) and, if use_aero_moment, the aero MOMENT.
        Force at COM: normal n=body-x, span s=body-y; AoA from sin a = n.vhat;
        CL = 2 sin a cos a, CD = CD0 + 2 sin^2 a; lift perp to wind and span.
        Moment = static (weathervane) + rate damping:
          * static: the force acts at a center of pressure CP_OFFSET aft of the COM along the
            chord (-body-z), giving M = r_cp x F. This is a restoring moment that grows with V^2
            and opposes rotating away from wind-alignment -> the airspeed-dependent control-
            authority limit a real winged body has (a sustained high rate becomes impossible as V
            rises), matching the XWing behavior. Force-only (moment=0) is the legacy default.
          * damping: -AERO_DAMP * 0.5 rho V S c^2 * omega_body, opposing body rates (grows with V)."""
        v_rel = self.vel[0] - self.wind
        V = float(np.linalg.norm(v_rel))
        if V < 1e-4:
            return np.zeros(3), np.zeros(3)
        vhat = v_rel / V
        n_hat, s_hat = R[:, 0], R[:, 1]
        sin_a = float(np.clip(n_hat @ vhat, -1.0, 1.0))
        cos_a = np.sqrt(max(0.0, 1.0 - sin_a * sin_a))
        qS = 0.5 * self.RHO * V * V * self.wing_area
        CL = 2.0 * sin_a * cos_a
        CD = self.CD0 + 2.0 * sin_a * sin_a
        f_drag = -CD * qS * vhat
        cross = np.cross(vhat, s_hat)
        nc = float(np.linalg.norm(cross))
        f_lift = (CL * qS / nc) * cross if nc > 1e-6 else np.zeros(3)
        F = f_lift + f_drag
        if not self.USE_AERO_MOMENT:
            return F, np.zeros(3)
        r_cp = -self.CP_OFFSET * R[:, 2]                       # CoP aft of COM along chord (-body-z)
        M_static = np.cross(r_cp, F)
        omega_body = R.T @ self.ang_v[0]
        M_damp_body = -self.AERO_DAMP * 0.5 * self.RHO * V * self.wing_area * self.CHORD ** 2 * omega_body
        return F, M_static + R @ M_damp_body

    # map my body frame (z=prop/cruise-fwd, x=wing-normal/lift, y=span) -> XWing aero model frame.
    # The XWing model is Y-UP (verified from its wind->body transform Twb = rotz(alpha)*roty(beta):
    # u=Va ca cb, v=-Va sa cb, w=Va sb -> alpha=atan2(-v,u) about z, beta=asin(w/Va) about y;
    # lift cy=f(alpha) on y, side cz=f(beta) on z). So: model_x(fwd)=my_z, model_y(lift)=my_x,
    # model_z(side)=my_y — a cyclic permutation (proper rotation, det=+1).
    _P_XW = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

    def _xwing_aero(self, R):
        """Full ported XWing aerodynamic model (aero_xwing.func_aero_model), including the two
        elevons (actual lagged servo deflections; de/da enter the model's force+moment terms).
        Returns (force, moment) in WORLD frame. alpha/beta/Va and body rates are computed in the
        XWing model frame via _P_XW; F,M are mapped back to my body then to world."""
        v_rel = self.vel[0] - self.wind
        v_xw = self._P_XW @ (R.T @ v_rel)                 # air-relative velocity in XWing model frame
        Va = float(np.linalg.norm(v_xw))
        if Va < 1e-4:
            return np.zeros(3), np.zeros(3)
        u, vv, w = v_xw
        alpha = float(np.arctan2(-vv, u))                 # AoA about model-z (y-up convention)
        beta = float(np.arcsin(np.clip(w / Va, -1.0, 1.0)))   # sideslip about model-y
        Wb = self._P_XW @ (R.T @ self.ang_v[0])           # body rates in XWing model frame
        F_xw, M_xw = func_aero_model(alpha, beta, Va, Wb, self.RHO,
                                     self.AERO_S, self.AERO_C, self.AERO_B,
                                     (self.XG, self.YG, self.ZG),
                                     float(self.fin_angles[0]), float(self.fin_angles[1]),
                                     self.aero_rand)
        return R @ (self._P_XW.T @ F_xw), R @ (self._P_XW.T @ M_xw)

    def _apply_wrench_and_wind(self, R, thrust, tau_body):
        did = int(self.DRONE_IDS[0])
        f_thrust = R[:, 2] * thrust                      # thrust along body +z, in world
        f_aero, m_aero = self._xwing_aero(R) if self.USE_XWING_AERO else self._wing_aero(R)
        p.applyExternalForce(did, -1, (f_thrust + f_aero).tolist(),
                             self.pos[0].tolist(), p.WORLD_FRAME, physicsClientId=self.CLIENT)
        tau_world = R @ tau_body
        if self.yaw_bias != 0.0:                          # constant yaw-torque disturbance (about body-z)
            tau_world = tau_world + R[:, 2] * self.yaw_bias
        tau_world = tau_world + m_aero                    # aerodynamic moment (weathervane + damping)
        p.applyExternalTorque(did, -1, tau_world.tolist(), p.WORLD_FRAME, physicsClientId=self.CLIENT)

    # ------------------------------------------------------------------- step
    def step(self, action):
        """Hold the policy CTBR set-point constant while the PID inner loop runs every physics
        sub-step; apply achieved wrench + wind + gravity, then update estimators + integrals."""
        self.current_action = np.clip(np.asarray(action, dtype=float).reshape(self.ACT_DIM), -1.0, 1.0)
        thrust_des, omega_des = self._decode_action(self.current_action)
        if self.ATT_CMD and self.TRIM_FF and self._ff is not None:
            # deviation from the episode's trim: a=0 holds trim exactly (absolute reference)
            R_ff, de_ff, T_ff = self._ff
            xy = self.current_action[-3:-1]
            v = np.array([self.TRIM_FF_K * xy[0], self.TRIM_FF_K * xy[1], 1.0])
            self._bz_des = R_ff.as_matrix() @ (v / np.linalg.norm(v))
            self._yaw_rate_des = float(self.current_action[-1]) * float(self.MAX_RATE[2])
            thrust_des = float(np.clip(
                T_ff + self.current_action[2] * self.TRIM_FF_THRUST * self.NOMINAL_HOVER,
                0.0, self.MAX_TOTAL_THRUST))
        elif self.ATT_CMD:
            xy = self.current_action[-3:-1]
            if self.ATT_REL:
                # body-relative: a=0 holds the current thrust axis; max correction atan(k)
                R0 = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
                v = np.array([self.ATT_REL_K * xy[0], self.ATT_REL_K * xy[1], 1.0])
                self._bz_des = R0 @ (v / np.linalg.norm(v))
            elif self.ATT_TILT_EXT > 0.0:
                # RESOLUTION-PRESERVING tilt extension. Trial 78 lifted the 80 deg cap by
                # rescaling |xy| linearly onto 0-120 deg and was 3.5x WORSE, because it
                # halved resolution everywhere (damage worst at hover, 3.7x). Legacy
                # arcsin is fine near hover and already coarse near its cap, which suits
                # the task. So keep legacy EXACTLY for |xy| <= 0.9 (0-64 deg) and spend
                # only the outer 10% of the action ball reaching ATT_TILT_EXT, where
                # steep descents live (measured need: 93-105 deg above 32 m/s).
                n = float(np.linalg.norm(xy))
                u = xy / n if n > 1e-6 else np.array([1.0, 0.0])
                if n <= 0.9:
                    tilt = float(np.arcsin(n))
                else:
                    f = min((n - 0.9) / 0.1, 1.0)
                    t0 = float(np.arcsin(0.9))
                    tilt = t0 + f * (np.radians(self.ATT_TILT_EXT) - t0)
                self._bz_des = np.array([np.sin(tilt) * u[0], np.sin(tilt) * u[1],
                                         np.cos(tilt)])
            elif self.ATT_TILT_MAX > 0.0:
                # FULL-SPHERE thrust-axis command. The legacy encoding below builds
                # bz_des.z = +sqrt(1-|xy|^2), so the commanded axis is confined to the UPPER
                # hemisphere and tilt is capped at arcsin(0.985) = 80.0 deg. Measured trim tilt
                # for a steep descent is 82.6 deg at gamma=-30 and 93 deg at gamma=-40 (25-34
                # m/s), i.e. OUTSIDE the action space at any action value — the aircraft can be
                # asked to fly a descent it cannot be commanded into. Here |xy| maps linearly to
                # tilt over [0, ATT_TILT_MAX], so past 90 deg is reachable.
                n = float(np.linalg.norm(xy))
                u = xy / n if n > 1e-6 else np.array([1.0, 0.0])
                tilt = np.radians(self.ATT_TILT_MAX) * min(n, 1.0)
                self._bz_des = np.array([np.sin(tilt) * u[0], np.sin(tilt) * u[1], np.cos(tilt)])
            else:
                # world-frame upper hemisphere (norm<=0.985 caps tilt at ~80 deg)
                n = float(np.linalg.norm(xy))
                if n > 0.985:
                    xy = xy * (0.985 / n)
                self._bz_des = np.array([xy[0], xy[1], np.sqrt(max(1.0 - xy @ xy, 1e-6))])
            self._yaw_rate_des = float(self.current_action[-1]) * float(self.MAX_RATE[2])
        v_prev = self.vel[0].copy()

        fin_alpha = 1.0 - np.exp(-self.PYB_TIMESTEP / self.FIN_TAU)   # servo first-order lag
        for _ in range(self.PYB_STEPS_PER_CTRL):
            if self.USE_ELEVONS:
                fin_norm = self.current_action[:2]
                if self.TRIM_FF and self._ff is not None:
                    fin_norm = np.clip(self._ff[1] / self.FIN_MAX
                                       + self.TRIM_FF_FIN * fin_norm, -1.0, 1.0)
                if self.ATT_CMD and self.FIN_ASSIST > 0.0:
                    assist = float(np.clip(self.FIN_ASSIST * self._omega_des_last[1]
                                           / self.MAX_RATE[1], -1.0, 1.0))
                    fin_norm = np.clip(fin_norm + assist, -1.0, 1.0)
                fin_cmd = (self.FIN_MAX * fin_norm) * self.fin_gain + self.fin_offset
                self.fin_angles += (fin_cmd - self.fin_angles) * fin_alpha
                self.fin_angles = np.clip(self.fin_angles, -self.FIN_MAX, self.FIN_MAX)
            R, thrust, tau_body = self._control_wrench(thrust_des, omega_des)
            self._apply_wrench_and_wind(R, thrust, tau_body)
            p.stepSimulation(physicsClientId=self.CLIENT)
            self._updateAndStoreKinematicInformation()

        self._update_wind_estimate(v_prev)
        # leaky, clamped integrals: dI/dt = err - I/tau -> constant error settles at I=err*tau and
        # old setpoint transients decay away (anti-windup; works with changing targets).
        if self.USE_VEL_INTEGRAL:
            err = self.target_vel - self.vel[0]
            self.vel_integral += (err - self.vel_integral / self.INTEGRAL_TAU) * self.CTRL_TIMESTEP
            self.vel_integral = np.clip(self.vel_integral, -self.MAX_SPEED, self.MAX_SPEED)
        if self.USE_YAW_INTEGRAL:
            R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
            dpsi = self._yaw_error(R)
            self.yaw_integral += (dpsi - self.yaw_integral / self.YAW_INTEGRAL_TAU) * self.CTRL_TIMESTEP
            self.yaw_integral = float(np.clip(self.yaw_integral, -np.pi, np.pi))

        obs = self._computeObs()
        reward = self._computeReward()
        terminated = self._computeTerminated()
        truncated = self._computeTruncated()
        info = self._computeInfo()
        self.step_counter += self.PYB_STEPS_PER_CTRL
        self.prev_action = self.current_action.copy()
        return obs, reward, terminated, truncated, info

    def _update_wind_estimate(self, v_prev):
        """Disturbance observer: recover the total external force from m*a = F_thrust + F_gravity +
        F_ext using NOMINAL mass + achieved thrust (what an onboard estimator has). F_ext lumps
        wind + wing aero; target-independent -> transfers to changing targets. EMA-filtered."""
        a = (self.vel[0] - v_prev) / self.CTRL_TIMESTEP
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        f_thrust = R[:, 2] * float(np.sum(self.motor_forces))
        f_ext = (self.NOMINAL_MASS * a - f_thrust
                 + np.array([0.0, 0.0, self.NOMINAL_MASS * self.G]))
        self.wind_est = ((1 - self.WIND_EST_ALPHA) * self.wind_est
                         + self.WIND_EST_ALPHA * f_ext)

    # ------------------------------------------------------------------- obs
    def _computeObs(self):
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        omega_body = R.T @ self.ang_v[0]
        rpm_norm = np.sqrt(np.clip(self.motor_forces / self.MOTOR_MAX, 0.0, 1.0))  # ESC telemetry
        pitot = float(R[:, 2] @ (self.vel[0] - self.wind))    # forward (axial) air-relative airspeed
        if self.PITOT_NOISE > 0.0:
            pitot += float(self.np_random.normal(0.0, self.PITOT_NOISE))

        vel_err = self.target_vel - self.vel[0]
        tgt = self.target_vel
        if self.VELYAW_HEADING_FRAME:
            # rotate world vectors into the current-heading frame (yaw-invariant control map);
            # R is still in obs so no attitude info is lost.
            psi = self._current_yaw(R)
            c, s = np.cos(-psi), np.sin(-psi)
            Rz = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
            vel_err = Rz @ vel_err
            tgt = Rz @ tgt

        parts = [vel_err / self.MAX_SPEED,        # 3
                 tgt / self.MAX_SPEED,            # 3
                 R.reshape(9),                    # 9
                 omega_body / self.MAX_RATE[0],   # 3
                 self.current_action,             # 4
                 rpm_norm]                        # 4  <- solves motor lag
        if self.USE_WIND_EST:
            parts.append(self.wind_est / self.NOMINAL_HOVER)   # 3  <- disturbance observer
        if self.REL_OBS:
            # COMMAND-SCALED velocity error. The absolute channel above divides by
            # MAX_SPEED, so at MAX_SPEED=50 a 0.5 m/s hover error is 0.01 — and
            # VecNormalize's running std is dominated by fast-band errors, compressing
            # slow-speed signal toward zero. Measured: one 0-50 policy matches the
            # specialist at 25-34 m/s (0.93x) but is 7.4x worse at hover. Dividing by the
            # COMMANDED speed gives comparable resolution at every commanded speed.
            vs = max(float(np.linalg.norm(tgt)), self.REL_FLOOR)
            parts.append(np.clip(vel_err / vs, -3.0, 3.0))     # 3
        parts.append([pitot / self.MAX_SPEED])                 # 1  <- forward airspeed (drives wings)
        if self.USE_ELEVONS:
            parts.append(self.fin_angles / self.FIN_MAX)       # 2  <- actual servo deflections
        if self.USE_VEL_INTEGRAL:
            parts.append(self.vel_integral / self.MAX_SPEED)   # 3  <- steady velocity-error nulling
        dpsi = self._yaw_error(R)
        parts.append([np.sin(dpsi), np.cos(dpsi)])             # 2  <- heading error (wrap-safe)
        if self.USE_YAW_INTEGRAL:
            parts.append([self.yaw_integral / np.pi])          # 1  <- steady heading-offset nulling
        if self.AIR_OBS:                                       # 3  <- true body-frame airflow
            parts.append((R.T @ (self.vel[0] - self.wind)) / self.MAX_SPEED)
        if self.PRIV_OBS:                                      # 27 <- CRITIC-ONLY hidden draw
            parts.append(self.aero_rand - 1.0)                             # 17
            parts.append([(self.XG - 0.4045) / 0.02,
                          (self.M - self.NOMINAL_MASS) / 0.25,
                          (self.motor_tau - 0.09) / 0.07])                 # 3
            parts.append(self.fin_gain - 1.0)                              # 2
            parts.append(self.fin_offset / 0.02)                           # 2
            parts.append(self.wind / max(self.WIND_MAX, 1.0))              # 3
        return np.concatenate(parts).astype(np.float32)

    # ---------------------------------------------------------------- reward
    def _computeReward(self):
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        omega_body = R.T @ self.ang_v[0]
        smooth = (-5e-4 * float(omega_body @ omega_body)
                  - 5e-4 * float((self.current_action - self.prev_action)
                                 @ (self.current_action - self.prev_action)))
        # TWO objectives: velocity AND heading. Each gets a sharp 1-tanh peak (steep gradient at 0,
        # no flat-top deadband) + a wide-coverage term (far-field gradient across the envelope),
        # combined ADDITIVELY (each always has a gradient) with a small MULTIPLICATIVE joint bonus
        # (high only when BOTH are nailed). Non-negative while alive; only terminal is numeric
        # divergence, so there is no suicide route to game the far-field pull.
        s = self.MAX_SPEED / 20.0
        d = np.linalg.norm(self.vel[0] - self.target_vel)
        a = abs(self._yaw_error(R))
        w = self.YAW_REWARD_WIDTH
        W = self.COV_WIDTH if self.COV_WIDTH > 0.0 else 10.0 * s
        cov = np.exp(-0.5 * (d / W) ** 2)                      # wide velocity coverage
        r_vel = (1.0 - np.tanh(d / 2.0)) + cov
        if self.VEL_PRECISION > 0.0:
            # narrow precision peak: the d/2 term is ~flat below 2 m/s, so this adds
            # gradient in the sub-1 m/s regime (width 0.5 m/s)
            r_vel += self.VEL_PRECISION * (1.0 - np.tanh(d / 0.5))
        if self.REL_BASIN > 0.0:
            # SCALE-INVARIANT APPROACH BASIN — the fix that makes one policy trainable over a
            # wide speed range. Every term above has an ABSOLUTE width and must keep it: the
            # goal is <1 m/s at any speed, so a relative goal would reward +-25 m/s at 50.
            # But absolute widths are numerically DEAD far from a fast target: an episode
            # starts at rest, so commanded 50 m/s means d=50, where the shaped gradient is
            # 4e-22 (vs 1.3e-1 at 5 m/s) — 21 orders of magnitude of vanishing signal. That,
            # not capacity, is why fast bands never trained from scratch and why trim-init
            # (which starts the episode AT the target, inside the live region) was the biggest
            # single gain at speed. This basin's width is a FRACTION OF THE COMMANDED SPEED,
            # so the pull from rest is the same at 5 and 50 m/s, while the goal stays absolute.
            vs = max(float(np.linalg.norm(self.target_vel)), self.REL_FLOOR)
            r_vel += self.REL_BASIN * np.exp(-0.5 * (d / (self.REL_WIDTH * vs)) ** 2)
        r_yaw = (1.0 - np.tanh(a / w)) + np.exp(-0.5 * (a / 1.0) ** 2)
        joint = (1.0 - np.tanh(d / 2.0)) * (1.0 - np.tanh(a / w))
        # yaw gate: scale the yaw payout by velocity coverage; the floor fraction always pays
        gf = self.YAW_GATE_FLOOR
        gate = (gf + (1.0 - gf) * cov) if self.YAW_GATE else 1.0
        if self.YAW_ATT_GATE:
            # attitude gate: in wing-borne flight the nose must follow the velocity vector,
            # so a random desired_yaw is structurally unsatisfiable at speed.
            # R[2,2] = 1 in hover (yaw fully enforced) -> 0 at 90-deg tilt (yaw released).
            gate = gate * float(np.clip(R[2, 2], 0.0, 1.0))
        # Linear far-field pull. The legacy coefficient is 0.02/s = 0.4/MAX_SPEED, i.e. it is
        # weakened by widening the envelope — a 0–50 policy gets 0.0080/(m/s) where a 0–10
        # specialist gets 0.0400, so asking for more range mechanically weakens the only term
        # that survives far from a fast target. Keyed to the COMMANDED speed instead, it
        # reproduces exactly what a specialist at that speed would have felt (0.4 at full-scale
        # error) at every commanded speed inside one policy.
        if self.CMD_LINEAR:
            lin = 0.4 / max(float(np.linalg.norm(self.target_vel)), self.REL_FLOOR)
        else:
            lin = 0.02 / s
        reward = r_vel + self.YAW_WEIGHT * gate * r_yaw + 0.5 * joint - lin * d + smooth
        if self._crashed():
            reward -= 10.0
        return float(reward)

    # --------------------------------------------------------- term / trunc
    def _crashed(self):
        # NO attitude limit -- a tailsitter legitimately tilts hard; only a diverged state counts.
        if not np.all(np.isfinite(self.pos[0])) or np.max(np.abs(self.pos[0])) > 1e4:
            return True
        return False

    def _computeTerminated(self):
        return bool(self._crashed())

    def _computeTruncated(self):
        return bool(self.step_counter / self.PYB_FREQ >= self.EPISODE_LEN_SEC)

    def _computeInfo(self):
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        return {"target_vel": self.target_vel.copy(),
                "desired_yaw": float(self.desired_yaw),
                "pos": self.pos[0].copy(),
                "vel": self.vel[0].copy(),
                "mass": self.M,
                "wind": self.wind.copy(),
                "motor_tau": self.motor_tau,
                "wind_est": self.wind_est.copy(),
                "vel_error": float(np.linalg.norm(self.vel[0] - self.target_vel)),
                "yaw_error": self._yaw_error(R)}
