from google import genai
from google.genai import types
import os
from .config import settings

class LLMClient:
    def __init__(self, api_key: str):
        # Google GenAI クライアントを初期化
        self.client = genai.Client(api_key=api_key)
        # 高速な会話用モデルを使用
        self.model = settings.gemini_model
        self.system_instruction = "あなたはプロフェッショナルで、電話応対を行うスペシャリストです。回答は全て短文でわかりやすく話してください。"
        self.chat = None

    async def generate_response(self, user_text: str):
        """
        ユーザーの入力を基に、セッション履歴を保持しながらGeminiから応答を生成します。
        """
        try:
            # チャットセッションの遅延初期化
            if self.chat is None:
                self.chat = self.client.aio.chats.create(
                    model=self.model,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction
                    )
                )

            # 既存のチャットセッションにメッセージを送信
            response = await self.chat.send_message(user_text)
            return response.text
        except Exception as e:
            print(f"Gemini error: {e}")
            return "申し訳ありません、エラーが発生しました。"
