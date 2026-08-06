#!/usr/bin/env python
import requests
import json
import time
import logging

# monitors your smoker stats every N seconds
# if X checks fail, an alert is sent to a slack channel
# configure an incoming web hook on the slack channel and
# set slack_hook_url to that

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class Watcher(object):

    def __init__(self, smoker_url, slack_hook_url, bad_check_limit=6, temp_error_limit=10, sleepfor=10):
        self.smoker_url = smoker_url
        self.slack_hook_url = slack_hook_url
        self.bad_check_limit = bad_check_limit
        self.temp_error_limit = temp_error_limit
        self.sleepfor = sleepfor
        self.bad_checks = 0
        self.stats = {}

    def get_stats(self):
        try:
            r = requests.get(self.smoker_url, timeout=1)
            return r.json()
        except requests.exceptions.Timeout:
            log.error("network timeout. check smoker_url and port.")
            return {}
        except requests.exceptions.ConnectionError:
            log.error("network connection error. check smoker_url and port.")
            return {}
        except:
            return {}

    def send_alert(self, msg):
        log.error("sending alert: %s" % msg)
        try:
            requests.post(self.slack_hook_url, json={'text': msg})
        except:
            pass

    def has_errors(self):
        if not self.stats:
            log.error("no data")
            return True
        if 'state' in self.stats and self.stats['state'] != 'RUNNING':
            log.error("smoker not running")
            return True
        if 'temperature' in self.stats and 'setpoint' in self.stats:
            err = abs(self.stats['setpoint'] - self.stats['temperature'])
            if err > self.temp_error_limit:
                log.error("temp out of whack %0.2f" % err)
                return True
        return False

    def run(self):
        log.info("started watching %s" % self.smoker_url)
        while True:
            self.stats = self.get_stats()
            if self.has_errors():
                self.bad_checks = self.bad_checks + 1
            else:
                log.info("OK temp=%0.2f target=%0.2f flapper=%0.2f%%" %
                         (self.stats['temperature'], self.stats['setpoint'], self.stats['heat']))

            if self.bad_checks >= self.bad_check_limit:
                msg = "error smoker needs help. %s" % json.dumps(self.stats, indent=2, sort_keys=True)
                self.send_alert(msg)
                self.bad_checks = 0

            time.sleep(self.sleepfor)

if __name__ == "__main__":

    watcher = Watcher(
        smoker_url = "http://192.168.1.84:8081/api/stats",
        slack_hook_url = "you must add this",
        bad_check_limit = 6,
        temp_error_limit = 10,
        sleepfor = 10 )

    watcher.run()
