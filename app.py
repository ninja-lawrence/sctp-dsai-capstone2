"""Main Streamlit application for SCTP Job Recommender & Skill Gap Analyzer."""
import streamlit as st
import json
from typing import Dict, Any, List
from config import (
    APP_TITLE,
    DEFAULT_KEYWORDS,
    EMPLOYMENT_TYPES,
    CURRENCIES,
    SALARY_INTERVALS,
    GEMINI_API_KEY,
    GEMINI_MODEL_NAME,
)
from services.llm_client import GeminiClient
from services.findsgjobs_client import fetch_all_findsgjobs, normalize_job
from services.resume_parser import parse_resume
from agents.junior_researchers import extract_profile_from_resume_text
from agents.schemas import UserProfile
from agents.pipeline import run_job_matching_pipeline
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
    }

if "jobs_raw" not in st.session_state:
    st.session_state["jobs_raw"] = []

if "ai_results" not in st.session_state:
    st.session_state["ai_results"] = None

if "llm_client" not in st.session_state:
    st.session_state["llm_client"] = None


def initialize_llm_client() -> GeminiClient:
    """Initialize and cache LLM client."""
    if st.session_state["llm_client"] is None:
        try:
            api_key = st.sidebar.text_input(
                "Gemini API Key",
                value=GEMINI_API_KEY,
                type="password",
                help="Enter your Google Gemini API key",
            )
            if not api_key:
                st.sidebar.warning("⚠️ Please enter your Gemini API key in the sidebar")
                return None
            
            model_name = st.sidebar.text_input(
                "Model Name",
                value=GEMINI_MODEL_NAME,
                help="Gemini model to use (e.g., gemini-pro)",
            )
            
            client = GeminiClient(api_key=api_key, model_name=model_name)
            st.session_state["llm_client"] = client
            st.sidebar.success("✅ LLM client initialized")
            return client
        except Exception as e:
            st.sidebar.error(f"❌ Failed to initialize LLM: {str(e)}")
            return None
    return st.session_state["llm_client"]


