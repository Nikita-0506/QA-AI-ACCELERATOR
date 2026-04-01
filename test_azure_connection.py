"""Test Azure OpenAI connection."""
import os
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

def test_azure_connection():
    """Test if Azure OpenAI is properly configured and working."""
    
    print("=" * 60)
    print("Testing Azure OpenAI Connection")
    print("=" * 60)
    
    # Get configuration
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    key = os.getenv("AZURE_OPENAI_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    
    # Check configuration
    print("\n📋 Configuration Check:")
    print(f"  Endpoint: {'✅ Set' if endpoint else '❌ Missing'}")
    if endpoint:
        print(f"    → {endpoint}")
    
    print(f"  API Key: {'✅ Set' if key else '❌ Missing'}")
    if key:
        print(f"    → {key[:10]}...{key[-4:]}")
    
    print(f"  Deployment: {'✅ Set' if deployment else '❌ Missing'}")
    if deployment:
        print(f"    → {deployment}")
    
    print(f"  API Version: {'✅ Set' if api_version else '❌ Missing'}")
    if api_version:
        print(f"    → {api_version}")
    
    # Check if all required vars are set
    if not all([endpoint, key, deployment]):
        print("\n❌ ERROR: Missing required Azure OpenAI configuration!")
        print("\nRequired variables in .env:")
        print("  - AZURE_OPENAI_ENDPOINT")
        print("  - AZURE_OPENAI_KEY")
        print("  - AZURE_OPENAI_DEPLOYMENT")
        print("  - AZURE_OPENAI_API_VERSION (optional)")
        return False
    
    # Try to connect
    print("\n🔌 Testing Connection...")
    
    try:
        client = AzureOpenAI(
            api_key=key,
            api_version=api_version or "2024-12-01-preview",
            azure_endpoint=endpoint
        )
        
        print("  → Client initialized successfully")
        
        # Test with a simple API call
        print("\n🤖 Sending test message...")
        
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "user", "content": "Say 'Hello, Azure OpenAI is working!' in one sentence."}
            ],
            max_tokens=50,
            temperature=0.3
        )
        
        result = response.choices[0].message.content
        
        print("\n✅ SUCCESS! Azure OpenAI is working!")
        print(f"\n🎉 Response from {deployment}:")
        print(f"  → {result}")
        
        print("\n" + "=" * 60)
        print("✅ All checks passed! Your Azure OpenAI is ready to use.")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("  1. Verify your Azure OpenAI endpoint URL is correct")
        print("  2. Check your API key is valid and not expired")
        print("  3. Confirm the deployment name matches your Azure portal")
        print("  4. Ensure your API version is supported")
        print("\n📖 Check Azure Portal → Your OpenAI Resource → Keys and Endpoint")
        return False

if __name__ == "__main__":
    test_azure_connection()