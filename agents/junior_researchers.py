"""Junior Researchers: Extract profile and job skills using LLM."""
import json
from typing import List
from agents.schemas import UserProfile, JobPosting, ExtractedSkills
from services.llm_client import LLMClient
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def extract_profile_from_resume_text(text: str, llm: LLMClient) -> UserProfile:
    """
    Extract user profile from resume text using LLM.
    
    Args:
        text: Raw resume text
        llm: LLM client instance
        
    Returns:
        UserProfile dictionary
    """
    system_prompt = """You are an expert ATS (Applicant Tracking System) resume parser.
Your task is to extract structured information from a resume text and return it as JSON.

Extract the following information:
- name: Full name (if available)
- headline: Professional headline or title
- summary: Professional summary or objective
- skills: List of technical and soft skills mentioned
- experience: List of work experiences, each with:
  - company: Company name
  - title: Job title
  - years: Years of experience (numeric or range)
  - responsibilities: Brief description of responsibilities
- education: List of education entries, each with:
  - institution: School/university name
  - degree: Degree type (e.g., "Bachelor's", "Master's")
  - field: Field of study
  - year: Graduation year (if available)
- target_roles: List of target job roles or career interests (if mentioned)
- experience_level: Overall experience level based on years and roles (one of: "Entry Level", "Junior", "Mid-Level", "Senior", "Lead", "Executive", or null if unclear)
- location: Preferred work location if mentioned (e.g., "Singapore", "Remote", etc.), or null
- salary_range_min: Minimum expected salary if mentioned (numeric), or null
- salary_range_max: Maximum expected salary if mentioned (numeric), or null
- salary_currency: Currency for salary if mentioned (e.g., "SGD", "USD"), default to "SGD" if not specified

Return ONLY valid JSON. Do not include markdown code blocks or explanations."""

    user_prompt = f"""Parse this resume text and extract the structured information:

{text[:4000]}"""  # Limit text length to avoid token limits

    try:
        response = llm.chat_json(system_prompt, user_prompt)
        
        # Ensure all required fields exist
        profile: UserProfile = {
            "name": response.get("name"),
            "headline": response.get("headline"),
            "summary": response.get("summary"),
            "skills": response.get("skills", []),
            "experience": response.get("experience", []),
            "education": response.get("education", []),
            "target_roles": response.get("target_roles", []),
            "experience_level": response.get("experience_level"),
            "location": response.get("location"),
            "salary_range_min": response.get("salary_range_min"),
            "salary_range_max": response.get("salary_range_max"),
            "salary_currency": response.get("salary_currency", "SGD"),
        }
        
        return profile
    except Exception as e:
        logger.error(f"Error extracting profile: {str(e)}")
        # Return minimal profile on error
        return {
            "name": None,
            "headline": None,
            "summary": None,
            "skills": [],
            "experience": [],
            "education": [],
            "target_roles": [],
            "experience_level": None,
            "location": None,
            "salary_range_min": None,
            "salary_range_max": None,
            "salary_currency": "SGD",
        }


def extract_skills_from_job(job: JobPosting, llm: LLMClient) -> ExtractedSkills:
    """
    Extract structured skills from a job posting using LLM.
    
    Args:
        job: JobPosting object
        llm: LLM client instance
        
    Returns:
        ExtractedSkills dictionary
    """
    system_prompt = """You are a job analysis expert. Extract structured skills and requirements from a job posting.

Return a JSON object with:
- hard_skills: List of technical skills, programming languages, tools, frameworks required
- soft_skills: List of soft skills, personal attributes, communication skills
- tools: List of specific software tools, platforms, or technologies mentioned
- seniority: Level of seniority (e.g., "junior", "mid-level", "senior", "lead", "entry-level")

Return ONLY valid JSON. Do not include markdown code blocks."""

    job_text = f"""Job Title: {job['title']}
Company: {job['company']}
Description:
{job['description'][:3000]}"""  # Limit description length

    user_prompt = f"""Extract skills and requirements from this job posting:

{job_text}"""

    try:
        response = llm.chat_json(system_prompt, user_prompt)
        
        skills: ExtractedSkills = {
            "hard_skills": response.get("hard_skills", []),
            "soft_skills": response.get("soft_skills", []),
            "tools": response.get("tools", []),
            "seniority": response.get("seniority"),
        }
        
        return skills
    except Exception as e:
        logger.error(f"Error extracting skills from job {job.get('id')}: {str(e)}")
        # Return minimal skills on error
        return {
            "hard_skills": [],
            "soft_skills": [],
            "tools": [],
            "seniority": None,
        }


def summarize_user_profile_for_matching(profile: UserProfile) -> str:
    """
    Create a natural language summary of user profile for use in matching prompts.
    
    Args:
        profile: UserProfile object
        
    Returns:
        Natural language summary string
    """
    parts = []
    
    if profile.get("name"):
        parts.append(f"Name: {profile['name']}")
    
    if profile.get("headline"):
        parts.append(f"Headline: {profile['headline']}")
    
    if profile.get("summary"):
        parts.append(f"Summary: {profile['summary']}")
    
    if profile.get("skills"):
        skills_str = ", ".join(profile["skills"])
        parts.append(f"Skills: {skills_str}")
    
    if profile.get("experience"):
        parts.append("Experience:")
        for exp in profile["experience"][:5]:  # Limit to top 5
            company = exp.get("company", "Unknown")
            title = exp.get("title", "Unknown")
            years = exp.get("years", "")
            parts.append(f"  - {title} at {company} ({years})")
    
    if profile.get("education"):
        parts.append("Education:")
        for edu in profile["education"][:3]:  # Limit to top 3
            degree = edu.get("degree", "")
            field = edu.get("field", "")
            institution = edu.get("institution", "")
            parts.append(f"  - {degree} in {field} from {institution}")
    
    if profile.get("target_roles"):
        roles_str = ", ".join(profile["target_roles"])
        parts.append(f"Target Roles: {roles_str}")
    
    return "\n".join(parts)

