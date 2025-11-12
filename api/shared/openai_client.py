import os
from openai import AzureOpenAI

def get_client() -> AzureOpenAI:
  return AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_KEY"],
    api_version="2025-03-01-preview",
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
  )
