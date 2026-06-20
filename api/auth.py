import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

security = HTTPBearer()
SECRET = os.environ.get("INTERNAL_JWT_SECRET", "")


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        jwt.decode(credentials.credentials, SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid internal token") from None
