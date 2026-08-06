import time

import pytest

import config
import oven


@pytest.fixture
def pid():
    '''PID with simple gains so the math can be checked by hand'''
    return oven.PID(ki=10, kp=2, kd=50)


@pytest.fixture
def sim(monkeypatch):
    '''SimulatedSmoker without a background control thread or auto-restart'''
    monkeypatch.setattr(oven.SimulatedSmoker, 'start', lambda self: None)
    monkeypatch.setattr(oven.config, 'automatic_restarts', False)
    return oven.SimulatedSmoker()


class TestPIDSwitch:
    '''outside the control window the controller is a binary switch'''

    def test_max_heat_when_cold(self, pid):
        assert pid.compute(setpoint=250, ispoint=100, dt=5) == 1

    def test_no_heat_when_hot(self, pid):
        assert pid.compute(setpoint=250, ispoint=400, dt=5) == 0

    def test_output_never_negative(self, pid):
        for ispoint in range(0, 600, 25):
            pid = oven.PID(ki=10, kp=2, kd=50)
            out = pid.compute(setpoint=250, ispoint=ispoint, dt=5)
            assert 0 <= out <= 1

    def test_no_windup_outside_window(self, pid):
        pid.compute(setpoint=252, ispoint=250, dt=5)
        iterm_before = pid.iterm
        pid.compute(setpoint=100, ispoint=250, dt=5)  # far above target
        assert pid.iterm == iterm_before
        assert pid.pidstats['i'] == iterm_before


class TestPIDWithinWindow:
    def test_proportional_term(self, pid):
        pid.compute(setpoint=252, ispoint=250, dt=5)
        # error = 2, kp = 2
        assert pid.pidstats['p'] == pytest.approx(4)

    def test_integral_accumulates(self, pid):
        pid.compute(setpoint=252, ispoint=250, dt=5)
        # error * dt / ki = 2 * 5 / 10 = 1
        assert pid.pidstats['i'] == pytest.approx(1)
        pid.compute(setpoint=252, ispoint=250, dt=5)
        assert pid.pidstats['i'] == pytest.approx(2)

    def test_derivative_term(self, pid):
        pid.compute(setpoint=252, ispoint=250, dt=5)
        # first call: lastErr = 0, so dErr = 2 / 5 = 0.4, kd = 50
        assert pid.pidstats['errDelta'] == pytest.approx(0.4)
        assert pid.pidstats['d'] == pytest.approx(20)

    def test_output_in_range(self, pid):
        out = pid.compute(setpoint=252, ispoint=250, dt=5)
        # 4 + 1 + 20 = 25 -> scaled by window_size of 100
        assert out == pytest.approx(0.25)
        assert pid.pidstats['out'] == pytest.approx(0.25)
        assert pid.pidstats['pid'] == pytest.approx(25)

    def test_control_window_boundary_inclusive(self, pid):
        # error == +window still goes through the proportional branch
        out = pid.compute(setpoint=255, ispoint=250, dt=5)
        assert 0 < out < 1

    def test_dt_drives_integral_and_delta(self, pid):
        pid.compute(setpoint=252, ispoint=250, dt=10)
        # timeDelta is the dt passed in, and doubles the i term
        assert pid.pidstats['timeDelta'] == pytest.approx(10)
        assert pid.pidstats['i'] == pytest.approx(2)


class TestPidstats:
    def test_fields_present(self, pid):
        pid.compute(setpoint=250, ispoint=200, dt=5)
        expected = {'time', 'timeDelta', 'setpoint', 'ispoint', 'err',
                    'errDelta', 'p', 'i', 'd', 'kp', 'ki', 'kd', 'pid', 'out'}
        assert expected <= set(pid.pidstats)

    def test_error_sign(self, pid):
        pid.compute(setpoint=250, ispoint=200, dt=5)  # below target
        assert pid.pidstats['err'] > 0
        pid.compute(setpoint=250, ispoint=300, dt=5)  # above target
        assert pid.pidstats['err'] < 0


