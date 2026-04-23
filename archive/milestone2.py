import cv2
import os
import numpy as np
import YanAPI
import logging

logging.basicConfig(level=logging.INFO)

YanAPI.sync_play_motion('reset')
# get image
photos_cache_dir = '../photos/'
imgs = os.listdir(photos_cache_dir)
imgs.sort(key=lambda name: int(name.split('.')[0]), reverse=True)
img_dir = imgs[0]
# find the target
bgr = cv2.imread(photos_cache_dir + img_dir)
hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
h, w = bgr.shape[:2]
lower_red = (0, 100, 100)
upper_red = (10, 255, 255)
mask = cv2.inRange(hsv, lower_red, upper_red)
_, contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) # find contours API for opencv 3.x
if len(contours) > 0:
    cnt = max(contours, key=cv2.contourArea)
    logging.info('Found target with area: {}'.format(cv2.contourArea(cnt)))
    # find the center of mass of the target
    M = cv2.moments(cnt)
    if M['m00'] != 0:
        cX = int(M['m10'] / M['m00'])
        # cY = int(M['m01'] / M['m00'])
        x_ratio = cX / w
        # y_ratio = cY / h
        # decide if the target is at the appropriate position
        if x_ratio < 0.4:
            YanAPI.sync_play_motion(name="walk", direction="left", speed="slow", repeat=1)
        elif x_ratio > 0.6:
            YanAPI.sync_play_motion(name="walk", direction="right", speed="slow", repeat=1)
        else:
            YanAPI.sync_play_motion(name="grab1")
else:
    logging.info('No target found.')
