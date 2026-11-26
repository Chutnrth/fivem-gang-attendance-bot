import csv
import json
import os
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo("Asia/Bangkok")
CSV_FILE = "gang_attendance.csv"
CONFIG_FILE = "gang_config.json"

intents = discord.Intents.default()
intents.message_content = True


def init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "วันที่",
                "เวลา",
                "สถานะ",
                "Discord_ID",
                "Discord_Tag",
                "ชื่อ_IC",
                "รายละเอียด/เหตุผล",
            ])


def save_config(guild_id: int, log_channel_id: int):
    data = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, mode="r", encoding="utf-8") as f:
            data = json.load(f)
    data[str(guild_id)] = {"log_channel_id": log_channel_id}
    with open(CONFIG_FILE, mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_log_channel_id(guild_id: int) -> int | None:
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, mode="r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(str(guild_id), {}).get("log_channel_id")


def get_today_record(user_id: int, today_str: str) -> dict | None:
    if not os.path.exists(CSV_FILE):
        return None
    with open(CSV_FILE, mode="r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["Discord_ID"] == str(user_id) and row["วันที่"] == today_str:
                return row
    return None


def save_record(
    user: discord.User | discord.Member,
    status: str,
    ic_name: str,
    detail: str,
    now: datetime,
):
    init_csv()
    with open(CSV_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            status,
            user.id,
            str(user),
            ic_name,
            detail,
        ])


async def send_log_embed(guild: discord.Guild | None, embed: discord.Embed):
    if guild is None:
        return
    log_id = get_log_channel_id(guild.id)
    if not log_id:
        return
    channel = guild.get_channel(log_id)
    if isinstance(channel, discord.TextChannel):
        await channel.send(embed=embed)


# ================= 1. ฟอร์มเช็คชื่อเข้าแก๊ง =================
class GangCheckInModal(discord.ui.Modal, title="เช็คชื่อเข้าแก๊งประจำวัน"):
    ic_name = discord.ui.TextInput(
        label="ชื่อ IC / ชื่อเล่นในแก๊ง",
        placeholder="เช่น Zerzig / ตี๋น้อย",
        required=True,
        max_length=100,
    )
    activity_note = discord.ui.TextInput(
        label="สถานะ / ช่วงเวลาเข้าเมือง",
        placeholder="เช่น เข้าเมืองปกติ / พร้อมวอร์ 20:00 / ฟาร์มของ",
        required=False,
        max_length=150,
    )

    async def on_submit(self, interaction: discord.Interaction):
        now = datetime.now(TZ)
        today_str = now.strftime("%Y-%m-%d")

        existing = get_today_record(interaction.user.id, today_str)
        if existing:
            await interaction.response.send_message(
                f"วันนี้ ({today_str}) คุณลงบันทึก **{existing['สถานะ']}** ไปแล้วครับ ไม่สามารถกดซ้ำได้",
                ephemeral=True,
            )
            return

        ic_val = self.ic_name.value.strip()
        note_val = self.activity_note.value.strip() or "เข้าเมืองปกติ"
        save_record(interaction.user, "มา", ic_val, note_val, now)

        embed = discord.Embed(
            title="✅ เช็คชื่อเข้าแก๊งสำเร็จ",
            color=discord.Color.green(),
            timestamp=now,
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="สมาชิก", value=interaction.user.mention, inline=True)
        embed.add_field(name="ชื่อ IC", value=ic_val, inline=True)
        embed.add_field(name="รายละเอียด", value=note_val, inline=False)
        embed.set_footer(text=f"เวลา {now.strftime('%d/%m/%Y %H:%M:%S')}")

        await interaction.response.send_message(embed=embed, ephemeral=True)
        await send_log_embed(interaction.guild, embed)


# ================= 2. ฟอร์มแจ้งลาแก๊ง =================
class GangLeaveModal(discord.ui.Modal, title="แบบฟอร์มแจ้งลาแก๊ง"):
    ic_name = discord.ui.TextInput(
        label="ชื่อ IC / ชื่อเล่นในแก๊ง",
        placeholder="เช่น Zerzig / ตี๋น้อย",
        required=True,
        max_length=100,
    )
    leave_type = discord.ui.TextInput(
        label="ประเภทการลา",
        placeholder="เช่น ลาไม่เข้าเมือง / ลาวอร์ / ลากิจธุระส่วนตัว",
        required=True,
        max_length=60,
    )
    reason = discord.ui.TextInput(
        label="เหตุผล / ช่วงวันที่ลา",
        placeholder="เช่น ติดเรียนกลับดึก เข้าเมืองได้อีกทีพรุ่งนี้",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        now = datetime.now(TZ)
        today_str = now.strftime("%Y-%m-%d")

        existing = get_today_record(interaction.user.id, today_str)
        if existing:
            await interaction.response.send_message(
                f"วันนี้ ({today_str}) คุณลงบันทึก **{existing['สถานะ']}** ไปแล้วครับ ไม่สามารถกดซ้ำได้",
                ephemeral=True,
            )
            return

        ic_val = self.ic_name.value.strip()
        detail_val = f"[{self.leave_type.value.strip()}] {self.reason.value.strip()}"
        save_record(interaction.user, "ลา", ic_val, detail_val, now)

        embed = discord.Embed(
            title="📝 แจ้งลาแก๊งประจำวัน",
            color=discord.Color.orange(),
            timestamp=now,
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="สมาชิก", value=interaction.user.mention, inline=True)
        embed.add_field(name="ชื่อ IC", value=ic_val, inline=True)
        embed.add_field(name="ประเภทการลา", value=self.leave_type.value.strip(), inline=False)
        embed.add_field(name="เหตุผล / ช่วงเวลา", value=self.reason.value.strip(), inline=False)
        embed.set_footer(text=f"แจ้งเมื่อ {now.strftime('%d/%m/%Y %H:%M:%S')}")

        await interaction.response.send_message(embed=embed, ephemeral=True)
        await send_log_embed(interaction.guild, embed)


# ================= 3. ปุ่มกดหน้าห้อง (Persistent Views) =================
class GangCheckInView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="เช็คชื่อเข้าเมือง / เข้าแก๊ง",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="fivem_gang_checkin_btn",
    )
    async def checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        today_str = datetime.now(TZ).strftime("%Y-%m-%d")
        existing = get_today_record(interaction.user.id, today_str)
        if existing:
            await interaction.response.send_message(
                f"วันนี้ ({today_str}) คุณลงบันทึก **{existing['สถานะ']}** ไปแล้วครับ",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(GangCheckInModal())


class GangLeaveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="กดแจ้งลาวันนี้",
        style=discord.ButtonStyle.danger,
        emoji="📝",
        custom_id="fivem_gang_leave_btn",
    )
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        today_str = datetime.now(TZ).strftime("%Y-%m-%d")
        existing = get_today_record(interaction.user.id, today_str)
        if existing:
            await interaction.response.send_message(
                f"วันนี้ ({today_str}) คุณลงบันทึก **{existing['สถานะ']}** ไปแล้วครับ",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(GangLeaveModal())


# ================= 4. ตัวบอทและ Slash Commands =================
class GangBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        init_csv()
        self.add_view(GangCheckInView())
        self.add_view(GangLeaveView())
        synced = await self.tree.sync()
        print(f"ซิงก์คำสั่ง Slash Commands สำเร็จ ({len(synced)} คำสั่ง)")


bot = GangBot()


@bot.event
async def on_ready():
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="FiveM Gang | เช็คชื่อ-แจ้งลา"),
    )
    print(f"ออนไลน์แล้ว: {bot.user}")


