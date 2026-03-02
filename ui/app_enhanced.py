"""Enhanced Streamlit UI with detailed analysis display."""
import streamlit as st
import os
from pathlib import Path
import sys
import json
from io import StringIO
from datetime import datetime
import base64

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.git_repo import GitRepoAnalyzer
from agent.parsers import CucumberJsonParser
from agent.report_builder_enhanced import EnhancedReportBuilder
from agent.analyzers.compare_runs import RunComparator
from agent.analyzers.llm_analyzer import LLMAnalyzer
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Testing Engine - QA Intelligence",
    page_icon="🧪",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 48px;
        font-weight: bold;
        color: #fff;
    }
    .metric-label {
        font-size: 14px;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .status-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
    }
    .status-ready {
        background-color: #1a472a;
        color: #4ade80;
    }
    .summary-box {
        background-color: #1a1a2e;
        border-left: 4px solid #3b82f6;
        padding: 12px;
        margin: 10px 0;
        border-radius: 4px;
    }
    .summary-text {
        font-weight: 600;
        color: #3b82f6;
        margin-bottom: 8px;
    }
    .report-frame {
        width: 100%;
        height: 600px;
        border: 1px solid #333;
        border-radius: 8px;
        background: white;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'analysis_timestamp' not in st.session_state:
    st.session_state.analysis_timestamp = None
if 'dataset_name' not in st.session_state:
    st.session_state.dataset_name = None
if 'metrics' not in st.session_state:
    st.session_state.metrics = None
if 'commits_cache' not in st.session_state:
    st.session_state.commits_cache = {}
if 'total_commits' not in st.session_state:
    st.session_state.total_commits = None

# Fixed LLM settings (hidden from UI)
MAX_TOKENS = 5000
MAX_WORKERS = 10
MAX_DETAILED_ANALYSIS = 20
TEMPERATURE = 0.10

# Helper function to load reports from dataset - IMPROVED
def load_reports_from_dataset(dataset_path=None):
    """Load baseline and current reports from multiple possible locations"""
    
    # Priority 1: Check project root html-reports folder
    base_dir = Path(__file__).parent.parent
    reports_dir = base_dir / "html-reports"
    
    if reports_dir.exists():
        report_files = sorted(list(reports_dir.glob("*.json")))
        if len(report_files) >= 2:
            with open(report_files[0], 'r', encoding='utf-8') as f:
                baseline_content = f.read()
            with open(report_files[1], 'r', encoding='utf-8') as f:
                current_content = f.read()
            return baseline_content, current_content
    
    # Priority 2: Check if dataset_path provided, look in dataset folder
    if dataset_path:
        dataset_reports = Path(dataset_path) / "reports"
        if dataset_reports.exists():
            report_files = sorted(list(dataset_reports.glob("*.json")))
            if len(report_files) >= 2:
                with open(report_files[0], 'r', encoding='utf-8') as f:
                    baseline_content = f.read()
                with open(report_files[1], 'r', encoding='utf-8') as f:
                    current_content = f.read()
                return baseline_content, current_content
    
    # No reports found
    return None, None

# Helper function to get total commits from repo
def get_total_commits(repo_url, github_token=None):
    """Get total number of commits in repository"""
    cache_key = f"total_commits|{repo_url}"
    
    # Check cache
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]
    
    try:
        with GitRepoAnalyzer(repo_url, github_token) as git:
            # Count total commits on HEAD
            total = sum(1 for _ in git.repo.iter_commits('HEAD'))
            
            # Cache the result
            st.session_state.commits_cache[cache_key] = total
            return total
    except Exception as e:
        st.warning(f"Could not get total commits: {e}")
        return 100  # Default fallback

