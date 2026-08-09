#!/usr/bin/env python3
'''PID tuner for the smoker.

Runs the open-loop "process reaction curve" test:

  1. hold the flapper at a fixed opening until the temperature settles
  2. step the flapper open a bit more and record the temperature response
  3. fit dead time (L) and time constant (T) to the S-shaped curve
  4. compute PID gains for a critically damped closed loop (the default)
     or the aggressive Ziegler-Nichols open-loop gains (--method zn)

The tuner only ever moves the flapper (openness 0..1); it never touches
anything else. It works against the simulated smoker (fast) or the real
hardware (slow, run it on the Pi).

Usage:
    python3 zn-tuner.py                  # simulated smoker, critically damped
    python3 zn-tuner.py --hardware       # real smoker
    python3 zn-tuner.py --method zn      # aggressive Ziegler-Nichols gains
    python3 zn-tuner.py --open1 0.3 --open2 0.5

Results are printed; copy pid_kp/pid_ki/pid_kd into config.py.
'''

import argparse
import json
import logging
import os
import sys
import time

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(script_dir, 'lib'))
try:
    import config
except ImportError:
    print("Could not import config.py - copy config.py.EXAMPLE to config.py first.")
    sys.exit(1)

from oven import BoardSimulated, SimulatedSmoker, Smoker

log = logging.getLogger("zn-tuner")


def recent(samples, window):
    '''the samples that fell within the last `window` seconds. samples is
    a list of (time, temp) tuples sorted by time.'''
    if not samples:
        return []
    t_end = samples[-1][0]
    return [s for s in samples if s[0] >= t_end - window]


def is_steady(samples, window, tolerance):
    '''True when the temperature has stayed within `tolerance` over the
    last `window` seconds. samples is a list of (time, temp) tuples.'''
    tail = recent(samples, window)
    if len(tail) < 2:
        return False
    if tail[-1][0] - tail[0][0] < window * 0.5:
        return False  # the window is not filled with data yet
    temps = [t for _, t in tail]
    return (max(temps) - min(temps)) <= tolerance


def fit_reaction_curve(samples, u1, u2, y1, y2, time_step, noise=0.5):
    '''fit dead time L and time constant T to a step response.

    samples is a list of (time, temp) relative to the moment of the step.
    y1/y2 are the steady state temperatures before/after the step, u1/u2
    the flapper openings. Returns (K, L, T) where K is the process gain
    in degrees per unit openness.'''
    total = y2 - y1
    if abs(total) < 4 * noise:
        raise ValueError("temperature barely moved (%+.1f deg) - bad step" % total)
    if u2 == u1:
        raise ValueError("flapper did not move")

    # dead time: when the temperature first rises above the noise floor.
    # on the noise-free sim this resolves to about one sample interval.
    t_start = None
    for t, temp in samples:
        if temp >= y1 + noise:
            t_start = t
            break
    if t_start is None:
        raise ValueError("temperature never responded to the step")

    # time constant: the 63.2% point of the total change, minus dead time
    target = y1 + 0.632 * total
    t_63 = None
    for t, temp in samples:
        if temp >= target:
            t_63 = t
            break
    if t_63 is None:
        raise ValueError("step response never reached 63.2%% of the change")

    L = max(t_start, time_step)  # never below the sampling resolution
    T = t_63 - L
    K = total / (u2 - u1)
    if L <= 0 or T <= 0:
        raise ValueError("fit produced L=%g T=%g - check the step" % (L, T))
    return K, L, T


def zeigler_nichols(K, L, T):
    '''Ziegler-Nichols open-loop (reaction curve) PID gains.
    Returns (Kp, Ti, Td) in the raw controller convention.'''
    Kp = 1.2 * T / (K * L)
    Ti = 2.0 * L
    Td = 0.5 * L
    return Kp, Ti, Td


