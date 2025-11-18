"""Pipeline orchestration for the full job matching workflow."""
from typing import List, Dict, Any
from agents.schemas import UserProfile, JobPosting
from services.llm_client import LLMClient
from services.findsgjobs_client import normalize_job
from agents.junior_researchers import extract_skills_from_job
from agents.supervisor import rank_jobs_for_user
from agents.senior_researcher import generate_skill_gap_for_match
from agents.review_board import review_recommendations
from agents.principal_investigator import finalize_output
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def run_job_matching_pipeline(
    llm: LLMClient,
    profile: UserProfile,
    raw_jobs: List[Dict[str, Any]],
    top_k: int = 10
) -> Dict[str, Any]:
    """
    Run the complete job matching pipeline.
    
    Steps:
    1. Normalize raw jobs -> JobPosting list
    2. Junior Researchers extract job skills
    3. Supervisor ranks jobs
    4. Senior Researcher generates skill gaps for top N
    5. Review Board checks outputs
    6. PI finalizes payload
    
    Args:
        llm: LLM client instance
        profile: User profile
        raw_jobs: List of raw job dictionaries from API
        top_k: Number of top jobs to analyze in detail
        
    Returns:
        Final output dictionary ready for UI
    """
    logger.info(f"Starting pipeline with {len(raw_jobs)} jobs")
    
    # Step 1: Normalize jobs
    logger.info("Step 1: Normalizing jobs...")
    normalized_jobs: List[JobPosting] = []
    for raw_job in raw_jobs:
        try:
            normalized_job = normalize_job(raw_job)
            normalized_jobs.append(normalized_job)
        except Exception as e:
            logger.warning(f"Failed to normalize job: {str(e)}")
            continue
    
    if not normalized_jobs:
        logger.warning("No jobs to process after normalization")
        return {
            "recommended_jobs": [],
            "skill_gaps": [],
            "warnings": ["No jobs found or failed to normalize jobs"],
            "overall_summary": "No jobs to analyze.",
            "upskilling_roadmap": [],
        }
    
    logger.info(f"Normalized {len(normalized_jobs)} jobs")
    
    # Step 2: Extract skills from jobs
    logger.info("Step 2: Extracting skills from jobs...")
    job_skills = {}
    import time
    for idx, job in enumerate(normalized_jobs):
        try:
            # Add small delay between requests to help stay within rate limits
            if idx > 0:
                time.sleep(0.5)  # 500ms delay between requests
            skills = extract_skills_from_job(job, llm)
            job_skills[job["id"]] = skills
        except Exception as e:
            error_msg = str(e)
            # Check if it's a rate limit error
            if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                logger.error(
                    f"Rate limit exceeded while extracting skills for job {job.get('id')}. "
                    f"Please wait a minute before retrying. Error: {error_msg}"
                )
                # Stop processing more jobs to avoid hitting limit further
                break
            else:
                logger.warning(f"Failed to extract skills for job {job.get('id')}: {error_msg}")
            continue
    
    logger.info(f"Extracted skills from {len(job_skills)} jobs")
    
    # Step 3: Rank jobs
    logger.info("Step 3: Ranking jobs...")
    try:
        matches = rank_jobs_for_user(profile, normalized_jobs, job_skills, llm, top_k=top_k)
        logger.info(f"Ranked {len(matches)} jobs")
    except Exception as e:
        logger.error(f"Failed to rank jobs: {str(e)}")
        matches = []
    
    if not matches:
        logger.warning("No matches found")
        return {
            "recommended_jobs": [],
            "skill_gaps": [],
            "warnings": ["No job matches found"],
            "overall_summary": "No matching jobs found.",
            "upskilling_roadmap": [],
        }
    
    # Step 4: Generate skill gaps for top matches
    logger.info("Step 4: Generating skill gap analysis...")
    gaps = []
    import time
    for idx, match in enumerate(matches):
        try:
            # Add small delay between requests to help stay within rate limits
            if idx > 0:
                time.sleep(0.5)  # 500ms delay between requests
            job = match["job"]
            skills = job_skills.get(job["id"], {})
            gap = generate_skill_gap_for_match(profile, job, skills, llm)
            gaps.append(gap)
        except Exception as e:
            error_msg = str(e)
            # Check if it's a rate limit error
            if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                logger.error(
                    f"Rate limit exceeded while generating skill gap for job {match['job'].get('id')}. "
                    f"Please wait a minute before retrying. Error: {error_msg}"
                )
                # Stop processing more jobs to avoid hitting limit further
                break
            else:
                logger.warning(f"Failed to generate gap for job {match['job'].get('id')}: {error_msg}")
            continue
    
    logger.info(f"Generated {len(gaps)} skill gap analyses")
    
    # Step 5: Review Board
    logger.info("Step 5: Reviewing outputs...")
    try:
        review_result = review_recommendations(profile, matches, gaps, llm)
        logger.info(f"Review found {len(review_result.get('warnings', []))} warnings")
    except Exception as e:
        logger.error(f"Review board failed: {str(e)}")
        review_result = {
            "warnings": [f"Review process encountered an error: {str(e)}"],
            "flagged_job_ids": [],
            "corrections": [],
        }
    
    # Step 6: Finalize output
    logger.info("Step 6: Finalizing output...")
    try:
        final_output = finalize_output(profile, matches, gaps, review_result)
        logger.info("Pipeline completed successfully")
        return final_output
    except Exception as e:
        logger.error(f"Failed to finalize output: {str(e)}")
        return {
            "recommended_jobs": [],
            "skill_gaps": [],
            "warnings": [f"Pipeline error: {str(e)}"],
            "overall_summary": "Pipeline encountered an error.",
            "upskilling_roadmap": [],
        }