class TestBoardSimulated:
    def test_starts_at_ambient(self):
        board = oven.BoardSimulated()
        assert board.temp_c == pytest.approx(config.sim_t_env)
        assert board.temp_sensor.temperature == pytest.approx(69.8)  # 21C in F

    def test_closed_flapper_does_not_heat(self):
        board = oven.BoardSimulated()
        board.step(openness=0, dt=50)
        assert board.temp_c == pytest.approx(config.sim_t_env)

    def test_open_flapper_heats(self):
        board = oven.BoardSimulated()
        board.step(openness=1, dt=50)
        # dT = p_heat * dt / c_oven = 800 * 50 / 2100 ~ 19C
        assert board.temp_c == pytest.approx(config.sim_t_env + 19.05, abs=0.01)

    def test_heat_scales_with_dt(self):
        board = oven.BoardSimulated()
        board.step(openness=1, dt=10)
        ten = board.temp_c
        board = oven.BoardSimulated()
        board.step(openness=1, dt=50)
        fifty = board.temp_c
        # from ambient q_out is ~0, so rise is linear in dt
        assert (fifty - config.sim_t_env) == pytest.approx(
            (ten - config.sim_t_env) * 5, rel=1e-6)

    def test_equilibrium_is_stable(self):
        board = oven.BoardSimulated()
        # T where q_in == q_out for openness = 1
        board.temp_c = config.sim_t_env + config.sim_p_heat * config.sim_r_oven
        before = board.temp_c
        board.step(openness=1, dt=50)
        assert board.temp_c == pytest.approx(before, abs=1e-9)

    def test_celsius_scale(self, monkeypatch):
        monkeypatch.setattr(config, 'temp_scale', 'c')
        board = oven.BoardSimulated()
        assert board.temp_sensor.temperature == pytest.approx(config.sim_t_env)


class TestGetAvgTemp:
    def test_chops_edges(self):
        sensor = oven.TempSensorReal.__new__(oven.TempSensorReal)
        temps = list(range(1, 11))  # 1..10
        # chops 2 items off each end -> avg(3..8) = 5.5
        assert sensor.get_avg_temp(temps, chop=25) == pytest.approx(5.5)

    def test_handles_small_lists(self):
        sensor = oven.TempSensorReal.__new__(oven.TempSensorReal)
        assert sensor.get_avg_temp([5, 7, 9], chop=25) == pytest.approx(7)


class TestSimulatedSmoker:
    def test_start_smoke(self, sim):
        assert sim.state == "IDLE"
        assert sim.start_smoke(250) is True
        assert sim.state == "RUNNING"
        assert sim.setpoint == 250
        assert sim.runtime == 0

    def test_start_smoke_clamps_high(self, sim):
        sim.start_smoke(1000)
        assert sim.setpoint == config.max_setpoint

    def test_start_smoke_clamps_low(self, sim):
        sim.start_smoke(10)
        assert sim.setpoint == config.min_setpoint

    def test_start_smoke_refuses_when_sensor_disconnected(self, sim):
        sim.board.temp_sensor.noConnection = True
        assert sim.start_smoke(250) is False
        assert sim.state == "IDLE"

    def test_set_setpoint_clamps(self, sim):
        sim.set_setpoint(1000)
        assert sim.setpoint == config.max_setpoint

    def test_abort_run_resets(self, sim):
        sim.start_smoke(250)
        sim.abort_run()
        assert sim.state == "IDLE"
        assert sim.heat == 0

    def test_control_heats_toward_setpoint(self, sim):
        sim.start_smoke(250)
        before = sim.current_temp()
        for _ in range(5):
            sim.control()
        assert sim.current_temp() > before

    def test_heat_stays_in_range(self, sim):
        sim.start_smoke(250)
        for _ in range(20):
            sim.control()
            assert 0 <= sim.heat <= 1

    def test_speed_invariance(self, sim):
        # the sim temperature persists across runs, so each speed needs a
        # fresh instance (still ambient). start is patched to a no-op by the
        # fixture, so a plain constructor is thread-free too.
        def run_at_speed(smoker, speed, cycles):
            smoker.speed = speed
            smoker.start_smoke(250)
            for _ in range(cycles):
                smoker.control()
            return smoker.current_temp()

        t1 = run_at_speed(sim, 1, 10)            # 10 x 5s  model time = 50s
        t2 = run_at_speed(oven.SimulatedSmoker(), 2, 5)  # 5 x 10s = 50s
        assert t2 == pytest.approx(t1, abs=0.2)

    def test_check_emergency_when_too_hot(self, sim):
        sim.start_smoke(250)
        sim.board.temp_sensor.temperature = config.emergency_shutoff_temp + 100
        sim.check_emergency()
        assert sim.state == "IDLE"

    def test_get_state_keys(self, sim):
        state = sim.get_state()
        for key in ('state', 'temperature', 'setpoint', 'heat', 'runtime',
                    'units', 'pidstats', 'simulate', 'sim_speed',
                    'wood_alert_threshold', 'wood_alert_cycles'):
            assert key in state
        assert state['simulate'] == config.simulate
        assert state['sim_speed'] == sim.speed

    def test_update_runtime_advances(self, sim):
        sim.start_smoke(250)
        sim.update_runtime()
        time.sleep(0.02)
        sim.update_runtime()
        assert sim.runtime > 0