@bot.tree.command(name="setup", description="สร้างห้องเช็คชื่อ ห้องแจ้งลา และห้องล็อกสำหรับแก๊ง FiveM")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def setup_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    if guild is None or guild.me is None:
        await interaction.followup.send("ไม่พบข้อมูลเซิร์ฟเวอร์ครับ", ephemeral=True)
        return

    member_overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            embed_links=True,
        ),
    }

    log_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
        ),
    }

    try:
        category = await guild.create_category("🏴 ระบบเช็คชื่อ-แจ้งลาแก๊ง", overwrites=member_overwrites)

        checkin_channel = await guild.create_text_channel("📋-เช็คชื่อเข้าแก๊ง", category=category)
        checkin_embed = discord.Embed(
            title="🏴 ระบบเช็คชื่อเข้าแก๊งประจำวัน",
            description=(
                "สมาชิกที่เข้าเมืองหรือพร้อมร่วมกิจกรรมวันนี้ กดปุ่มสีเขียวด้านล่างเพื่อกรอก **ชื่อ IC** ยืนยันตัวตน\n"
                "*(เช็คชื่อได้วันละ 1 ครั้ง)*"
            ),
            color=discord.Color.green(),
        )
        await checkin_channel.send(embed=checkin_embed, view=GangCheckInView())

        leave_channel = await guild.create_text_channel("📝-แจ้งลาแก๊ง", category=category)
        leave_embed = discord.Embed(
            title="📝 ระบบแจ้งลาแก๊งประจำวัน",
            description=(
                "หากติดธุระ ไม่สามารถเข้าเมือง หรือไม่สะดวกวอร์วันนี้ กรุณากดปุ่มด้านล่างเพื่อแจ้งลาล่วงหน้า"
            ),
            color=discord.Color.orange(),
        )
        await leave_channel.send(embed=leave_embed, view=GangLeaveView())

        log_channel = await guild.create_text_channel(
            "📊-ล็อกเช็คชื่อ-ลา",
            category=category,
            overwrites=log_overwrites,
        )
        save_config(guild.id, log_channel.id)

        await interaction.followup.send(
            f"ตั้งค่าระบบแก๊งเรียบร้อยแล้วครับ!\n"
            f"- ห้องเช็คชื่อ: {checkin_channel.mention}\n"
            f"- ห้องแจ้งลา: {leave_channel.mention}\n"
            f"- ห้องล็อก (เฉพาะหัวหน้า/แอดมิน): {log_channel.mention}",
            ephemeral=True,
        )
    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send(
            f"สร้างห้องไม่สำเร็จครับ (`{type(e).__name__}: {e}`)\n"
            f"กรุณาเช็กว่ายศของบอทมีสิทธิ์ **Manage Channels** หรือ **Administrator** แล้วหรือยังครับ",
            ephemeral=True,
        )


