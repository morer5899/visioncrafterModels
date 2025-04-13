import io
import numpy as np
from PIL import Image, ImageEnhance
import cv2
import logging

logger = logging.getLogger(__name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {
        'png', 'jpg', 'jpeg', 'webp'
    }

def pil_enhancement(img_bytes):
    try:
        img = Image.open(io.BytesIO(img_bytes))
        
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.2)
        
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.5)
        
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.1)
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
        
    except Exception as e:
        logger.error(f"PIL enhancement failed: {str(e)}")
        raise

def cv2_enhancement(img_bytes):
    try:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
        
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        img = cv2.filter2D(img, -1, kernel)
        
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        l = clahe.apply(l)
        lab = cv2.merge((l,a,b))
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        return img
    except Exception as e:
        logger.error(f"OpenCV enhancement failed: {str(e)}")
        raise