# Trial 18 — QUEUED: RecurrentPPO (LSTM) full-envelope generalist

| | |
|---|---|
| run dir | `results_velyaw_lstm` |
| queued behind | trial 17 (high-band chain); starts automatically when it completes |
| date queued | 2026-07-30 |
| question (user) | can ONE model cover 0–25 m/s AND handle the ±20% aero DR? |
| hypothesis | the LSTM performs implicit per-episode system-ID (infers THIS aircraft's coefficients from its response to actions, then adapts) — directly attacks the DR-identification term, the largest item in the V² error budget (±100–200 N at 40 m/s relative). Memory-study caveats apply: keep hand features (they helped even the LSTM), ~3× wall-clock. |
| baseline to beat | best full-envelope generalist: xw17 @12M = **5.26 m/s** |

## Exact changes
1. **`train_lstm.py` REBUILT** for the current env (old version targeted the deleted
   task API): mirrors train.py's full flag set + env kwargs; `RecurrentPPO("MlpLstmPolicy",
   n_steps=2048, batch_size=4096, net_arch=[256,256], lstm_hidden_size=256)`; γ/norm-γ wired;
   `config.json` gains `"algo": "recurrent_ppo"`.
2. **`eval_velyaw.py`** — LSTM support (exact code):
```python
class _Predictor:
    def __init__(self, model, recurrent):
        self.m = model; self.rec = recurrent; self.state = None; self.start = True
    def reset(self):
        self.state = None; self.start = True
    def predict(self, obs, deterministic=True):
        if self.rec:
            a, self.state = self.m.predict(obs, state=self.state,
                                           episode_start=np.array([self.start]),
                                           deterministic=deterministic)
            self.start = False
            return a, None
        return self.m.predict(obs, deterministic=deterministic)
# load(): algo=="recurrent_ppo" -> RecurrentPPO.load(...); returns _Predictor(model, recurrent)
# + fallback to ppo_ratevel_final.zip when best/ absent; model.reset() after every venv.reset()
#   (also added to analyze_velyaw's dive_recovery_test and traces loops)
```
3. Smoke-tested: 8k-step train + full eval path through the recurrent predictor. ✓

## Command (auto-queued)
```bash
python train_lstm.py --xwing-aero --yaw-bias 0.3 --max-speed 25 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --gamma 0.997 --episode-len 14 --n-envs 10 --timesteps 10000000 \
    --out-dir results_velyaw_lstm
# auto: analyze_velyaw.py --dir results_velyaw_lstm && log_trial.py   (~8h at LSTM throughput)
```

## Decision criteria (auto)
- vs xw17's 5.26: **≤ 4.0** → identification value confirmed; next: LSTM + convergence stage,
  and consider LSTM band specialists. **≈ 5** → memory adds nothing over the hand features
  here (consistent with the old memory study); drop the LSTM branch. Also compare its
  DR-only decomposition vs xw18b's 0.56 — the cleanest read on identification value.

---

## INCIDENT (2026-07-30 ~09:03): run killed at 287k steps
No traceback — external kill (probable RAM pressure from RecurrentPPO's 14 s-episode BPTT
buffers, or session teardown). Measured throughput was also impractical: **84 fps** → 10M ≈
33 h. **Relaunched leaner**: `--n-steps 1024` (new flag; halves buffer), 8 envs, episode-len
10 s (shorter BPTT sequences), 6M steps (sufficient for the A/B signal vs xw17; can continue
if promising). γ 0.997 retained.
```bash
python train_lstm.py --xwing-aero --yaw-bias 0.3 --max-speed 25 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --gamma 0.997 --episode-len 10 --n-steps 1024 --n-envs 8 --timesteps 6000000 \
    --out-dir results_velyaw_lstm2
```

## INCIDENT 2 (lstm2 killed at 565k, same signature) → crash-resilient supervisor
Two identical no-traceback deaths (287k, 565k) while MLP runs never die → RAM-pressure kill.
Mitigations (exact code in repo): `VecNormSaveCallback` (stats snapshot every 200k so resume
is consistent), `continue_train.py` gains RecurrentPPO support + `--model-file` (resume from
any checkpoint), and `lstm_supervisor.sh` auto-resumes from the latest checkpoint up to 8
times until the 6M target, then analyzes. Run dir: `results_velyaw_lstm3`, 6 envs.
