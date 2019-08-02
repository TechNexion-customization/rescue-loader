#!/bin/sh

max=`cat /tmp/max`
progress=`cat /tmp/progress`
pid=`ps | grep "dd of=/dev/mmcblk2" | head -1 | sed -e 's/^\s*\(\w*\).*/\1/'`

color=ffffff
color=a4ca39

if [ $1"X" != "X" ]
then
        color=$1
fi

while [ X$progress != X$max ]
do
	if [ -z $pid ]
	then
		pid=`ps | grep "dd of=/dev/mmcblk2" | head -1 | sed -e 's/^\s*\(\w*\).*/\1/'`
	fi
	progress=`tail -1 /tmp/progress | sed -e 's/^\(\w*\).*/\1/'`

	/usr/bin/fbprogress -fb /dev/fb0 -col ${color} $progress $max
	usleep 250000
	if [ -f /proc/$pid/exe ]
	then
		kill -USR1 $pid
	fi
done
