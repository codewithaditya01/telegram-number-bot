import os
import logging
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

from supabase import create_client, Client


# --------------------------------------------------
# ENVIRONMENT VARIABLES (DO NOT HARDCODE)
# --------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing environment variables")


# --------------------------------------------------
# SUPABASE CLIENT (v2+ compatible)
# --------------------------------------------------
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# UTIL: Normalize phone number
# --------------------------------------------------
def normalize_number(raw: str, default_region="IN"):
    try:
        if not raw.startswith("+"):
            parsed = phonenumbers.parse(raw, default_region)
        else:
            parsed = phonenumbers.parse(raw)

        if not phonenumbers.is_valid_number(parsed):
            return None

        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except Exception:
        return None


# --------------------------------------------------
# DATABASE FUNCTIONS
# --------------------------------------------------
def get_owner_from_db(number: str):
    result = supabase.table("numbers").select("*").eq("number", number).execute()
    if result.data:
        return result.data[0]
    return None


def save_owner_to_db(number: str, owner: str):
    supabase.table("numbers").upsert({
        "number": number,
        "owner": owner
    }).execute()


# --------------------------------------------------
# FORMAT RESPONSE
# --------------------------------------------------
def build_response(e164: str):
    parsed = phonenumbers.parse(e164)
    location = geocoder.description_for_number(parsed, "en") or "Unknown"
    sim_carrier = carrier.name_for_number(parsed, "en") or "Unknown"

    db_entry = get_owner_from_db(e164)

    msg = "📞 *Phone Number Information*\n\n"
    msg += f"• *Number:* `{e164}`\n"
    msg += f"• *Carrier:* {sim_carrier}\n"
    msg += f"• *Location:* {location}\n"

    if db_entry and db_entry.get("owner"):
        msg += f"• *Owner Name:* {db_entry['owner']}\n"
    else:
        msg += "• *Owner Name:* Not available\n"
        msg += f"\n➕ Add name using:\n`/add {e164} Name`\n"

    return msg


# --------------------------------------------------
# TELEGRAM HANDLERS
# --------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot is running 24/7\n\n"
        "Send a phone number (with or without country code)."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    e164 = normalize_number(text)

    if not e164:
        await update.message.reply_text("❌ Invalid phone number format.")
        return

    response = build_response(e164)
    await update.message.reply_markdown(response)


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage:\n/add +91XXXXXXXXXX Name")
        return

    number = context.args[0]
    owner = " ".join(context.args[1:])

    e164 = normalize_number(number)
    if not e164:
        await update.message.reply_text("❌ Invalid number.")
        return

    save_owner_to_db(e164, owner)
    await update.message.reply_text(f"✅ Saved:\n{e164} → {owner}")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

