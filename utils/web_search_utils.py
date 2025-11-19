"""Web search utility for finding current learning resources."""
from typing import List, Dict, Optional
from utils.logging_utils import get_logger

logger = get_logger(__name__)

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    DDGS = None


def search_learning_resources(skill: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search for current learning resources for a given skill using web search.
    
    Args:
        skill: The skill to search for learning resources
        max_results: Maximum number of results to return
        
    Returns:
        List of dictionaries with 'name', 'url', 'type', and 'description'
    """
    if not DDGS_AVAILABLE:
        logger.warning("duckduckgo_search not available. Install with: pip install duckduckgo-search")
        return []
    
    try:
        # Construct search query for learning resources
        search_query = f"{skill} online course certification training 2024"
        
        logger.info(f"Searching for learning resources: {search_query}")
        
        # Perform web search
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=max_results * 2))
        
        # Parse and filter results
        return parse_web_search_results(results, skill, max_results)
        
    except Exception as e:
        logger.warning(f"Web search failed for skill '{skill}': {str(e)}")
        return []


def parse_web_search_results(search_results: List[Dict], skill: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Parse web search results into structured learning resource format.
    
    Args:
        search_results: List of dictionaries containing web search results (from DDGS)
        skill: The skill these resources are for
        max_results: Maximum number of results to return
        
    Returns:
        List of dictionaries with 'name', 'url', 'type', and 'description'
    """
    resources = []
    seen_urls = set()
    
    # Parse each result (search_results is already a list from DDGS)
    for result in search_results[:max_results * 2]:  # Get more to filter duplicates
        # Extract fields from DDGS result format
        # DDGS returns dicts with keys: 'title', 'body', 'href'
        title = result.get("title", "")
        url = result.get("href", result.get("url", ""))
        snippet = result.get("body", result.get("snippet", result.get("description", "")))
        
        # Skip if URL already seen or invalid
        if not url or url in seen_urls:
            continue
        
        # Validate URL
        if not url.startswith(("http://", "https://")):
            continue
        
        seen_urls.add(url)
        
        # Determine resource type from URL/domain
        resource_type = "online_course"
        url_lower = url.lower()
        
        # Classify by domain
        if any(domain in url_lower for domain in ["coursera.org", "edx.org", "udemy.com", "udacity.com", "khanacademy.org", "pluralsight.com"]):
            resource_type = "online_course"
        elif any(domain in url_lower for domain in ["aws.amazon.com", "cloud.google.com", "microsoft.com/learn", "ibm.com", "oracle.com"]):
            resource_type = "certification"
        elif any(domain in url_lower for domain in ["generalassemb.ly", "lewagon.com", "flatironschool.com", "springboard.com"]):
            resource_type = "bootcamp"
        elif any(domain in url_lower for domain in [".edu", "/university", "/college", "mit.edu", "stanford.edu"]):
            resource_type = "university"
        elif any(domain in url_lower for domain in ["mooc.org", "futurelearn.com", "classcentral.com", "alison.com"]):
            resource_type = "mooc"
        elif "certification" in url_lower or "certificate" in url_lower:
            resource_type = "certification"
        elif "bootcamp" in url_lower:
            resource_type = "bootcamp"
        
        resources.append({
            "name": title or f"{skill} Learning Resource",
            "url": url,
            "type": resource_type,
            "description": snippet[:200] if snippet else "",  # Limit description length
        })
        
        if len(resources) >= max_results:
            break
    
    logger.info(f"Parsed {len(resources)} learning resources for skill: {skill}")
    return resources

