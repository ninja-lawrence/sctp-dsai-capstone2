"""Supervisor: Rank jobs for user based on profile match."""
import json
from typing import List, Dict
from agents.schemas import UserProfile, JobPosting, ExtractedSkills, JobMatch
from services.llm_client import LLMClient
from agents.junior_researchers import summarize_user_profile_for_matching
from utils.logging_utils import get_logger

logger = get_logger(__name__)


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
    
    # Helper function to normalize skill lists (handle dicts)
    def normalize_skill_list(skill_list):
        """Convert skill list to list of strings, handling dicts if present."""
        if not isinstance(skill_list, list):
            return []
        normalized = []
        for skill in skill_list:
            if isinstance(skill, str):
                normalized.append(skill)
            elif isinstance(skill, dict):
                # Extract skill name from dict (try common keys)
                skill_name = skill.get("skill") or skill.get("name") or skill.get("title") or str(skill)
                normalized.append(skill_name)
            else:
                normalized.append(str(skill))
        return normalized
    
    # Build job summaries for LLM
    job_summaries = []
    for job in jobs[:50]:  # Limit to 50 jobs to avoid token limits
        skills = job_skills.get(job["id"], {})
        
        # Normalize skill lists to ensure they're strings
        hard_skills = normalize_skill_list(skills.get('hard_skills', []))
        soft_skills = normalize_skill_list(skills.get('soft_skills', []))
        tools = normalize_skill_list(skills.get('tools', []))
        
        skills_text = f"""
Hard Skills: {', '.join(hard_skills[:10])}
Soft Skills: {', '.join(soft_skills[:10])}
Tools: {', '.join(tools[:10])}
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

CRITICAL: You MUST return a valid JSON array. Start with [ and end with ]. Each element must be a JSON object.

Return a JSON array of objects, each with:
- job_id: The job ID (string)
- title: The job title (string) 
- match_score: Float between 0.0 and 1.0
- reasoning: Brief explanation (1-2 sentences) of why this score

Example format:
[
  {
    "job_id": "123",
    "title": "Software Developer",
    "match_score": 0.85,
    "reasoning": "Strong match because..."
  },
  {
    "job_id": "456",
    "title": "Data Analyst",
    "match_score": 0.65,
    "reasoning": "Moderate match because..."
  }
]

Return ONLY the JSON array. Do NOT include markdown code blocks, explanations, or any other text."""

    user_prompt = f"""User Profile:
{profile_summary}

Jobs to Rank:
{json.dumps(job_summaries, indent=2)}

Rank these jobs and return match scores."""

    try:
        # Use chat_json_array since we expect an array response
        response = llm.chat_json_array(system_prompt, user_prompt)
        
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

