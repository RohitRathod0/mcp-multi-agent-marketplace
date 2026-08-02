import os
from dotenv import load_dotenv

# Reasoning: Load environment variables from .env file at startup.
# This keeps all secrets out of source code.
load_dotenv()

# Reasoning: Single place to access all config so any file can just import from here.
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "mistral-large-latest")

# Reasoning: Validate at import time so errors surface immediately on startup.
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY is not set. Please add it to your .env file.")
