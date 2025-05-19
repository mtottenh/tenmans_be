from config import Config
from state.service import StateService


state_service = StateService(Config.REDIS_URL)
