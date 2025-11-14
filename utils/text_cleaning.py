"""Text cleaning utilities."""
import re
from typing import List


def clean_text(text: str) -> str:
    """
    Basic text cleaning: normalize whitespace, remove extra newlines.
    
    Args:
        text: Raw text
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    # Replace multiple newlines with double newline
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()


def extract_skills_from_text(text: str) -> List[str]:
    """
    Extract potential skills from text (basic keyword extraction).
    This is a fallback; LLM extraction is preferred.
    
    Args:
        text: Text to extract skills from
        
    Returns:
        List of potential skill keywords
    """
    # Common technical skills keywords
    skill_keywords = [
        'python', 'java', 'javascript', 'sql', 'html', 'css', 'react', 'angular',
        'node.js', 'django', 'flask', 'aws', 'azure', 'docker', 'kubernetes',
        'git', 'agile', 'scrum', 'machine learning', 'data analysis', 'excel',
        'tableau', 'power bi', 'project management', 'leadership', 'communication'
    ]
    
    text_lower = text.lower()
    found_skills = []
    
    for skill in skill_keywords:
        if skill in text_lower:
            found_skills.append(skill.title())
    
    return list(set(found_skills))