def critically_damped(K, L, T, tau=None):
    '''lambda tuning for a first-order-plus-dead-time plant, giving a
    closed loop that is (in the small-dead-time limit) first order, hence
    critically damped: no overshoot.

    tau is the desired closed-loop time constant. the default tau = L is
    the standard fast-but-robust choice. returns (Kp, Ti, Td) in the raw
    controller convention, with Td = 0 (a PI controller; derivative would
    only amplify thermocouple noise on a first-order plant).'''
    if tau is None:
        tau = L
    Kp = T / (K * (tau + L))
    Ti = T
    Td = 0.0
    return Kp, Ti, Td


def to_config_gains(Kp, Ti, Td):
    '''convert raw gains to this project's PID class conventions.

    oven.py computes output = (kp*err + iterm + kd*dErr)/100 (clamped to
    +/-100 first), with iterm += err*dt/ki. so kp = 100*Kp and ki = Ti/kp
    and kd = kp*Td.'''
    kp = 100.0 * Kp
    ki = Ti / kp
    kd = kp * Td
    return kp, ki, kd


class ReactionCurveTuner:
    def __init__(self, smoker, open1, open2, time_step, stability=1.0,
                 noise=0.5, settle_window=300.0, max_wait=7200.0, max_temp=None):
        self.smoker = smoker
        # the model is stepped by hand (and time is instant) whenever the
        # board is simulated, even if the smoker class says otherwise (a
        # real Smoker falls back to a simulated board when GPIO init fails)
        self.simulated = isinstance(smoker.board, BoardSimulated)
        self.open1 = open1
        self.open2 = open2
        self.time_step = time_step
        self.stability = stability
        self.noise = noise
        self.settle_window = settle_window
        self.max_wait = max_wait
        self.max_temp = max_temp if max_temp is not None else \
            (260.0 if config.temp_scale == 'c' else 500.0)
        self.elapsed = 0.0
        self.samples = []
        if self.simulated:
            log.info("simulated model detected: advancing %.0f model-seconds "
                     "per step, no wall-clock waits" % self.time_step)
        else:
            log.info("real hardware detected: waiting %.0f wall-clock seconds "
                     "per sample" % self.time_step)

    def set_flapper(self, openness):
        '''openness is 0 (closed) to 1 (fully open); the only output the
        tuner controls.'''
        self.smoker.heat = openness
        self.smoker.output.heat(openness)

    def step_model(self, dt):
        '''advance the simulated model by dt model-seconds. no-op on the
        real smoker, where time passes on its own.'''
        if self.simulated:
            self.smoker.board.step(self.smoker.heat, dt)

    def read_temp(self):
        return self.smoker.current_temp()

    def settle(self, openness, label):
        '''hold the flapper at `openness` until the temperature settles,
        returning the steady state temperature.'''
        self.set_flapper(openness)
        phase_start = self.elapsed
        while self.elapsed - phase_start < self.max_wait:
            dt = self.time_step
            self.step_model(dt)
            self.elapsed += dt
            temp = self.read_temp()
            self.samples.append((self.elapsed, temp))
            if temp > self.max_temp:
                raise RuntimeError(
                    "temperature %.1f exceeded the safety limit %.1f - aborting"
                    % (temp, self.max_temp))
            if is_steady(self.samples, self.settle_window, self.stability):
                tail = recent(self.samples, self.settle_window)
                steady = sum(t for _, t in tail) / len(tail)
                log.info("  %s settled at %.1f %s after %.0f model-seconds"
                         % (label, steady, _unit(), self.elapsed))
                return steady
            if not self.simulated:
                time.sleep(self.time_step)
        raise RuntimeError(
            "%s never settled within %.0f seconds "
            "(last temperature %.1f %s; try --max-wait to give it longer or "
            "--settle-window if the temperature is just wandering)"
            % (label, self.max_wait, self.read_temp(), _unit()))

    def run(self):
        '''run the whole reaction-curve test. returns (y1, y2, K, L, T).'''
        log.info("step 1: hold flapper at %.2f until the temperature settles"
                 % self.open1)
        y1 = self.settle(self.open1, "baseline")

        log.info("step 2: step flapper to %.2f and watch the temperature"
                 % self.open2)
        t0 = self.elapsed
        self.samples = []
        y2 = self.settle(self.open2, "step response")
        step_samples = [(t - t0, temp) for t, temp in self.samples]

        K, L, T = fit_reaction_curve(step_samples, self.open1, self.open2,
                                     y1, y2, self.time_step, self.noise)
        return y1, y2, K, L, T

    def shutdown(self):
        '''close the flapper.'''
        try:
            self.set_flapper(0)
        except Exception:
            pass


