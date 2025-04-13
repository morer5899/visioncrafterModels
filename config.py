import os

# Base directory configuration
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# File storage paths
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads')
COMPRESSED_FOLDER = os.path.join(PROJECT_ROOT, 'compressed')
CONVERSION_OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, 'converted_documents_and_images')

# File size limits
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_COMPRESSION_SIZE = 50 * 1024 * 1024 * 1024  # 50GB

# Allowed extensions
ALLOWED_COMPRESSION_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov', 'avi', 'zip'}
ALLOWED_CONVERSION_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf', 'docx', 'txt', 'md'}
ALLOWED_ENHANCEMENT_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

# HuggingFace token
HF_TOKEN = os.getenv("HF_TOKEN", "your_default_hf_token_here")