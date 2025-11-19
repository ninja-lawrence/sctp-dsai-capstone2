# Technical Documentation: SCTP Job Search & Skill Gap Analyzer

## Overview

This application is an AI-driven job recommendation and skill gap analysis system built with Streamlit and Google Gemini LLM. It uses a multi-agent architecture where specialized AI agents collaborate to analyze job postings, match them with user profiles, and generate personalized skill gap analyses with learning recommendations.

## Architecture

### Multi-Agent System

The system implements a hierarchical multi-agent architecture inspired by research on self-improving AI agents. Each agent has a specific role and responsibility:

1. **Junior Researchers** (`agents/junior_researchers.py`): Extract structured information from unstructured text
2. **Supervisor** (`agents/supervisor.py`): Rank and score job matches
3. **Senior Researcher** (`agents/senior_researcher.py`): Generate detailed skill gap analysis
4. **Review Board** (`agents/review_board.py`): Quality assurance and validation
5. **Principal Investigator** (`agents/principal_investigator.py`): Finalize and consolidate outputs

### Data Flow

```
User Input (Resume/Profile)
    ↓
Junior Researchers → Extract Profile & Job Skills
    ↓
Supervisor → Rank Jobs by Match Score
    ↓
Senior Researcher → Generate Skill Gap Analysis
    ↓
Review Board → Validate & Flag Issues
    ↓
Principal Investigator → Consolidate Final Output
    ↓
UI Display
```

## Pipeline Execution

### Main Pipeline: `run_job_matching_pipeline()`

Located in `agents/pipeline.py`, this function orchestrates the complete workflow:

**Step 1: Normalize Jobs**
- Raw job dictionaries from FindSGJobs API are normalized into `JobPosting` schema
- Handles errors gracefully, skipping invalid jobs

**Step 2: Extract Skills from Jobs**
- Calls `extract_skills_from_job()` for each job (Junior Researcher)
- Extracts: hard_skills, soft_skills, tools, seniority
- Includes 500ms delay between requests to respect rate limits
- Stores results in `job_skills` dictionary (job_id → ExtractedSkills)

**Step 3: Rank Jobs**
- Calls `rank_jobs_for_user()` (Supervisor)
- Takes user profile, normalized jobs, and extracted skills
- Returns top K jobs sorted by match_score (0.0-1.0)

**Step 4: Generate Skill Gaps**
- For each top-ranked job, calls `generate_skill_gap_for_match()` (Senior Researcher)
- Generates detailed gap analysis including learning resources
- Includes 500ms delay between requests

**Step 5: Review Board**
- Calls `review_recommendations()` to validate outputs
- Checks for hallucinations, inconsistencies, mismatches
- Flags problematic recommendations

**Step 6: Finalize Output**
- Calls `finalize_output()` (Principal Investigator)
- Consolidates all results into final structure
- Builds upskilling roadmap from aggregated learning paths

### Alternative Pipeline: `run_skill_gap_analysis_only()`

Simplified pipeline that skips job ranking:

1. Normalize jobs
2. Extract skills from jobs
3. Generate skill gaps directly (no ranking step)
4. Build aggregated roadmap

Used when user wants to analyze a specific job without ranking multiple jobs.

## Agent Details

### 1. Junior Researchers (`agents/junior_researchers.py`)

**Purpose**: Extract structured information from unstructured text using LLM.

**Functions**:

#### `extract_profile_from_resume_text(text, llm)`
Extracts user profile from resume text.

**Prompt Strategy**:
- **System Prompt**: Defines the agent as an "expert ATS resume parser"
- **Why**: ATS (Applicant Tracking System) framing helps the LLM understand the structured extraction task
- **Output Format**: Explicit JSON schema with all required fields
- **Text Limit**: 4000 characters to avoid token limits

**Key Prompt Elements**:
```
"You are an expert ATS (Applicant Tracking System) resume parser.
Your task is to extract structured information from a resume text and return it as JSON."
```

**Extracted Fields**:
- Basic info: name, headline, summary
- Skills: List of technical and soft skills
- Experience: List with company, title, years, responsibilities
- Education: List with institution, degree, field, year
- Preferences: target_roles, experience_level, location, salary ranges

#### `extract_skills_from_job(job, llm)`
Extracts structured skills from job postings.

**Prompt Strategy**:
- **System Prompt**: Defines agent as "job analysis expert"
- **Why**: Focuses on skill extraction rather than full parsing
- **Categorization**: Separates hard_skills, soft_skills, tools, seniority
- **Text Limit**: 3000 characters from job description

**Key Prompt Elements**:
```
"You are a job analysis expert. Extract structured skills and requirements from a job posting."
```

