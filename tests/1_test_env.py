"""Test 1: Verify environment variables are loaded correctly."""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

def test_env_variables():
    print("=" * 60)
    print("TEST 1: Environment Variables Check")
    print("=" * 60)
    
    # Load .env file
    print("\n📂 Loading .env file...")
    load_dotenv()
    print("✓ .env file loaded")
    
    # Check Azure OpenAI variables
    print("\n🔵 Azure OpenAI Configuration:")
    azure_vars = {
        "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "AZURE_OPENAI_KEY": os.getenv("AZURE_OPENAI_KEY"),
        "AZURE_OPENAI_DEPLOYMENT": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        "AZURE_OPENAI_API_VERSION": os.getenv("AZURE_OPENAI_API_VERSION")
    }
    
    all_azure_set = True
    for key, value in azure_vars.items():
        if value:
            display_value = value if "KEY" not in key else f"{value[:10]}...{value[-4:]}"
            print(f"  ✅ {key}: {display_value}")
        else:
            print(f"  ❌ {key}: NOT SET")
            all_azure_set = False
    
    # Check GitHub token
    print("\n🐙 GitHub Configuration:")
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        print(f"  ✅ GITHUB_TOKEN: {github_token[:10]}...{github_token[-4:]}")
    else:
        print(f"  ⚠️  GITHUB_TOKEN: NOT SET (needed for private repos)")
    
    # Check OpenAI (fallback)
    print("\n🟢 OpenAI Configuration (Fallback):")
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        print(f"  ✅ OPENAI_API_KEY: {openai_key[:10]}...{openai_key[-4:]}")
    else:
        print(f"  ⚠️  OPENAI_API_KEY: NOT SET")
    
    # Summary
    print("\n" + "=" * 60)
    if all_azure_set:
        print("✅ TEST PASSED: All Azure OpenAI variables are set")
        print("   You can proceed to Test 2")
    else:
        print("❌ TEST FAILED: Some Azure OpenAI variables are missing")
        print("   Fix your .env file before proceeding")
    print("=" * 60)
    
    return all_azure_set

if __name__ == "__main__":
    test_env_variables()