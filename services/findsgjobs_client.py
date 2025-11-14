"""FindSGJobs API client wrapper."""
import requests
from typing import Iterable, Literal, Optional, Dict, Any, List
from config import FIND_SGJOBS_BASE_URL, FIND_SGJOBS_TIMEOUT, FIND_SGJOBS_MAX_PAGES
from agents.schemas import JobPosting
from utils.logging_utils import get_logger

logger = get_logger(__name__)

SortField = Literal["activation_date", "relevance"]
SortDirection = Literal["asc", "desc"]


def search_findsgjobs(
    page: int = 1,
    keywords: Optional[str] = None,
    employment_types: Optional[Iterable[int]] = None,
    job_categories: Optional[Iterable[int]] = None,
    min_education_levels: Optional[Iterable[int]] = None,
    min_years_experience: Optional[Iterable[int]] = None,
    nearest_mrt_ids: Optional[Iterable[int]] = None,
    position: Optional[Literal["pmet", "non_pmet"]] = None,
    currency_id: Optional[int] = None,
    min_salary: Optional[int] = None,
    max_salary: Optional[int] = None,
    salary_interval_id: Optional[int] = None,
    sort_field: Optional[SortField] = "activation_date",
    sort_direction: Optional[SortDirection] = "desc",
    timeout: int = FIND_SGJOBS_TIMEOUT,
) -> Dict[str, Any]:
    """
    Call FindSGJobs searchable job API and return the JSON response.

    All list-like filters are automatically joined with commas as required by the API.
    """
    params: Dict[str, Any] = {
        "page": page,
    }

    if keywords:
        params["keywords"] = keywords

    if employment_types:
        params["EmploymentType"] = ",".join(str(e) for e in employment_types)

    if job_categories:
        params["JobCategory"] = ",".join(str(c) for c in job_categories)

    if min_education_levels:
        params["MinimumEducationLevel"] = ",".join(str(e) for e in min_education_levels)

    if min_years_experience:
        params["MinimumYearsofExperience"] = ",".join(str(y) for y in min_years_experience)

    if nearest_mrt_ids:
        params["id_Job_NearestMRTStation"] = ",".join(str(m) for m in nearest_mrt_ids)

    if position:
        params["Position"] = position

    if currency_id is not None:
        params["id_Job_Currency"] = currency_id

    if min_salary is not None:
        params["id_Job_Salary"] = min_salary

    if max_salary is not None:
        params["id_Job_MaxSalary"] = max_salary

    if salary_interval_id is not None:
        params["id_Job_Interval"] = salary_interval_id

    if sort_field:
        params["sort_field"] = sort_field

    if sort_direction:
        params["sort_direction"] = sort_direction

    try:
        response = requests.get(FIND_SGJOBS_BASE_URL, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"FindSGJobs API error: {str(e)}")
        raise


def fetch_all_findsgjobs(
    max_pages: int = FIND_SGJOBS_MAX_PAGES,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper to fetch multiple pages of jobs.

    kwargs are passed to `search_findsgjobs` (e.g., keywords=..., job_categories=[...]).
    """
    all_jobs: List[Dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        try:
            data = search_findsgjobs(page=page, **kwargs)

            # Adjust this depending on the actual response structure
            jobs = data.get("data") or data.get("jobs") or data
            if not jobs:
                break

            if isinstance(jobs, list):
                all_jobs.extend(jobs)
            else:
                break
        except Exception as e:
            logger.warning(f"Error fetching page {page}: {str(e)}")
            break

    return all_jobs


def normalize_job(job_dict: Dict[str, Any]) -> JobPosting:
    """
    Normalize a raw job dictionary from FindSGJobs API into a JobPosting.
    
    Args:
        job_dict: Raw job dictionary from API
        
    Returns:
        Normalized JobPosting object
    """
    # Extract fields with fallbacks for different API response structures
    job_id = str(job_dict.get("id") or job_dict.get("job_id") or job_dict.get("Id") or "")
    title = job_dict.get("title") or job_dict.get("job_title") or job_dict.get("Title") or "N/A"
    company = job_dict.get("company") or job_dict.get("company_name") or job_dict.get("Company") or "N/A"
    location = job_dict.get("location") or job_dict.get("job_location") or job_dict.get("Location") or "N/A"
    
    # Salary handling
    salary_text = None
    if "salary" in job_dict:
        salary_text = str(job_dict["salary"])
    elif "salary_range" in job_dict:
        salary_text = str(job_dict["salary_range"])
    elif "Salary" in job_dict:
        salary_text = str(job_dict["Salary"])
    
    # Category
    category = job_dict.get("category") or job_dict.get("job_category") or job_dict.get("Category")
    
    # Description - try multiple fields
    description = (
        job_dict.get("description") or 
        job_dict.get("job_description") or 
        job_dict.get("Description") or 
        job_dict.get("summary") or 
        job_dict.get("Summary") or 
        ""
    )
    
    # URL
    url = job_dict.get("url") or job_dict.get("job_url") or job_dict.get("Url")
    
    return JobPosting(
        id=job_id,
        title=title,
        company=company,
        location=location,
        salary_text=salary_text,
        category=category,
        description=description,
        url=url,
    )