# Helper function to extract commits between refs - FIXED
def extract_commits_between_refs(repo_url, baseline_ref, current_ref, github_token=None):
    """Extract commits between two specific refs with proper data structure"""
    cache_key = f"{repo_url}|{baseline_ref}|{current_ref}"
    
    # Check cache
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]
    
    try:
        commits = []
        
        with GitRepoAnalyzer(repo_url, github_token) as git:
            # Get commits in range using GitPython
            commit_range = f"{baseline_ref}..{current_ref}"
            
            for commit in git.repo.iter_commits(commit_range):
                # Get changed files with stats
                changed_files = []
                for file, stats in commit.stats.files.items():
                    changed_files.append({
                        'file': file,
                        'insertions': stats['insertions'],
                        'deletions': stats['deletions'],
                        'lines': stats['lines']
                    })
                
                # Get diffs (optional, for detailed analysis)
                diffs = []
                if commit.parents:
                    parent = commit.parents[0]
                    for diff in parent.diff(commit, create_patch=True):
                        diff_data = {
                            'change_type': diff.change_type,
                            'old_path': diff.a_path,
                            'new_path': diff.b_path,
                        }
                        
                        if diff.diff:
                            try:
                                diff_text = diff.diff.decode('utf-8', errors='ignore')
                                if len(diff_text) > 10000:
                                    diff_data['diff'] = diff_text[:10000] + "\n... [truncated]"
                                else:
                                    diff_data['diff'] = diff_text
                            except:
                                diff_data['diff'] = None
                        
                        diffs.append(diff_data)
                
                # Build properly structured commit dict
                commit_data = {
                    'sha': commit.hexsha,
                    'author': {
                        'name': commit.author.name,
                        'email': commit.author.email
                    },
                    'date': commit.committed_datetime.isoformat(),
                    'message': commit.message.strip(),
                    'changed_files': changed_files,
                    'diffs': diffs,
                    'stats': {
                        'total_files': len(changed_files),
                        'total_insertions': commit.stats.total['insertions'],
                        'total_deletions': commit.stats.total['deletions'],
                        'total_lines': commit.stats.total['lines']
                    }
                }
                
                commits.append(commit_data)
        
        # Cache the result
        st.session_state.commits_cache[cache_key] = commits
        
        return commits
        
    except Exception as e:
        st.error(f"Failed to extract commits: {e}")
        import traceback
        st.code(traceback.format_exc())
        return []

# Helper function to extract commits by range
def extract_commits_by_range(repo_url, start_index, end_index, github_token=None):
    """Extract commits by index range (e.g., commits 5 to 15)"""
    cache_key = f"{repo_url}|range|{start_index}|{end_index}"
    
    # Check cache
    if cache_key in st.session_state.commits_cache:
        return st.session_state.commits_cache[cache_key]
    
    try:
        commits = []
        
        with GitRepoAnalyzer(repo_url, github_token) as git:
            # Get commits with skip and max_count
            # skip = start_index - 1 (0-indexed)
            # max_count = end_index - start_index + 1
            skip = start_index - 1
            count = end_index - start_index + 1
            
            all_commits_iter = git.repo.iter_commits('HEAD', skip=skip, max_count=count)
            
            for commit in all_commits_iter:
                changed_files = []
                for file, stats in commit.stats.files.items():
                    changed_files.append({
                        'file': file,
                        'insertions': stats['insertions'],
                        'deletions': stats['deletions'],
                    })
                
                commits.append({
                    'sha': commit.hexsha,
                    'author': {
                        'name': commit.author.name,
                        'email': commit.author.email
                    },
                    'date': commit.committed_datetime.isoformat(),
                    'message': commit.message.strip(),
                    'changed_files': changed_files,
                    'stats': {
                        'total_insertions': commit.stats.total['insertions'],
                        'total_deletions': commit.stats.total['deletions'],
                    }
                })
        
        # Cache the result
        st.session_state.commits_cache[cache_key] = commits
        
        return commits
        
    except Exception as e:
        st.error(f"Failed to extract commits: {e}")
        return []


# ── Pairwise commit inference helpers ──────────────────────────

def get_pairwise_diffs(repo_url, commits_list, github_token=None):
    """
    Given an ordered list of commits (newest-first from GitPython),
    return a list of dicts describing what changed between each
    consecutive pair (older → newer).
    """
    if len(commits_list) < 2:
        return []

    # commits_list is newest-first; reverse so pairs go old→new
    ordered = list(reversed(commits_list))
    pairs = []

    try:
        with GitRepoAnalyzer(repo_url, github_token) as git_analyzer:
            for i in range(len(ordered) - 1):
                older = ordered[i]
                newer = ordered[i + 1]

                older_sha = older['sha']
                newer_sha = newer['sha']

                # Get diff between the two commits
                changed_files = []
                diff_texts = []
                try:
                    older_commit = git_analyzer.repo.commit(older_sha)
                    newer_commit = git_analyzer.repo.commit(newer_sha)

                    for diff_item in older_commit.diff(newer_commit, create_patch=True):
                        file_path = diff_item.b_path or diff_item.a_path
                        diff_text = ""
                        if diff_item.diff:
                            try:
                                diff_text = diff_item.diff.decode('utf-8', errors='ignore')
                                if len(diff_text) > 5000:
                                    diff_text = diff_text[:5000] + "\n... [truncated]"
                            except Exception:
                                diff_text = ""

                        changed_files.append(file_path)
                        diff_texts.append({"file": file_path, "diff": diff_text})
                except Exception as e:
                    changed_files = []
                    diff_texts = []

                pairs.append({
                    "older": older,
                    "newer": newer,
                    "changed_files": changed_files,
                    "diffs": diff_texts,
                })

    except Exception as e:
        st.error(f"Failed to get pairwise diffs: {e}")
        return []

    return pairs


