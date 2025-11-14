"""Resume parser for PDF, DOCX, and TXT files."""
import re
from typing import Optional
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def parse_resume(file_content: bytes, filename: str) -> str:
    """
    Parse resume from uploaded file.
    
    Args:
        file_content: File content as bytes
        filename: Original filename
        
    Returns:
        Extracted text content
    """
    file_ext = filename.lower().split('.')[-1]
    
    if file_ext == 'txt':
        return parse_txt(file_content)
    elif file_ext == 'pdf':
        return parse_pdf(file_content)
    elif file_ext in ['docx', 'doc']:
        return parse_docx(file_content)
    else:
        raise ValueError(f"Unsupported file type: {file_ext}. Supported: txt, pdf, docx")


def parse_txt(file_content: bytes) -> str:
    """Parse plain text file."""
    try:
        text = file_content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = file_content.decode('latin-1')
        except UnicodeDecodeError:
            text = file_content.decode('utf-8', errors='ignore')
    
    return normalize_text(text)


def parse_pdf(file_content: bytes) -> str:
    """Parse PDF file."""
    try:
        import pypdf
        from io import BytesIO
        
        pdf_file = BytesIO(file_content)
        pdf_reader = pypdf.PdfReader(pdf_file)
        
        text_parts = []
        for page in pdf_reader.pages:
            text_parts.append(page.extract_text())
        
        text = "\n".join(text_parts)
        return normalize_text(text)
    except ImportError:
        logger.warning("pypdf not installed. Install with: pip install pypdf")
        raise ImportError("PDF parsing requires pypdf. Install with: pip install pypdf")
    except Exception as e:
        logger.error(f"PDF parsing error: {str(e)}")
        raise ValueError(f"Failed to parse PDF: {str(e)}")


def parse_docx(file_content: bytes) -> str:
    """Parse DOCX file."""
    try:
        from docx import Document
        from io import BytesIO
        
        docx_file = BytesIO(file_content)
        doc = Document(docx_file)
        
        text_parts = []
        for paragraph in doc.paragraphs:
            text_parts.append(paragraph.text)
        
        text = "\n".join(text_parts)
        return normalize_text(text)
    except ImportError:
        logger.warning("python-docx not installed. Install with: pip install python-docx")
        raise ImportError("DOCX parsing requires python-docx. Install with: pip install python-docx")
    except Exception as e:
        logger.error(f"DOCX parsing error: {str(e)}")
        raise ValueError(f"Failed to parse DOCX: {str(e)}")


def normalize_text(text: str) -> str:
    """
    Normalize whitespace and clean text.
    
    Args:
        text: Raw text
        
    Returns:
        Normalized text
    """
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    # Replace multiple newlines with double newline
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()

