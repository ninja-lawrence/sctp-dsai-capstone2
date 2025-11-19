"""Main Streamlit application for SCTP Job Search & Skill Gap Analyzer."""
import streamlit as st
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from config import (
    APP_TITLE,
    DEFAULT_KEYWORDS,
    EMPLOYMENT_TYPES,
    CURRENCIES,
    SALARY_INTERVALS,
    GEMINI_API_KEY,
    GEMINI_MODEL_NAME,
)
from services.llm_client import GeminiClient, list_available_models, get_gemini_rate_limit_status
from services.findsgjobs_client import fetch_all_findsgjobs, normalize_job, get_rate_limit_status
from services.resume_parser import parse_resume
from agents.junior_researchers import extract_profile_from_resume_text
from agents.schemas import UserProfile
from agents.pipeline import run_job_matching_pipeline, run_skill_gap_analysis_only
from agents.supervisor import rank_jobs_lightweight
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Page configuration
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "user_profile" not in st.session_state:
    st.session_state["user_profile"] = {
        "name": None,
        "headline": None,
        "summary": None,
        "skills": [],
        "experience": [],
        "education": [],
        "target_roles": [],
        "experience_level": None,
        "location": None,
        "salary_range_min": None,
        "salary_range_max": None,
        "salary_currency": "SGD",
    }

if "jobs_raw" not in st.session_state:
    st.session_state["jobs_raw"] = []

if "job_match_scores" not in st.session_state:
    st.session_state["job_match_scores"] = {}  # Maps job_id to match_score

if "ai_results" not in st.session_state:
    st.session_state["ai_results"] = None

if "llm_client" not in st.session_state:
    st.session_state["llm_client"] = None


# Track active tab to preserve it across reruns
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = 1  # Default to Profile tab (index 0)

# Store search keywords for URL construction
if "search_keywords" not in st.session_state:
    st.session_state["search_keywords"] = ""


def initialize_llm_client() -> Tuple[Optional[GeminiClient], str, str]:
    """
    Initialize and cache LLM client using config defaults.
    
    Returns:
        Tuple of (client, api_key, model_name) for use in UI
    """
    # Use API key and model name from config
    api_key = GEMINI_API_KEY
    model_name = GEMINI_MODEL_NAME
    
    # Check if we need to reinitialize the client
    need_reinit = False
    if st.session_state["llm_client"] is None:
        need_reinit = True
    else:
        # Check if API key or model name changed
        cached_client = st.session_state["llm_client"]
        if hasattr(cached_client, 'api_key'):
            if cached_client.api_key != api_key:
                need_reinit = True
        else:
            need_reinit = True
            
        if hasattr(cached_client, 'model_name'):
            if cached_client.model_name != model_name:
                need_reinit = True
        else:
            need_reinit = True
    
    if need_reinit:
        if not api_key:
            logger.warning("⚠️ Gemini API key not configured")
            return None, api_key, model_name
        
        try:
            client = GeminiClient(api_key=api_key, model_name=model_name)
            st.session_state["llm_client"] = client
            logger.info(f"✅ LLM client initialized with model: {model_name}")
            return client, api_key, model_name
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to initialize LLM: {error_msg}")
            return None, api_key, model_name
    
    return st.session_state["llm_client"], api_key, model_name