@bot.tree.command(name="today", description="เช็กยอดสมาชิกแก๊งที่มาและลาวันนี้")
async def today_command(interaction: discord.Interaction):
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    present_list = []
    leave_list = []

    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row["วันที่"] == today_str:
                    line = f"- **{row['ชื่อ_IC']}** ({row['รายละเอียด/เหตุผล']}) • `{row['เวลา']}`"
                    if row["สถานะ"] == "มา":
                        present_list.append(line)
                    else:
                        leave_list.append(line)

    if not present_list and not leave_list:
        await interaction.response.send_message(f"วันนี้ ({today_str}) ยังไม่มีคนในแก๊งกดเช็คชื่อหรือแจ้งลาครับ")
        return

    embed = discord.Embed(
        title=f"🏴 สรุปยอดสมาชิกแก๊งวันที่ {today_str}",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name=f"✅ เข้าเมือง / มา ({len(present_list)} คน)",
        value="\n".join(present_list) if present_list else "-",
        inline=False,
    )
    embed.add_field(
        name=f"📝 แจ้งลา ({len(leave_list)} คน)",
        value="\n".join(leave_list) if leave_list else "-",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token or token == "วาง_BOT_TOKEN_ตรงนี้":
        raise RuntimeError("ยังไม่ได้ใส่ DISCORD_TOKEN ในไฟล์ .env หรือ Environment Variables")
    bot.run(token)


if __name__ == "__main__":
    main()