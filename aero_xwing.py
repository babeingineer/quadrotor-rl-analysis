"""Faithful Python/numpy port of the XWing MATLAB aerodynamic model (funcAeroModel).

Given angle-of-attack `alpha`, sideslip `beta` (rad), airspeed `Va` (m/s), body rates
`Wb=[Wx,Wy,Wz]` (rad/s), air density `rho`, reference area/chord/span `S,C,b`, CoM
`[Xg,Yg,Zg]`, elevon deflections `Fin1,Fin2`, and a 17-element randomization vector
`rand_mat`, returns body-frame aerodynamic force `F` (3) and moment `M` (3).

This is a line-by-line translation of the MATLAB source (kept identical for verifiability):
coefficient constants, the alpha/beta 90-deg "folding", the nonlinear cx/cy/cz tables, and
the mx/my/mz moment build-up are all reproduced exactly. Set Fin1=Fin2=0 for the passive
(no-control-surface) aero — the weathervane static stiffness + rate damping that limit
rotational authority as airspeed rises.
"""
import numpy as np


def _sigmoid(x, x0, M):
    return 1.0 / (1.0 + np.exp(M * (x0 - x)))


def _poly3(c, x):
    return c[0] * x ** 3 + c[1] * x ** 2 + c[2] * x + c[3]


def _cx_non_linear(alpha, beta):
    """alpha, beta in RADIANS (already folded)."""
    CX0 = 0.022415926
    CXIAA0 = 0.78342879; ALPHA0 = -0.70572338
    CXIAA1 = 0.44780622; ALPHA1 = -6.74631689
    CXA_A0 = 0.516528819402; CXA_B0 = -0.085022931456
    CXA_A1 = -0.516528819402; CXA_B1 = -0.095022931456
    CXIBB = 0.210858354; CXB_A = 0.311635595721; CXB_B = -0.111292951456
    ad = np.degrees(alpha)
    cxa = ((1 - _sigmoid(ad, 1.5, 1.5)) *
           ((1 - _sigmoid(-ad, 22, 1)) * CXIAA0 * (alpha - np.radians(ALPHA0)) ** 2
            + _sigmoid(-ad, 22, 1) * (CXA_A1 * alpha + CXA_B1))
           + _sigmoid(ad, 1.5, 1.5) *
           ((1 - _sigmoid(ad, 28, 1)) * CXIAA1 * (alpha - np.radians(ALPHA1)) ** 2
            + _sigmoid(ad, 28, 1) * (CXA_A0 * alpha + CXA_B0)))
    bd = np.degrees(abs(beta))
    cxb = (1 - _sigmoid(bd, 34, 1)) * CXIBB * beta ** 2 + _sigmoid(bd, 34, 1) * (CXB_A * abs(beta) + CXB_B)
    return CX0 + cxa + cxb


def _cy_non_linear(alpha_deg):
    """alpha in DEGREES."""
    CY_NEG_NON_LIN = _poly3([0.000001528278, 0.000419128382, 0.026408163550, 0.083048585587], alpha_deg)
    CY_POS_NON_LIN = _poly3([0.000001311488, -0.000341258538, 0.018110345498, 0.143189427827], alpha_deg)
    CY_NEG_LIN = _poly3([-0.000598038658, -0.003442946059, 0.023749813987, 0.089668295538], alpha_deg)
    CY_POS_LIN = _poly3([-0.000006613339, -0.000013852559, 0.018676051853, 0.057226463253], alpha_deg)
    return ((1 - _sigmoid(alpha_deg, 3.3, 1.4)) *
            ((1 - _sigmoid(-alpha_deg, 7, 1)) * CY_NEG_LIN + _sigmoid(-alpha_deg, 7, 1) * CY_NEG_NON_LIN)
            + _sigmoid(alpha_deg, 3, 1.4) *
            ((1 - _sigmoid(alpha_deg, 29, 1)) * CY_POS_LIN + _sigmoid(alpha_deg, 29, 1) * CY_POS_NON_LIN))