def main():
    """Main application."""
    st.title(APP_TITLE)
    st.markdown("---")
    
    # Initialize LLM client (using config defaults, not from sidebar)
    llm_client, api_key_input, model_name_input = initialize_llm_client()
    
    # Sidebar configuration
    with st.sidebar:
        # st.header("⚙️ Configuration")
        
        # Job Search Settings
        st.subheader("Job Search Settings")
        
        col_sidebar_keywords, col_sidebar_button = st.columns([3, 1])
        
        with col_sidebar_keywords:
            search_keywords = st.text_input(
                "Keywords",
                value=DEFAULT_KEYWORDS,
                help="Job search keywords",
                key="sidebar_search_keywords",
            )
        
        with col_sidebar_button:
            st.markdown("<br>", unsafe_allow_html=True)  # Align button with input
            sidebar_search_button = st.button("🔍", use_container_width=True, key="sidebar_search_button", help="Search jobs")
            if sidebar_search_button:
                st.session_state["sidebar_search_triggered"] = True
                st.session_state["sidebar_search_keywords_value"] = search_keywords
                st.session_state["switch_to_tab2"] = True
                st.rerun()  # Force rerun to trigger tab switch
        
        employment_type_options = list(EMPLOYMENT_TYPES.keys())
        selected_employment_types = st.multiselect(
            "Employment Types",
            options=employment_type_options,
            help="Filter by employment type",
        )
        
        min_salary = st.number_input(
            "Min Salary",
            min_value=0,
            value=0,
            step=1000,
            help="Minimum salary filter",
        )
        
        salary_interval_options = list(SALARY_INTERVALS.keys())
        salary_interval = st.selectbox(
            "Salary Interval",
            options=[""] + salary_interval_options,
            help="Salary interval",
        )
        
        # Rate Limit Status
        st.markdown("---")
        st.subheader("📊 API Rate Limit Status")
        
        # FindSGJobs Rate Limit
        rate_status = get_rate_limit_status()
        remaining = rate_status["remaining_requests"]
        total = rate_status["rate_limit"]
        
        st.markdown("**FindSGJobs API:**")
        if remaining > total * 0.5:
            st.success(f"✅ {remaining}/{total} requests remaining")
        elif remaining > total * 0.2:
            st.warning(f"⚠️ {remaining}/{total} requests remaining")
        else:
            st.error(f"🔴 {remaining}/{total} requests remaining")
        
        st.caption(f"Rate limit: {total} requests per {rate_status['window_seconds']} seconds (per IP)")
        
        st.info("💡 Tip: APIs automatically throttle requests to stay within limits.")
    
    # Switch to tab2 if sidebar search button was clicked
    switch_to_tab2 = st.session_state.get("switch_to_tab2", False)
    
    # Show prominent message if we need to switch tabs
    if switch_to_tab2:
        st.info("🔍 **Search initiated!** Please click on the **'Job Search'** tab above to see your results.", icon="ℹ️")
    
    # Main content tabs
    # Use a unique key to preserve tab state
    tab1, tab2, tab3, tab4 = st.tabs([
        "👤 Profile",
        "🔍 Job Search",
        "📊 Skill Gap Analysis",
        "🐛 Debug / Raw Data",
    ])
    
    # Inject script to switch tabs if needed - must be after tabs are created
    if switch_to_tab2:
        st.session_state["switch_to_tab2"] = False
        # Use a more aggressive JavaScript approach with event dispatching
        st.markdown(
            """
            <script>
            (function() {
                function attemptTabSwitch() {
                    // Method 1: Try to find and click tab by text content
                    var allButtons = Array.from(document.querySelectorAll('button'));
                    var jobSearchButton = null;
                    
                    for (var i = 0; i < allButtons.length; i++) {
                        var btn = allButtons[i];
                        var text = (btn.textContent || btn.innerText || '').trim();
                        if (text.includes('Job Search') || text.includes('🔍 Job Search')) {
                            jobSearchButton = btn;
                            break;
                        }
                    }
                    
                    if (jobSearchButton) {
                        // Try multiple click methods
                        try {
                            jobSearchButton.click();
                        } catch(e) {
                            // Try dispatching a mouse event
                            var event = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            jobSearchButton.dispatchEvent(event);
                        }
                        return true;
                    }
                    
                    // Method 2: Find by role="tab" and click second one
                    var tabButtons = document.querySelectorAll('button[role="tab"]');
                    if (tabButtons.length > 1) {
                        try {
                            tabButtons[1].click();
                            return true;
                        } catch(e) {
                            var event = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            tabButtons[1].dispatchEvent(event);
                            return true;
                        }
                    }
                    
                    // Method 3: Find by data-baseweb
                    var basewebTabs = document.querySelectorAll('[data-baseweb="tab"]');
                    if (basewebTabs.length > 1) {
                        try {
                            basewebTabs[1].click();
                            return true;
                        } catch(e) {
                            var event = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            basewebTabs[1].dispatchEvent(event);
                            return true;
                        }
                    }
                    
                    return false;
                }
                
                // Try immediately and with delays
                if (!attemptTabSwitch()) {
                    setTimeout(attemptTabSwitch, 50);
                    setTimeout(attemptTabSwitch, 200);
                    setTimeout(attemptTabSwitch, 500);
                    setTimeout(attemptTabSwitch, 1000);
                }
            })();
            </script>
            """,
            unsafe_allow_html=True
        )
    
    # Note: Streamlit tabs don't have a direct way to programmatically set active tab
    # But we can track which tab content is being rendered
    
    # Tab 1: Profile
    with tab1:
        st.header("User Profile")
        
        # Resume Upload Section
        st.subheader("📄 Upload Resume")
        uploaded_file = st.file_uploader(
            "Upload your resume (PDF, DOCX, or TXT)",
            type=["pdf", "docx", "txt"],
            help="Upload your resume to automatically extract profile information",
        )
        
        if uploaded_file is not None:
            if st.button("Parse Resume"):
                with st.spinner("Parsing resume..."):
                    try:
                        file_content = uploaded_file.read()
                        resume_text = parse_resume(file_content, uploaded_file.name)
                        
                        if llm_client:
                            profile = extract_profile_from_resume_text(resume_text, llm_client)
                            st.session_state["user_profile"] = profile
                            st.success("✅ Resume parsed successfully!")
                            st.json(profile)
                        else:
                            st.error("❌ LLM client not initialized. Please configure API key in sidebar.")
                    except Exception as e:
                        st.error(f"❌ Error parsing resume: {str(e)}")
                        logger.error(f"Resume parsing error: {str(e)}")
        
        st.markdown("---")
        
        # Manual Profile Editing
        st.subheader("✏️ Manual Profile Editing")
        
        profile = st.session_state["user_profile"]
        
        # Basic Information
        st.markdown("#### Basic Information")
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Name", value=profile.get("name") or "")
            headline = st.text_input("Headline", value=profile.get("headline") or "")
            summary = st.text_area("Summary", value=profile.get("summary") or "", height=100)
        
        with col2:
            # Ensure skills and target_roles are lists (handle None case)
            skills_list = profile.get("skills") or []
            if not isinstance(skills_list, list):
                skills_list = []
            
            target_roles_list = profile.get("target_roles") or []
            if not isinstance(target_roles_list, list):
                target_roles_list = []
            
            skills_text = st.text_area(
                "Skills (comma-separated)",
                value=", ".join(skills_list),
                help="Enter skills separated by commas",
            )
            target_roles_text = st.text_area(
                "Target Roles (comma-separated)",
                value=", ".join(target_roles_list),
                help="Enter target job roles separated by commas",
            )
        
        st.markdown("---")
        st.markdown("#### Job Preferences")
        
        col3, col4 = st.columns(2)
        
        with col3:
            experience_level_options = ["", "Entry Level", "Junior", "Mid-Level", "Senior", "Lead", "Executive"]
            experience_level = st.selectbox(
                "Experience Level",
                options=experience_level_options,
                index=experience_level_options.index(profile.get("experience_level", "")) if profile.get("experience_level") in experience_level_options else 0,
                help="Your current experience level"
            )
            
            location = st.text_input(
                "Preferred Location",
                value=profile.get("location") or "",
                help="Preferred work location (e.g., Singapore, Remote, etc.)",
                placeholder="e.g., Singapore, Remote, Central Singapore"
            )
        
        with col4:
            salary_currency_options = ["SGD", "USD", "MYR", "IND"]
            salary_currency = st.selectbox(
                "Salary Currency",
                options=salary_currency_options,
                index=salary_currency_options.index(profile.get("salary_currency", "SGD")) if profile.get("salary_currency") in salary_currency_options else 0,
                help="Currency for salary expectations"
            )
            
            col_sal_min, col_sal_max = st.columns(2)
            with col_sal_min:
                salary_range_min = st.number_input(
                    "Min Salary",
                    min_value=0,
                    value=profile.get("salary_range_min") or 0,
                    step=1000,
                    help="Minimum expected salary"
                )
            with col_sal_max:
                salary_range_max = st.number_input(
                    "Max Salary",
                    min_value=0,
                    value=profile.get("salary_range_max") or 0,
                    step=1000,
                    help="Maximum expected salary (0 = no limit)"
                )
        
        if st.button("💾 Save Profile"):
            st.session_state["user_profile"] = {
                "name": name if name else None,
                "headline": headline if headline else None,
                "summary": summary if summary else None,
                "skills": [s.strip() for s in skills_text.split(",") if s.strip()],
                "experience": profile.get("experience", []),
                "education": profile.get("education", []),
                "target_roles": [r.strip() for r in target_roles_text.split(",") if r.strip()],
                "experience_level": experience_level if experience_level else None,
                "location": location if location else None,
                "salary_range_min": salary_range_min if salary_range_min > 0 else None,
                "salary_range_max": salary_range_max if salary_range_max > 0 else None,
                "salary_currency": salary_currency,
            }
            st.success("✅ Profile saved!")
    
    # Tab 2: Job Search & Recommendations
    with tab2:
        st.header("Job Search")
        
        # Step 1: Job Search
        st.subheader("Step 1: Search Jobs")
        
        col_search, col_button = st.columns([4, 1])
        
        with col_search:
            keywords_input = st.text_input(
                "Search Keywords",
                value=search_keywords,
                key="search_keywords_input",
            )
        
        with col_button:
            st.markdown("<br>", unsafe_allow_html=True)  # Align button with input
            search_button = st.button("🔍 Fetch Jobs from FindSGJobs", use_container_width=True)
        
        # Check if sidebar search button was clicked
        sidebar_search_triggered = st.session_state.get("sidebar_search_triggered", False)
        if sidebar_search_triggered:
            # Use sidebar keywords if sidebar button was clicked
            keywords_input = st.session_state.get("sidebar_search_keywords_value", search_keywords)
        
        if search_button or sidebar_search_triggered:
            # Reset sidebar trigger flag after using it
            if sidebar_search_triggered:
                st.session_state["sidebar_search_triggered"] = False
            # Validate keywords
            if not keywords_input or not keywords_input.strip():
                st.error("❌ Please enter keywords to search for jobs.")
                st.info("💡 Keywords cannot be empty. Enter job titles, skills, or company names.")
            else:
                with st.spinner("Fetching jobs... (Rate limited to 60 requests/minute)"):
                    try:
                        keywords = keywords_input.strip()
                        kwargs = {"keywords": keywords, "max_pages": 1}
                        
                        if selected_employment_types:
                            kwargs["employment_types"] = [
                                EMPLOYMENT_TYPES[et] for et in selected_employment_types
                            ]
                        
                        if min_salary > 0:
                            kwargs["min_salary"] = min_salary
                            kwargs["currency_id"] = CURRENCIES.get("SGD")
                        
                        if salary_interval:
                            kwargs["salary_interval_id"] = SALARY_INTERVALS.get(salary_interval)
                        
                        jobs = fetch_all_findsgjobs(**kwargs)
                        st.session_state["jobs_raw"] = jobs
                        st.session_state["search_keywords"] = keywords  # Store keywords for URL construction
                        
                        if len(jobs) == 0:
                            st.warning(
                                "⚠️ No jobs found. This could mean:\n"
                                "- The API returned an empty result\n"
                                "- The response structure is different than expected\n"
                                "- Check the Debug tab to see the raw API response"
                            )
                        else:
                            st.success(f"✅ Fetched {len(jobs)} jobs!")
                            
                            # Run job matching to sort by relevance
                            user_profile = st.session_state["user_profile"]
                            if llm_client and user_profile.get("skills"):
                                with st.spinner("🔍 Ranking jobs by relevance..."):
                                    try:
                                        # Normalize jobs for ranking
                                        normalized_jobs = []
                                        raw_to_normalized = {}  # Map raw job index to normalized job
                                        for idx, raw_job in enumerate(jobs):
                                            try:
                                                normalized_job = normalize_job(raw_job)
                                                normalized_jobs.append(normalized_job)
                                                raw_to_normalized[idx] = normalized_job
                                            except Exception as e:
                                                logger.warning(f"Failed to normalize job for ranking: {str(e)}")
                                                continue
                                        
                                        if normalized_jobs:
                                            # Get match scores
                                            match_scores = rank_jobs_lightweight(
                                                profile=user_profile,
                                                jobs=normalized_jobs,
                                                llm=llm_client
                                            )
                                            
                                            # Store match scores in session state
                                            st.session_state["job_match_scores"] = match_scores
                                            
                                            # Sort jobs_raw by match score (highest first)
                                            def get_match_score(idx_and_job):
                                                idx, raw_job = idx_and_job
                                                if idx in raw_to_normalized:
                                                    job_id = raw_to_normalized[idx]["id"]
                                                    return match_scores.get(job_id, 0.0)
                                                return 0.0
                                            
                                            # Create list of (index, job) tuples for sorting
                                            indexed_jobs = list(enumerate(jobs))
                                            indexed_jobs_sorted = sorted(indexed_jobs, key=get_match_score, reverse=True)
                                            jobs_sorted = [job for _, job in indexed_jobs_sorted]
                                            
                                            st.session_state["jobs_raw"] = jobs_sorted
                                            st.info(f"✨ Jobs sorted by relevance (most relevant first)")
                                    except Exception as e:
                                        logger.warning(f"Job ranking failed: {str(e)}")
                                        # Continue with unsorted jobs
                                        pass
                        
                        # Show updated rate limit status
                        new_rate_status = get_rate_limit_status()
                        st.caption(
                            f"Remaining API requests: {new_rate_status['remaining_requests']}/"
                            f"{new_rate_status['rate_limit']}"
                        )
                    except Exception as e:
                        error_msg = str(e)
                        if "429" in error_msg or "Rate limit" in error_msg:
                            st.error(
                                f"❌ Rate limit exceeded! Please wait a minute before trying again. "
                                f"Error: {error_msg}"
                            )
                        else:
                            st.error(f"❌ Error fetching jobs: {error_msg}")
                            st.info("💡 Check the Debug tab for more details about the API response.")
                        logger.error(f"Job fetch error: {error_msg}")
        
        # Step 2: Display Jobs
        if st.session_state["jobs_raw"]:
            max_results = 5
            total_displayed = min(len(st.session_state["jobs_raw"]), max_results)
            st.subheader(f"Step 2: Job Listings ({total_displayed} jobs)")
            
            # Add global CSS styles
            st.markdown(
                """
                <style>
                .job-card-container {
                    border: 1px solid #e1e5e9;
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 20px;
                    background-color: #ffffff;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                    transition: all 0.3s ease;
                }
                .job-card-container:hover {
                    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                    transform: translateY(-2px);
                }
                .job-row-container {
                    border: 1px solid #e1e5e9;
                    border-radius: 8px;
                    padding: 16px;
                    margin-bottom: 12px;
                    background-color: #ffffff;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                }
                .job-title {
                    font-size: 1.2em;
                    font-weight: 600;
                    color: #1a1a1a;
                    margin-bottom: 8px;
                }
                .job-company {
                    font-size: 1em;
                    color: #4a5568;
                    font-weight: 500;
                }
                .job-meta {
                    font-size: 0.9em;
                    color: #718096;
                    margin-top: 8px;
                }
                </style>
                """,
                unsafe_allow_html=True
            )
            
            # Display mode selector
            display_mode = st.radio(
                "Display Mode",
                ["Table View", "Card View"],
                horizontal=True,
                key="job_display_mode",
                index=0  # Default to Card View
            )
            
            # Limit to max 5 results
            all_jobs = st.session_state["jobs_raw"][:max_results]
            total_jobs = len(all_jobs)
            
            # Display all jobs (no pagination)
            jobs_to_display = all_jobs
                        
            if display_mode == "Table View":
                # Table View - Clean list format
                import pandas as pd
                
                for idx, job_raw in enumerate(jobs_to_display):
                    try:
                        job = normalize_job(job_raw)
                        
                        # Create a clean row
                        with st.container():
                            col_img, col_info, col_action = st.columns([0.8, 4, 1.2])
                            
                            with col_img:
                                company_name = str(job.get('company', 'Unknown')) if job.get('company') else 'Unknown'
                                
                                if job.get("image_url"):
                                    try:
                                        st.image(
                                            job["image_url"], 
                                            width=80
                                        )
                                    except:
                                        st.markdown(
                                            f"<div style='text-align: center; padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;'>"
                                            f"<div style='font-size: 24px;'>{company_name[0].upper() if company_name else '?'}</div></div>",
                                            unsafe_allow_html=True
                                        )
                                else:
                                    st.markdown(
                                        f"<div style='text-align: center; padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;'>"
                                        f"<div style='font-size: 24px;'>{company_name[0].upper() if company_name else '?'}</div></div>",
                                        unsafe_allow_html=True
                                    )
                            
                            with col_info:
                                job_title = str(job.get('title', 'N/A')) if job.get('title') else 'N/A'
                                job_company = str(job.get('company', 'Unknown')) if job.get('company') else 'Unknown'
                                job_location = str(job.get('location', 'N/A')) if job.get('location') else 'N/A'
                                job_id = job.get('id', '')
                                
                                # Get match percentage if available
                                match_scores = st.session_state.get("job_match_scores", {})
                                match_badge = ""
                                if job_id in match_scores:
                                    match_score = match_scores[job_id]
                                    match_percentage = match_score * 100
                                    # Color code based on match score
                                    if match_percentage >= 70:
                                        color = "#28a745"  # Green
                                    elif match_percentage >= 40:
                                        color = "#ffc107"  # Yellow
                                    else:
                                        color = "#dc3545"  # Red
                                    match_badge = f' <span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; font-weight: bold;">{match_percentage:.0f}% Match</span>'
                                
                                st.markdown(f"**{job_title}**{match_badge}", unsafe_allow_html=True)
                                st.markdown(f"*{job_company}* • 📍 {job_location}")
                                
                                # Meta info
                                meta_parts = []
                                if job.get("salary_text"):
                                    meta_parts.append(f"💰 {job['salary_text']}")
                                if job.get("category"):
                                    meta_parts.append(f"🏷️ {job['category']}")
                                
                                if meta_parts:
                                    st.caption(" • ".join(meta_parts))
                                
                                # Description preview
                                job_description = str(job.get('description', '')) if job.get('description') else ''
                                desc_preview = (job_description[:120] + "...") if len(job_description) > 120 else job_description
                                if desc_preview:
                                    st.caption(desc_preview)
                                
                                # Details expander under description
                                with st.expander("Details"):
                                    st.write("**Full Description:**")
                                    st.write(job_description if job_description else "No description available")
                                    # Use search keywords URL
                                    search_keywords_expander = st.session_state.get("search_keywords", "")
                                    if search_keywords_expander:
                                        keywords_encoded = search_keywords_expander.replace(" ", "+")
                                        job_url_expander = f"https://www.findsgjobs.com/jobs?keywords={keywords_encoded}"
                                        st.markdown(f'<a href="{job_url_expander}" target="_blank">View Full Posting →</a>', unsafe_allow_html=True)
                                    elif job.get("url"):
                                        st.markdown(f'<a href="{job["url"]}" target="_blank">View Full Posting →</a>', unsafe_allow_html=True)
                            
                            with col_action:
                                st.markdown("<br>", unsafe_allow_html=True)
                                # Construct URL using search keywords
                                search_keywords = st.session_state.get("search_keywords", "")
                                if search_keywords:
                                    # URL encode the keywords (replace spaces with +)
                                    keywords_encoded = search_keywords.replace(" ", "+")
                                    job_url = f"https://www.findsgjobs.com/jobs?keywords={keywords_encoded}"
                                    st.markdown(
                                        f'<a href="{job_url}" target="_blank" style="text-decoration: none;">'
                                        f'<button style="background-color: #1f77b4; color: white; border: none; '
                                        f'padding: 8px 16px; border-radius: 4px; cursor: pointer; width: 100%;">'
                                        f'View Job</button></a>',
                                        unsafe_allow_html=True
                                    )
                                elif job.get("url"):
                                    st.markdown(
                                        f'<a href="{job["url"]}" target="_blank" style="text-decoration: none;">'
                                        f'<button style="background-color: #1f77b4; color: white; border: none; '
                                        f'padding: 8px 16px; border-radius: 4px; cursor: pointer; width: 100%;">'
                                        f'View Job</button></a>',
                                        unsafe_allow_html=True
                                    )
                            
                            if idx < len(jobs_to_display) - 1:
                                st.divider()
                                
                    except Exception as e:
                        logger.warning(f"Error displaying job {idx}: {str(e)}")
                        continue
            else:
                # Card View - Clean grid layout
                jobs_per_row = 3
                for i in range(0, len(jobs_to_display), jobs_per_row):
                    cols = st.columns(jobs_per_row, gap="medium")
                    for j, col in enumerate(cols):
                        idx = i + j
                        if idx < len(jobs_to_display):
                            try:
                                job_raw = jobs_to_display[idx]
                                job = normalize_job(job_raw)
                                
                                with col:
                                    # Card container with border
                                    with st.container():
                                        # Image/Logo section
                                        if job.get("image_url"):
                                            try:
                                                st.image(
                                                    job["image_url"], 
                                                    width=120,
                                                    caption=str(job.get('company', ''))[:30]
                                                )
                                            except:
                                                company_name = str(job.get('company', 'Unknown')) if job.get('company') else 'Unknown'
                                                st.markdown(
                                                    f"<div style='text-align: center; padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white; margin-bottom: 15px;'>"
                                                    f"<div style='font-size: 24px; font-weight: bold;'>{company_name[0].upper() if company_name else '?'}</div>"
                                                    f"<div style='font-size: 12px; margin-top: 5px;'>{company_name[:20]}</div></div>",
                                                    unsafe_allow_html=True
                                                )
                                        else:
                                            company_name = str(job.get('company', 'Unknown')) if job.get('company') else 'Unknown'
                                            st.markdown(
                                                f"<div style='text-align: center; padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white; margin-bottom: 15px;'>"
                                                f"<div style='font-size: 24px; font-weight: bold;'>{company_name[0].upper() if company_name else '?'}</div>"
                                                f"<div style='font-size: 12px; margin-top: 5px;'>{company_name[:20]}</div></div>",
                                                unsafe_allow_html=True
                                            )
                                        
                                        # Title
                                        job_title = str(job.get('title', 'N/A')) if job.get('title') else 'N/A'
                                        job_id = job.get('id', '')
                                        
                                        # Get match percentage if available
                                        match_scores = st.session_state.get("job_match_scores", {})
                                        match_badge = ""
                                        if job_id in match_scores:
                                            match_score = match_scores[job_id]
                                            match_percentage = match_score * 100
                                            # Color code based on match score
                                            if match_percentage >= 70:
                                                color = "#28a745"  # Green
                                            elif match_percentage >= 40:
                                                color = "#ffc107"  # Yellow
                                            else:
                                                color = "#dc3545"  # Red
                                            match_badge = f' <span style="background-color: {color}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.9em; font-weight: bold;">{match_percentage:.0f}% Match</span>'
                                        
                                        st.markdown(f"### {job_title}{match_badge}", unsafe_allow_html=True)
                                        
                                        # Company and location
                                        job_company = str(job.get('company', 'Unknown')) if job.get('company') else 'Unknown'
                                        job_location = str(job.get('location', 'N/A')) if job.get('location') else 'N/A'
                                        st.markdown(f"**{job_company}**")
                                        st.caption(f"📍 {job_location}")
                                        
                                        # Salary and category
                                        if job.get("salary_text"):
                                            st.markdown(f"💰 **{job['salary_text']}**")
                                        if job.get("category"):
                                            st.caption(f"🏷️ {job['category']}")
                                        
                                        st.divider()
                                        
                                        # Description preview
                                        job_description = str(job.get('description', '')) if job.get('description') else ''
                                        desc_preview = (job_description[:120] + "...") if len(job_description) > 120 else job_description
                                        if desc_preview:
                                            st.caption(desc_preview)
                                        
                                        # Action buttons - use search keywords URL
                                        search_keywords_card = st.session_state.get("search_keywords", "")
                                        if search_keywords_card:
                                            keywords_encoded = search_keywords_card.replace(" ", "+")
                                            job_url_card = f"https://www.findsgjobs.com/jobs?keywords={keywords_encoded}"
                                            st.markdown(
                                                f'<a href="{job_url_card}" target="_blank" style="text-decoration: none;">'
                                                f'<button style="background-color: #1f77b4; color: white; border: none; '
                                                f'padding: 10px 20px; border-radius: 6px; cursor: pointer; width: 100%; '
                                                f'font-size: 14px;">🔗 View Job</button></a>',
                                                unsafe_allow_html=True
                                            )
                                        elif job.get("url"):
                                            st.markdown(
                                                f'<a href="{job["url"]}" target="_blank" style="text-decoration: none;">'
                                                f'<button style="background-color: #1f77b4; color: white; border: none; '
                                                f'padding: 10px 20px; border-radius: 6px; cursor: pointer; width: 100%; '
                                                f'font-size: 14px;">🔗 View Job</button></a>',
                                                unsafe_allow_html=True
                                            )
                                        
                                        with st.expander("📄 Full Details"):
                                            st.write("**Description:**")
                                            st.write(job_description if job_description else "No description available")
                                            # Use search keywords URL
                                            search_keywords_details = st.session_state.get("search_keywords", "")
                                            if search_keywords_details:
                                                keywords_encoded = search_keywords_details.replace(" ", "+")
                                                job_url_details = f"https://www.findsgjobs.com/jobs?keywords={keywords_encoded}"
                                                st.markdown(f'<a href="{job_url_details}" target="_blank">View Full Posting →</a>', unsafe_allow_html=True)
                                            elif job.get("url"):
                                                st.markdown(f'<a href="{job["url"]}" target="_blank">View Full Posting →</a>', unsafe_allow_html=True)
                                    
                            except Exception as e:
                                logger.warning(f"Error displaying job {idx}: {str(e)}")
                                continue
    
    # Tab 3: Skill Gap Analysis
    with tab3:
        st.header("Skill Gap Analysis")
        
        # Step 3: Run Skill Gap Analysis
        # st.subheader("Run Skill Gap Analysis")
        
        if not llm_client:
            st.warning("⚠️ Please configure Gemini API key in the sidebar first.")
        elif not st.session_state["user_profile"].get("skills"):
            st.warning("⚠️ Please set up your profile with skills first.")
        elif not st.session_state["jobs_raw"]:
            st.warning("⚠️ Please fetch jobs first in the 'Job Search' tab.")
        else:
            # Check if model name might be invalid
            model_name_display = model_name_input or GEMINI_MODEL_NAME
            if "gemini-1.5-pro" in model_name_display.lower():
                st.warning(
                    "⚠️ **Model Warning**: `gemini-1.5-pro` may not be available. "
                    "Try `gemini-1.5-flash` instead. Click '🔄 Reset LLM Client' after changing the model name."
                )
            
            # Create job selection dropdown
            st.markdown("**Select a job to analyze:**")
            
            # Prepare job options for selectbox
            job_options = []
            match_scores = st.session_state.get("job_match_scores", {})
            for idx, job_raw in enumerate(st.session_state["jobs_raw"]):
                try:
                    job = normalize_job(job_raw)
                    job_title = str(job.get('title', 'N/A')) if job.get('title') else 'N/A'
                    job_company = str(job.get('company', 'Unknown')) if job.get('company') else 'Unknown'
                    job_location = str(job.get('location', '')) if job.get('location') else ''
                    job_id = job.get('id', '')
                    
                    # Get match percentage if available
                    match_percentage = ""
                    if job_id in match_scores:
                        match_score = match_scores[job_id]
                        match_percentage = f" - {match_score*100:.0f}% Match"
                    
                    # Format option text
                    option_text = f"{job_title} - {job_company}"
                    if job_location:
                        option_text += f" ({job_location})"
                    if match_percentage:
                        option_text += match_percentage
                    
                    job_options.append((option_text, idx))
                except Exception as e:
                    logger.warning(f"Error formatting job {idx} for dropdown: {str(e)}")
                    job_options.append((f"Job #{idx+1} (Error loading details)", idx))
            
            # Create selectbox
            if job_options:
                selected_option = st.selectbox(
                    "Choose a job listing:",
                    options=[opt[0] for opt in job_options],
                    index=0,
                    help="Select one job to run the skill gap analysis",
                    key="selected_job_index"
                )
                
                # Find the selected job index
                selected_idx = next((idx for opt_text, idx in job_options if opt_text == selected_option), 0)
                selected_job = [st.session_state["jobs_raw"][selected_idx]]
                
                # Show selected job preview
                try:
                    preview_job = normalize_job(selected_job[0])
                    preview_text = f"📋 **Selected:** {preview_job.get('title', 'N/A')} at {preview_job.get('company', 'Unknown')}"
                    preview_job_id = preview_job.get('id', '')
                    match_scores = st.session_state.get("job_match_scores", {})
                    if preview_job_id in match_scores:
                        match_score = match_scores[preview_job_id]
                        preview_text += f" - **{match_score*100:.0f}% Match**"
                    st.info(preview_text)
                except:
                    st.info(f"📋 **Selected:** Job #{selected_idx + 1}")
            else:
                st.error("❌ No jobs available for selection.")
                selected_job = []
            
            if st.button("🚀 Run Skill Gap Analysis"):
                if not selected_job:
                    st.error("❌ Please select a job first.")
                else:
                    with st.spinner("Running skill gap analysis... This may take a few minutes."):
                        try:
                            results = run_skill_gap_analysis_only(
                                llm=llm_client,
                                profile=st.session_state["user_profile"],
                                raw_jobs=selected_job,
                            )
                            st.session_state["ai_results"] = results
                            st.success("✅ Skill gap analysis complete!")
                        except Exception as e:
                            error_msg = str(e)
                            # Check if it's a 404 model error
                            if "404" in error_msg and ("model" in error_msg.lower() or "not found" in error_msg.lower()):
                                st.error("❌ **Model Not Found Error**")
                                st.error(f"Error: {error_msg}")
                                st.info(
                                    "💡 **Solution**:\n"
                                    "1. Change the 'Model Name' in the sidebar to `gemini-1.5-flash`\n"
                                    "2. Click '🔄 Reset LLM Client' button\n"
                                    "3. Or click '📋 List Available Models' to see what models your API key supports"
                                )
                                # Auto-reset the client to force reinitialization
                                st.session_state["llm_client"] = None
                                st.rerun()
                            # Check if it's a rate limit error
                            elif "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                                st.error("❌ **Gemini API Rate Limit Exceeded**")
                                st.error(f"Error: {error_msg}")
                                st.warning(
                                    "⚠️ **Free Tier Limit**: 10 requests per minute per model\n\n"
                                    "**What happened**:\n"
                                    "- The system automatically retried with delays\n"
                                    "- But still hit the rate limit\n\n"
                                    "**Solutions**:\n"
                                    "1. **Wait 1 minute** and try again (quota resets every minute)\n"
                                    "2. **Upgrade your API plan** for higher limits\n"
                                    "3. Check your usage: https://ai.dev/usage?tab=rate-limit"
                                )
                                # Show partial results if available
                                if st.session_state.get("ai_results"):
                                    st.info("ℹ️ Partial results are available below (some jobs may be missing due to rate limits)")
                            else:
                                st.error(f"❌ Error running skill gap analysis: {error_msg}")
                            logger.error(f"Skill gap analysis error: {error_msg}")
        
        st.markdown("---")
        
        # Display Results
        if not st.session_state["ai_results"]:
            st.info("👆 Please run skill gap analysis above to see results.")
        else:
            results = st.session_state["ai_results"]
            gaps = results.get("skill_gaps", [])
            
            if gaps:
                st.subheader("Skill Gap Analysis by Job")
                
                for gap in gaps:
                    with st.expander(f"📊 {gap['job_title']}"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("**✅ Matched Skills:**")
                            matched_skills = gap.get("matched_skills") or []
                            if matched_skills and isinstance(matched_skills, list):
                                st.write(", ".join(matched_skills))
                            else:
                                st.write("None")
                            
                            st.write("**❌ Missing Required Skills:**")
                            missing_skills_writeup = gap.get("missing_required_skills_writeup", "")
                            if missing_skills_writeup:
                                st.write(missing_skills_writeup)
                            else:
                                # Fallback to list if writeup not available
                                missing_skills = gap.get("missing_required_skills") or []
                                if missing_skills and isinstance(missing_skills, list):
                                    st.write(", ".join(missing_skills))
                                else:
                                    st.write("None")
                        
                        with col2:
                            st.write("**⭐ Nice-to-Have Skills:**")
                            nice_to_have = gap.get("nice_to_have_skills") or []
                            if nice_to_have and isinstance(nice_to_have, list):
                                st.write(", ".join(nice_to_have))
                            else:
                                st.write("None")
                            
                            st.write("**📚 Suggested Learning Path:**")
                            if gap.get("suggested_learning_path"):
                                learning_path = gap["suggested_learning_path"]
                                if isinstance(learning_path, list):
                                    for i, step in enumerate(learning_path, 1):
                                        # Remove leading numbers if step already has them (e.g., "1. Step" -> "Step")
                                        step_clean = str(step).strip()
                                        # Check if step starts with a number pattern like "1. " or "1)"
                                        step_clean = re.sub(r'^\d+[\.\)]\s*', '', step_clean)
                                        st.write(f"{i}. {step_clean}")
                                else:
                                    st.write("No suggestions available")
                            else:
                                st.write("No suggestions available")
                        
                        # Learning Resources Section
                        st.markdown("---")
                        st.write("**🎓 Learning Resources & Certifications:**")
                        learning_resources = gap.get("learning_resources", [])
                        
                        if learning_resources:
                            # Group resources by skill
                            resources_by_skill = {}
                            for resource in learning_resources:
                                skill = resource.get("skill", "General")
                                if skill not in resources_by_skill:
                                    resources_by_skill[skill] = []
                                resources_by_skill[skill].append(resource)
                            
                            # Display resources grouped by skill
                            for skill, resources in resources_by_skill.items():
                                st.markdown(f"**For: {skill}**")
                                for resource in resources:
                                    resource_name = resource.get("name", "Unknown")
                                    resource_url = resource.get("url", "#")
                                    resource_type = resource.get("type", "online_course")
                                    
                                    # Validate URL before displaying
                                    if not resource_url or resource_url == "#" or not resource_url.startswith(('http://', 'https://')):
                                        # Invalid URL - display as text only
                                        icon = "📖"
                                        st.markdown(
                                            f'{icon} **{resource_name}** '
                                            f'<span style="color: #6c757d; font-size: 0.9em;">({resource_type.replace("_", " ").title()}) - <span style="color: #dc3545;">Invalid URL</span></span>',
                                            unsafe_allow_html=True
                                        )
                                        continue
                                    
                                    # Icon based on type
                                    type_icons = {
                                        "university": "🏛️",
                                        "online_course": "💻",
                                        "certification": "📜",
                                        "bootcamp": "🚀",
                                        "training_program": "📚",
                                        "mooc": "🌐",
                                    }
                                    icon = type_icons.get(resource_type, "📖")
                                    
                                    # Escape URL for HTML safety
                                    escaped_url = resource_url.replace('"', '&quot;').replace("'", "&#x27;")
                                    
                                    # Display as clickable link
                                    st.markdown(
                                        f'{icon} <a href="{escaped_url}" target="_blank" rel="noopener noreferrer" style="text-decoration: none; color: #1f77b4; font-weight: 500;">{resource_name}</a> '
                                        f'<span style="color: #6c757d; font-size: 0.9em;">({resource_type.replace("_", " ").title()})</span>',
                                        unsafe_allow_html=True
                                    )
                        else:
                            st.info("No specific learning resources available. Check the suggested learning path above for general guidance.")
                
                # Overall Roadmap
                roadmap = results.get("upskilling_roadmap", [])
                if roadmap:
                    st.subheader("🎯 Overall Upskilling Roadmap")
                    if isinstance(roadmap, list):
                        for i, step in enumerate(roadmap, 1):
                            # Remove leading numbers if step already has them (e.g., "1. Step" -> "Step")
                            step_clean = str(step).strip()
                            # Check if step starts with a number pattern like "1. " or "1)"
                            step_clean = re.sub(r'^\d+[\.\)]\s*', '', step_clean)
                            st.write(f"{i}. {step_clean}")
                    else:
                        st.write("No roadmap available")
                
                # Warnings
                warnings = results.get("warnings", [])
                if warnings:
                    st.subheader("⚠️ Warnings")
                    for warning in warnings:
                        st.warning(warning)
            else:
                st.info("No skill gap analysis available.")
    
    # Tab 4: Debug
    with tab4:
        st.header("Debug / Raw Data")
        
        st.subheader("User Profile (JSON)")
        st.json(st.session_state["user_profile"])
        
        st.subheader(f"Raw Jobs ({len(st.session_state['jobs_raw'])} jobs)")
        if st.session_state["jobs_raw"]:
            st.json(st.session_state["jobs_raw"][:5])  # Show first 5
            
            # Show structure analysis
            if st.session_state["jobs_raw"]:
                st.markdown("---")
                st.subheader("Job Structure Analysis")
                sample_job = st.session_state["jobs_raw"][0]
                
                st.write("**Sample job keys:**")
                if isinstance(sample_job, dict):
                    st.code(list(sample_job.keys()))
                    
                    # Show normalized version for comparison
                    st.write("**Normalized job (what the app sees):**")
                    try:
                        normalized = normalize_job(sample_job)
                        st.json({
                            "id": normalized.get("id"),
                            "title": normalized.get("title"),
                            "company": normalized.get("company"),
                            "location": normalized.get("location"),
                            "salary_text": normalized.get("salary_text"),
                            "category": normalized.get("category"),
                            "description_preview": normalized.get("description", "")[:100] + "..." if len(normalized.get("description", "")) > 100 else normalized.get("description", ""),
                        })
                    except Exception as e:
                        st.error(f"Error normalizing: {str(e)}")
                    
                    # Show field mapping
                    st.write("**Field Value Preview:**")
                    preview_data = []
                    for key, value in list(sample_job.items())[:10]:  # Show first 10 fields
                        value_preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        preview_data.append({
                            "Field Name": key,
                            "Type": type(value).__name__,
                            "Value Preview": value_preview
                        })
                    import pandas as pd
                    st.dataframe(pd.DataFrame(preview_data), width='stretch', hide_index=True)
                else:
                    st.write("Not a dictionary")
                
                st.write("**Full raw job (first job):**")
                st.json(sample_job)
        else:
            st.info("No jobs fetched yet.")
            
            # Add test API call button
            st.markdown("---")
            st.subheader("Test API Call")
            test_keywords = st.text_input("Test Keywords", value=DEFAULT_KEYWORDS, key="test_keywords")
            if st.button("🔬 Test API Call (Single Request)"):
                try:
                    import requests
                    from config import FIND_SGJOBS_BASE_URL
                    
                    test_params = {"page": 1, "keywords": test_keywords or DEFAULT_KEYWORDS}
                    with st.spinner("Making test API call..."):
                        response = requests.get(FIND_SGJOBS_BASE_URL, params=test_params, timeout=10)
                        st.write(f"**Status Code:** {response.status_code}")
                        st.write(f"**Content-Type:** {response.headers.get('Content-Type', 'N/A')}")
                        
                        try:
                            json_data = response.json()
                            st.write("**Response Structure:**")
                            st.json(json_data)
                            
                            # Analyze structure
                            if isinstance(json_data, dict):
                                st.write("**Top-level keys:**")
                                st.code(list(json_data.keys()))
                                # Check for common job list keys
                                for key in ["data", "jobs", "results", "items", "jobList", "JobList"]:
                                    if key in json_data:
                                        value = json_data[key]
                                        st.write(f"**Found key '{key}':** Type = {type(value).__name__}, Length = {len(value) if isinstance(value, (list, dict)) else 'N/A'}")
                                        if isinstance(value, list) and len(value) > 0:
                                            st.write(f"**First item in '{key}':**")
                                            st.json(value[0])
                            elif isinstance(json_data, list):
                                st.write(f"**Response is a list with {len(json_data)} items**")
                                if len(json_data) > 0:
                                    st.write("**First item:**")
                                    st.json(json_data[0])
                        except ValueError:
                            st.error("Response is not valid JSON")
                            st.text(response.text[:2000])
                except Exception as e:
                    st.error(f"Test API call failed: {str(e)}")
        
        st.subheader("AI Results (JSON)")
        if st.session_state["ai_results"]:
            st.json(st.session_state["ai_results"])
        else:
            st.info("No AI results yet.")


if __name__ == "__main__":
    main()