def generate_commit_pair_inference(llm, pair):
    """Use the LLM to summarise what changed between two commits."""
    older = pair["older"]
    newer = pair["newer"]
    diffs = pair["diffs"]

    # Build a concise prompt
    diff_summary_parts = []
    for d in diffs[:10]:  # cap at 10 files
        snippet = d["diff"][:1500] if d["diff"] else "(binary or empty)"
        diff_summary_parts.append(f"### {d['file']}\n```\n{snippet}\n```")

    diff_block = "\n\n".join(diff_summary_parts) if diff_summary_parts else "No file diffs available."

    prompt = f"""You are a senior software engineer reviewing commits.

**Older Commit:** {older['sha'][:8]} — {older['message']}
**Newer Commit:** {newer['sha'][:8]} — {newer['message']}
**Author:** {newer['author']['name']}
**Files Changed:** {', '.join(pair['changed_files'][:15]) or 'none detected'}

### Diffs
{diff_block}

Provide a concise inference (3-6 bullet points) covering:
1. **What changed** — summarise the code changes in plain English.
2. **Why it likely changed** — infer the intent (bug fix, feature, refactor, config, etc.).
3. **Potential impact** — what parts of the system could be affected.
4. **Risk level** — Low / Medium / High and a one-line justification.

Be specific: reference file names and line-level details where possible."""

    if not llm or not llm.client:
        # Fallback: rule-based summary when no LLM is available
        files_str = ", ".join(pair["changed_files"][:5]) or "unknown"
        return (
            f"- **Files changed:** {files_str}\n"
            f"- **Commit message:** {newer['message']}\n"
            f"- *LLM not configured — showing basic summary only.*"
        )

    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert code reviewer. Provide concise, "
                        "actionable commit-pair analysis in Markdown bullet points."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ LLM inference failed: {e}"


