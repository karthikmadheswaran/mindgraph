import jwt
import sentry_sdk
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
import os
from dotenv import load_dotenv

load_dotenv()

# --- Step 3 from our diagram: the "magnifying glass" ---
# This fetches the public key from your Supabase JWKS endpoint
# and caches it automatically so we don't hit Supabase on every request
SUPABASE_URL = os.getenv("SUPABASE_URL")
jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
jwks_client = PyJWKClient(jwks_url)

# This tells FastAPI to look for "Authorization: Bearer <token>" in headers
security = HTTPBearer()


async def get_current_user(credentials=Depends(security)) -> str:
    """
    The "door guy" — verifies the token and returns user_id.
    This runs before every protected endpoint.
    """
    token = credentials.credentials

    try:
        # Get the public key that matches this token's "kid" (key ID)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Verify signature + decode the token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )

        # Extract user_id from the "sub" claim
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        sentry_sdk.set_user({"id": user_id})
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")