def _cz_non_linear(beta_deg):
    """beta in DEGREES."""
    ab = abs(beta_deg)
    CZB_LIN_0 = -0.007179464182 * ab
    CZB_LIN_1 = -0.006799650085 * ab + 0.010249503314
    CZB_NON_LIN = _poly3([-0.000000668920, 0.000187774983, -0.012541772294, 0.075713571462], ab)
    return np.sign(beta_deg) * ((1 - _sigmoid(ab, 3, 2)) * CZB_LIN_0
                                + _sigmoid(ab, 3, 2) * ((1 - _sigmoid(ab, 21, 1)) * CZB_LIN_1
                                                        + _sigmoid(ab, 21, 1) * CZB_NON_LIN))


def _fold(ang_rad):
    """MATLAB 90-deg triangle folding of an angle (rad in -> rad out)."""
    d = np.degrees(ang_rad)
    return np.radians(np.mod(np.floor(d / 90), 2) * 90 + (-1.0) ** np.floor(d / 90) * np.mod(d, 90))


def func_aero_model(alpha, beta, Va, Wb, rho, S, C, b, CoM, Fin1, Fin2, rand_mat):
    Wx, Wy, Wz = Wb
    Xg, Yg = CoM[0], CoM[1]
    de = (Fin1 + Fin2) / 2.0
    da = (Fin2 - Fin1) / 2.0

    KSI = -13.17723091
    CXIDD = 0.070462936 * rand_mat[0]
    CYDE = -0.246638127 * rand_mat[1]
    CZDA = -0.003733863 * rand_mat[2]

    AXB = -0.332427957; BXB = 0.011053507
    MXB = (AXB * Yg + BXB) * rand_mat[3]
    MXDA = 0.032052967 * rand_mat[4]
    MXWX = -0.211755786 * rand_mat[5]

    AB = 0.330009974; BB = -0.141106402; ADA = 0.00370686; BDA = -0.000542507
    AWY = -0.200254404; BWY = 0.184485367; CWY = -0.044960659
    MYB = (AB * Xg + BB) * rand_mat[6]
    MYDA = (ADA * Xg + BDA) * rand_mat[7]
    MYWY = (AWY * Xg * Xg + BWY * Xg + CWY) * rand_mat[8]

    A0 = 0.076676624; B0 = -0.037770391
    AA_NEG = 1.186820596; BA_NEG = -0.543687141; AA_POS = 0.884270845; BA_POS = -0.396678696
    ADE = -0.248224398; BDE = 0.141370881; AWZ = -0.448746427; BWZ = 0.400671268; CWZ = -0.098542354
    MZ0 = (A0 * Xg + B0) * rand_mat[9]
    MZA = ((1 + np.sign(alpha)) / 2 * (AA_POS * Xg + BA_POS) * rand_mat[10]
           + (1 - np.sign(alpha)) / 2 * (AA_NEG * Xg + BA_NEG) * rand_mat[11])
    MZDE = (ADE * Xg + BDE) * rand_mat[12]
    MZWZ = (AWZ * Xg * Xg + BWZ * Xg + CWZ) * rand_mat[13]

    alpha_cx = _fold(alpha)
    beta_cx = _fold(beta)

    cx = _cx_non_linear(alpha_cx, beta_cx) * rand_mat[14] + CXIDD * (de + KSI * alpha_cx) * de / 2.0
    cy = _cy_non_linear(np.degrees(alpha)) * rand_mat[15] + CYDE * de
    cz = _cz_non_linear(np.degrees(beta)) * rand_mat[16] + CZDA * da

    Va = max(Va, 1e-6)
    Q = 0.5 * rho * Va * Va
    QS = Q * S
    fd = -QS * cx
    fl = QS * cy
    fs = QS * cz

    ca, sa = np.cos(alpha), np.sin(alpha)
    cb, sb = np.cos(beta), np.sin(beta)
    T1 = np.array([[ca, sa, 0.0], [-sa, ca, 0.0], [0.0, 0.0, 1.0]])
    T2 = np.array([[cb, 0.0, -sb], [0.0, 1.0, 0.0], [sb, 0.0, cb]])
    F = (T1 @ T2) @ np.array([fd, fl, fs])

    mx = MXB * beta_cx + MXDA * da + MXWX * Wx * C / (2.0 * Va)
    my = MYB * np.sign(beta) * beta_cx + MYDA * da + MYWY * Wy * b / Va
    mz = MZ0 + MZA * np.sign(alpha) * alpha_cx + MZDE * de + MZWZ * Wz * b / Va
    M = QS * C * np.array([mx, my, mz])
    return F, M
