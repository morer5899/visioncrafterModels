from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os
import uuid
import cv2
import time
import io
import numpy as np
import logging
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import threading
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from fpdf import FPDF
from PIL import Image
import fitz  # PyMuPDF
import comtypes.client  # For DOCX conversion (Windows only)
import tempfile
from gradio_client import Client

# Import utility functions
from utils.compression import (
    allowed_file as allowed_compression_file,
    compress_image,
    compress_video,
    compress_zip,
    cleanup_file
)
from utils.enhancement import (
    allowed_file as allowed_enhancement_file,
    pil_enhancement,
    cv2_enhancement
)
from utils.recoloring import hex_to_hsv

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://localhost:5175"], supports_credentials=True)

# Configuration - using paths relative to the app folder
app.config['BASE_DIR'] = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(app.config['BASE_DIR'], 'uploads')
app.config['COMPRESSED_FOLDER'] = os.path.join(app.config['BASE_DIR'], 'compressed')
app.config['CONVERSION_OUTPUT_FOLDER'] = os.path.join(app.config['BASE_DIR'], 'conversions')
app.config['MAX_FILE_SIZE'] = 10 * 1024 * 1024  # 10MB

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track files and their expiration times
FILE_TRACKER = {}

# Initialize Gradio client for background removal
bg_removal_client = Client("not-lain/background-removal")

# Ensure directories exist within the app folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['COMPRESSED_FOLDER'], exist_ok=True)
os.makedirs(app.config['CONVERSION_OUTPUT_FOLDER'], exist_ok=True)

# Create temp subdirectory within uploads
TEMP_DIR = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

# Background scheduler for cleanup
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())