**Output Structure**:
- `hard_skills`: Technical skills, programming languages, frameworks
- `soft_skills`: Communication, teamwork, leadership
- `tools`: Software tools, platforms, technologies
- `seniority`: Experience level required

### 2. Supervisor (`agents/supervisor.py`)

**Purpose**: Rank jobs based on user profile match.

#### `rank_jobs_lightweight(profile, jobs, llm)`

**Purpose**: Fast job ranking without requiring skill extraction. Used for initial sorting after job search.

**Key Differences from Full Ranking**:
- **No skill extraction required**: Uses job title, company, and description directly
- **Faster**: Single LLM call instead of multiple calls for skill extraction
- **Lighter weight**: Designed for quick sorting of search results
- **Returns**: Dictionary mapping `job_id` → `match_score` (0.0-1.0)

**Use Case**: Automatically runs after job search to sort results by relevance before user selects jobs for detailed analysis.

**Prompt Strategy**:
- Similar scoring system as full ranking (0.0-1.0 scale)
- Uses job description (truncated to 800 chars) instead of extracted skills
- Considers skill overlap based on description text and user skills
- Faster execution for initial filtering

#### `rank_jobs_for_user(profile, jobs, job_skills, llm, top_k=10)`

**Purpose**: Full job ranking with extracted skills. Used in complete pipeline.

**Prompt Strategy**:
- **System Prompt**: Defines agent as "job matching expert"
- **Scoring System**: Explicit 0.0-1.0 scale with clear thresholds
- **Why**: Provides clear scoring guidelines to ensure consistent match scores
- **Considerations**: Skill overlap, experience level, industry alignment, education

**Key Prompt Elements**:
```
"For each job, assign a match_score between 0.0 and 1.0, where:
- 1.0 = Perfect match (all requirements met, ideal fit)
- 0.7-0.9 = Strong match (most requirements met, good fit)
- 0.4-0.6 = Moderate match (some requirements met, possible fit)
- 0.1-0.3 = Weak match (few requirements met, stretch)
- 0.0 = No match (completely irrelevant)"
```

**Input Preparation**:
- Limits to 50 jobs to avoid token limits
- Truncates job descriptions to 500 characters
- Summarizes user profile using `summarize_user_profile_for_matching()`
- Includes extracted skills for each job

**Output**:
- List of `JobMatch` objects sorted by match_score (descending)
- Each match includes: job, match_score, reasoning

### 3. Senior Researcher (`agents/senior_researcher.py`)

**Purpose**: Generate detailed skill gap analysis with learning recommendations.

**Function**: `generate_skill_gap_for_match(profile, job, job_skills, llm)`

**Prompt Strategy**:
- **System Prompt**: Defines agent as "career advisor and skill gap analyst"
- **Why**: Career advisor framing helps generate actionable, user-friendly recommendations
- **Structured Analysis**: Five-part analysis (matched, missing required, nice-to-have, learning path, resources)
- **Learning Resources**: Requires actual URLs to real learning platforms

**Key Prompt Elements**:
```
"You are a career advisor and skill gap analyst. Your task is to analyze the gap between a user's skills and a job's requirements.

For a given job, identify:
1. Matched Skills: Skills the user already has that match the job requirements
2. Missing Required Skills: Critical skills the user lacks that are essential for the job
   - Provide a list of missing required skills
   - Also provide a narrative writeup (maximum 200 words) explaining the skill gaps, why these skills are critical for the role, and how they impact the user's ability to perform the job effectively
3. Nice-to-Have Skills: Beneficial skills the user lacks but are not critical
4. Suggested Learning Path: 3-5 high-level steps the user should take to bridge the gap
5. Learning Resources: For each missing required skill, suggest 2-3 specific learning resources (schools, online courses, certifications, bootcamps) with actual URLs"
```

**Learning Resources Requirements**:
- Must be well-known, reputable platforms
- Mix of free and paid options
- Include: Coursera, edX, Udemy, Udacity, Khan Academy, AWS/Google/Microsoft certifications, universities, bootcamps
- Each resource must have: name, url, type, skill

**Output Structure**:
- `matched_skills`: List of skills user already has
- `missing_required_skills`: Critical missing skills (list)
- `missing_required_skills_writeup`: Narrative explanation (max 200 words)
- `nice_to_have_skills`: Beneficial but not critical
- `suggested_learning_path`: 3-5 high-level steps
- `learning_resources`: List of LearningResource objects with URLs

### 4. Review Board (`agents/review_board.py`)

**Purpose**: Quality assurance - detect hallucinations and inconsistencies.

