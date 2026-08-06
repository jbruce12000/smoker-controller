import importlib.util
import json
import os

import pytest
import webtest

import config

# the app lives in smoker-controller.py, which is not a valid module name
_spec = importlib.util.spec_from_file_location(
    'smoker_controller', os.path.join(os.path.dirname(__file__), '..', 'smoker-controller.py'))
smoker_controller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoker_controller)

sc = smoker_controller


class FakeSmoker:
    def __init__(self, state):
        self.state = state
        self.speed = config.sim_speed
        self.calls = []
        self.records = []

    def get_state(self):
        return dict(self.state)

    def start_smoke(self, setpoint):
        self.calls.append(('start_smoke', setpoint))
        self.state = {'state': 'RUNNING', 'temperature': 70, 'setpoint': setpoint}
        return True

    def set_setpoint(self, setpoint):
        self.calls.append(('set_setpoint', setpoint))

    def abort_run(self):
        self.calls.append(('abort_run',))
        self.state = {'state': 'IDLE', 'temperature': 70, 'setpoint': 0}


class FakeWatcher:
    def __init__(self):
        self.recorded = 0
        self.observers = []

    def record(self):
        self.recorded += 1

    def add_observer(self, observer):
        self.observers.append(observer)


@pytest.fixture
def app(monkeypatch):
    '''smoker-controller routes wired to fakes'''
    fake_smoker = FakeSmoker({'state': 'IDLE', 'temperature': 70,
                              'setpoint': 0, 'heat': 0, 'runtime': 0,
                              'units': 'f', 'pidstats': {},
                              'simulate': config.simulate,
                              'sim_speed': config.sim_speed})
    fake_watcher = FakeWatcher()
    monkeypatch.setattr(sc, 'smoker', fake_smoker)
    monkeypatch.setattr(sc, 'smokerWatcher', fake_watcher)
    return webtest.TestApp(sc.app)


class TestApiStats:
    def test_returns_state_json(self, app):
        resp = app.get('/api/stats')
        assert resp.status_code == 200
        assert json.loads(resp.text)['state'] == 'IDLE'


class TestApiPost:
    def test_run_command(self, app):
        resp = app.post_json('/api', {'cmd': 'run', 'setpoint': 250})
        assert resp.status_code == 200
        assert resp.json == {'success': True}
        assert ('start_smoke', 250) in sc.smoker.calls
        assert sc.smokerWatcher.recorded == 1

    def test_run_uses_default_setpoint(self, app, monkeypatch):
        monkeypatch.setattr(config, 'default_setpoint', 225)
        app.post_json('/api', {'cmd': 'run'})
        assert ('start_smoke', 225) in sc.smoker.calls

    def test_stop_command(self, app):
        app.post_json('/api', {'cmd': 'stop'})
        assert ('abort_run',) in sc.smoker.calls


class TestWebRoot:
    def test_root_redirects(self, app):
        resp = app.get('/')
        assert resp.status_code == 302
        assert resp.location.endswith('/index.html')

    def test_index_served(self, app):
        resp = app.get('/index.html')
        assert resp.status_code == 200
        assert 'smoker' in resp.text.lower()

    def test_missing_file_404(self, app):
        assert app.get('/does-not-exist', status=404)


class TestHandleControlMessage:
    def test_run_command(self, app):
        sc.handle_control_message({'cmd': 'RUN', 'setpoint': 250})
        assert ('start_smoke', 250) in sc.smoker.calls
        assert sc.smokerWatcher.recorded == 1

    def test_run_uses_default_setpoint(self, app, monkeypatch):
        monkeypatch.setattr(config, 'default_setpoint', 225)
        sc.handle_control_message({'cmd': 'RUN'})
        assert ('start_smoke', 225) in sc.smoker.calls

    def test_set_temp(self, app):
        sc.handle_control_message({'cmd': 'SET_TEMP', 'setpoint': 275})
        assert ('set_setpoint', 275) in sc.smoker.calls

    def test_set_temp_without_value_is_ignored(self, app):
        sc.handle_control_message({'cmd': 'SET_TEMP'})
        assert sc.smoker.calls == []

    def test_stop_command(self, app):
        sc.handle_control_message({'cmd': 'STOP'})
        assert ('abort_run',) in sc.smoker.calls

    def test_sim_speed_in_simulation(self, app, monkeypatch):
        monkeypatch.setattr(config, 'simulate', True)
        sc.handle_control_message({'cmd': 'SIM_SPEED', 'speed': 10})
        assert sc.smoker.speed == 10

    def test_sim_speed_floor(self, app, monkeypatch):
        monkeypatch.setattr(config, 'simulate', True)
        sc.handle_control_message({'cmd': 'SIM_SPEED', 'speed': 0})
        assert sc.smoker.speed == 1

    def test_sim_speed_ignored_without_simulation(self, app, monkeypatch):
        monkeypatch.setattr(config, 'simulate', False)
        sc.handle_control_message({'cmd': 'SIM_SPEED', 'speed': 10})
        assert sc.smoker.speed == config.sim_speed

    def test_unknown_command_is_ignored(self, app):
        sc.handle_control_message({'cmd': 'FLIP_THE_OVEN'})
        assert sc.smoker.calls == []
