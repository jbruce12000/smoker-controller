import threading
import time
import datetime
import logging
import json
import os
import config

log = logging.getLogger(__name__)


class Output(object):
    '''controls the servo that opens and closes the smoker flapper'''

    def __init__(self):
        self.active = False
        self.gpio_servo = config.gpio_servo
        self.min_servo_angle = config.min_servo_angle
        self.max_servo_angle = config.max_servo_angle
        self.invert_servo = config.invert_servo
        self.load_libs()
        if self.active:
            self.servo = self.AngularServo(self.gpio_servo,
                                           min_angle=self.min_servo_angle,
                                           max_angle=self.max_servo_angle)
            self.reset()
        else:
            self.servo = None

    def reset(self):
        '''close the flapper'''
        if self.servo is None:
            return
        if self.invert_servo:
            self.move_slow(self.max_servo_angle)
        else:
            self.move_slow(self.min_servo_angle)

    def load_libs(self):
        '''load all the libs required by this class'''
        try:
            import gpiozero
            from gpiozero import AngularServo
            self.AngularServo = AngularServo
            from gpiozero.pins.pigpio import PiGPIOFactory
            gpiozero.Device.pin_factory = PiGPIOFactory('127.0.0.1')
            self.active = True
        except Exception:
            log.warning("Could not initialize GPIOs, smoker operation will only be simulated!")
            self.active = False

    def move_slow(self, end):
        '''move the servo 2 degrees at a time with a 1/10s sleep in between.
        less noise, less stress on the servo, less current spikes.
        returns the time spent moving.'''
        if self.servo is None:
            return 0
        start = int(self.servo.angle)
        end = int(end)
        step = 2
        slept = 0
        if start > end:
            step = step * -1

        log.info("servo changing angles from %d to %d" % (start, end))

        for i in range(start, end, step):
            self.servo.angle = i
            slept = slept + .1
            time.sleep(.1)

        return slept

    def heat(self, heating_percent):
        '''move the servo based on the heating_percent
           heating_percent is a float between 0 = closed and 1 = fully open'''
        if self.servo is None:
            return
        if self.invert_servo == True:
            heating_percent = float(1 - heating_percent)

        setpt_angle = self.min_servo_angle + \
            ((self.max_servo_angle - self.min_servo_angle) * heating_percent)

        self.move_slow(setpt_angle)

    def cool(self, sleepfor):
        '''no active cooling, so pass'''
        pass


class TempSensor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.temperature = 0
        self.bad_percent = 0
        self.time_step = config.sensor_time_wait
        self.noConnection = self.shortToGround = self.shortToVCC = self.unknownError = False


class TempSensorSimulated(TempSensor):
    '''temperature is set by the simulation model'''
    def __init__(self):
        TempSensor.__init__(self)


class TempSensorReal(TempSensor):
    '''real temperature sensor thread that takes N measurements
       during the time_step'''
    def __init__(self):
        TempSensor.__init__(self)
        self.sleeptime = self.time_step / float(config.temperature_average_samples)
        self.bad_count = 0
        self.ok_count = 0
        self.bad_stamp = 0

        if config.max31855:
            log.info("init MAX31855")
            from max31855 import MAX31855
            self.thermocouple = MAX31855(config.gpio_sensor_cs,
                                         config.gpio_sensor_clock,
                                         config.gpio_sensor_data,
                                         config.temp_scale)

        if config.max31856:
            log.info("init MAX31856")
            from max31856 import MAX31856
            software_spi = {'cs': config.gpio_sensor_cs,
                            'clk': config.gpio_sensor_clock,
                            'do': config.gpio_sensor_data,
                            'di': config.gpio_sensor_di}
            self.thermocouple = MAX31856(tc_type=config.thermocouple_type,
                                         software_spi=software_spi,
                                         units=config.temp_scale,
                                         ac_freq_50hz=config.ac_freq_50hz)

    def run(self):
        '''use a moving average of config.temperature_average_samples across the time_step'''
        temps = []
        while True:
            # reset error counter if time is up
            if (time.time() - self.bad_stamp) > (self.time_step * 2):
                if self.bad_count + self.ok_count:
                    self.bad_percent = (self.bad_count / (self.bad_count + self.ok_count)) * 100
                else:
                    self.bad_percent = 0
                self.bad_count = 0
                self.ok_count = 0
                self.bad_stamp = time.time()

            temp = self.thermocouple.get()
            self.noConnection = self.thermocouple.noConnection
            self.shortToGround = self.thermocouple.shortToGround
            self.shortToVCC = self.thermocouple.shortToVCC
            self.unknownError = self.thermocouple.unknownError

            is_bad_value = self.noConnection | self.unknownError
            if config.honour_theromocouple_short_errors:
                is_bad_value |= self.shortToGround | self.shortToVCC

            if not is_bad_value:
                temps.append(temp)
                if len(temps) > config.temperature_average_samples:
                    del temps[0]
                self.ok_count += 1
            else:
                log.error("Problem reading temp N/C:%s GND:%s VCC:%s ???:%s" %
                          (self.noConnection, self.shortToGround,
                           self.shortToVCC, self.unknownError))
                self.bad_count += 1

            if len(temps):
                self.temperature = self.get_avg_temp(temps)
            time.sleep(self.sleeptime)

    def get_avg_temp(self, temps, chop=25):
        '''
        strip off chop percent from the beginning and end of the sorted temps
        then return the average of what is left
        '''
        chop = chop / 100
        temps = sorted(temps)
        total = len(temps)
        items = int(total * chop)
        temps = temps[items:total - items]
        return sum(temps) / len(temps)


