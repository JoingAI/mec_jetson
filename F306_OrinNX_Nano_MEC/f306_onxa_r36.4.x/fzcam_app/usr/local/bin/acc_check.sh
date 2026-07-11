#!/bin/bash
# ************************
# * Check acc-det on/off 
# ************************
set -e
ACC_DETECT_GPIO="PP.06"
ACC_GPIO_INDEX=98

while true
do
	sleep 0.5
	val=`gpioget /dev/gpiochip0 98`
	if [ "$val" == "0" ];then
		continue
	else
		sleep 1
		val=`gpioget /dev/gpiochip0 98`
		if [ "$val" == "0" ];then
			continue
		else
			sleep 10 #Wait 10s
			init 0   #Power off 
		fi
	fi
done

