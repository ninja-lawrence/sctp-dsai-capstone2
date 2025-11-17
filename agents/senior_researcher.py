"""Senior Researcher: Generate detailed skill gap analysis."""
from agents.schemas import UserProfile, JobPosting, ExtractedSkills, SkillGapResult, LearningResource
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
4. Suggested Learning Path: 3-5 high-level steps the user should take to bridge the gap (DO NOT include URLs here - URLs go in learning_resources)
5. Learning Resources: For each missing required skill, suggest 2-3 specific learning resources (schools, online courses, certifications, bootcamps) with actual URLs

For learning resources, provide:
- name: Name of the institution/course/certification (e.g., "Coursera - Google Data Analytics", "AWS Certified Solutions Architect", "General Assembly Data Science Bootcamp")
- url: Actual URL to the learning resource (must be a real, accessible URL)
- type: One of: "university", "online_course", "certification", "bootcamp", "training_program", "mooc"
- skill: The specific skill this resource helps learn

Focus on well-known, reputable learning platforms and institutions. Include a mix of:
- Free and paid options
- Online courses (Coursera, edX, Udemy, Udacity, Khan Academy)
- Certifications (AWS, Google, Microsoft, IBM, etc.)
- Universities (if applicable)
- Bootcamps (General Assembly, Le Wagon, etc.)

CRITICAL: You MUST return a valid JSON object. Start with { and end with }. Do NOT use markdown formatting, numbered lists, or any explanatory text.

Return a JSON object with this exact structure:
{
  "matched_skills": ["skill1", "skill2"],
  "missing_required_skills": ["skill3", "skill4"],
  "nice_to_have_skills": ["skill5"],
  "suggested_learning_path": ["Step 1: Brief description without URLs", "Step 2: Brief description without URLs", "Step 3: Brief description without URLs"],
  "learning_resources": [
    {
      "name": "Coursera - Full Stack Web Development",
      "url": "https://www.coursera.org/...",
      "type": "online_course",
      "skill": "Full Stack Development"
    }
  ]
}

IMPORTANT RULES:
- suggested_learning_path should contain ONLY brief step descriptions (no URLs, no parentheses with URLs)
- URLs belong ONLY in learning_resources array, not in suggested_learning_path
- All strings in JSON must use double quotes, escape any quotes inside strings with backslash
- Do NOT include URLs or parentheses in suggested_learning_path strings

Return ONLY the JSON object. Do NOT include:
- Markdown code blocks (```json or ```)
- Numbered lists (1. {...}, 2. {...})
- Explanatory text before or after the JSON
- URLs in suggested_learning_path (URLs go in learning_resources only)
- Any text outside the JSON object"""

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
        
        # Parse learning resources
        learning_resources = []
        raw_resources = response.get("learning_resources", [])
        for resource in raw_resources:
            if isinstance(resource, dict) and "name" in resource and "url" in resource:
                learning_resources.append({
                    "name": resource.get("name", ""),
                    "url": resource.get("url", ""),
                    "type": resource.get("type", "online_course"),
                    "skill": resource.get("skill", ""),
                })
        
        # Normalize skills lists - ensure they are lists of strings
        def normalize_skills_list(skills):
            """Convert skills list to list of strings, handling dicts if present."""
            if not isinstance(skills, list):
                return []
            normalized = []
            for skill in skills:
                if isinstance(skill, str):
                    normalized.append(skill)
                elif isinstance(skill, dict):
                    # Extract skill name from dict (try common keys)
                    skill_name = skill.get("skill") or skill.get("name") or skill.get("title") or str(skill)
                    normalized.append(skill_name)
                else:
                    normalized.append(str(skill))
            return normalized
        
        gap_result: SkillGapResult = {
            "job_id": job["id"],
            "job_title": job["title"],
            "matched_skills": normalize_skills_list(response.get("matched_skills", [])),
            "missing_required_skills": normalize_skills_list(response.get("missing_required_skills", [])),
            "nice_to_have_skills": normalize_skills_list(response.get("nice_to_have_skills", [])),
            "suggested_learning_path": normalize_skills_list(response.get("suggested_learning_path", [])),
            "learning_resources": learning_resources,
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
            "learning_resources": [],
        }