class Board(object):
    '''real smoker board - thermocouple + servo'''
    def __init__(self):
        self.temp_sensor = TempSensorReal()
        self.temp_sensor.start()


class BoardSimulated(object):
    '''simulated board. the simulation model owns the temperature'''
    def __init__(self):
        self.temp_sensor = TempSensorSimulated()
        self.t_env = config.sim_t_env
        self.p_heat = config.sim_p_heat
        self.r_oven = config.sim_r_oven
        self.c_oven = config.sim_c_oven
        self.temp_c = self.t_env
        self.temp_sensor.temperature = self._to_scale(self.temp_c)

    def step(self, openness, dt):
        '''advance the model by dt seconds.
           openness is 0 (flapper closed) to 1 (flapper fully open).'''
        # heat from the fire reaching the chamber
        q_in = self.p_heat * openness
        # heat lost to the ambient environment
        q_out = (self.temp_c - self.t_env) / self.r_oven
        self.temp_c += (q_in - q_out) * dt / self.c_oven
        self.temp_sensor.temperature = self._to_scale(self.temp_c)

    def _to_scale(self, temp_c):
        if config.temp_scale == "f":
            return temp_c * 9.0 / 5.0 + 32
        return temp_c


class Smoker(threading.Thread):
    '''controls a smoker by reading a thermocouple and driving a servo
       flapper to hold a target temperature.'''
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.time_step = config.sensor_time_wait
        self.board = Board()
        self.output = Output()
        self.speed = config.sim_speed
        self.reset()
        self.start()

    def reset(self):
        self.state = "IDLE"
        self.setpoint = 0
        self.heat = 0
        self.start_time = 0
        self.runtime = 0
        self.pid = PID(ki=config.pid_ki, kd=config.pid_kd, kp=config.pid_kp)
        if hasattr(self, 'output'):
            self.output.cool(0)

    def current_temp(self):
        return self.board.temp_sensor.temperature + config.thermocouple_offset

    def start_smoke(self, setpoint=None):
        if self.board.temp_sensor.noConnection:
            log.info("Refusing to start - thermocouple not connected")
            return False
        if self.board.temp_sensor.shortToGround:
            log.info("Refusing to start - thermocouple short to ground")
            return False
        if self.board.temp_sensor.shortToVCC:
            log.info("Refusing to start - thermocouple short to VCC")
            return False
        if self.board.temp_sensor.unknownError:
            log.info("Refusing to start - thermocouple unknown error")
            return False

        if setpoint is None:
            setpoint = config.default_setpoint
        setpoint = float(setpoint)
        setpoint = sorted([config.min_setpoint, setpoint, config.max_setpoint])[1]

        self.reset()
        self.setpoint = setpoint
        self.start_time = datetime.datetime.now()
        self.runtime = 0
        self.state = "RUNNING"
        log.info("Starting smoke at %s degrees" % setpoint)
        return True

    def set_setpoint(self, setpoint):
        setpoint = float(setpoint)
        setpoint = sorted([config.min_setpoint, setpoint, config.max_setpoint])[1]
        self.setpoint = setpoint
        log.info("setpoint changed to %s degrees" % setpoint)

    def abort_run(self):
        log.info("stopping smoke")
        self.reset()
        self.save_restart_state()

    def update_runtime(self):
        runtime_delta = datetime.datetime.now() - self.start_time
        if runtime_delta.total_seconds() < 0:
            runtime_delta = datetime.timedelta(0)
        self.runtime = runtime_delta.total_seconds()

    def control(self):
        pid = self.pid.compute(self.setpoint, self.current_temp(), self.time_step)
        # clamp pid output to 0..1 (no active cooling on a smoker)
        self.heat = sorted([0.0, pid, 1.0])[1]
        self.output.heat(self.heat)

    def check_emergency(self):
        # no temperature emergency shutoff for a smoker - the PID and the
        # flapper are the only control you get, so a hot fire is expected.
        # but a broken thermocouple means no control at all, so stop on that.
        if self.board.temp_sensor.noConnection:
            log.info("emergency!!! lost connection to thermocouple, shutting down")
            self.reset()
        if self.board.temp_sensor.unknownError:
            log.info("emergency!!! unknown thermocouple error, shutting down")
            self.reset()
        if self.board.temp_sensor.bad_percent > 30:
            log.info("emergency!!! too many errors in a short period, shutting down")
            self.reset()

    def get_state(self):
        return {
            'state': self.state,
            'temperature': round(self.current_temp(), 1),
            'setpoint': self.setpoint,
            'heat': round(self.heat * 100, 0),
            'runtime': int(self.runtime),
            'units': config.temp_scale,
            'pidstats': self.pid.pidstats,
            'simulate': config.simulate,
            'sim_speed': self.speed if config.simulate else None,
            'wood_alert_threshold': config.wood_alert_threshold,
            'wood_alert_cycles': config.wood_alert_cycles,
        }

    def save_restart_state(self):
        if not config.automatic_restarts:
            return
        state = {'state': self.state, 'setpoint': self.setpoint, 'runtime': self.runtime}
        with open(config.automatic_restart_state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f)

    def maybe_auto_restart(self):
        if not config.automatic_restarts:
            return
        if not os.path.isfile(config.automatic_restart_state_file):
            return
        age_minutes = (time.time() - os.path.getmtime(config.automatic_restart_state_file)) / 60
        if age_minutes > config.automatic_restart_window:
            return
        try:
            with open(config.automatic_restart_state_file) as f:
                state = json.load(f)
        except ValueError:
            return
        if state.get('state') == 'RUNNING' and state.get('setpoint'):
            log.info("automatic restart at setpoint %s" % state['setpoint'])
            self.start_smoke(state['setpoint'])

    def run(self):
        while True:
            if self.state == "IDLE":
                self.maybe_auto_restart()
                time.sleep(1)
                continue
            if self.state == "RUNNING":
                self.update_runtime()
                self.control()
                self.check_emergency()
                self.save_restart_state()
                time.sleep(self.time_step)


