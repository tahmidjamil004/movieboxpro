import os
import re
import time
import asyncio
import threading
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pymongo import MongoClient
from flask import Flask, render_template_string

# --- CONFIGURATIONS ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", 0))
FORCE_JOIN = os.environ.get("FORCE_JOIN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
BASE_URL = os.environ.get("BASE_URL", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0)) 

# --- MONGODB SETUP ---
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
files_col = db["files"]
users_col = db["users"]
settings_col = db["settings"] 

DEFAULT_AD_1 = "https://adsterra.com/your-first-direct-link/"
DEFAULT_AD_2 = "https://adsterra.com/your-second-direct-link/"

# --- 18+ AUTO DETECTION KEYWORDS ---
ADULT_KEYWORDS = ['18+', 'xxx', 'porn', 'adult', 'hot', 'naked', 'erotic', '18 plus', 'nc-17']

# --- FUNCTION TO GET ADS FROM DB ---
def get_ad_links():
    ad1_doc = settings_col.find_one({"type": "ad_link_1"})
    ad2_doc = settings_col.find_one({"type": "ad_link_2"})
    link1 = ad1_doc["url"] if ad1_doc else DEFAULT_AD_1
    link2 = ad2_doc["url"] if ad2_doc else DEFAULT_AD_2
    return link1, link2

