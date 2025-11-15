"""Review Board: Sanity check outputs for hallucinations and inconsistencies."""
import json
from typing import List
from agents.schemas import UserProfile, JobMatch, SkillGapResult, ReviewResult
from services.llm_client import LLMClient
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def review_recommendations(
    profile: UserProfile,
    matches: List[JobMatch],
    gaps: List[SkillGapResult],
    llm: LLMClient
) -> ReviewResult:
    """
    Review recommendations for hallucinations, inconsistencies, and obvious errors.
    
    Args:
        profile: User profile
        matches: List of job matches
        gaps: List of skill gap results
        llm: LLM client instance
        
    Returns:
        ReviewResult dictionary with warnings and flagged items
    """
    if not matches:
        return {
            "warnings": [],
            "flagged_job_ids": [],
            "corrections": [],
        }
    
    user_skills = profile.get("skills", [])
    user_skills_text = ", ".join(user_skills) if user_skills else "None"
    
    # Extract additional profile information
    user_experience_level = profile.get("experience_level", "Not specified")
    user_location = profile.get("location", "Not specified")
    user_salary_min = profile.get("salary_range_min")
    user_salary_max = profile.get("salary_range_max")
    user_salary_currency = profile.get("salary_currency", "SGD")
    
    # Build salary text
    salary_text = "Not specified"
    if user_salary_min or user_salary_max:
        if user_salary_min and user_salary_max:
            salary_text = f"{user_salary_currency} {user_salary_min:,}-{user_salary_max:,}"
        elif user_salary_min:
            salary_text = f"{user_salary_currency} {user_salary_min:,}+"
        elif user_salary_max:
            salary_text = f"{user_salary_currency} up to {user_salary_max:,}"
    
    # Build summary of matches and gaps
    matches_summary = []
    for match in matches[:20]:  # Limit to 20 for token efficiency
        job = match["job"]
        gap = next((g for g in gaps if g["job_id"] == job["id"]), None)
        
        matches_summary.append({
            "job_id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "location": job.get("location", "Not specified"),
            "salary": job.get("salary_text", "Not specified"),
            "match_score": match["match_score"],
            "matched_skills": gap["matched_skills"][:5] if gap else [],
            "missing_skills": gap["missing_required_skills"][:5] if gap else [],
        })
    
    system_prompt = """You are a quality assurance reviewer for job recommendations. Your task is to identify:

1. Obviously irrelevant jobs (e.g., user is in F&B but job is "Senior Neurosurgeon")
2. Hallucinated skills (skills mentioned in matched_skills that don't appear in user profile)
3. Inconsistencies:
   - Experience level mismatch (e.g., job requires Senior but user is Junior, but match_score is high)
   - Location mismatch (e.g., user wants Remote but job is On-site only)
   - Salary mismatch (e.g., job pays much less than user's minimum expectation, but match_score is high)
4. Missing critical validations

Consider:
- User's experience level vs job requirements
- User's location preference vs job location
- User's salary expectations vs job salary range
- Overall fit beyond just skills

Return a JSON object with:
- warnings: List of warning messages describing issues found
- flagged_job_ids: List of job IDs that should be flagged for review
- corrections: List of correction suggestions (optional)

Be thorough but fair. Return ONLY valid JSON. Do not include markdown code blocks."""

    user_prompt = f"""User Profile:
- Skills: {user_skills_text}
- Experience Level: {user_experience_level}
- Preferred Location: {user_location}
- Salary Expectation: {salary_text}

Job Matches and Skill Gaps:
{json.dumps(matches_summary, indent=2)}

Review these recommendations for quality issues, considering experience level, location, and salary alignment."""

    try:
        response = llm.chat_json(system_prompt, user_prompt)
        
        review_result: ReviewResult = {
            "warnings": response.get("warnings", []),
            "flagged_job_ids": response.get("flagged_job_ids", []),
            "corrections": response.get("corrections", []),
        }
        
        return review_result
        
    except Exception as e:
        logger.error(f"Error in review board: {str(e)}")
        # Return empty review result on error
        return {
            "warnings": [f"Review process encountered an error: {str(e)}"],
            "flagged_job_ids": [],
            "corrections": [],
        }

