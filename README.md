# SCTP Job Recommender & Skill Gap Analyzer

An AI-driven job recommendation and skill gap analysis system built with Streamlit and Ollama (DeepSeek).

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

2. **Install and set up Ollama**:
   - Install Ollama from [https://ollama.ai](https://ollama.ai)
   - Start the Ollama server (usually runs automatically after installation)
   - Pull the DeepSeek model:
     ```bash
     ollama pull deepseek-r1
     ```
     Or use another model like `llama3`, `mistral`, `deepseek-coder`, etc.
     To see all available models, run: `ollama list`
   
3. **Set up environment variables (optional)**:
   - Environment variables are optional - defaults work for local setup
   - Option 1: Copy `.env.example` to `.env` and customize:
     ```bash
     # Linux/Mac:
     cp .env.example .env
     
     # Windows PowerShell:
     Copy-Item .env.example .env
     
     # Then edit .env with your preferred settings
     ```
   - Option 2: Create `.env` manually with:
     ```
     OLLAMA_BASE_URL=http://localhost:11434
     OLLAMA_MODEL_NAME=deepseek-r1
     ```
   - Available environment variables:
     - `OLLAMA_BASE_URL`: Ollama server URL (default: `http://localhost:11434`)
     - `OLLAMA_MODEL_NAME`: Model name to use (default: `deepseek-r1`)
   - Note: Default model is `deepseek-r1`. You can use the "List Available Models" button in the app to see all available models.
   - Alternatively, you can configure these settings directly in the Streamlit app sidebar without creating a `.env` file.

4. **Run the application**:
   ```bash
   streamlit run app.py
   ```
   
   **Important**: Make sure Ollama is running before starting the app. You can verify by running:
   ```bash
   ollama list
   ```

## Usage

1. **Configure Ollama**: 
   - Make sure Ollama is running (`ollama serve` if not already running)
   - Enter the Ollama base URL in the sidebar (default: http://localhost:11434)
   - Enter the model name (default: deepseek-r1)
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
│   ├── llm_client.py              # Ollama LLM client wrapper
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
- Ollama installed and running ([https://ollama.ai](https://ollama.ai))
- DeepSeek or another compatible model pulled (e.g., `ollama pull deepseek-r1`)
- Internet connection for job search API calls

## Troubleshooting

### Ollama Timeout Errors

If you encounter timeout errors (e.g., "Ollama request timeout after 3 attempts"), try the following:

1. **Use a faster model**: The default `deepseek-r1` model can be slow on some hardware. Try:
   - First, check available models:
     ```bash
     ollama list
     ```
   - Pull a faster alternative model (commonly available):
     ```bash
     ollama pull llama3
     # or
     ollama pull mistral
     # or
     ollama pull deepseek-coder
     ```
   - Then set `OLLAMA_MODEL_NAME` to the model name in your `.env` file or sidebar.

2. **Increase timeout**: Edit `config.py` and increase `OLLAMA_TIMEOUT_SECONDS` (default: 300 seconds).

3. **Check Ollama status**: Verify Ollama is running and responding:
   ```bash
   curl http://localhost:11434/api/tags
   ```

4. **Restart Ollama**: Stop and restart the Ollama server:
   ```bash
   # Stop Ollama (Ctrl+C if running in terminal)
   ollama serve
   ```

5. **Reduce prompt size**: If processing very long resumes, the prompt might be too large. The system automatically truncates to 4000 characters, but you can reduce this in `agents/junior_researchers.py`.

6. **Check system resources**: Large models require significant CPU/RAM. Monitor your system resources and consider using a smaller model if resources are limited.

## Notes

- The system uses LLM-only approach (no traditional ML models)
- All intelligence comes from prompt engineering and multi-agent workflows
- Resume parsing supports PDF, DOCX, and TXT formats
- Job data is fetched from FindSGJobs public API
- **Rate Limiting**: FindSGJobs API is limited to **60 requests per minute per IP**. 
  The application automatically throttles requests to stay within this limit. 
  See [FindSGJobs API documentation](https://www.findsgjobs.com/apis/job/searchable) for details.
- **Timeout Settings**: Default timeout is 300 seconds (5 minutes). Adjust `OLLAMA_TIMEOUT_SECONDS` in `config.py` if needed.

## License

This project is for SCTP capstone purposes.