def _unit():
    return "\u00b0C" if config.temp_scale == 'c' else "\u00b0F"


def _fmt_seconds(seconds):
    if seconds >= 60:
        return "%dm %ds" % (int(seconds) // 60, int(seconds) % 60)
    return "%ds" % int(seconds)


def report(y1, y2, K, L, T, method="critically-damped"):
    if method == "zn":
        Kp, Ti, Td = zeigler_nichols(K, L, T)
        header = "Ziegler-Nichols open-loop PID (raw)"
    else:
        Kp, Ti, Td = critically_damped(K, L, T)
        header = "Critically damped (lambda) PID (raw)"
    kp, ki, kd = to_config_gains(Kp, Ti, Td)

    print("\n=== Process reaction curve ===")
    print("  baseline flapper %.2f  ->  temperature %.1f %s" % (TUNER_OPEN1, y1, _unit()))
    print("  stepped  flapper %.2f  ->  temperature %.1f %s" % (TUNER_OPEN2, y2, _unit()))
    print("  process gain   K = %.0f %s per unit openness" % (K, _unit()))
    print("  dead time      L = %s" % _fmt_seconds(L))
    print("  time constant  T = %s" % _fmt_seconds(T))

    print("\n=== %s ===" % header)
    print("  Kp = %.4f    Ti = %s    Td = %s" % (Kp, _fmt_seconds(Ti), _fmt_seconds(Td)))

    print("\n=== Use these values in config.py ===")
    print("  pid_kp = %.3f" % kp)
    print("  pid_ki = %.3f   # integral time, seconds" % ki)
    print("  pid_kd = %.3f" % kd)

    print("\nNotes:")
    if method == "zn":
        print("  - Ziegler-Nichols is aggressive (expect ~25%% overshoot);")
        print("    for barbecue you will probably want to detune from here.")
        print("    rerun without --method zn for the critically damped gains.")
    else:
        print("  - critically damped (lambda) tuning targets no overshoot;")
        print("    rerun with --method zn for the aggressive Ziegler-Nichols gains.")
    print("  - If L looks like one sample interval, dead time is below the")
    print("    sensor resolution and these gains may be too hot.")
    if L <= 3 * TUNER_TIME_STEP:
        print("  - dead time is at the sampling floor - this is expected on the")
        print("    delay-free simulation; the real smoker will have real dead time.")


def choose_smoker(hardware=False, simulate=None):
    '''pick the smoker to tune, mirroring the controller itself: by
    default config.simulate decides, with --hardware / --simulate as
    overrides.'''
    if hardware:
        return Smoker()
    if simulate or config.simulate:
        return SimulatedSmoker()
    return Smoker()


def warn_if_smoke_in_progress():
    '''warn if another controller (e.g. the web server) has a smoke in
    progress - it would keep moving the flapper during the tune.'''
    state_file = config.automatic_restart_state_file
    if not os.path.isfile(state_file):
        return
    age_minutes = (time.time() - os.path.getmtime(state_file)) / 60
    if age_minutes > config.automatic_restart_window:
        return
    try:
        with open(state_file) as f:
            state = json.load(f)
    except (ValueError, IOError):
        return
    if state.get('state') == 'RUNNING':
        print("\nWARNING: %s says a smoke is in progress (setpoint %s, "
              "restarting within %d minutes)."
              % (state_file, state.get('setpoint'),
                 config.automatic_restart_window))
        print("If the web controller is running, stop it first - it will keep")
        print("moving the flapper and corrupt the tune. The tuner will proceed,")
        print("but the results are only valid if nothing else touches the smoker.")


def parse_args():
    p = argparse.ArgumentParser(description="PID tuner for the smoker")
    p.add_argument('--method', choices=('critically-damped', 'zn'),
                   default='critically-damped',
                   help="tuning rule: critically damped (default, no overshoot) "
                        "or aggressive Ziegler-Nichols")
    p.add_argument('--hardware', action='store_true',
                   help="tune the real smoker even if config.simulate is True")
    p.add_argument('--simulate', action='store_true',
                   help="tune the simulation even if config.simulate is False")
    p.add_argument('--open1', type=float, default=0.4,
                   help="flapper openness for the baseline (default 0.4)")
    p.add_argument('--open2', type=float, default=0.6,
                   help="flapper openness for the step (default 0.6)")
    p.add_argument('--max-temp', type=float, default=None,
                   help="safety shutdown temperature (default 500F / 260C)")
    p.add_argument('--max-wait', type=float, default=7200.0,
                   help="max seconds for a phase to settle (default 7200)")
    p.add_argument('--settle-window', type=float, default=300.0,
                   help="seconds of flat temperature required before a phase "
                        "counts as settled (default 300)")
    p.add_argument('--verbose', action='store_true', help="debug logging")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(name)s: %(message)s')

    for op in (args.open1, args.open2):
        if not (0.0 < op <= 1.0):
            print("flapper openness must be between 0 and 1")
            sys.exit(1)
    if args.open2 == args.open1:
        print("open1 and open2 must differ (that's the step)")
        sys.exit(1)

    # take over: the tuner owns the flapper, so the controller must not run.
    # disable auto-restart BEFORE the smoker thread starts, otherwise a fresh
    # state.json can auto-restart a smoke and the controller's control() will
    # keep moving the flapper every cycle, fighting the tuner's constant hold.
    config.automatic_restarts = False

    try:
        if args.hardware:
            smoker = Smoker()
            simulated = False
            why = "forced with --hardware"
        elif args.simulate:
            smoker = SimulatedSmoker()
            simulated = True
            why = "forced with --simulate"
        else:
            simulated = config.simulate
            why = "config.simulate = %s" % config.simulate
            smoker = SimulatedSmoker() if simulated else Smoker()
    except Exception as e:
        print("\nCould not set up the smoker: %s" % e)
        print("This usually means simulate = False in config.py but the")
        print("hardware libraries are not installed. Try:")
        print("    python3 zn-tuner.py --simulate")
        sys.exit(1)

    # warn about another controller (e.g. the web server) driving the flapper
    warn_if_smoke_in_progress()

    if simulated:
        print("\nTuning the simulated smoker (no hardware needed, %s)." % why)
    else:
        print("\nWARNING: tuning the real smoker (%s)." % why)
        print("Make sure the fire is burning and keep an eye on it - the")
        print("tuner will hold the flapper open at %.2f for a while." % args.open2)

    smoker.abort_run()
    if smoker.state != "IDLE":
        log.warning("controller thread is still running (state %s), stopping it"
                    % smoker.state)
        smoker.abort_run()

    tuner = ReactionCurveTuner(smoker, args.open1, args.open2,
                               time_step=smoker.time_step,
                               settle_window=args.settle_window,
                               max_wait=args.max_wait,
                               max_temp=args.max_temp)
    try:
        y1, y2, K, L, T = tuner.run()
    except (RuntimeError, ValueError) as e:
        print("\nTuning failed: %s" % e)
        sys.exit(1)
    finally:
        tuner.shutdown()

    global TUNER_OPEN1, TUNER_OPEN2, TUNER_TIME_STEP
    TUNER_OPEN1, TUNER_OPEN2, TUNER_TIME_STEP = args.open1, args.open2, smoker.time_step
    report(y1, y2, K, L, T, method=args.method)


if __name__ == "__main__":
    main()
