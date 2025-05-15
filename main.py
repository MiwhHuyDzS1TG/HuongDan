import discord
from discord.ext import commands
import asyncio
import hashlib
import os

# --- Cấu hình Bot ---
GUILD_ID = 1370793069066190938
CHANNEL_ID = 1372449991393542195

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
pending_messages = {}

# ====================
# ConfirmButton xử lý xác nhận
# ====================
class ConfirmButton(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="✅ Xác nhận", style=discord.ButtonStyle.green, custom_id="confirm_button")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.guild_permissions.administrator:
            guild = bot.get_guild(GUILD_ID)
            if guild is None:
                await interaction.response.send_message("❌ Bot không trong server!", ephemeral=True)
                return
            channel = guild.get_channel(CHANNEL_ID)
            if channel is None:
                await interaction.response.send_message("❌ Không tìm thấy channel admin!", ephemeral=True)
                return

            await channel.send(f"<@{self.user_id}> đã duyệt")

            try:
                user = await bot.fetch_user(self.user_id)
                await user.send(f"<@{self.user_id}> 🟢Admin đã duyệt yêu cầu của bạn")
            except Exception as e:
                print(f"Lỗi gửi DM cho user {self.user_id}: {e}")

            pending_messages.pop(self.user_id, None)

            for child in self.children:
                child.disabled = True
            await interaction.message.edit(content=interaction.message.content + "\n✅ Đã xác nhận", view=self)

            await interaction.response.send_message("Đã xác nhận thành công!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bạn không có quyền xác nhận!", ephemeral=True)

# ====================
# Sự kiện khởi động bot
# ====================
@bot.event
async def on_ready():
    print(f"✅ Bot đã sẵn sàng: {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    try:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print("Đã sync lệnh slash trong guild")
    except Exception as e:
        print(f"Lỗi khi sync slash command: {e}")

# ====================
# Xử lý tin nhắn DM
# ====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Bot không ở trong server đích.")
            return

        channel = guild.get_channel(CHANNEL_ID)
        if not channel:
            print("❌ Không tìm thấy channel đích.")
            return

        user_id = message.author.id

        if user_id not in pending_messages:
            pending_messages[user_id] = {
                "texts": [],
                "files": [],
                "countdown_task": None,
                "countdown_msg": None,
            }

        data = pending_messages[user_id]

        if message.content:
            data["texts"].append(message.content)

        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image"):
                data["files"].append(await attachment.to_file())

        if data["countdown_task"]:
            data["countdown_task"].cancel()

        data["countdown_task"] = bot.loop.create_task(countdown_send_dm(user_id, 10))

    await bot.process_commands(message)

async def countdown_send_dm(user_id: int, total_seconds: int = 10):
    data = pending_messages.get(user_id)
    if not data:
        return

    try:
        user = await bot.fetch_user(user_id)
    except Exception as e:
        print(f"Lỗi khi fetch user {user_id}: {e}")
        return

    try:
        countdown_msg = await user.send(f"⏳ Tin nhắn của bạn sẽ được gửi đi trong {total_seconds} giây...")
        data["countdown_msg"] = countdown_msg

        for remaining in range(total_seconds - 1, 0, -1):
            await asyncio.sleep(1)
            try:
                await countdown_msg.edit(content=f"⏳ Tin nhắn của bạn sẽ được gửi đi trong {remaining} giây...")
            except Exception:
                pass

        await asyncio.sleep(1)
        await send_pending(user_id)

    except asyncio.CancelledError:
        countdown_msg = data.get("countdown_msg")
        if countdown_msg:
            try:
                await countdown_msg.delete()
            except:
                pass
        raise

async def send_pending(user_id: int):
    data = pending_messages.get(user_id)
    if not data:
        return

    guild = bot.get_guild(GUILD_ID)
    channel = guild.get_channel(CHANNEL_ID)
    user = await bot.fetch_user(user_id)

    texts = "\n".join(data["texts"]) if data["texts"] else "[Không có nội dung]"
    files = data["files"]

    content = f"📩 Tin nhắn mới từ **{user}** (`{user_id}`):\n{texts}"
    view = ConfirmButton(user_id)

    try:
        await channel.send(content, files=files, view=view)
        await user.send("✅ Tin nhắn của bạn đã được gửi đến admin và đang chờ xác nhận.")
    except Exception as e:
        print(f"Lỗi gửi message tổng hợp: {e}")

    pending_messages.pop(user_id, None)

# ====================
# Slash command UUID
# ====================
class UUIDCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="uuid", description="Tạo offline UUID cho username Minecraft")
    @discord.app_commands.describe(username="Tên người dùng Minecraft")
    async def uuid(self, interaction: discord.Interaction, username: str):
        if interaction.channel_id != CHANNEL_ID:
            await interaction.response.send_message("Lệnh này chỉ chạy ở kênh được phép!", ephemeral=True)
            return

        input_bytes = ("OfflinePlayer:" + username).encode("utf-8")
        md5_hash = hashlib.md5(input_bytes).digest()
        b = bytearray(md5_hash)
        b[6] = (b[6] & 0x0f) | 0x30
        b[8] = (b[8] & 0x3f) | 0x80

        hex_str = b.hex()
        offline_uuid = f"{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"
        await interaction.response.send_message(f"Offline UUID của **{username}** là:\n`{offline_uuid}`")

async def setup_cogs():
    await bot.add_cog(UUIDCommands(bot))

# ====================
# Khởi chạy bot (Railway không cần keep_alive)
# ====================
async def main():
    await setup_cogs()
    await bot.start("MTM3MjQ0OTQ1NjY1NzY2NjEwOA.GUjgNq.hSK219PDr8A2RDQ7HC2BD9gmzy5DSxirBRR3LM")


if __name__ == "__main__":
    asyncio.run(main())
