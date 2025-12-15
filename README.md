# AmiVoice STT on Conversation Relay with Gemini

Twilio Media Streams、AmiVoice、Google Gemini、および Twilio Conversation Relay を組み合わせた、リアルタイム日本語音声対話ボットのデモ実装です。
ConversatoinRelayを単独で利用すると、音声認識エンジンとしてGoogleとDeepgramのみが利用可能ですが、AmiVoiceと組み合わせることで、日本語のより優れた音声認識を可能にします。

## 特徴

*   **音声認識 (STT):** [AmiVoice API](https://acp.amivoice.com/) を使用し、高精度な日本語認識を実現（Twilio Media Streams経由）。
*   **AI 応答 (LLM):** [Google Gemini API](https://ai.google.dev/) (Flash Lite) を使用し、コンテキストを保持した自然な会話が可能。
*   **音声合成 (TTS):** [Twilio Conversation Relay](https://www.twilio.com/docs/voice/conversation-relay) を使用し、Google Neural2/Chirp 音声による高品質な発話を実現。
*   **アーキテクチャ:** 入力（Media Stream）と出力（Conversation Relay）を分けるハイブリッド構成により、柔軟な制御と低遅延を両立。

## 必要要件

*   Python 3.10+
*   Twilio アカウント
*   AmiVoice API APPKEY
*   Google Gemini API Key
*   ngrok (ローカル開発用)

## セットアップ

1.  **リポジトリをクローン**
    ```bash
    git clone <repository-url>
    cd <repository-name>
    ```

2.  **依存関係のインストール**
    ```bash
    pip install -r requirements.txt
    ```

3.  **環境変数の設定**
    `.env.example` をコピーして `.env` を作成し、各APIキーを設定してください。
    ```bash
    cp .env.example .env
    ```
    
    `.env` の内容:
    ```ini
    AMIVOICE_APPKEY=your_amivoice_appkey
    GEMINI_API_KEY=your_gemini_api_key
    TWILIO_ACCOUNT_SID=...
    TWILIO_AUTH_TOKEN=...
    ```

    **Config設定:**
    `config.py` にて、使用するモデルやボイス、言語設定などのデフォルト値を変更可能です。

## 実行方法

1.  **サーバーの起動**
    ```bash
    python main.py
    # または
    uvicorn main:app --reload
    ```
    サーバーは `http://localhost:8000` で起動します。

2.  **ngrok で公開** (別ターミナル)
    ```bash
    ngrok http 8000
    ```
    出力されたHTTPSのURL（例: `https://xxxx-xxxx.ngrok-free.app`）をコピーします。

3.  **Twilio の設定**
    *   Twilio Console で電話番号設定ページを開きます。
    *   "Voice & Fax" セクションの **A Call Comes In** Webhook に、上記のngrok URLに `/voice` を付与したものを設定します。
        *   例: `https://xxxx-xxxx.ngrok-free.app/voice`
    *   HTTPメソッドは `POST` を選択し、保存します。

4.  **電話をかける**
    設定したTwilio番号に電話をかけ、AIとの会話を開始してください。

## ファイル構成

*   `main.py`: FastAPIサーバー。Twilio Webhookのハンドリング、WebSocketセッション管理を行う中核モジュール。
*   `amivoice_client.py`: AmiVoice WebSocket API との通信クライアント。
*   `llm_client.py`: Google Gemini API とのチャットセッション管理クライアント。
*   `config.py`: アプリケーション設定の一元管理 (Pydantic利用)。