**Function**: `review_recommendations(profile, matches, gaps, llm)`

**Prompt Strategy**:
- **System Prompt**: Defines agent as "quality assurance reviewer"
- **Why**: QA framing helps identify errors and inconsistencies systematically
- **Validation Checks**: Four categories of issues to detect

**Key Prompt Elements**:
```
"You are a quality assurance reviewer for job recommendations. Your task is to identify:

1. Obviously irrelevant jobs (e.g., user is in F&B but job is "Senior Neurosurgeon")
2. Hallucinated skills (skills mentioned in matched_skills that don't appear in user profile)
3. Inconsistencies:
   - Experience level mismatch (e.g., job requires Senior but user is Junior, but match_score is high)
   - Location mismatch (e.g., user wants Remote but job is On-site only)
   - Salary mismatch (e.g., job pays much less than user's minimum expectation, but match_score is high)
4. Missing critical validations"
```

**Input Preparation**:
- Limits to 20 matches for token efficiency
- Includes user profile details: skills, experience level, location, salary expectations
- Summarizes matches with key information

**Output**:
- `warnings`: List of warning messages
- `flagged_job_ids`: Jobs that should be reviewed
- `corrections`: Optional correction suggestions

### 5. Principal Investigator (`agents/principal_investigator.py`)

**Purpose**: Consolidate all outputs into final structure for UI.

**Function**: `finalize_output(profile, matches, gaps, review_result)`

**No LLM Calls**: This agent performs data aggregation and formatting only.

**Responsibilities**:
- Build `recommended_jobs` list from matches
- Aggregate `upskilling_roadmap` from all skill gaps (deduplicated, top 10)
- Generate `overall_summary` text
- Include warnings from Review Board
- Structure final `FinalOutput` dictionary

## Prompt Engineering Rationale

### Why These Prompts?

1. **Role-Based Framing**: Each agent is given a specific professional role (ATS parser, career advisor, QA reviewer). This helps the LLM adopt the appropriate perspective and generate contextually appropriate outputs.

2. **Explicit Output Formats**: All prompts specify exact JSON structures. This ensures:
   - Consistent parsing
   - Predictable outputs
   - Easier error handling

3. **Scoring Guidelines**: The Supervisor uses explicit scoring thresholds (0.0-1.0 with ranges). This prevents arbitrary scores and ensures consistency.

4. **Token Management**: 
   - Text truncation (4000 chars for resumes, 3000 for job descriptions, 500 for summaries)
   - Job limits (50 for ranking, 20 for review)
   - Prevents token limit errors

5. **Actionable Outputs**: Senior Researcher prompt emphasizes:
   - Real URLs (not placeholders)
   - Reputable platforms
   - Mix of free/paid options
   - Specific skill mapping

6. **Error Prevention**: Review Board prompt explicitly lists types of errors to catch, reducing hallucinations and inconsistencies.

## Usage Flow

### 1. Profile Setup

**Option A: Resume Upload**
- User uploads PDF/DOCX/TXT resume
- `parse_resume()` extracts raw text
- `extract_profile_from_resume_text()` (Junior Researcher) extracts structured profile
- Profile stored in `st.session_state["user_profile"]`

**Option B: Manual Entry**
- User manually enters skills, experience, preferences
- Saved directly to session state

### 2. Job Search

- User enters keywords in sidebar or main tab
- `fetch_all_findsgjobs()` queries FindSGJobs API
- Raw jobs stored in `st.session_state["jobs_raw"]`
- **Automatic Job Matching** (if user profile has skills):
  - Normalizes jobs for ranking
  - Calls `rank_jobs_lightweight()` to get match scores
  - Sorts jobs by match score (highest first)
  - Stores match scores in `st.session_state["job_match_scores"]`
  - Displays match percentages in UI
- Jobs displayed in table or card view with match percentages

### 3. Skill Gap Analysis

**Full Pipeline** (not currently used in UI):
- Calls `run_job_matching_pipeline()`
- Returns ranked jobs + skill gaps

**Analysis Only** (current UI flow):
- User selects one job from dropdown (jobs pre-sorted by relevance)
- Dropdown shows match percentage for each job (e.g., "Software Engineer - Company - 85% Match")
- Selected job preview also displays match percentage
- Calls `run_skill_gap_analysis_only()`
- Returns skill gaps for selected job

### 4. Results Display

- **Job Listings**: Display match percentages with color-coded badges:
  - Green (≥70%): Strong match
  - Yellow (40-69%): Moderate match
  - Red (<40%): Weak match