# Sidebar
with st.sidebar:
    # ═══════════════════════════════════════════════════════
    # Repository Configuration - ALWAYS VISIBLE
    # ═══════════════════════════════════════════════════════
    st.header("📂 Repository Configuration")
    
    repo_url = st.text_input(
        "Git Repository URL",
        value="https://github.com/Inadev-Data-Lab/QA_Playwright_Repo",
        help="GitHub repository URL"
    )
    
    github_token = st.text_input(
        "GitHub Token (optional)",
        type="password",
        value=os.getenv("GITHUB_TOKEN", ""),
        help="Required for private repositories"
    )
    
    # Get total commits when repo URL changes
    if repo_url:
        if st.session_state.total_commits is None or st.session_state.get('last_repo_url') != repo_url:
            with st.spinner("Fetching repository info..."):
                st.session_state.total_commits = get_total_commits(repo_url, github_token or None)
                st.session_state.last_repo_url = repo_url
        
        total_commits = st.session_state.total_commits
        st.caption(f"📊 Total commits in repository: **{total_commits}**")
    else:
        total_commits = 100  # Default
    
    st.divider()
    
    # ═══════════════════════════════════════════════════════
    # Commit Selection Mode
    # ═══════════════════════════════════════════════════════
    st.header("📦 Commit Selection")
    
    commit_mode = st.radio(
        "Selection Mode",
        options=["Commit Range (by number)", "Specific Commits (by hash/ref)"],
        index=0,
        help="Choose how to select commits for analysis"
    )
    
    if commit_mode == "Commit Range (by number)":
        st.markdown("**Select Commit Range**")
        st.caption(f"Repository has {total_commits} total commits")
        
        # Range slider for commit selection
        commit_range = st.slider(
            "Commit Range (newest to oldest)",
            min_value=1,
            max_value=total_commits,
            value=(1, min(30, total_commits)),
            help="Select range of commits to analyze (1 = newest commit)"
        )
        
        start_commit, end_commit = commit_range
        st.caption(f"Will analyze commits **{start_commit}** to **{end_commit}** ({end_commit - start_commit + 1} commits)")
        
        use_commit_range = False
        use_index_range = True
        baseline_ref = None
        current_ref = None
        
    else:  # Specific Commits mode
        st.markdown("**Specify Commit Refs**")
        
        baseline_ref = st.text_input(
            "Baseline Ref",
            value="36f96ae5",
            help="Starting commit (baseline) - commit hash, branch, or tag"
        )
        
        current_ref = st.text_input(
            "Current Ref",
            value="1ea635a0",
            help="Ending commit (current) - commit hash, branch, or tag"
        )
        
        use_commit_range = True
        use_index_range = False
        commits_to_analyze = None
    
    st.divider()
    
    # Azure OpenAI Status
    st.header("🔑 Azure OpenAI")
    
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    openai_key_env = os.getenv("OPENAI_API_KEY")
    
    if azure_endpoint and azure_deployment and azure_key:
        st.success("✅ Credentials loaded from .env")
        with st.expander("View Configuration", expanded=False):
            st.caption(f"**Endpoint:** {azure_endpoint[:50]}...")
            st.caption(f"**Deployment:** {azure_deployment}")
    elif openai_key_env:
        st.success("✅ OpenAI Credentials loaded from .env")
    else:
        st.warning("⚠️ No AI credentials configured")
        st.caption("Add credentials to .env file")
    
    # Optional override
    openai_key_override = st.text_input(
        "API Key Override (optional)",
        type="password",
        value="",
        help="Override .env configuration"
    )
    
    # Caching option
    st.divider()
    st.header("⚙️ Settings")
    
    enable_cache = st.checkbox(
        "Enable Caching",
        value=True,
        help="Cache LLM results for faster repeat analysis"
    )
    
    cache_dir = ".llm_cache" if enable_cache else None
    
    st.divider()
    
    # Test Reports Upload - ONLY in "Specific Commits" mode
    if use_commit_range:
        st.header("📊 Test Reports")
        st.caption("Upload baseline and current test reports")
        baseline_json = st.file_uploader("Baseline Report (JSON)", type=["json"], key="baseline_upload")
        current_json = st.file_uploader("Current Report (JSON)", type=["json"], key="current_upload")
    else:
        # In "Commit Range" mode, reports come from dataset
        baseline_json = None
        current_json = None

# Main content area
st.title("🧪 Testing Engine")
st.markdown("**AI-Powered Test Failure Analysis — Commits × Reports > Actionable Intelligence**")

# Determine dataset path
base_dir = Path(__file__).parent.parent
data_path = base_dir / "pulled_data" / "QA_Playwright_Repo_20260210_163229"

# Load reports based on mode
if use_commit_range:
    # Specific Commits mode: require uploads
    ready_status = baseline_json is not None and current_json is not None
    if ready_status:
        baseline_content = baseline_json.read().decode('utf-8')
        current_content = current_json.read().decode('utf-8')
    else:
        baseline_content = None
        current_content = None
else:
    # Commit Range mode: load from dataset
    baseline_content, current_content = load_reports_from_dataset(data_path)
    ready_status = baseline_content is not None and current_content is not None

# Show metrics if we have report data
if 'report' in st.session_state and st.session_state.metrics:
    metrics = st.session_state.metrics
    
    # Metrics cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['commits']}</div>
            <div class="metric-label">COMMITS</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['test_reports']}</div>
            <div class="metric-label">TEST REPORTS</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['report_size_kb']}</div>
            <div class="metric-label">REPORT SIZE (KB)</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{metrics['contributors']}</div>
            <div class="metric-label">CONTRIBUTORS</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🤖 AI Analysis",
    "📦 Commits",
    "🔍 Commit Inference",
    "📊 Test Reports",
    "📜 History"
])