def main():
    """Main application."""
    st.title(APP_TITLE)
    st.markdown("---")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # LLM Config
        st.subheader("LLM Settings")
        llm_client = initialize_llm_client()
        
        if llm_client:
            st.text(f"Model: {GEMINI_MODEL_NAME}")
        
        st.markdown("---")
        
        # Job Search Settings
        st.subheader("Job Search Settings")
        search_keywords = st.text_input(
            "Keywords",
            value=DEFAULT_KEYWORDS,
            help="Job search keywords",
        )
        
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
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "👤 Profile",
        "🔍 Job Search & Recommendations",
        "📊 Skill Gap Analysis",
        "🐛 Debug / Raw Data",
    ])
    
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
        
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Name", value=profile.get("name") or "")
            headline = st.text_input("Headline", value=profile.get("headline") or "")
            summary = st.text_area("Summary", value=profile.get("summary") or "", height=100)
        
        with col2:
            skills_text = st.text_area(
                "Skills (comma-separated)",
                value=", ".join(profile.get("skills", [])),
                help="Enter skills separated by commas",
            )
            target_roles_text = st.text_area(
                "Target Roles (comma-separated)",
                value=", ".join(profile.get("target_roles", [])),
                help="Enter target job roles separated by commas",
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
            }
            st.success("✅ Profile saved!")
    
    # Tab 2: Job Search & Recommendations
    with tab2:
        st.header("Job Search & AI Recommendations")
        
        # Step 1: Job Search
        st.subheader("Step 1: Search Jobs")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            keywords_input = st.text_input(
                "Search Keywords",
                value=search_keywords,
                key="search_keywords_input",
            )
        
        with col2:
            max_pages = st.number_input("Max Pages", min_value=1, max_value=10, value=3)
        
        if st.button("🔍 Fetch Jobs from FindSGJobs"):
            with st.spinner("Fetching jobs..."):
                try:
                    kwargs = {"keywords": keywords_input, "max_pages": max_pages}
                    
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
                    st.success(f"✅ Fetched {len(jobs)} jobs!")
                except Exception as e:
                    st.error(f"❌ Error fetching jobs: {str(e)}")
                    logger.error(f"Job fetch error: {str(e)}")
        
        # Step 2: Display Jobs
        if st.session_state["jobs_raw"]:
            st.subheader(f"Step 2: Job Listings ({len(st.session_state['jobs_raw'])} jobs)")
            
            for idx, job_raw in enumerate(st.session_state["jobs_raw"][:20]):  # Show first 20
                try:
                    job = normalize_job(job_raw)
                    with st.expander(f"📋 {job['title']} - {job['company']}"):
                        st.write(f"**Location:** {job['location']}")
                        if job.get("salary_text"):
                            st.write(f"**Salary:** {job['salary_text']}")
                        st.write(f"**Description:** {job['description'][:500]}...")
                        if job.get("url"):
                            st.markdown(f"[View Job →]({job['url']})")
                except Exception as e:
                    logger.warning(f"Error displaying job {idx}: {str(e)}")
                    continue
        
        # Step 3: Run AI Matching
        st.subheader("Step 3: Run AI Job Recommendations")
        
        if not llm_client:
            st.warning("⚠️ Please configure Gemini API key in the sidebar first.")
        elif not st.session_state["user_profile"].get("skills"):
            st.warning("⚠️ Please set up your profile with skills first.")
        elif not st.session_state["jobs_raw"]:
            st.warning("⚠️ Please fetch jobs first.")
        else:
            if st.button("🚀 Run AI Job Recommendations & Skill Gap Analysis"):
                with st.spinner("Running AI pipeline... This may take a few minutes."):
                    try:
                        results = run_job_matching_pipeline(
                            llm=llm_client,
                            profile=st.session_state["user_profile"],
                            raw_jobs=st.session_state["jobs_raw"],
                            top_k=10,
                        )
                        st.session_state["ai_results"] = results
                        st.success("✅ AI analysis complete!")
                    except Exception as e:
                        st.error(f"❌ Error running pipeline: {str(e)}")
                        logger.error(f"Pipeline error: {str(e)}")
        
        # Display Recommendations
        if st.session_state["ai_results"]:
            st.subheader("Step 4: Recommended Jobs")
            
            results = st.session_state["ai_results"]
            recommended_jobs = results.get("recommended_jobs", [])
            
            if recommended_jobs:
                for job in recommended_jobs:
                    score = job.get("match_score", 0.0)
                    score_color = "🟢" if score >= 0.7 else "🟡" if score >= 0.4 else "🔴"
                    
                    with st.expander(
                        f"{score_color} {job['title']} - {job['company']} "
                        f"(Match: {score:.1%})"
                    ):
                        st.write(f"**Location:** {job.get('location', 'N/A')}")
                        if job.get("salary_text"):
                            st.write(f"**Salary:** {job['salary_text']}")
                        st.write(f"**Reasoning:** {job.get('reasoning', 'N/A')}")
                        if job.get("url"):
                            st.markdown(f"[View Job →]({job['url']})")
            else:
                st.info("No recommendations available.")
    
    # Tab 3: Skill Gap Analysis
    with tab3:
        st.header("Skill Gap Analysis")
        
        if not st.session_state["ai_results"]:
            st.info("👆 Please run AI matching first in the 'Job Search & Recommendations' tab.")
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
                            if gap.get("matched_skills"):
                                st.write(", ".join(gap["matched_skills"]))
                            else:
                                st.write("None")
                            
                            st.write("**❌ Missing Required Skills:**")
                            if gap.get("missing_required_skills"):
                                st.write(", ".join(gap["missing_required_skills"]))
                            else:
                                st.write("None")
                        
                        with col2:
                            st.write("**⭐ Nice-to-Have Skills:**")
                            if gap.get("nice_to_have_skills"):
                                st.write(", ".join(gap["nice_to_have_skills"]))
                            else:
                                st.write("None")
                            
                            st.write("**📚 Suggested Learning Path:**")
                            if gap.get("suggested_learning_path"):
                                for i, step in enumerate(gap["suggested_learning_path"], 1):
                                    st.write(f"{i}. {step}")
                            else:
                                st.write("No suggestions available")
                
                # Overall Roadmap
                roadmap = results.get("upskilling_roadmap", [])
                if roadmap:
                    st.subheader("🎯 Overall Upskilling Roadmap")
                    for i, step in enumerate(roadmap, 1):
                        st.write(f"{i}. {step}")
                
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
        else:
            st.info("No jobs fetched yet.")
        
        st.subheader("AI Results (JSON)")
        if st.session_state["ai_results"]:
            st.json(st.session_state["ai_results"])
        else:
            st.info("No AI results yet.")


if __name__ == "__main__":
    main()

