#!/usr/bin/env python3
from gpiozero import AngularServo
from time import sleep

import gpiozero
from gpiozero.pins.pigpio import PiGPIOFactory
gpiozero.Device.pin_factory = PiGPIOFactory('127.0.0.1')


s = AngularServo(24, min_angle=-50, max_angle=50)

while(True):

  for x in range(-50,50):
    print("%s" %(x))
    s.angle = x
    sleep(1)

  sleep(5)