with tab1:
    st.header("Run AI Analysis")
    st.markdown("Send commit history and test reports to Azure OpenAI for intelligent root cause analysis.")
    
    # Add helpful setup guide when reports not found
    if not use_commit_range and not ready_status:
        st.warning("⚠️ **No test reports found**")
        st.markdown("""
        To use "Commit Range" mode, you need to add test reports to the project:
        
        **Option 1: Project Root (Recommended)**
        ```
        qa-intelligence-agent/
        ├── html-reports/          ← Create this folder
        │   ├── report1.json       ← Add your baseline report
        │   └── report2.json       ← Add your current report
        ├── ui/
        └── agent/
        ```
        
        **Steps:**
        1. Create the `html-reports` folder at the project root
        2. Place your JSON test reports (Cucumber format) there
        3. Refresh this page
        
        **Or switch to "Specific Commits" mode to upload reports manually.**
        """)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        analyze_button = st.button("🔬 Analyze Now", type="primary", use_container_width=True, disabled=not ready_status)
    
    with col2:
        if ready_status:
            if use_commit_range and repo_url and baseline_ref and current_ref:
                st.markdown(f"""
                <div class="status-badge status-ready">
                    ✅ Ready — Range: {baseline_ref[:7]} → {current_ref[:7]} + 2 reports
                </div>
                """, unsafe_allow_html=True)
            elif use_index_range:
                num_commits = end_commit - start_commit + 1
                st.markdown(f"""
                <div class="status-badge status-ready">
                    ✅ Ready — Commits {start_commit}-{end_commit} ({num_commits} commits) + 2 reports
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("⚠️ Please configure repository and refs")
        else:
            if use_commit_range:
                st.warning("⚠️ Please upload both baseline and current reports")
            else:
                st.error("❌ No reports found in dataset. Please add reports to html-reports/ folder")
    
    # Analysis logic
    if analyze_button:
        if not ready_status:
            if use_commit_range:
                st.error("❌ Please upload both baseline and current reports")
            else:
                st.error("❌ No reports found in dataset. Place JSON reports in html-reports/ folder")
            st.stop()
        
        # Progress tracking
        progress_container = st.container()
        progress_bar = st.progress(0)
        output_container = st.expander("📊 Analysis Progress", expanded=True)
        
        with st.spinner("🔎 Analyzing repository and generating AI insights..."):
            try:
                with output_container:
                    status_placeholder = st.empty()
                    
                    # Parse reports
                    status_placeholder.info("📖 Parsing test reports...")
                    progress_bar.progress(10)
                    
                    baseline_summary = CucumberJsonParser.parse(baseline_content)
                    current_summary = CucumberJsonParser.parse(current_content)
                    
                    status_placeholder.success(f"✓ Parsed: {baseline_summary.total} baseline, {current_summary.total} current tests")
                    
                    # Git analysis - depends on mode
                    if use_commit_range:
                        status_placeholder.info(f"🔍 Extracting commits: {baseline_ref} → {current_ref}...")
                        progress_bar.progress(20)
                        
                        commits = extract_commits_between_refs(repo_url, baseline_ref, current_ref, github_token)
                        
                        if not commits:
                            st.error("❌ Failed to extract commits. Check repository URL and refs.")
                            st.stop()
                        
                        raw_changes = [(c['changed_files'][0]['file'] if c.get('changed_files') else '', 
                                       '', 
                                       c['stats']['total_insertions'], 
                                       c['stats']['total_deletions']) for c in commits]
                        
                        status_placeholder.success(f"✓ Extracted {len(commits)} commits in range")
                        
                    else:
                        # Use commit index range
                        status_placeholder.info(f"🔍 Extracting commits {start_commit} to {end_commit}...")
                        progress_bar.progress(20)
                        
                        commits = extract_commits_by_range(repo_url, start_commit, end_commit, github_token or None)
                        
                        if not commits:
                            st.error("❌ Failed to extract commits.")
                            st.stop()
                        
                        raw_changes = []
                        
                        status_placeholder.success(f"✓ Extracted {len(commits)} commits")
                    
                    progress_bar.progress(30)
                    
                    # Calculate metrics
                    contributors = len(set(c['author']['name'] for c in commits if isinstance(c, dict) and 'author' in c))
                    report_size_kb = round((len(baseline_content) + len(current_content)) / 1024, 1)
                    
                    st.session_state.metrics = {
                        'commits': len(commits),
                        'test_reports': 2,
                        'report_size_kb': report_size_kb,
                        'contributors': contributors
                    }
                    
                    # Build report
                    status_placeholder.info("🤖 Initializing AI analyzer...")
                    
                    report_builder = EnhancedReportBuilder(
                        openai_api_key=openai_key_override or None,
                        max_workers=MAX_WORKERS,
                        cache_dir=cache_dir,
                        max_detailed_analysis=MAX_DETAILED_ANALYSIS
                    )
                    
                    progress_bar.progress(40)
                    
                    # Find regressions
                    status_placeholder.info("🔬 Comparing test runs...")
                    regressions = RunComparator.find_regressions(baseline_summary, current_summary)
                    improvements = RunComparator.find_improvements(baseline_summary, current_summary)
                    duration_regressions = RunComparator.find_duration_regressions(baseline_summary, current_summary)
                    
                    status_placeholder.success(f"✓ Found {len(regressions)} regressions, {len(improvements)} improvements")
                    progress_bar.progress(50)
                    
                    # AI Analysis
                    status_placeholder.info("🧠 Running AI analysis...")
                    
                    old_stdout = sys.stdout
                    sys.stdout = captured_output = StringIO()
                    
                    try:
                        report = report_builder.build_detailed_report(
                            repo_url=repo_url,
                            baseline_commit=baseline_ref if use_commit_range else f"HEAD~{end_commit}",
                            current_commit=current_ref if use_commit_range else f"HEAD~{start_commit-1}",
                            baseline_summary=baseline_summary,
                            current_summary=current_summary,
                            commits=commits,
                            raw_file_changes=raw_changes,
                            regressions=regressions,
                            improvements=improvements,
                            duration_regressions=duration_regressions
                        )
                        
                        output_text = captured_output.getvalue()
                        if output_text:
                            st.code(output_text, language="text")
                        
                    finally:
                        sys.stdout = old_stdout
                    
                    progress_bar.progress(100)
                    status_placeholder.success("✅ Analysis complete!")
                    
                    st.session_state.report = report
                    st.session_state.commits = commits
                    st.session_state.analysis_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.exception(e)
    
    # Display results
    if 'report' in st.session_state:
        st.divider()
        st.header("📋 Analysis Results")
        
        if st.session_state.analysis_timestamp:
            st.caption(f"Generated: {st.session_state.analysis_timestamp}")
        
        report = st.session_state.report
        
        # Executive Summary
        st.subheader("📊 Executive Summary")
        st.info(report["executive_summary"])
        
        # Key Findings
        if report.get("key_findings"):
            st.subheader("🔍 Key Findings")
            for i, finding in enumerate(report["key_findings"]):
                st.warning(finding)
        
        # Detailed Failures
        st.divider()
        st.subheader("💥 Test Failures Analysis")
        
        detailed_regressions = [r for r in report["regressions"] 
                                if "Not analyzed in detail" not in str(r.get("analysis", {}).get("root_cause", ""))]
        quick_regressions = [r for r in report["regressions"] 
                            if "Not analyzed in detail" in str(r.get("analysis", {}).get("root_cause", ""))]
        
        if detailed_regressions:
            st.markdown(f"**🔬 Detailed AI Analysis ({len(detailed_regressions)} regressions)**")
            
            for i, regression in enumerate(detailed_regressions):
                analysis = regression.get("analysis", {})
                
                explanation = analysis.get("detailed_explanation", "")
                summary_line = explanation.split('\n')[0] if explanation else "No summary available"
                if len(summary_line) > 100:
                    summary_line = summary_line[:100] + "..."
                
                st.markdown(f"""
                <div class="summary-box">
                    <div class="summary-text">❌ {regression['scenario_name']}</div>
                    <div style="color: #ccc; font-size: 14px;">{summary_line}</div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("📖 View Full Analysis", expanded=False):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.markdown("**🤖 AI Analysis**")
                        if analysis.get("analysis_type") == "llm_powered":
                            provider = analysis.get("provider", "AI")
                            st.success(f"Powered by {provider}")
                        
                        st.markdown(explanation)
                    
                    with col2:
                        st.markdown("**📊 Metrics**")
                        st.metric(
                            "Duration Change",
                            f"{regression['current_duration_ms']:.0f}ms",
                            f"+{regression['current_duration_ms'] - regression['baseline_duration_ms']:.0f}ms"
                        )
                        
                        st.markdown("**🐛 Error Details**")
                        error_msg = regression.get("error_message", "No error message")
                        if len(error_msg) > 200:
                            st.code(error_msg[:200] + "\n...", language="text")
                            if st.button("Show Full Error", key=f"err_{i}"):
                                st.code(error_msg, language="text")
                        else:
                            st.code(error_msg, language="text")
        
        if quick_regressions:
            st.divider()
            st.markdown(f"**📋 Quick Summary ({len(quick_regressions)} lower priority regressions)**")
            
            for regression in quick_regressions:
                with st.expander(f"⚠️ {regression['scenario_name']}"):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"**Feature:** {regression['feature']}")
                        if regression.get('error_message'):
                            st.code(regression['error_message'][:200], language="text")
                    with col2:
                        st.metric("Duration", f"{regression['current_duration_ms']:.0f}ms")

