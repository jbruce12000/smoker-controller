import logging
import os

script_dir = os.path.dirname(os.path.abspath(__file__))

########################################################################
#
#   General options

### Logging
log_level = logging.INFO
log_format = '%(asctime)s %(levelname)s %(name)s: %(message)s'

### Server
listening_ip = "0.0.0.0"
listening_port = 9099

### Temperature scale - all temperatures in this file (and in the web
#   interface) are assumed to be in this scale.
temp_scale = "f"  # c = Celsius | f = Fahrenheit

# Valid range for the target temperature in the web interface
min_setpoint = 85
max_setpoint = 500
default_setpoint = 250

# Compensate a thermocouple that reads high or low (e.g. -4 if it reads
# 36F in ice water).
thermocouple_offset = 0

########################################################################
#
#   GPIO Setup (BCM SoC Numbering Schema)
#
#   Check the RasPi docs to see where these GPIOs are connected on the
#   P1 header for your board type/rev.

### Servo output
gpio_servo = 24       # gpio pin controlling the servo
min_servo_angle = -50 # servo angle (degrees) for a closed flapper
max_servo_angle = 50  # servo angle (degrees) for an open flapper
invert_servo = True   # swap which servo angle means "more heat"

### Thermocouple adapter selection:
#   max31855 - bitbang SPI interface
#   max31856 - bitbang SPI interface, requires thermocouple_type
max31855 = 1
max31856 = 0
# only applies to max31856. 0x3 = K type, see lib/max31856.py for others
thermocouple_type = 0x3

### Thermocouple connection (using bitbang interfaces)
gpio_sensor_cs = 27
gpio_sensor_clock = 22
gpio_sensor_data = 17
gpio_sensor_di = 10 # only used with max31856

########################################################################
#
#   Duty cycle of the entire system in seconds
#
#   Every N seconds a decision is made about the angle to set on the
#   servo. The thermocouple is read temperature_average_samples times
#   during that period and the average value is used.
sensor_time_wait = 5

# number of thermocouple samples to average during each duty cycle
temperature_average_samples = 20

# Thermocouple AC frequency filtering - True for 50Hz locales,
# leave False for 60Hz locales
ac_freq_50hz = False

# Some thermocouples start erroneously reporting "short" errors at high
# temperatures. Set this to False to ignore those errors.
honour_theromocouple_short_errors = False

########################################################################
#
#   PID parameters
#
#   These control how aggressively the flapper reacts to the difference
#   between the current temperature and the target. Note that pid_ki is
#   inverted - a smaller number means more integral action.
pid_kp = 10   # Proportional
pid_ki = 100  # Integral
pid_kd = 50   # Derivative

# The window (in degrees) around the target within which PID control
# takes place. Outside this window the flapper is fully open (too cold)
# or fully closed (too hot). The bigger the window, the more integral
# accumulates.
pid_control_window = 5

########################################################################
#
#   Wood alarm
#
#   A flapper held wide open during steady state usually means the fire
#   is running low and needs more wood. If the flapper stays above the
#   threshold percentage for more than this many consecutive control
#   cycles, the web interface turns the flapper readout background red
#   as an "add wood" reminder.
wood_alert_threshold = 75 # flapper % above which the flapper counts as "wide open"
wood_alert_cycles = 10    # consecutive cycles above the threshold before the alarm

########################################################################
#
#   Simulation parameters
#
#   Set simulate = True to run without hardware. The model approximates
#   a wood-fired smoker: the flapper openness (0-1) sets how much heat
#   reaches the cooking chamber.
simulate = True
sim_t_env  = 21.0    # deg C ambient temperature
sim_p_heat = 800.0   # W effective fire power when flapper is fully open
sim_r_oven = 0.5     # K/W thermal resistance chamber -> ambient
sim_c_oven = 2100.0  # J/K heat capacity of the smoker chamber
sim_speed = 1        # simulation time multiplier: 1 = real time, 10 = 10x faster

########################################################################
#
#   Automatic restarts
#
#   If the pi reboots (power brown-out) while a smoke is in progress,
#   the controller resumes at the saved target temperature. The state
#   file must NOT be in /tmp (it is cleaned up on boot).
automatic_restarts = True
automatic_restart_window = 30 # max minutes the pi can be down
automatic_restart_state_file = os.path.join(script_dir, 'state.json')
