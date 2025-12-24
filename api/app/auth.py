import os
from fastapi import Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

def require_extension_token(x_extension_token: str = Header(default="")):
    expected = os.getenv("EXTENSION_TOKEN","")
    # if not expected:
    #     raise HTTPException(500, "EXTENSION_TOKEN not set")
    # if x_extension_token != expected:
    #     raise HTTPException(401, "Invalid extension token")
