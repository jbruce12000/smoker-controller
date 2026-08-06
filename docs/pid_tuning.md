Tuning PID Values
=================

This animation is worth a thousand words...

![Image](https://upload.wikimedia.org/wikipedia/commons/3/33/PID_Compensation_Animated.gif)

## The Goal

A controller with properly tuned PID values reacts quickly to changes in the target temperature, but does not overshoot much. It settles quickly from any oscillations and hovers really close to the target.

## The Tuning Process

Start with some reasonable values for the PID settings in config.py...

    pid_kp = 10
    pid_ki = 100
    pid_kd = 50

When you change values, change only one at a time and watch the impact. Change values by either doubling or halving.

Run the controller (use `simulate = True` in config.py to practice without hardware) and change the target between a couple of temperatures, e.g. 200 and 250 F, every 30 minutes. It will likely shoot past the target the first time. This is normal - we'll get rid of most of the overshoot, but probably not all.

Let's balance pid_ki first (the integral). The lower the pid_ki, the greater the impact it will have on the system. If a system is consistently low or high, the integral is used to help bring the system closer to the target. The integral accumulates over time and has [potentially] a bigger and bigger impact.

* If you have a steady state (no oscillations), but the temperature is always above the target, increase pid_ki.
* If you have a steady state (no oscillations), but the temperature is always below the target, decrease pid_ki.
* If you have an oscillation but the temperature is mostly above the target, increase pid_ki.
* If you have an oscillation but the temperature is mostly below the target, decrease pid_ki.

Let's set pid_kp next (proportional). Think of pid_kp as a dimmable control that opens the flapper when below the target and closes it when above. The amount the flapper moves is defined by pid_kp. Be careful reducing pid_kp too much. It can result in strange behavior.

* If you have oscillations that don't stop or increase in size, reduce pid_kp
* If you have too much overshoot (after adjusting pid_kd), reduce pid_kp
* If you approach the target wayyyy tooo sloooowly, increase pid_kp

Now set pid_kd (derivative). pid_kd makes an impact when there is a change in temperature. It's used to reduce oscillations.

* If you have oscillations that take too long to settle, increase pid_kd
* If you have crazy, unpredictable behavior from the controller, reduce pid_kd

Expect some overshoot as the smoker reaches the target temperature the first time, but no oscillation. After that the temperature should remain within a degree or two of the target.

## Troubleshooting

* only change one value at a time, then test it.
* change values by doubling or halving
