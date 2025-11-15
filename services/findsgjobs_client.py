"""FindSGJobs API client wrapper with rate limiting."""
import requests
import time
import logging
from typing import Iterable, Literal, Optional, Dict, Any, List
from collections import deque
from config import (
    FIND_SGJOBS_BASE_URL,
    FIND_SGJOBS_TIMEOUT,
    FIND_SGJOBS_MAX_PAGES,
    FIND_SGJOBS_RATE_LIMIT,
    FIND_SGJOBS_RATE_LIMIT_WINDOW,
)
from agents.schemas import JobPosting
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Rate limiter: track request timestamps
_request_timestamps: deque = deque()


def _check_rate_limit() -> None:
    """
    Check if we're within rate limit, wait if necessary.
    
    Rate limit: 60 requests per minute per IP.
    """
    current_time = time.time()
    
    # Remove timestamps outside the time window
    while _request_timestamps and current_time - _request_timestamps[0] > FIND_SGJOBS_RATE_LIMIT_WINDOW:
        _request_timestamps.popleft()
    
    # If we're at the limit, wait until the oldest request expires
    if len(_request_timestamps) >= FIND_SGJOBS_RATE_LIMIT:
        oldest_timestamp = _request_timestamps[0]
        wait_time = FIND_SGJOBS_RATE_LIMIT_WINDOW - (current_time - oldest_timestamp) + 0.1
        if wait_time > 0:
            logger.warning(f"Rate limit reached. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            # Clean up again after waiting
            current_time = time.time()
            while _request_timestamps and current_time - _request_timestamps[0] > FIND_SGJOBS_RATE_LIMIT_WINDOW:
                _request_timestamps.popleft()
    
    # Record this request
    _request_timestamps.append(time.time())


def get_rate_limit_status() -> Dict[str, Any]:
    """
    Get current rate limit status.
    
    Returns:
        Dictionary with rate limit information
    """
    current_time = time.time()
    
    # Clean up old timestamps
    while _request_timestamps and current_time - _request_timestamps[0] > FIND_SGJOBS_RATE_LIMIT_WINDOW:
        _request_timestamps.popleft()
    
    requests_in_window = len(_request_timestamps)
    remaining_requests = max(0, FIND_SGJOBS_RATE_LIMIT - requests_in_window)
    
    return {
        "requests_in_window": requests_in_window,
        "remaining_requests": remaining_requests,
        "rate_limit": FIND_SGJOBS_RATE_LIMIT,
        "window_seconds": FIND_SGJOBS_RATE_LIMIT_WINDOW,
    }

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

    # Check and enforce rate limit
    _check_rate_limit()
    
    try:
        response = requests.get(FIND_SGJOBS_BASE_URL, params=params, timeout=timeout)
        
        # Check for rate limit response (429 Too Many Requests)
        if response.status_code == 429:
            logger.error("Rate limit exceeded (429). Please wait before making more requests.")
            raise requests.exceptions.HTTPError(
                f"Rate limit exceeded: {response.status_code} - {response.text}"
            )
        
        response.raise_for_status()
        
        # Try to parse JSON
        try:
            json_data = response.json()
            logger.debug(f"API response status: {response.status_code}, Content-Type: {response.headers.get('Content-Type')}")
            return json_data
        except ValueError as e:
            # If JSON parsing fails, log the response text
            logger.error(f"Failed to parse JSON response: {str(e)}")
            logger.error(f"Response text (first 1000 chars): {response.text[:1000]}")
            raise ValueError(f"Invalid JSON response from API: {str(e)}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"FindSGJobs API error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response text: {e.response.text[:500]}")
        raise


def fetch_all_findsgjobs(
    max_pages: int = FIND_SGJOBS_MAX_PAGES,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper to fetch multiple pages of jobs.

    kwargs are passed to `search_findsgjobs` (e.g., keywords=..., job_categories=[...]).
    
    Note: Rate limited to 60 requests per minute per IP. This function will automatically
    throttle requests to stay within the limit.
    """
    all_jobs: List[Dict[str, Any]] = []
    
    # Check rate limit status before starting
    rate_status = get_rate_limit_status()
    if rate_status["remaining_requests"] < max_pages:
        logger.warning(
            f"Only {rate_status['remaining_requests']} requests remaining in window. "
            f"Requesting {max_pages} pages may hit rate limit."
        )

    for page in range(1, max_pages + 1):
        try:
            data = search_findsgjobs(page=page, **kwargs)
            
            # Log the response structure for debugging
            if isinstance(data, dict):
                logger.info(f"API response for page {page}: dict with keys: {list(data.keys())}")
            else:
                logger.info(f"API response for page {page}: {type(data).__name__}")

            # Try multiple possible response structures
            jobs = None
            
            # Common API response patterns
            if isinstance(data, dict):
                # First, try common keys that typically contain job lists
                for key in ["data", "jobs", "results", "items", "jobList", "JobList", "job_list"]:
                    if key in data:
                        value = data[key]
                        if isinstance(value, list):
                            jobs = value
                            logger.info(f"Found jobs list in key '{key}' with {len(value)} items")
                            break
                        elif isinstance(value, dict):
                            # Sometimes the value is nested in another dict
                            logger.debug(f"Key '{key}' contains a dict, checking nested structure")
                            # Check if this dict contains a list
                            for nested_key, nested_value in value.items():
                                if isinstance(nested_value, list) and len(nested_value) > 0:
                                    if isinstance(nested_value[0], dict):
                                        jobs = nested_value
                                        logger.info(f"Found jobs list in nested key '{key}.{nested_key}' with {len(nested_value)} items")
                                        break
                            if jobs:
                                break
                
                # If still no jobs, check if data itself is a list-like dict (numeric keys)
                if not jobs:
                    if all(isinstance(k, (int, str)) and str(k).isdigit() for k in data.keys()):
                        # Convert dict with numeric keys to list
                        sorted_items = sorted(data.items(), key=lambda x: int(str(x[0])))
                        jobs = [item[1] for item in sorted_items]
                        logger.info(f"Converted dict with numeric keys to list with {len(jobs)} items")
                
                # If still no jobs, check if the entire response is a list wrapped in a dict
                if not jobs and len(data) == 1:
                    first_value = list(data.values())[0]
                    if isinstance(first_value, list):
                        jobs = first_value
                        logger.info(f"Found jobs list as single dict value with {len(first_value)} items")
                
                # If still no jobs, check if any value in the dict is a list
                if not jobs:
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            # Check if it looks like job data
                            if isinstance(value[0], dict):
                                jobs = value
                                logger.info(f"Found jobs list in key '{key}' with {len(value)} items")
                                break
                
                # Last resort: if data itself looks like a single job object
                if not jobs and any(key in data for key in ["id", "title", "job_title", "Title", "company", "Company"]):
                    jobs = [data]  # Wrap single job in a list
                    logger.info("Response appears to be a single job object, wrapping in list")
                    
            elif isinstance(data, list):
                # API might return a list directly
                jobs = data
                logger.info(f"API returned list directly with {len(data)} items")
            
            if not jobs:
                logger.warning(f"No jobs found in response for page {page}. Response structure: {type(data)}")
                logger.debug(f"Response sample: {str(data)[:500]}")
                break

            if isinstance(jobs, list):
                if len(jobs) == 0:
                    logger.info(f"Page {page} returned empty list, stopping pagination")
                    break
                all_jobs.extend(jobs)
                logger.info(f"Page {page}: Added {len(jobs)} jobs (total: {len(all_jobs)})")
            elif isinstance(jobs, dict):
                # Handle case where API returns a single job as a dict, or a dict with job data
                logger.info(f"Page {page}: Received dict response, attempting to extract jobs")
                
                # Check if this dict looks like a single job object
                if any(key in jobs for key in ["id", "title", "job_title", "Title", "company", "Company"]):
                    # It's a single job object, wrap it in a list
                    logger.info(f"Page {page}: Dict appears to be a single job object")
                    all_jobs.append(jobs)
                else:
                    # Try to find job data within the dict
                    # Look for nested lists or dicts that might contain jobs
                    found_nested_jobs = False
                    for key, value in jobs.items():
                        if isinstance(value, list) and len(value) > 0:
                            if isinstance(value[0], dict):
                                logger.info(f"Page {page}: Found nested list of jobs in key '{key}'")
                                all_jobs.extend(value)
                                found_nested_jobs = True
                                break
                        elif isinstance(value, dict):
                            # Check if this nested dict is a job object
                            if any(k in value for k in ["id", "title", "job_title", "Title"]):
                                logger.info(f"Page {page}: Found nested job dict in key '{key}'")
                                all_jobs.append(value)
                                found_nested_jobs = True
                    
                    if not found_nested_jobs:
                        logger.warning(
                            f"Page {page}: Could not extract jobs from dict. "
                            f"Dict keys: {list(jobs.keys())}. "
                            f"Stopping pagination."
                        )
                        # Log a sample of the dict structure for debugging
                        logger.debug(f"Dict sample: {str(jobs)[:500]}")
                        break
            else:
                logger.warning(
                    f"Jobs is not a list or dict: {type(jobs)}, value: {str(jobs)[:200]}, "
                    f"stopping pagination"
                )
                break
        except requests.exceptions.HTTPError as e:
            # If rate limit exceeded, stop fetching
            if "429" in str(e) or "Rate limit" in str(e):
                logger.error(f"Rate limit exceeded at page {page}. Stopping fetch.")
                break
            raise
        except Exception as e:
            logger.warning(f"Error fetching page {page}: {str(e)}")
            break

    return all_jobs


def normalize_job(job_dict: Dict[str, Any]) -> JobPosting:
    """
    Normalize a raw job dictionary from FindSGJobs API into a JobPosting.
    
    The API returns data in nested structure:
    - job_dict["job"] contains job-specific fields
    - job_dict["company"] contains company-specific fields
    
    Args:
        job_dict: Raw job dictionary from API
        
    Returns:
        Normalized JobPosting object
    """
    import json
    import re
    
    def extract_text(value: Any) -> str:
        """Extract readable text from various data types."""
        if value is None:
            return ""
        
        if isinstance(value, str):
            # Clean HTML tags if present
            value = re.sub(r'<[^>]+>', '', value)
            # Decode HTML entities
            value = value.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&bull;', '•')
            # Remove extra whitespace
            cleaned = ' '.join(value.split())
            return cleaned if cleaned else ""
        
        if isinstance(value, dict):
            # Try common text fields
            for text_key in ['caption', 'text', 'content', 'name', 'title', 'value', 'description', 'label']:
                if text_key in value:
                    result = extract_text(value[text_key])
                    if result:
                        return result
            # If dict has address or name field
            if 'address' in value:
                return extract_text(value['address'])
            if 'name' in value:
                return extract_text(value['name'])
            return ""
        
        if isinstance(value, list):
            if len(value) > 0:
                # If list contains dicts with 'caption', extract captions
                captions = []
                for item in value:
                    if isinstance(item, dict) and 'caption' in item:
                        captions.append(extract_text(item['caption']))
                    else:
                        captions.append(extract_text(item))
                result = ", ".join([c for c in captions if c])
                if result:
                    return result
            return ""
        
        return str(value) if value else ""
    
    def safe_get_nested(data: Dict[str, Any], *keys: str, default: str = "") -> str:
        """Try multiple keys in nested structure."""
        for key in keys:
            if key in data:
                value = data[key]
                result = extract_text(value)
                if result:
                    return result
        return default
    
    # Extract nested job and company data
    job_data = job_dict.get("job", {})
    company_data = job_dict.get("company", {})
    
    # If job_data is empty, try using job_dict directly
    if not job_data:
        job_data = job_dict
    
    # Extract job ID - look for actual job ID fields
    # Try multiple possible job ID fields
    job_id = None
    
    # Check for job ID in various possible locations
    if "id" in job_data:
        job_id = str(job_data["id"])
    elif "job_id" in job_data:
        job_id = str(job_data["job_id"])
    elif "Id" in job_data:
        job_id = str(job_data["Id"])
    elif "JobId" in job_data:
        job_id = str(job_data["JobId"])
    elif "id" in job_dict:
        job_id = str(job_dict["id"])
    
    # If still no job ID, use company_sid as fallback (but note it's not ideal)
    if not job_id:
        job_id = str(job_data.get("company_sid", ""))
    
    # Last resort: create a placeholder ID
    if not job_id:
        title_part = safe_get_nested(job_data, "Title", "title", default="job")[:20]
        company_part = safe_get_nested(company_data, "CompanyName", "company_name", default="company")[:20]
        job_id = f"{title_part}_{company_part}".replace(" ", "_")
    
    # Extract title
    title = safe_get_nested(
        job_data,
        "Title", "title", "job_title", "JobTitle", "name", "Name"
    )
    
    # Extract company name from company data
    company = safe_get_nested(
        company_data,
        "CompanyName", "company_name", "Company", "company", "name", "Name"
    )
    
    # Extract location from company GooglePlace
    location = ""
    if "GooglePlace" in company_data:
        google_place = company_data["GooglePlace"]
        if isinstance(google_place, dict):
            location = extract_text(google_place.get("address")) or extract_text(google_place.get("name"))
    
    # If no location from GooglePlace, try other fields
    if not location:
        location = safe_get_nested(
            job_data,
            "location", "Location", "address", "Address", "city", "City"
        )
    
    # Build salary text from components
    salary_text = None
    min_salary = job_data.get("id_Job_Salary")
    max_salary = job_data.get("id_Job_MaxSalary")
    salary_interval = job_data.get("id_Job_Interval", {})
    currency = job_data.get("id_Job_Currency", {})
    
    if min_salary or max_salary:
        currency_str = extract_text(currency) or "SGD"
        interval_str = extract_text(salary_interval) or "month"
        
        if min_salary and max_salary:
            salary_text = f"{currency_str} {min_salary:,}-{max_salary:,} per {interval_str}"
        elif min_salary:
            salary_text = f"{currency_str} {min_salary:,}+ per {interval_str}"
        elif max_salary:
            salary_text = f"{currency_str} up to {max_salary:,} per {interval_str}"
    
    # Extract category from JobCategory array
    category = ""
    job_categories = job_data.get("JobCategory", [])
    if isinstance(job_categories, list) and len(job_categories) > 0:
        categories = []
        for cat in job_categories:
            if isinstance(cat, dict):
                cat_text = extract_text(cat.get("caption"))
                if cat_text:
                    categories.append(cat_text)
        category = ", ".join(categories) if categories else ""
    
    # Extract description
    description = safe_get_nested(
        job_data,
        "JobDescription", "job_description", "Description", "description",
        "summary", "Summary", "details", "Details", "content", "Content"
    )
    
    # Clean HTML from description
    if description:
        description = re.sub(r'<[^>]+>', '', description)
        description = description.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&bull;', '•')
        description = ' '.join(description.split())
    
    if not description:
        description = "No description available."
    
    # Extract URL - try multiple sources
    url = None
    
    # First, try to find URL in job data
    url_candidates = [
        job_data.get("url"),
        job_data.get("job_url"),
        job_data.get("Url"),
        job_data.get("URL"),
        job_data.get("link"),
        job_data.get("Link"),
        job_data.get("application_url"),
        job_data.get("ApplicationUrl"),
        job_dict.get("url"),
        job_dict.get("job_url"),
    ]
    
    for candidate in url_candidates:
        if candidate:
            url_text = extract_text(candidate)
            if url_text and url_text.startswith("http"):
                url = url_text
                break
    
    # If still no URL, try to build a search URL that would find this job
    # This is more reliable than guessing the job URL structure
    if not url:
        # Build a search URL with job title and company to help users find the job
        job_title = safe_get_nested(job_data, "Title", "title", default="")
        company_name = safe_get_nested(company_data, "CompanyName", "company_name", default="")
        
        if job_title or company_name:
            # Create a search query
            search_query_parts = []
            if job_title:
                search_query_parts.append(job_title.replace(" ", "+"))
            if company_name:
                search_query_parts.append(company_name.replace(" ", "+"))
            
            if search_query_parts:
                search_query = "+".join(search_query_parts)
                # Use FindSGJobs jobs URL format: /jobs?keywords=...
                url = f"https://www.findsgjobs.com/jobs?keywords={search_query}"
        
        # Last resort: use company website if available (but note it's not the job page)
        if not url and "Website" in company_data:
            company_website = extract_text(company_data["Website"])
            if company_website and company_website.startswith("http"):
                url = company_website
    
    # Extract image URL from company Logo
    image_url = None
    if "Logo" in company_data:
        logo = company_data["Logo"]
        if isinstance(logo, dict):
            # Try different URL fields
            for url_field in ["src", "file_url", "uri", "url"]:
                if url_field in logo and logo[url_field]:
                    logo_path = logo[url_field]
                    # Build full URL if it's a relative path
                    if logo_path.startswith("http"):
                        image_url = logo_path
                    elif logo_path.startswith("files/"):
                        image_url = f"https://www.findsgjobs.com/{logo_path}"
                    else:
                        image_url = f"https://www.findsgjobs.com/files/{logo_path}"
                    break
    
    # If no logo, try FeaturedImage or other image fields
    if not image_url:
        featured_image = company_data.get("id__FeaturedImage")
        if featured_image and isinstance(featured_image, dict):
            for url_field in ["src", "file_url", "uri", "url"]:
                if url_field in featured_image and featured_image[url_field]:
                    img_path = featured_image[url_field]
                    if img_path.startswith("http"):
                        image_url = img_path
                    elif img_path.startswith("files/"):
                        image_url = f"https://www.findsgjobs.com/{img_path}"
                    break
    
    logger.debug(f"Normalized job - Title: '{title}', Company: '{company}', Location: '{location}'")
    
    return JobPosting(
        id=job_id if job_id else "",
        title=title if title else "Job Title Not Available",
        company=company if company else "Company Not Specified",
        location=location if location else "Location Not Specified",
        salary_text=salary_text,
        category=category if category else None,
        description=description,
        url=url,
        image_url=image_url,
    )