# -------------------------------
# Conversion Utility Functions
# -------------------------------
def allowed_conversion_file(filename):
    """Check if the file extension is allowed for conversion"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {
        'png', 'jpg', 'jpeg', 'webp', 'pdf', 'docx', 'txt', 'md'
    }

def docx_to_pdf(input_path, output_path):
    """Convert DOCX to PDF (Windows only)"""
    try:
        word = comtypes.client.CreateObject('Word.Application')
        doc = word.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=17)  # 17 = PDF format
        doc.Close()
        word.Quit()
        logger.info(f"Converted DOCX to PDF: {input_path} → {output_path}")
        return True
    except Exception as e:
        logger.error(f"DOCX conversion failed: {str(e)}")
        raise RuntimeError("Word document conversion failed. Is Microsoft Word installed?")

def txt_to_pdf(input_path, output_path):
    """Convert plain text to PDF"""
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        with open(input_path, "r", encoding='utf-8') as txt_file:
            text = txt_file.read()
        
        pdf.multi_cell(0, 10, text)
        pdf.output(output_path)
        logger.info(f"Converted TXT to PDF: {input_path} → {output_path}")
        return True
    except Exception as e:
        logger.error(f"TXT conversion failed: {str(e)}")
        raise RuntimeError("Text file conversion failed")

def markdown_to_pdf(input_path, output_path):
    """Convert Markdown to PDF (basic implementation)"""
    try:
        with open(input_path, 'r', encoding='utf-8') as md_file:
            md_text = md_file.read()
        
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, md_text)
        pdf.output(output_path)
        logger.info(f"Converted Markdown to PDF: {input_path} → {output_path}")
        return True
    except Exception as e:
        logger.error(f"Markdown conversion failed: {str(e)}")
        raise RuntimeError("Markdown conversion failed")

def pdf_to_png(input_path, output_dir):
    """Convert PDF to PNG using PyMuPDF"""
    try:
        doc = fitz.open(input_path)
        image_files = []
        
        for i, page in enumerate(doc):
            # Render page at 300 DPI
            pix = page.get_pixmap(dpi=300)
            output_path = os.path.join(output_dir, f"page_{i+1}.png")
            pix.save(output_path)
            image_files.append(os.path.basename(output_path))
            logger.info(f"Converted page {i+1} to {output_path}")
        
        return image_files
    except Exception as e:
        logger.error(f"PDF conversion failed: {str(e)}")
        raise RuntimeError("PDF to image conversion failed")

def jpg_to_pdf(input_path, output_path):
    """Convert image to PDF"""
    try:
        with Image.open(input_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(output_path, "PDF", resolution=100.0)
        logger.info(f"Converted image to PDF: {input_path} → {output_path}")
        return True
    except Exception as e:
        logger.error(f"Image conversion failed: {str(e)}")
        raise RuntimeError("Image to PDF conversion failed")

def convert_file(input_path, output_dir):
    """Main conversion dispatcher"""
    try:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        file_name = os.path.splitext(os.path.basename(input_path))[0]
        file_extension = os.path.splitext(input_path)[1].lower()
        output_files = []

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        if file_extension == '.docx':
            output_pdf = os.path.join(output_dir, f"{file_name}.pdf")
            if docx_to_pdf(input_path, output_pdf):
                output_files.append(output_pdf)
        
        elif file_extension == '.txt':
            output_pdf = os.path.join(output_dir, f"{file_name}.pdf")
            if txt_to_pdf(input_path, output_pdf):
                output_files.append(output_pdf)
        
        elif file_extension == '.md':
            output_pdf = os.path.join(output_dir, f"{file_name}.pdf")
            if markdown_to_pdf(input_path, output_pdf):
                output_files.append(output_pdf)
        
        elif file_extension == '.pdf':
            output_files = pdf_to_png(input_path, output_dir)
        
        elif file_extension in ('.jpg', '.jpeg', '.png'):
            output_pdf = os.path.join(output_dir, f"{file_name}.pdf")
            if jpg_to_pdf(input_path, output_pdf):
                output_files.append(output_pdf)
        
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")

        # Return relative paths for web access
        return [os.path.relpath(f, output_dir) for f in output_files]

    except Exception as e:
        logger.error(f"Conversion failed for {input_path}: {str(e)}")
        raise  # Re-raise for Flask to handle

# -------------------------------
# Background Removal Endpoint
# -------------------------------
@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image_file = request.files['image']
    
    # Validate file size
    max_size = app.config['MAX_FILE_SIZE']
    file_size = len(image_file.read())
    image_file.seek(0)
    
    if file_size > max_size:
        return jsonify({"error": f"Image too large (max {max_size//(1024*1024)}MB)"}), 400
    
    # Create unique temp directory within app folder
    temp_dir = os.path.join(TEMP_DIR, str(uuid.uuid4()))
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        input_filename = secure_filename(image_file.filename)
        input_path = os.path.join(temp_dir, input_filename)
        image_file.save(input_path)
        
        # Verify the image is valid
        try:
            with Image.open(input_path) as img:
                img.verify()
        except Exception as e:
            return jsonify({"error": "Invalid image file", "details": str(e)}), 400

        try:
            # Call the background removal service
            result = bg_removal_client.predict(
                input_path,
                fn_index=0,
                api_name="/predict"
            )
            
            # Handle different response formats
            result_path = result[0] if isinstance(result, list) else result
            
            if not result_path or not os.path.exists(result_path):
                return jsonify({
                    "error": "Background removal failed - no output file",
                    "details": "Service returned empty result"
                }), 500
                
            # Move result to our conversions folder
            output_filename = f"bg_removed_{input_filename}"
            final_path = os.path.join(app.config['CONVERSION_OUTPUT_FOLDER'], output_filename)
            os.rename(result_path, final_path)
            
            # Create response
            response = send_file(
                final_path,
                mimetype='image/webp',
                as_attachment=True,
                download_name=output_filename
            )
            
            @response.call_on_close
            def cleanup():
                try:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    if os.path.exists(input_path):
                        os.remove(input_path)
                    os.rmdir(temp_dir)
                except Exception as e:
                    logger.error(f"Cleanup error: {str(e)}")
            
            return response
            
        except Exception as e:
            logger.error(f"Background removal failed: {str(e)}")
            return jsonify({
                "error": "Background removal service error",
                "details": str(e)
            }), 500
            
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        return jsonify({
            "error": "Image processing failed",
            "details": str(e)
        }), 500
    finally:
        # Fallback cleanup
        try:
            if os.path.exists(temp_dir):
                for filename in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                os.rmdir(temp_dir)
        except Exception as e:
            logger.error(f"Final cleanup error: {str(e)}")

# -------------------------------
# Compression Endpoints
# -------------------------------
@app.route('/compress', methods=['POST'])
def compress():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_compression_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    try:
        compression_level = int(request.form.get('compression_level', 50))
        file_type = request.form.get('file_type', 'image')
    except ValueError:
        return jsonify({'error': 'Invalid compression parameters'}), 400

    filename = secure_filename(file.filename)
    unique_id = str(uuid.uuid4())
    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_id}_{filename}")
    compressed_filename = f"compressed_{unique_id}_{filename}"
    compressed_path = os.path.join(app.config['COMPRESSED_FOLDER'], compressed_filename)

    file.save(upload_path)

    try:
        original_size = os.path.getsize(upload_path)

        if file_type == 'image':
            quality = max(1, min(100, compression_level))
            compress_image(upload_path, compressed_path, quality)
        elif file_type == 'video':
            crf = max(0, min(51, 51 - (compression_level * 0.51)))
            compress_video(upload_path, compressed_path, crf)
        elif file_type == 'folder':
            compress_zip(upload_path, compressed_path)
        else:
            return jsonify({'error': 'Unsupported file type'}), 400

        if not os.path.exists(compressed_path):
            raise Exception("Compressed file was not created successfully")

        compressed_size = os.path.getsize(compressed_path)
        if compressed_size == 0:
            raise Exception("Compressed file is empty")

        cleanup_file(upload_path)

        # Add file to tracker with expiration
        expiration_time = datetime.now() + timedelta(minutes=5)
        FILE_TRACKER[compressed_filename] = expiration_time
        logger.info(f"Added file to tracker: {compressed_filename}")

        download_url = f"/download/{unique_id}/{compressed_filename}"
        return jsonify({
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': f"{(original_size - compressed_size) / original_size * 100:.2f}%",
            'download_url': download_url,
            'filename': compressed_filename
        })

    except Exception as e:
        cleanup_file(upload_path)
        cleanup_file(compressed_path)
        logger.error(f"Error during compression: {str(e)}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# File Conversion Endpoints
# -------------------------------
@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if not allowed_conversion_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        filename = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        file.save(filename)
        
        output_files = convert_file(filename, app.config['CONVERSION_OUTPUT_FOLDER'])
        
        if not output_files:
            return jsonify({"error": "Conversion failed - no output generated"}), 400
            
        # Create full URLs for the output files
        output_urls = [f"/conversion-output/{f}" for f in output_files]
        
        return jsonify({
            "message": "File converted successfully",
            "output_files": output_urls
        })
        
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        return jsonify({
            "error": "File conversion failed",
            "details": str(e)
        }), 500

# -------------------------------
# Conversion Output Endpoint
# -------------------------------
@app.route('/conversion-output/<path:filename>', methods=['GET'])
def conversion_output(filename):
    try:
        safe_filename = secure_filename(filename)
        file_path = os.path.join(app.config['CONVERSION_OUTPUT_FOLDER'], safe_filename)
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return jsonify({'error': 'File not found'}), 404

        # Start a background thread to delete the file after 5 seconds
        threading.Thread(target=delete_file_after_delay, args=(file_path,), daemon=True).start()

        return send_from_directory(app.config['CONVERSION_OUTPUT_FOLDER'], safe_filename, as_attachment=True)
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# Image Enhancement Endpoint
# -------------------------------
@app.route('/enhance', methods=['POST'])
def enhance_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if not allowed_enhancement_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400
        
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    
    if file_length > app.config['MAX_FILE_SIZE']:
        return jsonify({"error": f"File too large. Max size: {app.config['MAX_FILE_SIZE']//(1024*1024)}MB"}), 400
    
    try:
        img_bytes = file.read()
        
        try:
            logger.info("Attempting PIL enhancement")
            enhanced_bytes = pil_enhancement(img_bytes)
            return send_file(io.BytesIO(enhanced_bytes), mimetype='image/png')
        except Exception as pil_error:
            logger.warning(f"PIL enhancement failed: {str(pil_error)}")
            
        try:
            logger.info("Attempting OpenCV enhancement")
            enhanced_img = cv2_enhancement(img_bytes)
            _, buffer = cv2.imencode('.png', enhanced_img)
            return send_file(io.BytesIO(buffer), mimetype='image/png')
        except Exception as cv_error:
            logger.error(f"OpenCV enhancement failed: {str(cv_error)}")
            return jsonify({
                "error": "Image enhancement failed",
                "details": str(cv_error)
            }), 500
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            "error": "Image processing failed",
            "details": str(e)
        }), 500

# -------------------------------
# Image Recoloring Endpoint
# -------------------------------
@app.route('/recolor', methods=['POST'])
def recolor_object():
    try:
        image_file = request.files['image']
        mask_file = request.files['mask']
        color_hex = request.form['color']

        img = cv2.imdecode(np.frombuffer(image_file.read(), np.uint8), cv2.IMREAD_COLOR)
        mask = cv2.imdecode(np.frombuffer(mask_file.read(), np.uint8), cv2.IMREAD_GRAYSCALE)

        if img is None or mask is None:
            return {"error": "Invalid image or mask"}, 400
        if img.shape[:2] != mask.shape:
            return {"error": "Image and mask size mismatch"}, 400

        target_h, target_s, _ = hex_to_hsv(color_hex)
        _, binary_mask = cv2.threshold(mask, 250, 255, cv2.THRESH_BINARY)

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hsv_modified = hsv.copy()
        hsv_modified[binary_mask == 255, 0] = target_h
        hsv_modified[binary_mask == 255, 1] = target_s

        recolored_bgr = cv2.cvtColor(hsv_modified, cv2.COLOR_HSV2BGR)
        final_img = img.copy()
        final_img[binary_mask == 255] = recolored_bgr[binary_mask == 255]

        _, buffer = cv2.imencode('.png', final_img)
        return send_file(io.BytesIO(buffer.tobytes()), mimetype='image/png')

    except Exception as e:
        return {"error": str(e)}, 500

# -------------------------------
# Common Download Endpoint
# -------------------------------
@app.route('/download/<unique_id>/<filename>', methods=['GET'])
def download_file(unique_id, filename):
    try:
        if not all(c.isalnum() or c in '_-.' for c in filename):
            return jsonify({'error': 'Invalid filename'}), 400
            
        file_path = os.path.join(app.config['COMPRESSED_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return jsonify({'error': 'File not found'}), 404

        original_filename = filename.split('_', 2)[-1]
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=original_filename,
            mimetype='application/octet-stream'
        )
        
        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Successfully deleted file: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting file {file_path}: {e}")
        
        if filename in FILE_TRACKER:
            del FILE_TRACKER[filename]
            logger.info(f"Removed file from tracker: {filename}")
        
        return response
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# Utility Functions
# -------------------------------
def delete_file_after_delay(path, delay=5):
    """Delete a file after a specified delay"""
    time.sleep(delay)
    try:
        if path and os.path.exists(path):
            os.remove(path)
            logger.info(f"Deleted file after download: {path}")
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")

def cleanup_old_files():
    """Clean up files older than 5 minutes in all storage folders"""
    try:
        now = datetime.now()
        
        # Clean uploads (including temp files)
        if os.path.exists(app.config['UPLOAD_FOLDER']):
            for root, dirs, files in os.walk(app.config['UPLOAD_FOLDER']):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.isfile(file_path):
                        if now.timestamp() - os.path.getmtime(file_path) > 300:
                            cleanup_file(file_path)
                # Remove empty directories
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    try:
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                    except:
                        pass
        
        # Clean compressed files
        if os.path.exists(app.config['COMPRESSED_FOLDER']):
            for filename in os.listdir(app.config['COMPRESSED_FOLDER']):
                file_path = os.path.join(app.config['COMPRESSED_FOLDER'], filename)
                if os.path.isfile(file_path):
                    if now.timestamp() - os.path.getmtime(file_path) > 300:
                        cleanup_file(file_path)
        
        # Clean conversion outputs
        if os.path.exists(app.config['CONVERSION_OUTPUT_FOLDER']):
            for filename in os.listdir(app.config['CONVERSION_OUTPUT_FOLDER']):
                file_path = os.path.join(app.config['CONVERSION_OUTPUT_FOLDER'], filename)
                if os.path.isfile(file_path):
                    if now.timestamp() - os.path.getmtime(file_path) > 300:
                        cleanup_file(file_path)
        
        # Clean FILE_TRACKER references
        for filename, expiration in list(FILE_TRACKER.items()):
            if now > expiration:
                file_path = os.path.join(app.config['COMPRESSED_FOLDER'], filename)
                cleanup_file(file_path)
                del FILE_TRACKER[filename]
                
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")

# Initialize scheduler to run every minute
scheduler.add_job(func=cleanup_old_files, trigger="interval", minutes=1)

if __name__ == '__main__':
    # Print the paths for verification
    print(f"Application folder: {app.config['BASE_DIR']}")
    print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"Compressed folder: {app.config['COMPRESSED_FOLDER']}")
    print(f"Conversion output folder: {app.config['CONVERSION_OUTPUT_FOLDER']}")
    
    # Run initial cleanup
    cleanup_old_files()
    
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)