with tab2:
    st.header("📦 Commit History")
    
    if 'commits' in st.session_state and st.session_state.commits:
        commits = st.session_state.commits
        
        if use_commit_range:
            st.markdown(f"**Range:** `{baseline_ref}` → `{current_ref}` | **Total Commits:** {len(commits)}")
        else:
            st.markdown(f"**Repository:** {repo_url.split('/')[-1]} | **Commits:** {start_commit} to {end_commit} ({len(commits)} total)")
        
        st.divider()
        
        st.subheader("🔍 Search commits")
        search_query = st.text_input(
            "Search by message, author, or hash...",
            placeholder="Search by message, author, or hash...",
            label_visibility="collapsed"
        )
        
        filtered_commits = commits
        if search_query:
            filtered_commits = [c for c in commits 
                               if search_query.lower() in c['message'].lower() 
                               or search_query.lower() in c['author']['name'].lower()
                               or search_query.lower() in c['sha'].lower()]
        
        for commit in filtered_commits:
            sha = commit['sha'][:8]
            author = commit['author']['name']
            date = commit['date']
            message = commit['message']
            
            with st.expander(f"**{sha}** — {message[:80]}", expanded=False):
                st.markdown(f"**Author:** {author}")
                st.markdown(f"**Date:** {date}")
                st.markdown(f"**Message:** {message}")
                
                if 'changed_files' in commit and commit['changed_files']:
                    st.markdown(f"**Files Changed:** {len(commit['changed_files'])}")
                    for file in commit['changed_files'][:5]:
                        st.markdown(f"- `{file['file']}`")
    else:
        st.info("Run analysis first to see commit history")

