"""Senior Researcher: Generate detailed skill gap analysis."""
from agents.schemas import UserProfile, JobPosting, ExtractedSkills, SkillGapResult
from services.llm_client import LLMClient
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def generate_skill_gap_for_match(
    profile: UserProfile,
    job: JobPosting,
    job_skills: ExtractedSkills,
    llm: LLMClient
) -> SkillGapResult:
    """
    Generate detailed skill gap analysis for a job match.
    
    Args:
        profile: User profile
        job: Job posting
        job_skills: Extracted skills from job posting
        llm: LLM client instance
        
    Returns:
        SkillGapResult dictionary
    """
    user_skills = profile.get("skills", [])
    user_skills_text = ", ".join(user_skills) if user_skills else "None specified"
    
    job_hard_skills = job_skills.get("hard_skills", [])
    job_soft_skills = job_skills.get("soft_skills", [])
    job_tools = job_skills.get("tools", [])
    
    system_prompt = """You are a career advisor and skill gap analyst. Your task is to analyze the gap between a user's skills and a job's requirements.

For a given job, identify:
1. Matched Skills: Skills the user already has that match the job requirements
2. Missing Required Skills: Critical skills the user lacks that are essential for the job
3. Nice-to-Have Skills: Beneficial skills the user lacks but are not critical
4. Suggested Learning Path: 3-5 high-level steps the user should take to bridge the gap

Return a JSON object with:
- matched_skills: List of matched skill names
- missing_required_skills: List of critical missing skills
- nice_to_have_skills: List of beneficial but not critical missing skills
- suggested_learning_path: List of 3-5 learning steps (high-level, no platform branding)

Be specific and actionable. Return ONLY valid JSON. Do not include markdown code blocks."""

    user_prompt = f"""User Skills: {user_skills_text}

Job Title: {job['title']}
Company: {job['company']}

Job Required Skills:
Hard Skills: {', '.join(job_hard_skills)}
Soft Skills: {', '.join(job_soft_skills)}
Tools: {', '.join(job_tools)}

Job Description:
{job['description'][:2000]}

Analyze the skill gap and provide recommendations."""

    try:
        response = llm.chat_json(system_prompt, user_prompt)
        
        gap_result: SkillGapResult = {
            "job_id": job["id"],
            "job_title": job["title"],
            "matched_skills": response.get("matched_skills", []),
            "missing_required_skills": response.get("missing_required_skills", []),
            "nice_to_have_skills": response.get("nice_to_have_skills", []),
            "suggested_learning_path": response.get("suggested_learning_path", []),
        }
        
        return gap_result
        
    except Exception as e:
        logger.error(f"Error generating skill gap for job {job.get('id')}: {str(e)}")
        # Return minimal gap result on error
        return {
            "job_id": job["id"],
            "job_title": job["title"],
            "matched_skills": [],
            "missing_required_skills": [],
            "nice_to_have_skills": [],
            "suggested_learning_path": ["Error during analysis - please review job manually"],
        }

