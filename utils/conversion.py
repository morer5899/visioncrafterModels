import os
import comtypes.client
from fpdf import FPDF
from pdf2image import convert_from_path
from PIL import Image
import logging
import time
import threading

logger = logging.getLogger(__name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {
        'png', 'jpg', 'jpeg', 'webp', 'pdf', 'docx', 'txt', 'md'
    }

def docx_to_pdf(input_path, output_path):
    try:
        word = comtypes.client.CreateObject('Word.Application')
        doc = word.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=17)
        doc.Close()
        word.Quit()
        logger.info(f"Converted {input_path} to {output_path}")
    except Exception as e:
        logger.error(f"Error converting DOCX to PDF: {e}")
        raise

def txt_to_pdf(input_path, output_path):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        with open(input_path, "r") as txt_file:
            text = txt_file.read()
        pdf.multi_cell(0, 10, text)
        pdf.output(output_path)
        logger.info(f"Converted {input_path} to {output_path}")
    except Exception as e:
        logger.error(f"Error converting TXT to PDF: {e}")
        raise

def markdown_to_pdf(input_path, output_path):
    try:
        with open(input_path, 'r') as md_file:
            md_text = md_file.read()
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, md_text)
        pdf.output(output_path)
        logger.info(f"Converted {input_path} to {output_path}")
    except Exception as e:
        logger.error(f"Error converting Markdown to PDF: {e}")
        raise

def pdf_to_png(input_path, output_dir):
    try:
        images = convert_from_path(input_path)
        image_files = []
        for i, img in enumerate(images):
            output_path = os.path.join(output_dir, f"page_{i+1}.png")
            img.save(output_path, 'PNG')
            image_files.append(os.path.basename(output_path))
            logger.info(f"Converted page {i+1} of {input_path} to {output_path}")
        return image_files
    except Exception as e:
        logger.error(f"Error converting PDF to PNG: {e}")
        raise

def jpg_to_pdf(input_path, output_path):
    try:
        image = Image.open(input_path).convert("RGB")
        image.save(output_path, "PDF")
        os.remove(input_path)
        logger.info(f"Converted {input_path} to {output_path} and deleted original")
    except Exception as e:
        logger.error(f"Error converting Image to PDF: {e}")
        raise

def convert_file(input_path, output_dir):
    file_name = os.path.splitext(os.path.basename(input_path))[0]
    file_extension = os.path.splitext(input_path)[1].lower()
    output_path = os.path.join(output_dir, file_name)
    output_files = []

    try:
        if file_extension == '.docx':
            output_pdf = output_path + '.pdf'
            docx_to_pdf(input_path, output_pdf)
            output_files.append(os.path.basename(output_pdf))
        elif file_extension == '.txt':
            output_pdf = output_path + '.pdf'
            txt_to_pdf(input_path, output_pdf)
            output_files.append(os.path.basename(output_pdf))
        elif file_extension == '.md':
            output_pdf = output_path + '.pdf'
            markdown_to_pdf(input_path, output_pdf)
            output_files.append(os.path.basename(output_pdf))
        elif file_extension == '.pdf':
            image_files = pdf_to_png(input_path, output_dir)
            output_files.extend(image_files)
        elif file_extension in ['.jpg', '.jpeg', '.png']:
            output_pdf = output_path + '.pdf'
            jpg_to_pdf(input_path, output_pdf)
            output_files.append(os.path.basename(output_pdf))
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
    except Exception as e:
        logger.error(f"Error in conversion: {e}")
        raise

    return output_files

def delete_file_after_delay(path, delay=5):
    time.sleep(delay)
    try:
        os.remove(path)
        logger.info(f"Deleted file after download: {path}")
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")