with tab3:
    st.header("� Commit-by-Commit Inference")
    st.markdown(
        "Select a commit range and get an AI-powered summary of "
        "**what changed between each consecutive pair** of commits."
    )

    # ── Controls ──────────────────────────────────────────
    inf_col1, inf_col2 = st.columns([3, 1])

    with inf_col1:
        if use_index_range:
            inf_range = st.slider(
                "Commit range for inference",
                min_value=1,
                max_value=total_commits,
                value=(start_commit, end_commit),
                key="inf_range_slider",
                help="Pick the range of commits (1 = newest)",
            )
            inf_start, inf_end = inf_range
        else:
            inf_start_ref = st.text_input("Older commit ref", value=baseline_ref or "", key="inf_older")
            inf_end_ref = st.text_input("Newer commit ref", value=current_ref or "", key="inf_newer")
            inf_start, inf_end = None, None  # handled via refs

    with inf_col2:
        run_inference = st.button(
            "⚡ Run Inference", type="primary", use_container_width=True, key="run_inf"
        )

    # ── Execution ─────────────────────────────────────────
    if run_inference:
        with st.spinner("Cloning repo & computing pairwise diffs…"):
            # Fetch commits
            if use_index_range:
                inf_commits = extract_commits_by_range(
                    repo_url, inf_start, inf_end, github_token or None
                )
            else:
                inf_commits = extract_commits_between_refs(
                    repo_url, inf_start_ref, inf_end_ref, github_token or None
                )

            if len(inf_commits) < 2:
                st.warning("Need at least 2 commits to produce pairwise inference.")
            else:
                st.success(f"Fetched **{len(inf_commits)}** commits — generating **{len(inf_commits)-1}** pairwise inferences.")

                pairs = get_pairwise_diffs(repo_url, inf_commits, github_token or None)

                if not pairs:
                    st.error("Could not compute diffs between commits.")
                else:
                    # Initialise LLM (reuses existing Azure / OpenAI config)
                    llm = LLMAnalyzer(api_key=openai_key_override or None)

                    progress = st.progress(0)
                    results = []

                    for idx, pair in enumerate(pairs):
                        inference_text = generate_commit_pair_inference(llm, pair)
                        results.append((pair, inference_text))
                        progress.progress((idx + 1) / len(pairs))

                    # Store in session for persistence across reruns
                    st.session_state["inference_results"] = results

    # ── Display results ───────────────────────────────────
    if "inference_results" in st.session_state and st.session_state["inference_results"]:
        results = st.session_state["inference_results"]
        st.divider()
        st.subheader(f"📋 Pairwise Inference  ({len(results)} pairs)")

        for idx, (pair, inference_text) in enumerate(results):
            older = pair["older"]
            newer = pair["newer"]
            label = (
                f"**{older['sha'][:8]}** → **{newer['sha'][:8]}**  ·  "
                f"{newer['message'][:70]}"
            )

            with st.expander(label, expanded=(idx == 0)):
                meta_col1, meta_col2, meta_col3 = st.columns([2, 2, 1])
                with meta_col1:
                    st.caption(f"**Author:** {newer['author']['name']}")
                with meta_col2:
                    st.caption(f"**Date:** {newer['date'][:10]}")
                with meta_col3:
                    st.caption(f"**Files:** {len(pair['changed_files'])}")

                # Show changed file list
                if pair["changed_files"]:
                    with st.popover("📂 Changed files"):
                        for f in pair["changed_files"]:
                            st.markdown(f"- `{f}`")

                st.markdown("---")
                st.markdown(inference_text)
    else:
        if not run_inference if 'run_inference' in dir() else True:
            st.info("Select a commit range above and click **⚡ Run Inference** to begin.")

