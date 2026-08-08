import importlib.util
import math
import os

import pytest

import config
import oven

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'zn_tuner', os.path.join(_here, '..', 'zn-tuner.py'))
zn_tuner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(zn_tuner)

zt = zn_tuner


def step_response(K, L, T, y1, u2, u1, time_step, duration, noise=0.0):
    '''synthetic samples of a first-order step response plus dead time:
    temp(t) = y1 for t < L, then y1 + K*(u2-u1)*(1 - exp(-(t-L)/T)).'''
    total = K * (u2 - u1)
    samples = []
    t = 0
    while t <= duration:
        if t < L:
            temp = y1
        else:
            temp = y1 + total * (1 - math.exp(-(t - L) / T))
        if noise:
            temp += noise * math.sin(t)
        samples.append((t, temp))
        t += time_step
    return samples


class TestFitReactionCurve:
    def test_recovers_known_parameters(self):
        # response rises past the noise floor within one sample of the true
        # dead time, so the fit resolves L and T to the sampling grid
        y1, K, L, T, u1, u2, dt = 100.0, 2000.0, 20.0, 200.0, 0.4, 0.6, 1.0
        samples = step_response(K, L, T, y1, u2, u1, dt, duration=500)
        fit_K, fit_L, fit_T = zt.fit_reaction_curve(samples, u1, u2, y1,
                                                    y1 + K * (u2 - u1), dt)
        assert fit_K == pytest.approx(K, rel=1e-9)
        assert fit_L == pytest.approx(L, abs=1.5)
        assert fit_T == pytest.approx(T, abs=2)

    def test_process_gain_is_total_over_delta_openness(self):
        y1, u1, u2, dt = 100.0, 0.5, 1.0, 1.0
        samples = step_response(400.0, 0.0, 50.0, y1, u2, u1, dt, duration=300)
        fit_K, _, _ = zt.fit_reaction_curve(samples, u1, u2, y1, 300.0, dt)
        assert fit_K == pytest.approx(400.0)

    def test_dead_time_never_below_sampling_resolution(self):
        # no real dead time: the fit must still report at least one sample
        # interval, which shifts the time constant down by one dt
        y1, u1, u2, dt = 100.0, 0.4, 0.6, 5.0
        samples = step_response(250.0, 0.0, 100.0, y1, u2, u1, dt, duration=800)
        fit_K, fit_L, fit_T = zt.fit_reaction_curve(samples, u1, u2, y1,
                                                    y1 + 50.0, dt)
        assert fit_L == pytest.approx(dt)
        assert fit_T == pytest.approx(100.0, abs=dt)

    def test_rejects_step_that_barely_moved(self):
        samples = [(t, 100.0) for t in range(0, 100, 1)]
        with pytest.raises(ValueError):
            zt.fit_reaction_curve(samples, 0.4, 0.6, 100.0, 101.0, 1.0)

    def test_rejects_flat_flapper(self):
        samples = step_response(250.0, 10.0, 100.0, 200.0, 0.6, 0.6, 1.0, 400)
        with pytest.raises(ValueError):
            zt.fit_reaction_curve(samples, 0.6, 0.6, 200.0, 300.0, 1.0)

    def test_rejects_no_response(self):
        samples = [(t, 200.0) for t in range(0, 100, 1)]
        with pytest.raises(ValueError):
            zt.fit_reaction_curve(samples, 0.4, 0.6, 200.0, 400.0, 1.0)


class TestZeiglerNichols:
    def test_hand_checked_gains(self):
        K, L, T = 2.0, 4.0, 50.0
        Kp, Ti, Td = zt.zeigler_nichols(K, L, T)
        assert Kp == pytest.approx(1.2 * T / (K * L))
        assert Ti == pytest.approx(2.0 * L)
        assert Td == pytest.approx(0.5 * L)


class TestCriticallyDamped:
    def test_default_closed_loop_time_constant_is_dead_time(self):
        # Kp = T/(K*(tau+L)) with tau = L by default, so Kp = T/(2KL)
        K, L, T = 720.0, 5.0, 1050.0
        Kp, Ti, Td = zt.critically_damped(K, L, T)
        assert Kp == pytest.approx(T / (K * 2 * L))
        assert Ti == pytest.approx(T)
        assert Td == 0.0

    def test_explicit_tau(self):
        K, L, T, tau = 720.0, 5.0, 1050.0, 20.0
        Kp, Ti, Td = zt.critically_damped(K, L, T, tau=tau)
        assert Kp == pytest.approx(T / (K * (tau + L)))
        assert Ti == pytest.approx(T)

    def test_no_derivative(self):
        # derivative would only amplify thermocouple noise on a first-order
        # plant, so the critically damped rule is a PI controller
        _, _, Td = zt.critically_damped(720.0, 5.0, 1050.0)
        assert Td == 0.0

    def test_config_gains(self):
        K, L, T = 720.0, 5.0, 1050.0
        Kp, Ti, Td = zt.critically_damped(K, L, T)
        kp, ki, kd = zt.to_config_gains(Kp, Ti, Td)
        assert kp == pytest.approx(100.0 * Kp)
        assert ki == pytest.approx(Ti / (100.0 * Kp))
        assert kd == 0.0

    def test_sim_gains_are_less_aggressive_than_zn(self):
        K, L, T = 720.0, 5.0, 1050.0
        cd_kp, _, _ = zt.to_config_gains(*zt.critically_damped(K, L, T))
        zn_kp, _, _ = zt.to_config_gains(*zt.zeigler_nichols(K, L, T))
        assert cd_kp < zn_kp


