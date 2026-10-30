#!/bin/bash
set -u
for attempt in 1 2 3 4; do
	ok=1
	for d in 0 4; do
		timeout 4 v4l2-ctl -d /dev/video$d --set-fmt-video=width=1920,height=1536,pixelformat=UYVY --stream-mmap=4 --stream-count=5 --stream-to=/dev/null >/dev/null 2>&1
		[ $? -eq 0 ] || ok=0
	done
	if [ $ok -eq 1 ]; then
		echo "fzcam healthcheck OK (attempt $attempt)"
		exit 0
	fi
	echo "fzcam healthcheck failed (attempt $attempt), reload fzcam and reconfigure"
	sleep 1
	modprobe -r fzcam 2>/dev/null
	sleep 1
	modprobe fzcam 2>/dev/null
	sleep 2
	/usr/local/bin/fzcam_cfg >/dev/null 2>&1
done
echo "fzcam healthcheck FAILED after retries"
exit 1
