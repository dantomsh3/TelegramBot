import os
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from bot import start, handle_text  # עדכן לפי הפונקציות שלך

def run():
    TOKEN = os.environ["BOT_TOKEN"]      # יגיע מהגדרות Render
    APP_URL = os.environ["APP_URL"]      # הכתובת שתינתן לך אחרי הפריסה

    app = ApplicationBuilder().token(TOKEN).build()

    # רשום את אותם handlers שיש לך
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # הפעלת Webhook
    port = int(os.environ.get("PORT", "10000"))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}",
        drop_pending_updates=True
    )

if __name__ == "__main__":
    run()
