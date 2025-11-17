"""Principal Investigator: Finalize and consolidate output."""
import re
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
    
    def normalize_step(step):
        """Convert step to string, handling dicts if present, and remove step numbering."""
        if isinstance(step, str):
            step_str = step
        elif isinstance(step, dict):
            # Extract step text from dict (try common keys)
            step_str = step.get("step") or step.get("description") or step.get("text") or str(step)
        else:
            step_str = str(step)
        
        # Remove step numbering patterns like "Step 1:", "Step 1", "1. ", "1)", etc.
        step_str = re.sub(r'^Step\s+\d+\s*:\s*', '', step_str, flags=re.IGNORECASE)
        step_str = re.sub(r'^Step\s+\d+\s+', '', step_str, flags=re.IGNORECASE)
        step_str = re.sub(r'^\d+[\.\)]\s*', '', step_str)
        step_str = step_str.strip()
        
        return step_str
    
    for gap in gaps:
        for step in gap.get("suggested_learning_path", []):
            step_str = normalize_step(step)
            step_lower = step_str.lower().strip()
            if step_lower and step_lower not in seen_paths:
                upskilling_roadmap.append(step_str)
                seen_paths.add(step_lower)
    
    # Limit roadmap to top 10 unique items
    upskilling_roadmap = upskilling_roadmap[:10]
    
    # Normalize warnings to strings
    def normalize_warning(warning):
        """Convert warning to string, handling dicts if present."""
        if isinstance(warning, str):
            return warning
        elif isinstance(warning, dict):
            return warning.get("message") or warning.get("warning") or str(warning)
        else:
            return str(warning)
    
    warnings_list = review_result.get('warnings', [])
    normalized_warnings = [normalize_warning(w) for w in warnings_list[:3]]
    
    # Generate overall summary
    overall_summary = f"""
Found {len(matches)} job recommendations based on your profile.

Top matches:
{chr(10).join(f"- {job['title']} at {job['company']} (Match: {job['match_score']:.1%})" for job in recommended_jobs[:5])}

{'⚠️ ' + '; '.join(normalized_warnings) if normalized_warnings else ''}
""".strip()
    
    # Normalize all warnings in final output
    all_warnings = review_result.get("warnings", [])
    normalized_all_warnings = [normalize_warning(w) for w in all_warnings]
    
    final_output: FinalOutput = {
        "recommended_jobs": recommended_jobs,
        "skill_gaps": gaps,
        "warnings": normalized_all_warnings,
        "overall_summary": overall_summary,
        "upskilling_roadmap": upskilling_roadmap,
    }
    
    return final_output

