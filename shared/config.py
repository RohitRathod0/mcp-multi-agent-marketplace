import os
from dotenv import load_dotenv

# Reasoning: Load environment variables from .env file at startup.
# This keeps all secrets out of source code.
load_dotenv()

# Reasoning: Single place to access all config so any file can just import from here.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022")

# Reasoning: Validate at import time so errors surface immediately on startup.
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is not set. Please add it to your .env file.")
