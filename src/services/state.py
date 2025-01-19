from state.service import StateService
from config import Config
state_service = StateService(Config.REDIS_URL)