def run_skill_gap_analysis_only(
    llm: LLMClient,
    profile: UserProfile,
    raw_jobs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Run skill gap analysis only (no job recommendations/ranking).
    
    Steps:
    1. Normalize raw jobs -> JobPosting list
    2. Junior Researchers extract job skills
    3. Senior Researcher generates skill gaps directly
    
    Args:
        llm: LLM client instance
        profile: User profile
        raw_jobs: List of raw job dictionaries from API (typically 1 job)
        
    Returns:
        Final output dictionary with skill gaps only (no recommendations)
    """
    logger.info(f"Starting skill gap analysis with {len(raw_jobs)} jobs")
    
    # Step 1: Normalize jobs
    logger.info("Step 1: Normalizing jobs...")
    normalized_jobs: List[JobPosting] = []
    for raw_job in raw_jobs:
        try:
            normalized_job = normalize_job(raw_job)
            normalized_jobs.append(normalized_job)
        except Exception as e:
            logger.warning(f"Failed to normalize job: {str(e)}")
            continue
    
    if not normalized_jobs:
        logger.warning("No jobs to process after normalization")
        return {
            "recommended_jobs": [],
            "skill_gaps": [],
            "warnings": ["No jobs found or failed to normalize jobs"],
            "overall_summary": "No jobs to analyze.",
            "upskilling_roadmap": [],
        }
    
    logger.info(f"Normalized {len(normalized_jobs)} jobs")
    
    # Step 2: Extract skills from jobs
    logger.info("Step 2: Extracting skills from jobs...")
    job_skills = {}
    import time
    for idx, job in enumerate(normalized_jobs):
        try:
            # Add small delay between requests to help stay within rate limits
            if idx > 0:
                time.sleep(0.5)  # 500ms delay between requests
            skills = extract_skills_from_job(job, llm)
            job_skills[job["id"]] = skills
        except Exception as e:
            error_msg = str(e)
            # Check if it's a rate limit error
            if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                logger.error(
                    f"Rate limit exceeded while extracting skills for job {job.get('id')}. "
                    f"Please wait a minute before retrying. Error: {error_msg}"
                )
                # Stop processing more jobs to avoid hitting limit further
                break
            else:
                logger.warning(f"Failed to extract skills for job {job.get('id')}: {error_msg}")
            continue
    
    logger.info(f"Extracted skills from {len(job_skills)} jobs")
    
    # Step 3: Generate skill gaps directly (no ranking)
    logger.info("Step 3: Generating skill gap analysis...")
    gaps = []
    import time
    for idx, job in enumerate(normalized_jobs):
        try:
            # Add small delay between requests to help stay within rate limits
            if idx > 0:
                time.sleep(0.5)  # 500ms delay between requests
            skills = job_skills.get(job["id"], {})
            gap = generate_skill_gap_for_match(profile, job, skills, llm)
            gaps.append(gap)
        except Exception as e:
            error_msg = str(e)
            # Check if it's a rate limit error
            if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                logger.error(
                    f"Rate limit exceeded while generating skill gap for job {job.get('id')}. "
                    f"Please wait a minute before retrying. Error: {error_msg}"
                )
                # Stop processing more jobs to avoid hitting limit further
                break
            else:
                logger.warning(f"Failed to generate gap for job {job.get('id')}: {error_msg}")
            continue
    
    logger.info(f"Generated {len(gaps)} skill gap analyses")
    
    # Build upskilling roadmap (aggregate from all gaps)
    upskilling_roadmap = []
    seen_paths = set()
    
    for gap in gaps:
        for step in gap.get("suggested_learning_path", []):
            step_lower = step.lower().strip()
            if step_lower and step_lower not in seen_paths:
                upskilling_roadmap.append(step)
                seen_paths.add(step_lower)
    
    # Limit roadmap to top 10 unique items
    upskilling_roadmap = upskilling_roadmap[:10]
    
    # Generate overall summary
    if gaps:
        job_titles = [gap.get("job_title", "Unknown") for gap in gaps]
        overall_summary = f"Skill gap analysis completed for {len(gaps)} job(s): {', '.join(job_titles)}"
    else:
        overall_summary = "No skill gap analysis available."
    
    final_output = {
        "recommended_jobs": [],  # Empty - no recommendations
        "skill_gaps": gaps,
        "warnings": [],
        "overall_summary": overall_summary,
        "upskilling_roadmap": upskilling_roadmap,
    }
    
    logger.info("Skill gap analysis completed successfully")
    return final_output
