import threading
import logging
import json
import time
import config
from oven import Smoker

log = logging.getLogger(__name__)


class OvenWatcher(threading.Thread):
    '''records the smoker state and pushes it to all connected websocket clients'''
    def __init__(self, smoker):
        self.last_log = []
        self.observers = []
        threading.Thread.__init__(self)
        self.daemon = True
        self.smoker = smoker
        self.start()

    def run(self):
        while True:
            smoker_state = self.smoker.get_state()

            # record state for any new clients that join
            if smoker_state.get("state") == "RUNNING":
                self.last_log.append(smoker_state)

            self.notify_all(smoker_state)
            time.sleep(self.smoker.time_step)

    def lastlog_subset(self, maxpts=500):
        '''send about maxpts from lastlog by skipping unwanted data'''
        totalpts = len(self.last_log)
        if totalpts <= maxpts:
            return self.last_log
        every_nth = int(totalpts / (maxpts - 1))
        return self.last_log[::every_nth]

    def record(self):
        self.last_log = []
        self.last_log.append(self.smoker.get_state())

    def add_observer(self, observer):
        backlog = {
            'type': "backlog",
            'log': self.lastlog_subset(),
            'state': self.smoker.get_state(),
        }
        try:
            observer.send(json.dumps(backlog))
        except Exception:
            log.error("Could not send backlog to new observer")

        self.observers.append(observer)

    def notify_all(self, message):
        message_json = json.dumps(message)
        log.debug("sending to %d clients: %s" % (len(self.observers), message_json))
        for wsock in self.observers[:]:
            if wsock:
                try:
                    wsock.send(message_json)
                except Exception:
                    log.error("could not write to socket %s" % wsock)
                    self.observers.remove(wsock)
            else:
                self.observers.remove(wsock)
