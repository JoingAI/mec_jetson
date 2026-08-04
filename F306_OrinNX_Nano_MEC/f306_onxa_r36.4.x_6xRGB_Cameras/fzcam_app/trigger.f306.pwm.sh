cd /sys/class/pwm/pwmchip0
echo 0 > export
cd pwm0

#25Hz/25fps
echo 40000000 > period
echo 8000000 > duty_cycle
echo 1 > enable

#30Hz/30fps
echo 33333333 > period 
echo 3333333 > duty_cycle
echo 1 > enable  #30Hz 10%
