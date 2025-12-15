import asyncio
import websockets
import json
import audioop
from typing import Callable, Awaitable
from .config import settings

class AmiVoiceClient:
    """
    AmiVoice WebSocket API クライアント
    音声データをリアルタイムで送信し、認識結果を受信します
    """
    def __init__(self, app_key: str, on_message: Callable[[dict], Awaitable[None]] = None):
        self.app_key = app_key
        self.url = settings.amivoice_url
        self.ws = None
        self.on_message = on_message
        self.state = None # audioopの状態保持用 (現在は使用していません)

    async def connect(self):
        """Websocket接続を確立し、初期コマンドを送信します"""
        print(f"Connecting to AmiVoice...")
        self.ws = await websockets.connect(self.url)
        
        # スタートコマンド送信
        # s <format> <options>
        # MULAW: 8kHz mu-law形式 (Twilioからの音声をそのまま使用)
        # -a-general: 汎用会話モデル
        # output=json: 結果をJSONで受け取る
        # resultUpdatedInterval=500: 途中経過を500ms間隔で受け取る (これがないと'U'イベントが来ない)
        command = f"s MULAW -a-general authorization={self.app_key} output=json resultUpdatedInterval=500"
        await self.ws.send(command)
        print("Connected to AmiVoice and sent start command (MULAW).")
        
        # 受信ループをバックグラウンドで開始
        asyncio.create_task(self.receive_loop())

    async def send_audio(self, mulaw_chunk: bytes):
        """
        8kHz Mulaw音声データを直接AmiVoiceへ送信します
        """
        if not self.ws:
            return

        try:
            # プロトコル: 'p' (0x70) + バイナリ音声データ
            # トランスコードは不要 (AmiVoiceがMULAWをネイティブサポート)
            await self.ws.send(b'p' + mulaw_chunk)
            
        except Exception as e:
            print(f"Error sending audio to AmiVoice: {e}")

    async def receive_loop(self):
        """AmiVoiceからのメッセージ受信ループ"""
        if not self.ws:
            return
            
        try:
            async for message in self.ws:
                if self.on_message:
                    # メッセージ形式: "code json_data" (例: "A {...}") または "code" (例: "s")
                    # 単なるJSONのケースもあり得ます
                    
                    text_msg = message
                    if isinstance(message, bytes):
                        text_msg = message.decode('utf-8')

                    # 1. JSONを含まない単一コードのチェック (s, S, C, e, E 等)
                    if len(text_msg) <= 3 and text_msg.strip() in ['s', 'S', 'C', 'e', 'E']:
                         # ステータス通知などはログ出力または無視
                         # print(f"AmiVoice Status: {text_msg}")
                         continue

                    # 2. "Code JSON" 形式のチェック (例: "A {...}")
                    if len(text_msg) > 2 and text_msg[1] == ' ':
                        code = text_msg[0]
                        json_str = text_msg[2:]
                        try:
                            data = json.loads(json_str)
                            
                            if isinstance(data, dict):
                                data['code'] = code
                            else:
                                data = {'code': code, 'payload': data}
                            
                            await self.on_message(data)
                            continue
                        except json.JSONDecodeError:
                            print(f"AmiVoice Non-JSON body: {text_msg}")
                    
                    # 3. 通常のJSON形式としてパース (フォールバック)
                    try:
                        data = json.loads(text_msg)
                        await self.on_message(data)
                    except json.JSONDecodeError:
                        print(f"AmiVoice Non-JSON received: {text_msg}")
        except websockets.exceptions.ConnectionClosed:
            print("AmiVoice connection closed.")
        except Exception as e:
            print(f"AmiVoice receive error: {e}")
            
    async def close(self):
        """接続を切断し、終了コマンドを送ります"""
        if self.ws:
            try:
                await self.ws.send('e') # 終了コマンド
                await self.ws.close()
            except:
                pass
            self.ws = None
