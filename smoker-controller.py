#!/usr/bin/env python

import os
import sys
import logging
import json

import bottle
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket import WebSocketError

try:
    sys.dont_write_bytecode = True
    import config
    sys.dont_write_bytecode = False
except ImportError:
    print("Could not import config file.")
    print("Copy config.py.EXAMPLE to config.py and adapt it for your setup.")
    exit(1)

logging.basicConfig(level=config.log_level, format=config.log_format)
log = logging.getLogger("smoker-controller")
log.info("Starting smoker controller")

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(script_dir, 'lib'))

from oven import Smoker, SimulatedSmoker
from ovenWatcher import OvenWatcher

app = bottle.Bottle()

smoker = None
smokerWatcher = None


def build_controller():
    '''construct the smoker and its watcher. deferred so importing this
    module (e.g. in tests) does not start any threads.'''
    global smoker, smokerWatcher
    if config.simulate:
        log.info("running in simulation mode")
        smoker = SimulatedSmoker()
    else:
        log.info("running with real hardware")
        smoker = Smoker()
    smokerWatcher = OvenWatcher(smoker)


def handle_control_message(msgdict):
    '''dispatch a control websocket message. extracted from the ws loop so
    it can be tested directly.'''
    cmd = msgdict.get('cmd')
    if cmd == "RUN":
        setpoint = msgdict.get('setpoint', config.default_setpoint)
        log.info("RUN command received, setpoint = %s" % setpoint)
        if smoker.start_smoke(setpoint):
            smokerWatcher.record()
    elif cmd == "SET_TEMP":
        setpoint = msgdict.get('setpoint')
        if setpoint is not None:
            smoker.set_setpoint(setpoint)
    elif cmd == "SIM_SPEED":
        if config.simulate:
            speed = max(1, int(msgdict.get('speed', 1)))
            smoker.speed = speed
            log.info("simulation speed set to %dx" % speed)
    elif cmd == "STOP":
        log.info("STOP command received")
        smoker.abort_run()


@app.get('/')
def index():
    return bottle.redirect('/index.html')


@app.get('/api/stats')
def api_stats():
    return json.dumps(smoker.get_state())


@app.post('/api')
def api():
    log.info("/api is alive")
    log.info(bottle.request.json)

    if bottle.request.json['cmd'] == 'run':
        setpoint = bottle.request.json.get('setpoint', config.default_setpoint)
        log.info('api requested run at setpoint = %s' % setpoint)
        smoker.start_smoke(setpoint)
        smokerWatcher.record()

    if bottle.request.json['cmd'] == 'stop':
        log.info("api stop command received")
        smoker.abort_run()

    return {"success": True}


@app.route('/<filename:path>')
def send_static(filename):
    return bottle.static_file(filename, root=os.path.join(script_dir, "public"))


def get_websocket_from_request():
    env = bottle.request.environ
    wsock = env.get('wsgi.websocket')
    if not wsock:
        bottle.abort(400, 'Expected WebSocket request.')
    return wsock


@app.route('/control')
def handle_control():
    wsock = get_websocket_from_request()
    log.info("websocket (control) opened")
    while True:
        try:
            message = wsock.receive()
            if not message:
                break
            log.info("Received (control): %s" % message)
            handle_control_message(json.loads(message))
        except WebSocketError as e:
            log.error(e)
            break
    log.info("websocket (control) closed")


@app.route('/status')
def handle_status():
    wsock = get_websocket_from_request()
    smokerWatcher.add_observer(wsock)
    log.info("websocket (status) opened")
    while True:
        try:
            message = wsock.receive()
            wsock.send("Your message was: %r" % message)
        except WebSocketError:
            break
    log.info("websocket (status) closed")


def main():
    build_controller()
    ip = config.listening_ip
    port = config.listening_port
    log.info("listening on %s:%d" % (ip, port))

    server = WSGIServer((ip, port), app, handler_class=WebSocketHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
