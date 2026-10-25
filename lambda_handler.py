"""
Entry point for AWS Lambda.

API Gateway sends the request to Lambda.
Mangum connects the request to FastAPI.
"""

from mangum import Mangum

from api import app

# FastAPI does not need startup or shutdown events
handler = Mangum(app, lifespan="off")
