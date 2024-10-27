from passlib.context import CryptContext
from datetime import timedelta, datetime
from src.config import Config
import uuid
import jwt
import logging

password_ctx = CryptContext(schemes=["scrypt"])

ACCESS_TOKEN_EXPIRY = 3600


def generate_password_hash(password: str) -> str:
    return password_ctx.hash(password)


def verify_password(password: str, hash: str) -> bool:
    return password_ctx.verify(password, hash)


def create_access_token(player_data: dict, expiry: timedelta = None, refresh: bool = False):
    expiry = timedelta(seconds=ACCESS_TOKEN_EXPIRY) if expiry is None else expiry
    
    payload = {"player": player_data, "exp": datetime.now() + expiry}
    payload['jti'] = str(uuid.uuid4())
    payload['refresh'] = refresh

    token = jwt.encode(
        payload=payload, key=Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM
    )
    return token


def decode_token(token: str) -> dict:
    try:
        token_data = jwt.decode(jwt=token, key=Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
        return token_data
    except jwt.PyJWTError as e:
        logging.exception(e)
        return None