class SimulatedSmoker(Smoker):
    '''same controller, but the physics are simulated instead of real hardware'''
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.time_step = config.sensor_time_wait
        self.board = BoardSimulated()
        self.output = Output()
        self.speed = config.sim_speed
        self.reset()
        self.start()

    def control(self):
        pid = self.pid.compute(self.setpoint, self.current_temp(), self.time_step * self.speed)
        self.heat = sorted([0.0, pid, 1.0])[1]
        self.board.step(self.heat, self.time_step * self.speed)
        self.log_status()

    def log_status(self):
        p = self.pid.pidstats
        log.info("temp=%.1f, target=%.1f, error=%.1f, pid=%.2f, flapper=%.0f%%, run_time=%ds" %
                 (p['ispoint'], p['setpoint'], p['err'], p['pid'],
                  self.heat * 100, self.runtime))


class PID():
    def __init__(self, ki=1, kp=1, kd=1):
        self.ki = ki
        self.kp = kp
        self.kd = kd
        self.iterm = 0
        self.lastErr = 0
        self.pidstats = {}

    def compute(self, setpoint, ispoint, dt):
        now = datetime.datetime.now()
        timeDelta = dt

        window_size = 100

        error = float(setpoint - ispoint)
        # outside the control window the controller acts like a binary
        # switch: fully open when too cold, fully closed when too hot.
        # integral only accumulates inside the window (no windup).
        icomp = 0
        output = 0
        out4logs = 0
        dErr = 0
        if error < (-1 * config.pid_control_window):
            log.debug("smoker outside pid control window, max cooling")
            output = 0
        elif error > (1 * config.pid_control_window):
            log.debug("smoker outside pid control window, max heating")
            output = 1
        else:
            icomp = (error * timeDelta * (1 / self.ki))
            self.iterm += (error * timeDelta * (1 / self.ki))
            dErr = (error - self.lastErr) / timeDelta
            output = self.kp * error + self.iterm + self.kd * dErr
            output = sorted([-1 * window_size, output, window_size])[1]
            out4logs = output
            output = float(output / window_size)

        self.lastErr = error

        # not actively cooling, so
        if output < 0:
            output = 0

        self.pidstats = {
            'time': time.mktime(now.timetuple()),
            'timeDelta': timeDelta,
            'setpoint': setpoint,
            'ispoint': ispoint,
            'err': error,
            'errDelta': dErr,
            'p': self.kp * error,
            'i': self.iterm,
            'd': self.kd * dErr,
            'kp': self.kp,
            'ki': self.ki,
            'kd': self.kd,
            'pid': out4logs,
            'out': output,
        }

        return output
