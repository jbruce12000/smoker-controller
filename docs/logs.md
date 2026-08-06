Logs for a Smoke
================

Logs from the app on the pi go to **/var/log/daemon.log** and look like this...

    Jan 21 06:25:40 raspberrypi python[286]: 2026-01-21 06:25:40,390 INFO oven: temp=250.4, target=250.0, error=-0.4, pid=0.250, flapper=25%, run_time=15993s

| log variable | meaning |
| ------------ | ------- |
| temp | temperature read by thermocouple |
| target | target temperature |
| error | target minus temperature |
| pid | pid value for that cycle |
| flapper | flapper position as a percentage of open |
| run_time | seconds since the smoke started |
