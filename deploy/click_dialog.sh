#!/bin/bash
export DISPLAY=:99
export WINEPREFIX=/home/trader/.wine

echo "Dialog detected at 445,444 size 390x154"
echo "Clicking EULA checkbox and Next button..."

# Dialog origin: 445,444 - size 390x154
# Dialog bottom is at y=444+154=598
# Checkbox (bottom left): around x=460, y=564
# Next button (bottom right): around x=780, y=580

# Click checkbox area - try multiple spots
for y in 555 560 565 570 575; do
    for x in 455 460 465 470; do
        xdotool mousemove $x $y
        xdotool click 1
        sleep 0.05
    done
done
echo "Checkbox clicked"
sleep 1

# Take screenshot to verify
import -window root /tmp/after_checkbox.png 2>/dev/null

# Click Next button area
for y in 570 575 580 585; do
    for x in 770 775 780 785 790 795 800; do
        xdotool mousemove $x $y
        xdotool click 1
        sleep 0.05
    done
done
echo "Next button clicked"
sleep 2

# Take screenshot
import -window root /tmp/after_next.png 2>/dev/null
convert /tmp/after_next.png -trim info: 2>/dev/null

echo "Waiting 10 seconds..."
sleep 10

import -window root /tmp/after_wait.png 2>/dev/null
convert /tmp/after_wait.png -trim info: 2>/dev/null

echo "CLICKS_DONE"
