# SCTP Job Search & Skill Gap Analyzer

An AI-driven job recommendation and skill gap analysis system built with Streamlit and Google Gemini LLM.

## 🌐 Live Demo

**Deployed Application**: [https://dsai-findsgjob-capstone.streamlit.app/](https://dsai-findsgjob-capstone.streamlit.app/)

## Features

- 🔍 **Job Search**: Search jobs from FindSGJobs API
- 👤 **Profile Management**: Upload resume or manually enter profile information
- 🤖 **AI-Powered Matching**: Multi-agent LLM system for job matching
- 📊 **Skill Gap Analysis**: Detailed analysis of skills needed vs. skills possessed
- 🎯 **Upskilling Roadmap**: Personalized learning path recommendations

## Architecture

The system uses a multi-agent architecture inspired by Fareed Khan's "Building a Training Architecture for Self-Improving AI Agents":

- **Junior Researchers**: Extract profile and job skills
- **Supervisor**: Rank jobs based on match scores
- **Senior Researcher**: Generate detailed skill gap analysis
- **Review Board**: Sanity check outputs for hallucinations
- **Principal Investigator**: Finalize and consolidate outputs

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables**:
   - Copy `.env.example` to `.env`
   - Add your Google Gemini API key:
     ```
     GEMINI_API_KEY=your_api_key_here
     GEMINI_MODEL_NAME=gemini-1.5-pro
     ```
   - Note: Default model is `gemini-1.5-pro`. If you get a 404 error, try `gemini-1.5-flash` or use the "List Available Models" button in the app to see all available models.

3. **Run the application**:
   ```bash
   streamlit run app.py
   ```

## Usage

1. **Configure API Key**: Enter your Gemini API key in the sidebar
2. **Set Up Profile**: 
   - Upload your resume (PDF/DOCX/TXT) OR
   - Manually enter your skills and profile information
3. **Search Jobs**: Enter keywords and fetch jobs from FindSGJobs
4. **Run AI Analysis**: Click "Run AI Job Recommendations & Skill Gap Analysis"
5. **Review Results**: 
   - View recommended jobs with match scores
   - Check skill gap analysis for each job
   - Review upskilling roadmap

## Project Structure

```
.
├── app.py                          # Main Streamlit application
├── config.py                       # Configuration constants
├── requirements.txt                # Python dependencies
├── services/
│   ├── llm_client.py              # Gemini LLM client wrapper
│   ├── findsgjobs_client.py       # FindSGJobs API client
│   └── resume_parser.py           # Resume parsing utilities
├── agents/
│   ├── schemas.py                 # Data models/schemas
│   ├── junior_researchers.py      # Profile and job skill extraction
│   ├── supervisor.py              # Job ranking
│   ├── senior_researcher.py       # Skill gap analysis
│   ├── review_board.py            # Quality assurance
│   ├── principal_investigator.py  # Output finalization
│   └── pipeline.py                # Pipeline orchestration
└── utils/
    ├── logging_utils.py           # Logging utilities
    └── text_cleaning.py           # Text processing utilities
```

## Requirements

- Python 3.10+
- Google Gemini API key
- Internet connection for API calls

## Notes

- The system uses LLM-only approach (no traditional ML models)
- All intelligence comes from prompt engineering and multi-agent workflows
- Resume parsing supports PDF, DOCX, and TXT formats
- Job data is fetched from FindSGJobs public API
- **Rate Limiting**: FindSGJobs API is limited to **60 requests per minute per IP**. 
  The application automatically throttles requests to stay within this limit. 
  See [FindSGJobs API documentation](https://www.findsgjobs.com/apis/job/searchable) for details.

## License

This project is for SCTP capstone purposes.

