"""Senior Researcher: Generate detailed skill gap analysis."""
from agents.schemas import UserProfile, JobPosting, ExtractedSkills, SkillGapResult, LearningResource
from services.llm_client import LLMClient
from utils.logging_utils import get_logger
from utils.web_search_utils import search_learning_resources

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
    
    # Identify missing skills early to search for current learning resources
    all_job_skills = set(job_hard_skills + job_tools)
    user_skills_set = set(user_skills)
    missing_skills = list(all_job_skills - user_skills_set)
    
    # Search for current learning resources for missing skills
    learning_resources_context = {}
    if missing_skills:
        logger.info(f"Searching for learning resources for {len(missing_skills)} missing skills")
        for skill in missing_skills[:5]:  # Limit to top 5 to avoid too many searches
            try:
                resources = search_learning_resources(skill, max_results=3)
                if resources:
                    learning_resources_context[skill] = resources
                    logger.info(f"Found {len(resources)} resources for skill: {skill}")
            except Exception as e:
                logger.warning(f"Failed to search for resources for {skill}: {str(e)}")
                continue
    
    # Build context string from web search results
    resources_context_text = ""
    if learning_resources_context:
        resources_context_text = "\n\n**Current Learning Resources Found (from web search - use these verified URLs):**\n"
        for skill, resources in learning_resources_context.items():
            resources_context_text += f"\nFor skill '{skill}':\n"
            for res in resources:
                resources_context_text += f"- **{res['name']}**: {res['url']} (Type: {res['type']})\n"
                if res.get('description'):
                    resources_context_text += f"  Description: {res['description'][:150]}...\n"
        resources_context_text += "\nIMPORTANT: Prioritize using the URLs from the web search results above as they are current and verified. You may supplement with additional well-known resources if needed.\n"
    
    system_prompt = """You are a career advisor and skill gap analyst. Your task is to analyze the gap between a user's skills and a job's requirements.

For a given job, identify:
1. Matched Skills: Skills the user already has that match the job requirements
2. Missing Required Skills: Critical skills the user lacks that are essential for the job
   - Provide a list of missing required skills
   - Also provide a narrative writeup (maximum 200 words) explaining the skill gaps, why these skills are critical for the role, and how they impact the user's ability to perform the job effectively
3. Nice-to-Have Skills: Beneficial skills the user lacks but are not critical
4. Suggested Learning Path: 3-5 high-level steps the user should take to bridge the gap
5. Learning Resources: For each missing required skill, suggest 2-3 specific learning resources (schools, online courses, certifications, bootcamps) with actual URLs

IMPORTANT: Use the learning resources provided in the context below (from current web search) as your primary source. These are verified, current URLs from 2024. You may supplement with additional well-known resources if needed, but prioritize the provided resources.

For learning resources, provide:
- name: Name of the institution/course/certification (e.g., "Coursera - Google Data Analytics", "AWS Certified Solutions Architect", "General Assembly Data Science Bootcamp")
- url: Actual URL to the learning resource (must be a real, accessible URL - prefer URLs from the web search context provided)
- type: One of: "university", "online_course", "certification", "bootcamp", "training_program", "mooc"
- skill: The specific skill this resource helps learn

Focus on well-known, reputable learning platforms and institutions. Include a mix of:
- Free and paid options
- Online courses (Coursera, edX, Udemy, Udacity, Khan Academy)
- Certifications (AWS, Google, Microsoft, IBM, etc.)
- Universities (if applicable)
- Bootcamps (General Assembly, Le Wagon, etc.)

Return a JSON object with:
- matched_skills: List of matched skill names
- missing_required_skills: List of critical missing skills
- missing_required_skills_writeup: A narrative writeup (maximum 200 words) explaining the missing required skills, why they are critical, and their impact on job performance. Write in a clear, professional tone.
- nice_to_have_skills: List of beneficial but not critical missing skills
- suggested_learning_path: List of 3-5 learning steps (high-level)
- learning_resources: List of objects, each with {name, url, type, skill}

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
{resources_context_text}

Analyze the skill gap and provide recommendations. Use the learning resources from the web search context above when available, as they are current and verified."""

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
        
        gap_result: SkillGapResult = {
            "job_id": job["id"],
            "job_title": job["title"],
            "matched_skills": response.get("matched_skills", []),
            "missing_required_skills": response.get("missing_required_skills", []),
            "missing_required_skills_writeup": response.get("missing_required_skills_writeup", ""),
            "nice_to_have_skills": response.get("nice_to_have_skills", []),
            "suggested_learning_path": response.get("suggested_learning_path", []),
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
            "missing_required_skills_writeup": "Unable to generate skill gap analysis due to an error. Please review the job requirements manually.",
            "nice_to_have_skills": [],
            "suggested_learning_path": ["Error during analysis - please review job manually"],
            "learning_resources": [],
        }

