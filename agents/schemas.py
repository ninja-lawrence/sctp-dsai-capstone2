"""Data models/schemas for the job matching system."""
from typing import TypedDict, List, Optional, Dict, Any


class UserProfile(TypedDict, total=False):
    """User profile extracted from resume or manual input."""
    name: Optional[str]
    headline: Optional[str]
    summary: Optional[str]
    skills: List[str]
    experience: List[Dict[str, Any]]  # [{company, title, years, responsibilities}]
    education: List[Dict[str, Any]]  # [{institution, degree, field, year}]
    target_roles: List[str]
    experience_level: Optional[str]  # e.g., "entry", "junior", "mid-level", "senior", "lead", "executive"
    location: Optional[str]  # Preferred work location
    salary_range_min: Optional[int]  # Minimum expected salary
    salary_range_max: Optional[int]  # Maximum expected salary
    salary_currency: Optional[str]  # e.g., "SGD", "USD"


class JobPosting(TypedDict):
    """Normalized job posting structure."""
    id: str
    title: str
    company: str
    location: str
    salary_text: Optional[str]
    category: Optional[str]
    description: str
    url: Optional[str]
    image_url: Optional[str]  # Company logo or job image URL


class ExtractedSkills(TypedDict, total=False):
    """Skills extracted from a job posting."""
    hard_skills: List[str]
    soft_skills: List[str]
    tools: List[str]
    seniority: Optional[str]  # e.g., "junior", "mid-level", "senior", "lead"


class JobMatch(TypedDict):
    """Job match with score and reasoning."""
    job: JobPosting
    match_score: float  # 0.0 to 1.0
    reasoning: str


class LearningResource(TypedDict):
    """Learning resource (school/institution/certification)."""
    name: str  # Name of the institution/course/certification
    url: str  # Link to the learning resource
    type: str  # e.g., "university", "online_course", "certification", "bootcamp", "training_program"
    skill: str  # Which skill this resource helps learn


class SkillGapResult(TypedDict, total=False):
    """Skill gap analysis for a specific job."""
    job_id: str
    job_title: str
    matched_skills: List[str]
    missing_required_skills: List[str]
    missing_required_skills_writeup: Optional[str]  # Narrative writeup (max 200 words) about missing skills
    nice_to_have_skills: List[str]
    suggested_learning_path: List[str]  # High-level upskilling suggestions
    learning_resources: List[LearningResource]  # Links to schools/institutions/certifications


class ReviewResult(TypedDict, total=False):
    """Review board output."""
    warnings: List[str]
    flagged_job_ids: List[str]
    corrections: List[Dict[str, Any]]


class FinalOutput(TypedDict, total=False):
    """Final output from Principal Investigator."""
    recommended_jobs: List[Dict[str, Any]]
    skill_gaps: List[SkillGapResult]
    warnings: List[str]
    overall_summary: Optional[str]
    upskilling_roadmap: List[str]

