"""Principal Investigator: Finalize and consolidate output."""
from typing import List
from agents.schemas import (
    UserProfile,
    JobMatch,
    SkillGapResult,
    ReviewResult,
    FinalOutput
)
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def finalize_output(
    profile: UserProfile,
    matches: List[JobMatch],
    gaps: List[SkillGapResult],
    review_result: ReviewResult
) -> FinalOutput:
    """
    Consolidate all outputs into final structure for UI rendering.
    
    Args:
        profile: User profile
        matches: List of job matches
        gaps: List of skill gap results
        review_result: Review board output
        
    Returns:
        FinalOutput dictionary ready for UI
    """
    # Build recommended jobs list
    recommended_jobs = []
    for match in matches:
        job = match["job"]
        gap = next((g for g in gaps if g["job_id"] == job["id"]), None)
        
        job_dict = {
            "job_id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "salary_text": job.get("salary_text"),
            "url": job.get("url"),
            "match_score": match["match_score"],
            "reasoning": match["reasoning"],
            "category": job.get("category"),
        }
        
        recommended_jobs.append(job_dict)
    
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
    overall_summary = f"""
Found {len(matches)} job recommendations based on your profile.

Top matches:
{chr(10).join(f"- {job['title']} at {job['company']} (Match: {job['match_score']:.1%})" for job in recommended_jobs[:5])}

{'⚠️ ' + '; '.join(review_result.get('warnings', [])[:3]) if review_result.get('warnings') else ''}
""".strip()
    
    final_output: FinalOutput = {
        "recommended_jobs": recommended_jobs,
        "skill_gaps": gaps,
        "warnings": review_result.get("warnings", []),
        "overall_summary": overall_summary,
        "upskilling_roadmap": upskilling_roadmap,
    }
    
    return final_output

