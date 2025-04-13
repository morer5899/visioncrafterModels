import numpy as np
import cv2
import logging

logger = logging.getLogger(__name__)

def hex_to_hsv(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        bgr_pixel = np.uint8([[[b, g, r]]])
        hsv_pixel = cv2.cvtColor(bgr_pixel, cv2.COLOR_BGR2HSV)
        return hsv_pixel[0, 0, 0], hsv_pixel[0, 0, 1], hsv_pixel[0, 0, 2]
    except Exception as e:
        logger.error(f"Error converting hex to HSV: {str(e)}")
        raise