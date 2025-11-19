"""Supervisor: Rank jobs for user based on profile match."""
import json
from typing import List, Dict
from agents.schemas import UserProfile, JobPosting, ExtractedSkills, JobMatch
from services.llm_client import LLMClient
from agents.junior_researchers import summarize_user_profile_for_matching
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def rank_jobs_lightweight(
    profile: UserProfile,
    jobs: List[JobPosting],
    llm: LLMClient,
) -> Dict[str, float]:
    """
    Lightweight job ranking that doesn't require skill extraction.
    Uses job title, company, and description to quickly score jobs.
    
    Args:
        profile: User profile
        jobs: List of job postings
        llm: LLM client instance
        
    Returns:
        Dictionary mapping job_id to match_score (0.0 to 1.0)
    """
    if not jobs:
        return {}
    
    profile_summary = summarize_user_profile_for_matching(profile)
    
    # Build simplified job summaries (no skill extraction needed)
    job_summaries = []
    for job in jobs[:50]:  # Limit to 50 jobs to avoid token limits
        job_summaries.append({
            "id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "description": job["description"][:800],  # Truncate description
        })
    
    system_prompt = """You are a job matching expert. Your task is to quickly rank jobs based on how well they match a user's profile.

For each job, assign a match_score between 0.0 and 1.0, where:
- 1.0 = Perfect match (all requirements met, ideal fit)
- 0.7-0.9 = Strong match (most requirements met, good fit)
- 0.4-0.6 = Moderate match (some requirements met, possible fit)
- 0.1-0.3 = Weak match (few requirements met, stretch)
- 0.0 = No match (completely irrelevant)

Consider:
- Skill overlap (based on job description and user skills)
- Experience level alignment
- Industry/role alignment
- Job title relevance

Return a JSON array of objects, each with:
- job_id: The job ID
- match_score: Float between 0.0 and 1.0

Return ONLY valid JSON array. Do not include markdown code blocks."""

    user_prompt = f"""User Profile:
{profile_summary}

Jobs to Rank:
{json.dumps(job_summaries, indent=2)}

Rank these jobs and return match scores."""

    try:
        response = llm.chat_json(system_prompt, user_prompt)
        
        # Ensure response is a list
        if not isinstance(response, list):
            response = [response] if isinstance(response, dict) else []
        
        # Create a mapping of job_id to match_score
        match_scores: Dict[str, float] = {}
        for match_data in response:
            job_id = str(match_data.get("job_id") or match_data.get("id", ""))
            if job_id:
                match_scores[job_id] = float(match_data.get("match_score", 0.0))
        
        return match_scores
        
    except Exception as e:
        logger.error(f"Error in lightweight ranking: {str(e)}")
        # Fallback: return empty dict (jobs will remain unsorted)
        return {}


def rank_jobs_for_user(
    profile: UserProfile,
    jobs: List[JobPosting],
    job_skills: Dict[str, ExtractedSkills],
    llm: LLMClient,
    top_k: int = 10
) -> List[JobMatch]:
    """
    Rank jobs for user based on profile match using LLM.
    
    Args:
        profile: User profile
        jobs: List of job postings
        job_skills: Dictionary mapping job_id to ExtractedSkills
        llm: LLM client instance
        top_k: Number of top matches to return
        
    Returns:
        List of JobMatch objects sorted by match_score (descending)
    """
    if not jobs:
        return []
    
    profile_summary = summarize_user_profile_for_matching(profile)
    
    # Build job summaries for LLM
    job_summaries = []
    for job in jobs[:50]:  # Limit to 50 jobs to avoid token limits
        skills = job_skills.get(job["id"], {})
        skills_text = f"""
Hard Skills: {', '.join(skills.get('hard_skills', [])[:10])}
Soft Skills: {', '.join(skills.get('soft_skills', [])[:10])}
Tools: {', '.join(skills.get('tools', [])[:10])}
Seniority: {skills.get('seniority', 'Not specified')}
"""
        
        job_summaries.append({
            "id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "description": job["description"][:500],  # Truncate description
            "skills": skills_text,
        })
    
    system_prompt = """You are a job matching expert. Your task is to rank jobs based on how well they match a user's profile.

For each job, assign a match_score between 0.0 and 1.0, where:
- 1.0 = Perfect match (all requirements met, ideal fit)
- 0.7-0.9 = Strong match (most requirements met, good fit)
- 0.4-0.6 = Moderate match (some requirements met, possible fit)
- 0.1-0.3 = Weak match (few requirements met, stretch)
- 0.0 = No match (completely irrelevant)

Consider:
- Skill overlap (hard skills, tools)
- Experience level alignment
- Industry/role alignment
- Education requirements

Return a JSON array of objects, each with:
- job_id: The job ID
- match_score: Float between 0.0 and 1.0
- reasoning: Brief explanation (1-2 sentences) of why this score

Return ONLY valid JSON array. Do not include markdown code blocks."""

    user_prompt = f"""User Profile:
{profile_summary}

Jobs to Rank:
{json.dumps(job_summaries, indent=2)}

Rank these jobs and return match scores."""

    try:
        response = llm.chat_json(system_prompt, user_prompt)
        
        # Ensure response is a list
        if not isinstance(response, list):
            response = [response] if isinstance(response, dict) else []
        
        # Create a mapping of job_id to match data
        match_dict: Dict[str, Dict] = {}
        for match_data in response:
            job_id = str(match_data.get("job_id") or match_data.get("id", ""))
            if job_id:
                match_dict[job_id] = {
                    "match_score": float(match_data.get("match_score", 0.0)),
                    "reasoning": str(match_data.get("reasoning", "No reasoning provided")),
                }
        
        # Build JobMatch objects
        matches: List[JobMatch] = []
        for job in jobs:
            job_id = job["id"]
            if job_id in match_dict:
                match_data = match_dict[job_id]
                matches.append({
                    "job": job,
                    "match_score": match_data["match_score"],
                    "reasoning": match_data["reasoning"],
                })
        
        # Sort by match_score descending
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        
        # Return top_k
        return matches[:top_k]
        
    except Exception as e:
        logger.error(f"Error ranking jobs: {str(e)}")
        # Fallback: return jobs with default scores
        return [
            {
                "job": job,
                "match_score": 0.5,
                "reasoning": "Error during ranking - default score assigned",
            }
            for job in jobs[:top_k]
        ]

