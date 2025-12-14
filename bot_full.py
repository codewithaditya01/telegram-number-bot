from supabase import create_client, Client
import phonenumbers
from phonenumbers import geocoder, carrier, PhoneNumberFormat

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters


# ----------------------------------------------------
# SUPABASE CONFIG
# ----------------------------------------------------
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------------------------------------------------
# NORMALIZE NUMBER
# ----------------------------------------------------
def normalize_number(raw_input, default_region="IN"):
    try:
        if default_region and not raw_input.startswith("+"):
            parsed = phonenumbers.parse(raw_input, default_region)
        else:
            parsed = phonenumbers.parse(raw_input)
        if not phonenumbers.is_possible_number(parsed):
            return None
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except:
        return None


# ----------------------------------------------------
# LOOKUP NAME FROM CLOUD DB
# ----------------------------------------------------
def lookup_owner(e164):
    result = supabase.table("numbers").select("*").eq("number", e164).execute()
    if result.data:
        return result.data[0]
    return None


# ----------------------------------------------------
# INSERT OR UPDATE NAME IN CLOUD DB
# ----------------------------------------------------
def save_owner(e164, name, location=None):
    supabase.table("numbers").upsert({
        "number": e164,
        "owner": name,
        "location": location
    }).execute()


# ----------------------------------------------------
# FORMAT INFO FOR TELEGRAM
# ----------------------------------------------------
def format_info(e164):
    db_entry = lookup_owner(e164)

    parsed = phonenumbers.parse(e164)
    sim_car = carrier.name_for_number(parsed, "en") or "Unknown"
    sim_loc = geocoder.description_for_number(parsed, "en") or "Unknown"

    message = "📞 *Phone Number Information*\n\n"
    message += f"• *Number:* `{e164}`\n"

    if db_entry:
        message += f"• *Owner:* {db_entry['owner']}\n"
        if db_entry.get("location"):
            message += f"• *Saved Location:* {db_entry['location']}\n"
    else:
        message += "• *Owner:* Not in database\n"

    message += f"• *Carrier:* {sim_car}\n"
    message += f"• *Location:* {sim_loc}\n"

    if not db_entry:
        message += f"\nTo add name:\n`/add {e164} OwnerName`"

    return message


# ----------------------------------------------------
# TELEGRAM HANDLERS
# ----------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cloud bot active! Send a phone number.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    e164 = normalize_number(raw)

    if not e164:
        await update.message.reply_text("Invalid number format.")
        return

    message = format_info(e164)
    await update.message.reply_markdown(message)


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        number = context.args[0]
        name = " ".join(context.args[1:])
    except:
        await update.message.reply_text("Use format: /add +91XXXXXXXXXX Name")
        return

    e164 = normalize_number(number)
    if not e164:
        await update.message.reply_text("Invalid number format.")
        return

    save_owner(e164, name)
    await update.message.reply_text(f"✔ Saved to cloud:\n{e164} → {name}")


# ----------------------------------------------------
# RUN BOT
# ----------------------------------------------------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("☁️ Cloud Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
