import os


class UnsupportedFormatError(Exception):
    pass


def extract_text(file_path: str) -> str:
    """
    从文件中提取纯文本。
    支持 .pdf / .docx / .md / .txt
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return _extract_pdf(file_path)
    elif ext == '.docx':
        return _extract_docx(file_path)
    elif ext in ('.md', '.txt'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    else:
        raise UnsupportedFormatError(f"不支持的文件格式: {ext}")


def _extract_pdf(file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _extract_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def split_into_chunks(text: str, max_chunk_size: int = 500) -> list:
    """
    按双换行切分段落；超过 max_chunk_size 的段落硬切。
    """
    if not text or not text.strip():
        return []
    raw_paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    for para in raw_paragraphs:
        if len(para) <= max_chunk_size:
            chunks.append(para)
        else:
            for i in range(0, len(para), max_chunk_size):
                chunk = para[i:i + max_chunk_size]
                if chunk:
                    chunks.append(chunk)
    return chunks


def process_document(doc_instance) -> None:
    """
    提取文本、切分段落，更新 KnowledgeDocument 实例。
    doc_instance 需已 save()（有 id 和 file 字段）。
    """
    from apps.requirement_analysis.models import KnowledgeDocument
    try:
        doc_instance.status = KnowledgeDocument.STATUS_PROCESSING
        doc_instance.save(update_fields=['status'])

        file_path = doc_instance.file.path
        text = extract_text(file_path)
        chunks = split_into_chunks(text)

        doc_instance.content_text = text
        doc_instance.chunks = chunks
        doc_instance.status = KnowledgeDocument.STATUS_INDEXED
        doc_instance.error_msg = ''
        doc_instance.save(update_fields=['content_text', 'chunks', 'status', 'error_msg'])
    except Exception as e:
        doc_instance.status = KnowledgeDocument.STATUS_FAILED
        doc_instance.error_msg = str(e)[:500]
        doc_instance.save(update_fields=['status', 'error_msg'])
