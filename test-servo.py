#!/usr/bin/env python3
import time
from time import sleep
import config
import logging

log = logging.getLogger(__name__)

class Output(object):
    def __init__(self):
        self.active = False
        self.gpio_servo = config.gpio_servo
        self.min_servo_angle = config.min_servo_angle
        self.max_servo_angle = config.max_servo_angle
        self.invert_servo = config.invert_servo
        self.load_libs()
        self.servo = self.AngularServo(self.gpio_servo, \
            min_angle = self.min_servo_angle, \
            max_angle = self.max_servo_angle)
        #self.reset()

    def reset(self):
        '''sweep from closed to open and back again'''
        if self.invert_servo:
            self.servo.angle = self.min_servo_angle
        else:
            self.servo.angle = self.max_servo_angle
        time.sleep(1)
        if self.invert_servo:
            self.servo.angle = self.max_servo_angle
        else:
            self.servo.angle = self.min_servo_angle
        time.sleep(1)

    def load_libs(self):
        '''load all the libs required by this class'''
        try:
            import gpiozero
            from gpiozero import AngularServo
            self.AngularServo = AngularServo
            from gpiozero.pins.pigpio import PiGPIOFactory
            gpiozero.Device.pin_factory = PiGPIOFactory('127.0.0.1')
            self.active = True
        except:
            msg = "Could not initialize GPIOs, oven operation will only be simulated!"
            log.warning(msg)
            self.active = False

    def heat(self,heating_percent):
        '''move servo to a specific angle based on heating percent
           heating_percent is a float between 0 = no heat and 1 = 100% heating
        '''
        if self.invert_servo == True:
            heating_percent = float(1 - heating_percent)

        setpt_angle = self.min_servo_angle + \
            ((self.max_servo_angle - self.min_servo_angle) * heating_percent)
       
        log.info("servo_angle=%d" % (setpt_angle))
        print("servo_angle=%d" % (setpt_angle))
        self.servo.angle = setpt_angle
 
        # amount of time between decisions
        #time.sleep(config.sensor_time_wait)
        time.sleep(0.1)
        #time.sleep(10)

    def cool(self,sleepfor):
        '''no active cooling, so pass'''
        pass

if __name__== "__main__":

  output = Output()
  output.heat(0)
  for i in range(100):
      output.heat(i/100)
  for i in range(100):
      output.heat(1-(i/100))


  #output.heat(.25)
  #output.heat(.5)
  #output.heat(.75)
  #output.heat(1)
  #output.heat(0)