class TestToConfigGains:
    def test_converts_to_project_convention(self):
        # oven.py: output = (kp*err + iterm + kd*dErr)/100,
        # iterm += err*dt/ki, so kp = 100*Kp, ki = Ti/kp, kd = kp*Td
        Kp, Ti, Td = 0.3333, 10.0, 2.5
        kp, ki, kd = zt.to_config_gains(Kp, Ti, Td)
        assert kp == pytest.approx(100.0 * Kp)
        assert ki == pytest.approx(Ti / (100.0 * Kp))
        assert kd == pytest.approx(100.0 * Kp * Td)

    def test_round_trip_with_known_curve(self):
        y1, K, L, T, u1, u2, dt = 100.0, 2000.0, 20.0, 200.0, 0.4, 0.6, 1.0
        samples = step_response(K, L, T, y1, u2, u1, dt, duration=500)
        fit_K, fit_L, fit_T = zt.fit_reaction_curve(samples, u1, u2, y1,
                                                    y1 + K * (u2 - u1), dt)
        Kp, Ti, Td = zt.zeigler_nichols(fit_K, fit_L, fit_T)
        kp, ki, kd = zt.to_config_gains(Kp, Ti, Td)
        # the whole chain is wired together: config gains come from the fit
        assert kp == pytest.approx(100.0 * 1.2 * fit_T / (fit_K * fit_L))
        assert ki == pytest.approx(Ti / kp)
        assert kd == pytest.approx(kp * Td)


class TestIsSteady:
    def test_flat_temperature_is_steady(self):
        samples = [(t * 5.0, 350.0) for t in range(100)]  # 500s of flat data
        assert zt.is_steady(samples, window=300, tolerance=1.0)

    def test_flat_window_inside_noisy_run(self):
        samples = []
        for t in range(0, 1000, 5):
            temp = 300.0 if t < 650 else 350.0 + 0.2 * math.sin(t)
            samples.append((t, temp))
        assert zt.is_steady(samples, window=300, tolerance=1.0)

    def test_window_not_filled_with_data(self):
        # two samples 10s apart: recent() has them but the span is far
        # short of half the window, so not enough history to call it steady
        samples = [(100.0, 350.0), (110.0, 350.2)]
        assert not zt.is_steady(samples, window=300, tolerance=1.0)

    def test_rising_temperature_not_steady(self):
        samples = [(t * 5.0, 300.0 + t) for t in range(100)]
        assert not zt.is_steady(samples, window=300, tolerance=1.0)

    def test_empty_is_not_steady(self):
        assert not zt.is_steady([], window=300, tolerance=1.0)


class TestRecent:
    def test_keeps_only_last_window(self):
        samples = [(0, 1.0), (10, 2.0), (20, 3.0), (30, 4.0)]
        tail = zt.recent(samples, window=15)
        assert tail == [(20, 3.0), (30, 4.0)]

    def test_empty_input(self):
        assert zt.recent([], window=15) == []


class TestClosedLoopIntegration:
    '''gains from the tuner actually converge on the simulated smoker'''

    def test_critically_damped_gains_converge_without_overshoot(self):
        # model theory: K = p_heat*r_oven per unit openness (scaled to the
        # configured temperature scale), T = r_oven*c_oven, L = the sensor
        # sampling interval (dead time resolves to the floor on the sim)
        scale = 9.0 / 5.0 if config.temp_scale == 'f' else 1.0
        K = config.sim_p_heat * config.sim_r_oven * scale
        T = config.sim_r_oven * config.sim_c_oven
        L = config.sensor_time_wait
        Kp, Ti, Td = zt.critically_damped(K, L, T)
        kp, ki, kd = zt.to_config_gains(Kp, Ti, Td)

        smoker = oven.SimulatedSmoker.__new__(oven.SimulatedSmoker)
        smoker.board = oven.BoardSimulated()
        smoker.output = oven.Output()
        smoker.time_step = config.sensor_time_wait
        smoker.speed = 1
        smoker.reset()
        smoker.pid = oven.PID(ki=ki, kp=kp, kd=kd)
        smoker.setpoint = 250
        smoker.state = "RUNNING"
        smoker.runtime = 0

        peak = 0.0
        for _ in range(400):
            smoker.control()
            peak = max(peak, smoker.current_temp())
        assert smoker.current_temp() == pytest.approx(250, abs=60)
        assert peak <= 255  # critically damped: no overshoot past the target