- **Skill Gap Analysis**: Shown per job with:
  - Matched skills
  - Missing required skills (with narrative writeup)
  - Nice-to-have skills
  - Learning path (3-5 steps)
  - Learning resources (with clickable URLs)
- Overall upskilling roadmap (aggregated)
- Warnings from Review Board

## Rate Limiting

### Gemini API
- **Free Tier**: 10 requests per minute per model
- **Implementation**: `_check_gemini_rate_limit()` tracks timestamps per model
- **Retry Logic**: Automatic retry with exponential backoff on 429 errors
- **Delays**: 500ms delay between requests in pipeline steps

### FindSGJobs API
- **Limit**: 60 requests per minute per IP
- **Implementation**: Rate limiter in `findsgjobs_client.py`
- **Throttling**: Automatic request throttling

## Error Handling

### LLM Errors
- **JSON Parse Errors**: Try to extract JSON from markdown code blocks
- **Rate Limit Errors**: Automatic retry with delays
- **Model Not Found**: Helpful error messages with available models
- **Fallback**: Return minimal valid structures on errors

### Pipeline Errors
- Each step has try/except blocks
- Errors logged but don't stop entire pipeline
- Partial results returned when possible
- Warnings added to final output

## Data Schemas

### UserProfile
- Basic info: name, headline, summary
- Skills: List[str]
- Experience: List[Dict] with company, title, years, responsibilities
- Education: List[Dict] with institution, degree, field, year
- Preferences: target_roles, experience_level, location, salary ranges

### JobPosting
- id, title, company, location
- salary_text, category
- description, url, image_url

### ExtractedSkills
- hard_skills, soft_skills, tools: List[str]
- seniority: Optional[str]

### SkillGapResult
- job_id, job_title
- matched_skills, missing_required_skills: List[str]
- missing_required_skills_writeup: Optional[str] (narrative)
- nice_to_have_skills: List[str]
- suggested_learning_path: List[str]
- learning_resources: List[LearningResource]

### LearningResource
- name, url, type, skill

## UI Features

### Match Percentage Display

After job search, if the user profile contains skills, the system automatically:
1. Runs lightweight job matching using `rank_jobs_lightweight()`
2. Sorts jobs by match score (highest relevance first)
3. Displays match percentages throughout the UI:
   - **Job Search Tab**: Color-coded badges next to job titles in both Table and Card views
   - **Skill Gap Analysis Tab**: Match percentage shown in dropdown options and selected job preview
4. Match scores stored in `st.session_state["job_match_scores"]` for persistence

**Color Coding**:
- 🟢 Green (≥70%): Strong match - ideal fit
- 🟡 Yellow (40-69%): Moderate match - possible fit
- 🔴 Red (<40%): Weak match - stretch opportunity

This helps users quickly identify the most relevant jobs without running full skill gap analysis.

## Technical Implementation Details

### LLM Client (`services/llm_client.py`)

**GeminiClient**:
- Wraps Google Generative AI SDK
- Implements `chat()` and `chat_json()` methods
- Handles rate limiting, retries, error parsing
- Extracts JSON from markdown code blocks automatically

**Rate Limiting**:
- Per-model timestamp tracking using `deque`
- Sliding window (60 seconds)
- Automatic wait when limit reached

**Retry Logic**:
- Max 3 retries for rate limit errors
- Extracts retry delay from error messages
- Exponential backoff

### Pipeline Orchestration (`agents/pipeline.py`)

**Sequential Execution**:
- Steps run in order (no parallelization)
- Each step depends on previous step's output
- Errors in one step don't cascade (handled individually)

**Data Flow**:
- Raw jobs → Normalized jobs → Extracted skills → Ranked matches → Skill gaps → Reviewed → Finalized

**Token Management**:
- Text truncation at multiple levels
- Limits on number of items processed
- Summaries instead of full text where possible

## Configuration

### Environment Variables
- `GEMINI_API_KEY`: Google Gemini API key
- `GEMINI_MODEL_NAME`: Model to use (default: gemini-2.5-flash)

### Config Constants (`config.py`)
- Rate limits: 10 req/min for Gemini, 60 req/min for FindSGJobs
- Default keywords: "data analyst"
- Top K jobs: 10
- Employment types, currencies, salary intervals mappings

## Future Improvements

1. **Parallel Processing**: Run skill extraction in parallel for multiple jobs
2. **Caching**: Cache extracted skills for jobs to avoid re-processing
3. **Streaming**: Stream results as they're generated
4. **Batch Processing**: Process multiple jobs in single LLM call
5. **Fine-tuning**: Fine-tune prompts based on user feedback
6. **Multi-model**: Support multiple LLM providers (OpenAI, Anthropic, etc.)