with tab4:
    st.header("�📊 Test Reports")
    
    if ready_status and baseline_content and current_content:
        st.markdown("### 📄 Test Reports Preview")
        
        with st.expander("📊 Report Preview", expanded=True):
            if 'report' in st.session_state:
                report = st.session_state.report
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### Baseline")
                    baseline_metrics = report["test_summary"]["baseline"]
                    st.metric("Total", baseline_metrics["total"])
                    st.metric("Passed", baseline_metrics["passed"])
                    st.metric("Failed", baseline_metrics["failed"])
                
                with col2:
                    st.markdown("#### Current")
                    current_metrics = report["test_summary"]["current"]
                    baseline_metrics = report["test_summary"]["baseline"]
                    st.metric("Total", current_metrics["total"])
                    st.metric("Passed", current_metrics["passed"], 
                             delta=current_metrics["passed"] - baseline_metrics["passed"])
                    st.metric("Failed", current_metrics["failed"], 
                             delta=current_metrics["failed"] - baseline_metrics["failed"], 
                             delta_color="inverse")
            else:
                st.info("Run analysis to see report comparison")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👁️ View Baseline Report", use_container_width=True):
                st.session_state['show_baseline'] = not st.session_state.get('show_baseline', False)
        
        with col2:
            if st.button("👁️ View Current Report", use_container_width=True):
                st.session_state['show_current'] = not st.session_state.get('show_current', False)
        
        if st.session_state.get('show_baseline', False):
            st.markdown("#### Baseline Report")
            try:
                baseline_data = json.loads(baseline_content)
                st.json(baseline_data)
            except:
                st.code(baseline_content, language="json")
        
        if st.session_state.get('show_current', False):
            st.markdown("#### Current Report")
            try:
                current_data = json.loads(current_content)
                st.json(current_data)
            except:
                st.code(current_content, language="json")
    else:
        if use_commit_range:
            st.info("Upload test reports in the sidebar to view them here")
        else:
            st.warning("No reports found in dataset. Place JSON reports in html-reports/ folder")

with tab5:
    st.header("📜 History")
    
    if 'report' in st.session_state:
        report = st.session_state.report
        
        st.subheader("📝 Code Changes")
        for file_change in report["detailed_file_changes"][:10]:
            with st.expander(f"📄 {file_change['file_path']}"):
                st.caption(file_change['summary'])
                
                for line_change in file_change["line_changes"][:5]:
                    if line_change['change_type'] == 'modified':
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Line {line_change['line_number']} (Before)**")
                            st.code(line_change.get('old_content', ''), language="text")
                        with col2:
                            st.markdown(f"**Line {line_change['line_number']} (After)**")
                            st.code(line_change.get('new_content', ''), language="text")
        
        st.divider()
        
        st.subheader("📥 Export Report")
        report_json = json.dumps(report, indent=2, default=str)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📥 Download JSON",
                data=report_json,
                file_name=f"analysis_{st.session_state.analysis_timestamp.replace(' ', '_').replace(':', '-')}.json" if st.session_state.analysis_timestamp else "analysis.json",
                mime="application/json",
                use_container_width=True
            )
        
        with col2:
            markdown_summary = f"""# QA Intelligence Report
Generated: {st.session_state.analysis_timestamp}

{report["executive_summary"]}

## Key Findings
{chr(10).join(f"- {f}" for f in report.get("key_findings", []))}
"""
            st.download_button(
                "📄 Download Markdown",
                data=markdown_summary,
                file_name=f"summary_{st.session_state.analysis_timestamp.replace(' ', '_').replace(':', '-')}.md" if st.session_state.analysis_timestamp else "summary.md",
                mime="text/markdown",
                use_container_width=True
            )
    else:
        st.info("Run analysis first to see history and export options")