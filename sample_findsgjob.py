# pip install requests
import requests
from typing import Iterable, Literal, Optional, Dict, Any, List

FIND_SGJOBS_BASE_URL = "https://www.findsgjobs.com/apis/job/searchable"

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
    timeout: int = 10,
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

    response = requests.get(FIND_SGJOBS_BASE_URL, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_all_findsgjobs(
    max_pages: int = 5,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper to fetch multiple pages of jobs.

    kwargs are passed to `search_findsgjobs` (e.g., keywords=..., job_categories=[...]).
    """
    all_jobs: List[Dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        data = search_findsgjobs(page=page, **kwargs)

        # Adjust this depending on the actual response structure
        jobs = data.get("data") or data.get("jobs") or data
        if not jobs:
            break

        if isinstance(jobs, list):
            all_jobs.extend(jobs)
        else:
            break

    return all_jobs


# Optional mapping dicts for readability
EMPLOYMENT_TYPES = {
    "full_time": 76,
    "part_time": 977,
    "permanent": 978,
    "temporary": 979,
    "contract": 980,
    "internship": 981,
    "freelance": 982,
    "contract_to_perm": 983,
}

CURRENCIES = {
    "SGD": 1275916990,
    "MYR": 1275916991,
    "USD": 1275916992,
    "IND": 1275916993,
}

SALARY_INTERVALS = {
    "hour": 1895,
    "day": 1896,
    "week": 1897,
    "month": 1898,
    "annual": 1899,
}


if __name__ == "__main__":
    # 1) Simple: latest "data analyst" jobs
    print("=== Latest 'data analyst' jobs ===")
    jobs1 = search_findsgjobs(
        page=1,
        keywords="data analyst",
        sort_field="activation_date",
        sort_direction="desc",
    )
    print(jobs1)

    # 2) Full-time IT PMET jobs, Diploma and above, min 2 years exp
    print("\n=== Full-time IT PMET jobs (Diploma+, 2+ yrs exp) ===")
    it_jobs = fetch_all_findsgjobs(
        max_pages=3,
        keywords="software engineer",
        employment_types=[EMPLOYMENT_TYPES["full_time"]],
        job_categories=[1861],  # Information Technology
        min_education_levels=[869, 870, 871, 872, 873, 874, 875],  # Diploma and above
        min_years_experience=list(range(955, 975)),  # 2 years and above
        position="pmet",
        sort_field="activation_date",
        sort_direction="desc",
    )
    print(f"Total jobs fetched: {len(it_jobs)}")

    # 3) Filter by salary: SGD 3000–6000 / month
    print("\n=== SGD 3k–6k per month 'data' jobs ===")
    salary_jobs = search_findsgjobs(
        page=1,
        keywords="data",
        currency_id=CURRENCIES["SGD"],
        min_salary=3000,
        max_salary=6000,
        salary_interval_id=SALARY_INTERVALS["month"],
    )
    print(salary_jobs)
