from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # APIキー (環境変数から読み込まれます)
    amivoice_appkey: str
    gemini_api_key: str
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None

    # Google Gemini 設定
    # gemini_model: str = "gemini-2.0-flash-exp" # 旧モデル
    gemini_model: str = "gemini-2.5-flash-lite"
    
    # AmiVoice 設定
    amivoice_url: str = "wss://acp-api.amivoice.com/v1/"
    
    # Twilio / Conversation Relay 設定
    # Voice: ja-JP-Neural2-B または ja-JP-Chirp3-HD-Aoede
    twilio_voice_name: str = "ja-JP-Chirp3-HD-Aoede"
    
    # 言語設定デフォルト
    language_code: str = "ja-JP"
    tts_provider: str = "google"
    transcription_provider: str = "google"
    speech_model: str = "long"

    class Config:
        env_file = ".env"
        # pydantic-settings では環境変数はデフォルトで大文字小文字を区別しません
        # 通常はフィールド名と一致させます (大文字小文字無視)
        # 例: AMIVOICE_APPKEY -> amivoice_appkey

settings = Settings()
