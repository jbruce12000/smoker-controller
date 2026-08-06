import json

import pytest

import ovenWatcher


class FakeSmoker:
    def __init__(self, state, time_step=5):
        self.state = state
        self.time_step = time_step

    def get_state(self):
        return self.state


class FakeSocket:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


class BadSocket:
    def send(self, msg):
        raise RuntimeError("broken socket")


def make_watcher(smoker):
    '''build an OvenWatcher without a background thread'''
    w = ovenWatcher.OvenWatcher.__new__(ovenWatcher.OvenWatcher)
    w.smoker = smoker
    w.last_log = []
    w.observers = []
    return w


def run_once(w, monkeypatch):
    '''execute one iteration of the run loop, then break out of it'''
    def boom(s):
        raise StopIteration
    monkeypatch.setattr(ovenWatcher.time, 'sleep', boom)
    with pytest.raises(StopIteration):
        w.run()


class TestRun:
    def test_appends_running_state_and_notifies(self, monkeypatch):
        smoker = FakeSmoker({'state': 'RUNNING', 'temperature': 250})
        w = make_watcher(smoker)
        sock = FakeSocket()
        w.observers.append(sock)
        run_once(w, monkeypatch)
        assert w.last_log == [smoker.state]
        assert len(sock.sent) == 1

    def test_idle_state_notified_but_not_logged(self, monkeypatch):
        smoker = FakeSmoker({'state': 'IDLE', 'temperature': 70})
        w = make_watcher(smoker)
        sock = FakeSocket()
        w.observers.append(sock)
        run_once(w, monkeypatch)
        assert w.last_log == []
        assert len(sock.sent) == 1


class TestRecord:
    def test_clears_old_history(self):
        smoker = FakeSmoker({'state': 'RUNNING', 'temperature': 250})
        w = make_watcher(smoker)
        w.last_log = [{'old': 1}, {'old': 2}]
        w.record()
        assert w.last_log == [smoker.state]


class TestLastlogSubset:
    def test_returns_everything_when_small(self):
        w = make_watcher(FakeSmoker({'state': 'RUNNING', 'temperature': 100}))
        w.last_log = [{'i': i} for i in range(100)]
        assert w.lastlog_subset(maxpts=500) == w.last_log

    def test_decimates_large_history(self):
        w = make_watcher(FakeSmoker({'state': 'RUNNING', 'temperature': 100}))
        w.last_log = [{'i': i} for i in range(600)]
        subset = w.lastlog_subset(maxpts=100)
        # every_nth = int(600 / 99) = 6
        assert len(subset) == 100
        assert subset[0] == w.last_log[0]
        assert subset[1] == w.last_log[6]


class TestAddObserver:
    def test_sends_backlog_and_registers(self):
        smoker = FakeSmoker({'state': 'RUNNING', 'temperature': 250})
        w = make_watcher(smoker)
        w.last_log = [{'state': 'RUNNING', 'temperature': 200}]
        sock = FakeSocket()
        w.add_observer(sock)
        assert len(sock.sent) == 1
        msg = json.loads(sock.sent[0])
        assert msg['type'] == 'backlog'
        assert msg['state'] == smoker.state
        assert msg['log'] == w.last_log
        assert w.observers == [sock]

    def test_registers_even_if_backlog_fails(self):
        smoker = FakeSmoker({'state': 'RUNNING', 'temperature': 250})
        w = make_watcher(smoker)
        w.last_log = [{'state': 'RUNNING', 'temperature': 200}]
        bad = BadSocket()
        w.add_observer(bad)
        assert w.observers == [bad]


class TestNotifyAll:
    def test_sends_to_all_observers(self):
        w = make_watcher(FakeSmoker({'state': 'RUNNING', 'temperature': 250}))
        s1, s2 = FakeSocket(), FakeSocket()
        w.observers = [s1, s2]
        w.notify_all({'state': 'RUNNING', 'temperature': 250})
        assert json.loads(s1.sent[0]) == {'state': 'RUNNING', 'temperature': 250}
        assert json.loads(s2.sent[0]) == {'state': 'RUNNING', 'temperature': 250}

    def test_removes_dead_and_empty_sockets(self):
        w = make_watcher(FakeSmoker({'state': 'RUNNING', 'temperature': 250}))
        good, bad = FakeSocket(), BadSocket()
        w.observers = [good, bad, None]
        w.notify_all({'state': 'RUNNING'})
        assert w.observers == [good]
        assert len(good.sent) == 1
