"""Enhanced Streamlit UI with detailed analysis display."""
import streamlit as st
import os
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.git_repo import GitRepoAnalyzer
from agent.parsers import CucumberJsonParser
from agent.report_builder_enhanced import EnhancedReportBuilder
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="QA Intelligence Agent - Enhanced",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 QA Intelligence Agent - Enhanced Analysis")
st.markdown("**AI-powered analysis that explains exactly what changed and why tests failed**")

# Sidebar
with st.sidebar:
    st.header("Configuration")
    
    repo_url = st.text_input(
        "Git Repository URL",
        value="https://github.com/Inadev-Data-Lab/QA_Playwright_Repo",
    )
    
    github_token = st.text_input(
        "GitHub Token (optional)",
        type="password",
        value=os.getenv("GITHUB_TOKEN", ""),
    )
    
    openai_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=os.getenv("OPENAI_API_KEY", ""),
        help="Required for AI-powered analysis. Get one at https://platform.openai.com/"
    )
    
    baseline_ref = st.text_input("Baseline Ref", value="36f96ae5")
    current_ref = st.text_input("Current Ref", value="1ea635a0")
    
    st.divider()
    
    baseline_json = st.file_uploader("Baseline Report (JSON)", type=["json"])
    current_json = st.file_uploader("Current Report (JSON)", type=["json"])
    
    analyze_button = st.button("🔍 Analyze", type="primary", use_container_width=True)

# Main content
if analyze_button:
    if not baseline_json or not current_json:
        st.error("Please upload both reports")
        st.stop()
    
    with st.spinner("🔎 Analyzing repository and generating AI insights..."):
        try:
            # Parse reports
            baseline_content = baseline_json.read().decode('utf-8')
            current_content = current_json.read().decode('utf-8')
            
            baseline_summary = CucumberJsonParser.parse(baseline_content)
            current_summary = CucumberJsonParser.parse(current_content)
            
            # Git analysis
            with GitRepoAnalyzer(repo_url, github_token or None) as git:
                commits = git.get_commits_between(baseline_ref, current_ref)
                raw_changes = git.get_diff(baseline_ref, current_ref)
                
                # Build enhanced report
                report_builder = EnhancedReportBuilder(openai_api_key=openai_key or None)
                
                # Find regressions
                from agent.analyzers.compare_runs import RunComparator
                regressions = RunComparator.find_regressions(baseline_summary, current_summary)
                improvements = RunComparator.find_improvements(baseline_summary, current_summary)
                duration_regressions = RunComparator.find_duration_regressions(baseline_summary, current_summary)
                
                report = report_builder.build_detailed_report(
                    repo_url=repo_url,
                    baseline_commit=baseline_ref,
                    current_commit=current_ref,
                    baseline_summary=baseline_summary,
                    current_summary=current_summary,
                    commits=commits,
                    raw_file_changes=raw_changes,
                    regressions=regressions,
                    improvements=improvements,
                    duration_regressions=duration_regressions
                )
                
                st.session_state.report = report
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.exception(e)
            st.stop()

# Display results
if 'report' in st.session_state:
    report = st.session_state.report
    
    # Executive Summary
    st.header("📊 Executive Summary")
    st.info(report["executive_summary"])
    
    # Key Findings
    if report.get("key_findings"):
        st.header("🔍 Key Findings")
        for finding in report["key_findings"]:
            st.warning(finding)
    
    # Detailed tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "💥 Failures Analysis",
        "📝 Code Changes",
        "📈 Metrics",
        "📥 Export"
    ])
    
    with tab1:
        st.header("Detailed Failure Analysis")
        
        for regression in report["regressions"]:
            with st.expander(f"❌ {regression['scenario_name']}", expanded=True):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("Analysis")
                    analysis = regression.get("analysis", {})
                    
                    if analysis.get("analysis_type") == "llm_powered":
                        st.success("🤖 AI-Powered Analysis")
                    else:
                        st.info("📊 Rule-Based Analysis")
                    
                    st.markdown(analysis.get("detailed_explanation", "No analysis available"))
                
                with col2:
                    st.subheader("Metrics")
                    st.metric(
                        "Duration Change",
                        f"{regression['current_duration_ms']:.0f}ms",
                        f"+{regression['current_duration_ms'] - regression['baseline_duration_ms']:.0f}ms"
                    )
                    
                    st.subheader("Error Details")
                    with st.expander("View full error"):
                        st.code(regression.get("error_message", "No error message"), language="text")
    
    with tab2:
        st.header("Detailed Code Changes")
        
        for file_change in report["detailed_file_changes"]:
            with st.expander(f"📄 {file_change['file_path']} ({file_change['change_type']})"):
                st.caption(file_change['summary'])
                
                for line_change in file_change["line_changes"][:10]:  # Show first 10 changes
                    st.markdown(f"**Line {line_change['line_number']}** - _{line_change['change_type']}_")
                    
                    if line_change['change_type'] == 'modified':
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Before:**")
                            st.code(line_change.get('old_content', ''), language="text")
                        with col2:
                            st.markdown("**After:**")
                            st.code(line_change.get('new_content', ''), language="text")
                    
                    elif line_change['change_type'] == 'added':
                        st.markdown("**Added:**")
                        st.code(line_change.get('new_content', ''), language="text")
                    
                    elif line_change['change_type'] == 'removed':
                        st.markdown("**Removed:**")
                        st.code(line_change.get('old_content', ''), language="text")
                    
                    st.divider()
    
    with tab3:
        st.header("Test Metrics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Baseline")
            metrics = report["test_summary"]["baseline"]
            st.metric("Total", metrics["total"])
            st.metric("Passed", metrics["passed"])
            st.metric("Failed", metrics["failed"])
        
        with col2:
            st.subheader("Current")
            metrics = report["test_summary"]["current"]
            baseline_metrics = report["test_summary"]["baseline"]
            st.metric("Total", metrics["total"])
            st.metric("Passed", metrics["passed"], delta=metrics["passed"] - baseline_metrics["passed"])
            st.metric("Failed", metrics["failed"], delta=metrics["failed"] - baseline_metrics["failed"], delta_color="inverse")
    
    with tab4:
        st.header("Export Report")
        
        import json
        report_json = json.dumps(report, indent=2, default=str)
        
        st.download_button(
            label="📥 Download Full Report (JSON)",
            data=report_json,
            file_name="intelligence-report-enhanced.json",
            mime="application/json",
            use_container_width=True
        )
else:
    st.info("""
    ### 👋 Welcome to the Enhanced QA Intelligence Agent!
    
    This tool provides:
    - **Line-by-line code analysis**: See exactly what changed and where
    - **AI-powered explanations**: Understand why tests failed in plain English
    - **Root cause analysis**: Connect code changes to test failures
    - **Actionable recommendations**: Get specific steps to fix issues
    
    **To get started:**
    1. Enter your repository details and commit refs
    2. Add an OpenAI API key for AI-powered analysis (optional but recommended)
    3. Upload your baseline and current test reports
    4. Click Analyze
    
    The agent will analyze your code changes and explain everything in human-friendly language!
    """)