# --- FLASK WEB APP SETUP (2-Step Ads Verification) ---
app_web = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Movie Verification</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #121212; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: #1e1e1e; padding: 20px; border-radius: 10px; text-align: center; width: 90%; max-width: 400px; box-shadow: 0 0 10px rgba(0,0,0,0.5); }
        .btn { background-color: #007bff; color: white; padding: 15px; margin: 10px 0; border: none; border-radius: 5px; cursor: pointer; width: 100%; font-size: 16px; font-weight: bold; text-decoration: none; display: inline-block; }
        .btn:disabled { background-color: #555; cursor: not-allowed; }
        .btn-success { background-color: #28a745; }
        .timer { color: #ffcc00; font-size: 18px; font-weight: bold; }
        .step { margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #333; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🎬 Movie File Verification</h2>
        <p>ফাইল পেতে নিচের ২টি ধাপ সম্পন্ন করুন। (অ্যাড বাইপাস করা যাবে না)</p>
        
        <div class="step">
            <h3>Step 1</h3>
            <button id="ad1" class="btn" onclick="openAd1()">Watch Ad 1</button>
            <p id="timer1" class="timer" style="display:none;">Please wait <span id="count1">5</span> seconds...</p>
        </div>

        <div class="step">
            <h3>Step 2</h3>
            <button id="ad2" class="btn" disabled onclick="openAd2()">Watch Ad 2</button>
            <p id="timer2" class="timer" style="display:none;">Please wait <span id="count2">5</span> seconds...</p>
        </div>

        <div>
            <button id="finalBtn" class="btn btn-success" disabled onclick="getFile()">🚀 Get File</button>
        </div>
    </div>

    <script>
        let ad1Clicked = false;
        let ad2Clicked = false;

        function openAd1() {
            window.open("{{ ad_link_1 }}", "_blank");
            document.getElementById("ad1").disabled = true;
            document.getElementById("timer1").style.display = "block";
            let count = 5;
            const interval = setInterval(() => {
                count--;
                document.getElementById("count1").innerText = count;
                if (count <= 0) {
                    clearInterval(interval);
                    document.getElementById("timer1").style.display = "none";
                    document.getElementById("ad2").disabled = false;
                    ad1Clicked = true;
                }
            }, 1000);
        }

        function openAd2() {
            if (!ad1Clicked) return;
            window.open("{{ ad_link_2 }}", "_blank");
            document.getElementById("ad2").disabled = true;
            document.getElementById("timer2").style.display = "block";
            let count = 5;
            const interval = setInterval(() => {
                count--;
                document.getElementById("count2").innerText = count;
                if (count <= 0) {
                    clearInterval(interval);
                    document.getElementById("timer2").style.display = "none";
                    document.getElementById("finalBtn").disabled = false;
                    ad2Clicked = true;
                }
            }, 1000);
        }

        function getFile() {
            if (!ad2Clicked) return;
            window.location.href = "https://t.me/{{ bot_username }}?start=get_{{ file_id }}";
        }
    </script>
</body>
</html>
"""

@app_web.route('/verify/<file_id>')
def verify(file_id):
    link1, link2 = get_ad_links() 
    return render_template_string(
        HTML_TEMPLATE, 
        ad_link_1=link1, 
        ad_link_2=link2, 
        bot_username=BOT_USERNAME, 
        file_id=file_id
    )

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# --- PYROGRAM BOT SETUP ---
app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def is_joined(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_JOIN, user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

async def auto_delete(message: Message, delay_minutes=30):
    await asyncio.sleep(delay_minutes * 60)
    try:
        await message.delete()
    except:
        pass

# ==========================================
# 🛡️ ADMIN COMMANDS
# ==========================================

@app.on_message(filters.command("stats") & filters.user(OWNER_ID) & filters.private)
async def stats(client, message):
    total_users = users_col.count_documents({})
    total_files = files_col.count_documents({})
    link1, link2 = get_ad_links()
    await message.reply_text(
        f"**📊 CTG Movie Bot Stats 📊**\n\n"
        f"👥 **Total Users:** `{total_users}`\n"
        f"🎬 **Total Files:** `{total_files}`\n\n"
        f"🔗 **Current Ad Link 1:** `{link1}`\n"
        f"🔗 **Current Ad Link 2:** `{link2}`"
    )

@app.on_message(filters.command("index") & filters.user(OWNER_ID) & filters.private)
async def index_files(client, message):
    msg = await message.reply("⏳ Indexing files...")
    count = 0
    async for msg_obj in client.iter_history(LOG_CHANNEL):
        if msg_obj.document or msg_obj.video:
            file_name = msg_obj.document.file_name if msg_obj.document else msg_obj.video.file_name
            file_id = msg_obj.document.file_id if msg_obj.document else msg_obj.video.file_id
            file_type = "document" if msg_obj.document else "video"
            file_size = msg_obj.document.file_size if msg_obj.document else msg_obj.video.file_size
            
            if not files_col.find_one({"msg_id": msg_obj.message_id}):
                files_col.insert_one({
                    "file_name": file_name.lower(),
                    "file_id": file_id,
                    "file_type": file_type,
                    "file_size": file_size,
                    "msg_id": msg_obj.message_id
                })
                count += 1
    await msg.edit_text(f"✅ Indexing Complete! Added {count} new files.")

@app.on_message(filters.command("delete") & filters.user(OWNER_ID) & filters.private)
async def delete_file(client, message):
    if len(message.command) < 2:
        return await message.reply("❌ **Usage:** `/delete <message_id>`")
    try:
        msg_id = int(message.command[1])
    except ValueError:
        return await message.reply("❌ Message ID অবশ্যই সংখ্যা হতে হবে!")
    result = files_col.delete_one({"msg_id": msg_id})
    if result.deleted_count > 0:
        await message.reply(f"✅ File with Message ID `{msg_id}` deleted!")
    else:
        await message.reply(f"❌ No file found with ID `{msg_id}`.")

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID) & filters.private)
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ **Usage:** Reply to a message with `/broadcast`")
    broadcast_msg = message.reply_to_message
    users = list(users_col.find({}))
    status_msg = await message.reply(f"📢 Broadcast started... Total: {len(users)}")
    success, failed = 0, 0
    for user in users:
        try:
            await broadcast_msg.copy(chat_id=user['user_id'])
            success += 1
            await asyncio.sleep(0.5)
        except Exception:
            failed += 1
            users_col.delete_one({"user_id": user['user_id']})
    await status_msg.edit_text(f"✅ **Broadcast Complete!**\n\n✅ Success: {success}\n❌ Failed: {failed}")

@app.on_message(filters.command("setad1") & filters.user(OWNER_ID) & filters.private)
async def set_ad_link_1(client, message):
    if len(message.command) < 2:
        return await message.reply("❌ **Usage:** `/setad1 <link>`\n💡 Example: `/setad1 https://adsterra.com/link1`")
    url = message.command[1]
    settings_col.update_one({"type": "ad_link_1"}, {"$set": {"url": url}}, upsert=True)
    await message.reply(f"✅ **Step 1 Ad Link** আপডেট হয়েছে!\n🔗 `{url}`")

@app.on_message(filters.command("setad2") & filters.user(OWNER_ID) & filters.private)
async def set_ad_link_2(client, message):
    if len(message.command) < 2:
        return await message.reply("❌ **Usage:** `/setad2 <link>`\n💡 Example: `/setad2 https://adsterra.com/link2`")
    url = message.command[1]
    settings_col.update_one({"type": "ad_link_2"}, {"$set": {"url": url}}, upsert=True)
    await message.reply(f"✅ **Step 2 Ad Link** আপডেট হয়েছে!\n🔗 `{url}`")

# ==========================================
# 👤 USER COMMANDS & HANDLERS
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id, "join_date": datetime.now()})
    
    if len(message.command) == 2 and message.command[1].startswith("get_"):
        msg_id = int(message.command[1].split("_")[1])
        if not await is_joined(client, user_id):
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("জয়েন করো 🚪", url=f"https://t.me/{FORCE_JOIN}")],
                                        [InlineKeyboardButton("✅ চেক করি", callback_data=f"checkjoin_{msg_id}")]])
            return await message.reply("❌ ফাইল পেতে আগে চ্যানেল জয়েন করো!", reply_markup=btn)
        try:
            sent_msg = await client.copy_message(chat_id=user_id, from_chat_id=LOG_CHANNEL, message_id=msg_id)
            status_msg = await message.reply("✅ ফাইল পাঠানো হয়েছে!\n⏳ **৩০ মিনিট পর অটো ডিলিট হয়ে যাবে!**")
            asyncio.create_task(auto_delete(sent_msg, 30))
            asyncio.create_task(auto_delete(status_msg, 30))
        except Exception as e:
            await message.reply(f"❌ Error: {e}")
        return

    await message.reply_text("**🎬 CTG Movie Bot 🎬**\n\n👋 মুভির নাম লিখে সার্চ করো 👉")

@app.on_callback_query(filters.regex("^checkjoin_"))
async def check_join_callback(client, callback_query):
    msg_id = int(callback_query.data.split("_")[1])
    if await is_joined(client, callback_query.from_user.id):
        await callback_query.message.delete()
        try:
            sent_msg = await client.copy_message(chat_id=callback_query.from_user.id, from_chat_id=LOG_CHANNEL, message_id=msg_id)
            status_msg = await callback_query.message.reply("✅ ফাইল পাঠানো হয়েছে!\n⏳ **৩০ মিনিট পর অটো ডিলিট হয়ে যাবে!**")
            asyncio.create_task(auto_delete(sent_msg, 30))
            asyncio.create_task(auto_delete(status_msg, 30))
        except Exception as e:
            await callback_query.message.reply(f"❌ Error: {e}")
    else:
        await callback_query.answer("❌ এখনো জয়েন করোনি!", show_alert=True)

@app.on_message(filters.text & filters.private & ~filters.command(["start", "index", "stats", "delete", "broadcast", "setad1", "setad2"]))
async def search_movie(client, message):
    query = message.text.lower().strip()
    if not await is_joined(client, message.from_user.id):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("জয়েন করো 🚪", url=f"https://t.me/{FORCE_JOIN}")],
                                    [InlineKeyboardButton("✅ চেক করি", callback_data="justcheck")]])
        return await message.reply("❌ মুভি পেতে আগে চ্যানেল জয়েন করো!", reply_markup=btn)

    results = list(files_col.find({"file_name": {"$regex": query, "$options": "i"}}).limit(10))
    if not results:
        return await message.reply("❌ কোনো মুভি পাওয়া যায়নি!")

    for res in results:
        file_name = res['file_name']
        size_mb = round(int(res['file_size']) / 1024 / 1024, 2)
        msg_id = res['msg_id']
        is_adult = any(keyword in file_name for keyword in ADULT_KEYWORDS)
        adult_tag = " 🔞 [18+ ADULT]" if is_adult else ""
        
        verify_url = f"{BASE_URL}/verify/{msg_id}"
        caption = (
            f"**🎬 File Name:** `{file_name}`\n"
            f"**📦 File Size:** `{size_mb} MB`{adult_tag}\n\n"
            f"⬇️ ফাইল ডাউনলোড করতে নিচের বাটনে ক্লিক করো। ২ ধাপে ভেরিফিকেশন করতে হবে।"
        )
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download File (2-Step Verify)", url=verify_url)]])
        await message.reply_text(caption, reply_markup=btn)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("Bot & Web Server Starting...")
    app.run()
