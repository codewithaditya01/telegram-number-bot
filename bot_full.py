import os
import logging
import threading
from flask import Flask

import phonenumbers
from phonenumbers import geocoder, carrier, PhoneNumberFormat

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from supabase import create_client


# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO)


# ================= DUMMY WEB SERVER =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"


def run_web():
    app.run(host="0.0.0.0", port=PORT)


# ================= BOT HELPERS =================
def normalize_number(raw, region="IN"):
    try:
        parsed = phonenumbers.parse(raw, region if not raw.startswith("+") else None)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except Exception:
        return None


def get_owner(number):
    res = supabase.table("numbers").select("owner").eq("number", number).execute()
    if res.data:
        return res.data[0]["owner"]
    return None


def save_owner(number, owner):
    supabase.table("numbers").upsert({
        "number": number,
        "owner": owner
    }).execute()


def build_message(number):
    parsed = phonenumbers.parse(number)
    loc = geocoder.description_for_number(parsed, "en") or "Unknown"
    car = carrier.name_for_number(parsed, "en") or "Unknown"
    owner = get_owner(number)

    msg = (
        "━━━━━━━━━━━━━━━━━━━\n"
        "📞 *PHONE NUMBER DETAILS*\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 *Number*\n`{number}`\n\n"
        f"📡 *Carrier*\n{car}\n\n"
        f"🌍 *Location*\n{loc}\n\n"
    )

    if owner:
        msg += f"👤 *Owner Name*\n{owner}\n\n"
    else:
        msg += (
            "👤 *Owner Name*\n_Not available_\n\n"
            f"➕ Add using:\n`/add {number} Name`\n\n"
        )

    msg += "━━━━━━━━━━━━━━━━━━━"
    return msg


# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome!*\n\n"
        "Send a phone number to get details.\n\n"
        "Example:\n`+919876543210`",
        parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = normalize_number(update.message.text)
    if not number:
        await update.message.reply_text("❌ Invalid phone number.")
        return
    await update.message.reply_markdown(build_message(number))


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage:\n/add +91XXXXXXXXXX Name")
        return

    number = normalize_number(context.args[0])
    if not number:
        await update.message.reply_text("❌ Invalid number.")
        return

    owner = " ".join(context.args[1:])
    save_owner(number, owner)
    await update.message.reply_text(f"✅ Saved:\n{number} → {owner}")


# ================= MAIN =================
def main():
    # Start dummy web server
    threading.Thread(target=run_web, daemon=True).start()

    # Start Telegram bot
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("add", add))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logging.info("🤖 Bot is running 24/7")
    app_bot.run_polling()


if __name__ == "__main__":
    main()
