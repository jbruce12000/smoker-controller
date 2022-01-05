Smoker Controller
==========

Turns a Raspberry Pi into a web-enabled smoker controller.

This is a crazy stick burner smoker controller experiment. I had a smoker custom built by Lonnie Smith of [Bubba Grills](http://bubbagrills.net) and added a six inch servo controlled flapper to the top of a custom short exhaust over the center of the firebox. Controlling this flapper from completely closed to open gives me about 75F degrees of control. A thermocouple reads the temperature wherever it's placed in the smoker and this custom PID software controls the smoker to within a few degrees.

A Word about Fire Management

Fire Management is the most important part of any stick smoker. The operator controls the temperature by the size of the fire, and the amount of oxygen available through the firebox door and dampers. With this controller, the operator has a little more leeway and a little less work. Instead of choking the fire out to cool it using dampers, which creates white smoke, the controller shunts some of that heat from the firebox so it never makes it to the meat. The operator still needs to put wood on the fire every half hour or so, but this takes about 30 seconds without any damper adjustments. Add a couple splits, walk away and know that the temperature will barely change. It gives the operator a chance to concentrate on the most important part of stick burners - drinking beer and hanging with friends.

## Features

  * handles temperature increases and decreases well - adding wood or opening doors to check meat
  * can set a single temperature or a crazy complex temperature schedule
  * no limit to runtime - smoke for days if you want
  * use wifi to view status from multiple devices at once as a web page - computer, tablet etc
  * NIST-linearized conversion for accurate K type thermocouple readings
  * supports PID parameters you tune to your smoker
  * api for starting and stopping
  * supports MAX31856 and MAX31855 thermocouple boards
  * support for K, J, N, R, S, T, E, or B type thermocouples
  * automatically deals with changes to environment like wind or sudden temperature changes as a front comes through. Here is 30 minutes with a setpoint of 250F on a windy day...

![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/30-minutes.png)

**Run Smoker Schedule**

![Image](https://github.com/jbruce12000/smoker-controller/blob/main/public/assets/images/kiln-running.png)

**Edit Smoker Schedule**

![Image](https://github.com/jbruce12000/smoker-controller/blob/main/public/assets/images/kiln-schedule.png)

## Hardware

### Parts

| Image | Hardware | Description |
| ------| -------- | ----------- |
| ![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/rpi.png) | [Raspberry Pi](https://www.adafruit.com/category/105) | Virtually any Raspberry Pi will work since only a few GPIO pins are being used. |
| ![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/max31855.png) | [MAX31855](https://www.adafruit.com/product/269) or [MAX31856](https://www.adafruit.com/product/3263) | Thermocouple breakout board |
| ![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/k-type-thermocouple.png) | [K-Type Thermocouple](https://www.auberins.com/index.php?main_page=product_info&cPath=20_3&products_id=39) | Any $10 waterproof thermocouple will do just fine |
| ![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/breadboard.png) | Breadboard | breadboard, ribbon cable, connector for pi's gpio pins & connecting wires |
| ![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/servo.png) | Servo | Powerful enough to move the flapper, same as those used in RC cars |
| ![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/cap.png) | Exhaust Cap Flapper | Just like the ones you see on big-rigs and tractors. Mine is 6 inches in diameter because my exhaust was 5.5 inches. |
| ![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/cap.png) | Offset Smoker | Custom offset smoker with exhaust added to the fire box |

### Schematic

The pi has three gpio pins connected to the MAX31855 chip. S0 is configured as an input and CS and SCK are outputs. The signal that controls the servo is a gpio output. Since only four gpio pins are in use, any pi can be used for this project. See the [config](https://github.com/jbruce12000/smoker-controller/blob/main/config.py) file for gpio pin configuration.

![Image](https://raw.githubusercontent.com/jbruce12000/smoker-controller/main/public/assets/images/schematic.png)

## Software 

### Raspberry PI OS

Download [Raspberry PI OS](https://www.raspberrypi.org/software/). Use Rasberry PI Imaging tool to install the OS on an SD card. Boot the OS, open a terminal and...

    $ sudo apt-get update
    $ sudo apt-get dist-upgrade
    $ sudo apt-get install python3-virtualenv libevent-dev virtualenv
    $ git clone https://github.com/jbruce12000/smoker-controller
    $ cd smoker-controller
    $ virtualenv -p python3 venv
    $ source venv/bin/activate
    $ pip install --upgrade setuptools
    $ pip install greenlet bottle gevent gevent-websocket
    $ pip install -r requirements.txt


## Configuration

All parameters are defined in config.py, just copy the example and review/change to your mind's content.

    $ cp config.py.EXAMPLE config.py

You should change, test, and verify PID parameters in config.py.  Here is a [PID Tuning Guide](https://github.com/jbruce12000/smoker-controller/blob/main/docs/pid_tuning.md).

You may want to change the configuration parameter **sensor_time_wait**. It's the duty cycle for the entire system.  It's set to ten seconds by default which means that a decision is made every 10s about the angle to set on the servo. The angle is slowly changed over a second to limit current spikes and voltage drops.

## Usage

### Server Startup

    $ source venv/bin/activate; ./kiln-controller.py

### Autostart Server onBoot
If you want the server to autostart on boot, run the following command:

    $ /home/pi/kiln-controller/start-on-boot

### Wifi Web Access

Click http://127.0.0.1:8081 for local development or the IP
of your PI and the port defined in config.py (default 8081).

## License

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

## Support & Contact

You shouldn't build this. It's a lot of work. Took me a few months to put everything together while I was waiting for my smoker to be delivered.
