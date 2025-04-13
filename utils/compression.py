import os
import zipfile
import subprocess
from PIL import Image
import logging

logger = logging.getLogger(__name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {
        'png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov', 'avi', 'zip'
    }

def compress_image(input_path, output_path, quality):
    try:
        with Image.open(input_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(output_path, quality=quality, optimize=True)
        return True
    except Exception as e:
        logger.error(f"Image compression failed: {str(e)}")
        raise

def compress_video(input_path, output_path, crf=28):
    try:
        result = subprocess.run([
            'ffmpeg', '-y',
            '-i', input_path,
            '-vcodec', 'libx264',
            '-crf', str(crf),
            '-preset', 'ultrafast',
            '-movflags', '+faststart',
            '-acodec', 'aac',
            '-strict', 'experimental',
            output_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Video compression failed: {e.stderr.decode()}")
        raise
    except Exception as e:
        logger.error(f"Video compression error: {str(e)}")
        raise

def compress_zip(input_path, output_path):
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.isdir(input_path):
                for root, _, files in os.walk(input_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, input_path)
                        zipf.write(file_path, arcname)
            else:
                zipf.write(input_path, os.path.basename(input_path))
        return True
    except Exception as e:
        logger.error(f"ZIP compression failed: {str(e)}")
        raise

def cleanup_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
            logger.info(f"Successfully removed file: {path}")
    except Exception as e:
        logger.error(f"Error removing file {path}: {e}")