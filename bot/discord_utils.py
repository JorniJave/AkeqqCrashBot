import logging
import sys
import queue
import threading
from logging.handlers import QueueHandler, QueueListener
from imports import discord, commands, asyncio, traceback, aiohttp, time
from .translations import get_translation
from .ui import c_info, c_success, c_warning, c_error, c_input, c_delete_roles, c_delete_channels, c_create_channels, \
    c_create_role, c_remove_user_roles, CYAN, RESET

# Настройка асинхронного логирования
log_queue = queue.Queue(-1)
file_handler = logging.FileHandler('bot.log', mode='a', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(formatter)
console_handler.stream.reconfigure(encoding='utf-8', errors='replace')

queue_handler = QueueHandler(log_queue)
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(queue_handler)

listener = QueueListener(log_queue, file_handler)
listener.start()

STATS = {
    "deleted_roles": [],
    "deleted_channels": [],
    "deleted_categories": [],
    "removed_user_roles": [],
    "created_channels": [],
    "created_roles": [],
    "sent_messages": 0,
    "channel_status": {},
}


async def check_token_and_connect(token, max_retries=3, base_delay=5):
    logging.debug(f"Entering check_token_and_connect: max_retries={max_retries}, base_delay={base_delay}")
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            logging.debug(f"check_token_and_connect: attempt {attempt + 1}/{max_retries}")
            try:
                async with session.get(
                        'https://discord.com/api/v10/users/@me',
                        headers={'Authorization': f'Bot {token}'}
                ) as response:
                    logging.debug(
                        f"check_token_and_connect: HTTP status={response.status}, headers={dict(response.headers)}")
                    if response.status == 200:
                        c_success(get_translation("valid_token"))
                        logging.info("Token validated successfully")
                        intents = discord.Intents.default()
                        intents.members = True
                        intents.message_content = True
                        intents.guilds = True
                        bot = commands.Bot(command_prefix='!', intents=intents)
                        logging.debug("Exiting check_token_and_connect: bot created")
                        return bot
                    elif response.status == 429:
                        retry_after = float(response.headers.get('Retry-After', base_delay))
                        c_warning(get_translation("429_error", "token check", attempt + 1, max_retries, retry_after))
                        logging.warning(f"429 error during token check, retrying after {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                    elif response.status == 401:
                        c_error(get_translation("invalid_token"))
                        logging.error("Invalid token")
                        raise discord.errors.LoginFailure("Invalid token")
                    else:
                        c_error(get_translation("http_error", response.status))
                        logging.error(f"HTTP error {response.status}")
                        raise discord.errors.HTTPException(f"HTTP {response.status}")
            except Exception as e:
                c_error(get_translation("token_check_error", e))
                logging.error(f"Token check error: {e}\n{traceback.format_exc()}")
                raise
    c_error(get_translation("max_retries_429"))
    logging.error("Max retries reached for 429 error during token check")
    logging.debug("Exiting check_token_and_connect: max retries reached")
    sys.exit(1)


async def handle_discord_request(coro, operation_name, semaphore, max_retries=2, base_delay=0.2):
    logging.debug(
        f"Entering handle_discord_request: operation_name={operation_name}, max_retries={max_retries}, base_delay={base_delay}")
    async with semaphore:
        logging.debug(f"handle_discord_request: acquired semaphore, active_tasks={semaphore._value}")
        for attempt in range(max_retries):
            logging.debug(f"handle_discord_request: attempt {attempt + 1}/{max_retries} for {operation_name}")
            try:
                result = await coro
                logging.info(f"Operation {operation_name} completed successfully")
                logging.debug(f"Exiting handle_discord_request: result={result}")
                return result
            except discord.errors.HTTPException as e:
                logging.debug(
                    f"handle_discord_request: HTTPException - status={e.status}, code={e.code}, text={e.text}, headers={e.response.headers if e.response else None}")
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', base_delay)
                    c_warning(get_translation("429_error", operation_name, attempt + 1, max_retries, retry_after))
                    logging.warning(
                        f"429 error during {operation_name}, retrying after {retry_after} seconds, headers={e.response.headers if e.response else None}")
                    await asyncio.sleep(retry_after)
                else:
                    c_error(get_translation("unknown_error", operation_name, e))
                    logging.error(f"HTTP error during {operation_name}: {e}\n{traceback.format_exc()}")
                    raise
            except Exception as e:
                c_error(get_translation("unknown_error", operation_name, e))
                logging.error(f"Unknown error during {operation_name}: {e}\n{traceback.format_exc()}")
                raise
        c_warning(get_translation("429_skip", operation_name))
        logging.warning(f"Skipped {operation_name} due to 429")
        logging.debug(f"Exiting handle_discord_request: skipped due to 429")
        return None


async def create_channels_and_send_messages(guild, total, name, greeting, greeting_count, semaphore, batch_size=5,
                                            pause=0.01, delay=0.05):
    logging.debug(
        f"Entering create_channels_and_send_messages: total={total}, name={name}, greeting_count={greeting_count}, batch_size={batch_size}, pause={pause}, delay={delay}")
    start_time = time.time()
    c_create_channels()

    # Выводим статистику перед началом
    total_messages = total * greeting_count
    c_info(f"Создание {total} каналов по {greeting_count} сообщений в каждом. Всего: {total_messages} сообщений")

    if not guild.me.guild_permissions.mention_everyone:
        c_warning("Бот не имеет прав на упоминание @everyone и @here! Уведомления могут не работать.")
        logging.warning("Bot lacks 'Mention Everyone' permission. Mentions may not trigger notifications.")

    created = []
    direct_spam_tasks = []
    min_sent = asyncio.Event()
    min_sent.value = greeting_count
    stop_event = asyncio.Event()
    created_channels = 0
    base_channel_delay = pause
    progress_step_channels = max(1, total // 5)  # Прогресс создания каналов каждые 20%
    progress_step_messages = max(1, total_messages // 5)  # Прогресс отправки сообщений каждые 20%
    last_reported_messages = 0  # Для отслеживания последнего вывода прогресса сообщений

    message_text = f"{greeting}\n@everyone @here" if greeting else "@everyone @here"

    for i in range(1, total + 1, batch_size):
        batch_end = min(i + batch_size, total + 1)
        batch = range(i, batch_end)
        tasks = []
        for j in batch:
            logging.debug(f"create_channels_and_send_messages: creating channel {j}/{total}")
            tasks.append(
                handle_discord_request(
                    guild.create_text_channel(f"{name}-{j}"),
                    get_translation("channel_creation", f"{name}-{j}"),
                    semaphore
                )
            )
        try:
            new_channels = await asyncio.gather(*tasks, return_exceptions=True)
            for idx, (new_channel, channel_num) in enumerate(zip(new_channels, batch)):
                if isinstance(new_channel, Exception):
                    if isinstance(new_channel, discord.HTTPException) and new_channel.status == 429:
                        retry_after = getattr(new_channel, 'retry_after', 1.0)
                        c_warning(
                            f"429 ошибка при создании канала {channel_num}/{total}, повтор через {retry_after} секунд")
                        logging.warning(
                            f"429 error creating channel {name}-{channel_num}, retrying after {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        base_channel_delay = min(base_channel_delay * 1.5, 0.5)
                        try:
                            new_channel = await handle_discord_request(
                                guild.create_text_channel(f"{name}-{channel_num}"),
                                get_translation("channel_creation", f"{name}-{channel_num}"),
                                semaphore
                            )
                            if new_channel:
                                created.append(new_channel)
                                created_channels += 1
                                STATS["created_channels"].append(new_channel.name)
                                logging.info(f"Created channel: {new_channel.name} after 429")
                                direct_spam_tasks.append(
                                    asyncio.create_task(
                                        spam_messages(new_channel, message_text, greeting_count, min_sent, stop_event,
                                                      delay, semaphore))
                                )
                        except discord.HTTPException as e2:
                            c_error(f"Повторная ошибка при создании канала {channel_num}: {e2}")
                            logging.error(f"Retry error creating channel {name}-{channel_num}: {e2}")
                    else:
                        c_error(f"Ошибка при создании канала {channel_num}: {new_channel}")
                        logging.error(f"Error creating channel {name}-{channel_num}: {new_channel}")
                elif new_channel:
                    created.append(new_channel)
                    created_channels += 1
                    STATS["created_channels"].append(new_channel.name)
                    logging.info(f"Created channel: {new_channel.name}")
                    direct_spam_tasks.append(
                        asyncio.create_task(
                            spam_messages(new_channel, message_text, greeting_count, min_sent, stop_event, delay,
                                          semaphore))
                    )
        except Exception as e:
            c_error(f"Ошибка при создании батча каналов {i}-{batch_end - 1}: {e}")
            logging.error(f"Error creating channel batch {i}-{batch_end - 1}: {e}")

        # Прогресс создания каналов
        if created_channels % progress_step_channels == 0 or created_channels == total:
            percentage = (created_channels / total) * 100
            c_info(get_translation("create_channels_progress") + f": {created_channels}/{total} ({percentage:.0f}%)")

        # Прогресс отправки сообщений (проверяем каждую итерацию)
        sent_messages = STATS["sent_messages"]
        if sent_messages >= last_reported_messages + progress_step_messages or sent_messages == total_messages:
            percentage = (sent_messages / total_messages) * 100
            c_info(f"Прогресс отправки сообщений: {sent_messages}/{total_messages} ({percentage:.0f}%)")
            last_reported_messages = sent_messages - (sent_messages % progress_step_messages)

        await asyncio.sleep(base_channel_delay)
        logging.debug(f"create_channels_and_send_messages: paused for {base_channel_delay}s")

    if created_channels < total:
        c_warning(f"Создано только {created_channels} каналов из {total} из-за ошибок")
        logging.warning(f"Created only {created_channels} channels out of {total} due to errors")

    if direct_spam_tasks:
        logging.info(f"Waiting for spam completion in {len(direct_spam_tasks)} channels")
        try:
            # Ожидаем завершения всех задач спама, продолжая отслеживать прогресс
            while direct_spam_tasks:
                done, pending = await asyncio.wait(direct_spam_tasks, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
                direct_spam_tasks = list(pending)
                sent_messages = STATS["sent_messages"]
                if sent_messages >= last_reported_messages + progress_step_messages or sent_messages == total_messages:
                    percentage = (sent_messages / total_messages) * 100
                    c_info(f"Прогресс отправки сообщений: {sent_messages}/{total_messages} ({percentage:.0f}%)")
                    last_reported_messages = sent_messages - (sent_messages % progress_step_messages)

            final_min = min_sent.value
            c_success(get_translation("direct_spam_completed"))
            c_info(get_translation("min_messages_sent", final_min))
            logging.info(f"All spam tasks completed, minimum messages sent: {final_min}")

            incomplete_channels = [
                name for name, sent in STATS["channel_status"].items()
                if sent < greeting_count
            ]
            if incomplete_channels:
                c_warning(get_translation("incomplete_channels", len(incomplete_channels), greeting_count,
                                          ", ".join(incomplete_channels)))
                logging.warning(
                    f"Found {len(incomplete_channels)} channels with incomplete messages: {', '.join(incomplete_channels)}")
            else:
                c_info(get_translation("all_channels_complete"))
                logging.info("All channels have the expected number of messages")
        except KeyboardInterrupt:
            c_warning(get_translation("spam_interrupted"))
            logging.warning("Direct spam completion interrupted")
            for task in direct_spam_tasks:
                task.cancel()
            await asyncio.gather(*direct_spam_tasks, return_exceptions=True)
            raise
        except Exception as e:
            c_error(get_translation("direct_spam_error", e))
            logging.error(f"Direct spam completion error: {e}\n{traceback.format_exc()}")

    c_success(get_translation("channels_and_messages_done"))
    logging.info(f"Channel creation and message sending completed, total duration={time.time() - start_time:.2f}s")
    logging.debug(f"Exiting create_channels_and_send_messages: completed")
    return created


async def spam_messages(channel, message_text, spam_count, min_sent, stop_event, delay=0.05,
                        semaphore=asyncio.Semaphore(30)):
    """Ускоренная функция спама с адаптацией к rate limit"""
    sent_count = 0
    start_time = time.time()
    logging.debug(f"Entering spam_messages: channel={channel.name}, spam_count={spam_count}, delay={delay}")
    logging.info(f"Started spamming in channel {channel.name}")

    while sent_count < spam_count and not stop_event.is_set():
        try:
            async with semaphore:
                await channel.send(message_text)
                sent_count += 1
                STATS["sent_messages"] += 1
                logging.info(f"Sent message {sent_count}/{spam_count} in {channel.name}")
                await asyncio.sleep(delay)
                if sent_count < min_sent.value:
                    min_sent.value = sent_count
                if sent_count == spam_count:
                    min_sent.value = spam_count
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 1.0
                c_warning(f"429 ошибка в {channel.name}, повтор через {retry_after} секунд")
                logging.warning(f"429 error in {channel.name}, retrying after {retry_after} seconds")
                await asyncio.sleep(retry_after)
                delay = min(delay * 1.5, 0.5)
            else:
                c_warning(f"Ошибка при отправке в {channel.name}: {e}")
                logging.warning(f"Error sending message in {channel.name}: {e}")
                min_sent.value = min(min_sent.value, sent_count)
                break
    logging.info(f"Spamming completed in {channel.name}, sent {sent_count}/{spam_count}")
    STATS["channel_status"][channel.name] = sent_count
    if sent_count < min_sent.value:
        min_sent.value = sent_count
    logging.debug(f"Exiting spam_messages: duration={time.time() - start_time:.2f}s")


async def delete_channels_fast(guild, semaphore, batch_size=50, pause=0.05):
    logging.debug(f"Entering delete_channels_fast: batch_size={batch_size}, pause={pause}")
    start_time = time.time()
    c_delete_channels()
    text_and_voice = [ch for ch in guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
    categories = [ch for ch in guild.channels if isinstance(ch, discord.CategoryChannel)]
    if not text_and_voice:
        c_info(get_translation("no_channels_to_delete"))
        logging.info("No text or voice channels to delete")
    if not categories:
        c_info(get_translation("no_categories_to_delete"))
        logging.info("No categories to delete")

    deleted_count = 0
    total_channels = len(text_and_voice)
    progress_step = max(1, total_channels // 5)
    base_pause = pause

    for i in range(0, len(text_and_voice), batch_size):
        logging.debug(
            f"delete_channels_fast: batch {i // batch_size + 1}, channels={min(batch_size, len(text_and_voice) - i)}")
        batch = text_and_voice[i:i + batch_size]
        tasks = [handle_discord_request(ch.delete(), get_translation("channel_deletion", ch.name), semaphore) for ch in
                 batch]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            deleted_count += len(batch)
            STATS["deleted_channels"].extend([ch.name for ch in batch])
            logging.info(f"Deleted channel batch: {[ch.name for ch in batch]}")
            if deleted_count % progress_step == 0 or deleted_count == total_channels:
                percentage = (deleted_count / total_channels) * 100 if total_channels > 0 else 100
                c_info(get_translation(
                    "delete_channels_progress") + f": {deleted_count}/{total_channels} ({percentage:.0f}%)")
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 1.0
                c_warning(f"429 ошибка при удалении каналов, пауза {retry_after} секунд")
                logging.warning(f"429 error deleting channels, pausing for {retry_after} seconds")
                await asyncio.sleep(retry_after)
                base_pause = min(base_pause * 1.5, 0.5)
                continue
            else:
                c_error(get_translation("channel_deletion_error", e))
                logging.error(f"Batch channel deletion error: {e}\n{traceback.format_exc()}")
        await asyncio.sleep(base_pause)
        logging.debug(f"delete_channels_fast: paused for {base_pause}s")

    deleted_categories = 0
    total_categories = len(categories)
    progress_step_categories = max(1, total_categories // 5)
    base_pause = pause

    for i in range(0, len(categories), batch_size):
        logging.debug(
            f"delete_channels_fast: category batch {i // batch_size + 1}, categories={min(batch_size, len(categories) - i)}")
        batch = categories[i:i + batch_size]
        tasks = [handle_discord_request(ch.delete(), get_translation("category_deletion", ch.name), semaphore) for ch in
                 batch]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            deleted_categories += len(batch)
            STATS["deleted_categories"].extend([ch.name for ch in batch])
            logging.info(f"Deleted category batch: {[ch.name for ch in batch]}")
            if deleted_categories % progress_step_categories == 0 or deleted_categories == total_categories:
                percentage = (deleted_categories / total_categories) * 100 if total_categories > 0 else 100
                c_info(get_translation(
                    "delete_categories_progress") + f": {deleted_categories}/{total_categories} ({percentage:.0f}%)")
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 1.0
                c_warning(f"429 ошибка при удалении категорий, пауза {retry_after} секунд")
                logging.warning(f"429 error deleting categories, pausing for {retry_after} seconds")
                await asyncio.sleep(retry_after)
                base_pause = min(base_pause * 1.5, 0.5)
                continue
            else:
                c_error(get_translation("category_deletion_error", e))
                logging.error(f"Batch category deletion error: {e}\n{traceback.format_exc()}")
        await asyncio.sleep(base_pause)
        logging.debug(f"delete_channels_fast: paused for {base_pause}s")

    c_success(get_translation("channel_deletion_completed"))
    logging.info(f"Channel deletion completed, total duration={time.time() - start_time:.2f}s")
    logging.debug(f"Exiting delete_channels_fast: completed")


async def remove_all_roles(guild, semaphore):
    logging.debug("Entering remove_all_roles")
    start_time = time.time()
    c_delete_roles()
    if not guild.me.guild_permissions.manage_roles:
        c_warning(get_translation("no_permissions_roles"))
        logging.warning("Bot lacks 'Manage Roles' permission. Skipping role deletion.")
        logging.debug("Exiting remove_all_roles: no permissions")
        return
    roles_to_delete = [role for role in guild.roles if role != guild.default_role]
    if not roles_to_delete:
        c_info(get_translation("no_roles_to_delete"))
        logging.info("No roles to delete (excluding @everyone)")

    deleted_roles = 0
    total_roles = len(roles_to_delete)
    progress_step = max(1, total_roles // 5)

    for role in roles_to_delete:
        logging.debug(f"remove_all_roles: processing role {role.name}")
        if role.position >= guild.me.top_role.position:
            c_warning(get_translation("role_higher", role.name))
            logging.warning(f"Skipped role {role.name}: role is higher than bot's top role")
            deleted_roles += 1
            continue
        try:
            await handle_discord_request(role.delete(), get_translation("role_deletion", role.name), semaphore)
            STATS["deleted_roles"].append(role.name)
            logging.info(f"Deleted role {role.name}")
            deleted_roles += 1
            if deleted_roles % progress_step == 0 or deleted_roles == total_roles:
                percentage = (deleted_roles / total_roles) * 100 if total_roles > 0 else 100
                c_info(
                    get_translation("delete_roles_progress") + f": {deleted_roles}/{total_roles} ({percentage:.0f}%)")
        except Exception as e:
            c_error(get_translation("role_deletion_error", role.name, e))
            logging.error(f"Role deletion error for {role.name}: {e}\n{traceback.format_exc()}")
            deleted_roles += 1
    c_success(get_translation("roles_deleted"))
    logging.info(f"Role deletion completed, total duration={time.time() - start_time:.2f}s")
    logging.debug(f"Exiting remove_all_roles: completed")


async def create_bot_role(guild, role_name, semaphore):
    logging.debug(f"Entering create_bot_role: role_name={role_name}")
    start_time = time.time()
    c_create_role()
    bot_role = discord.utils.get(guild.roles, name=role_name)
    if not bot_role:
        try:
            bot_role = await handle_discord_request(
                guild.create_role(
                    name=role_name,
                    permissions=discord.Permissions(administrator=True),
                    colour=discord.Colour.blue(),
                    hoist=True,
                    mentionable=True
                ),
                get_translation("role_creation", role_name),
                semaphore
            )
            STATS["created_roles"].append(role_name)
            c_success(get_translation("role_created", role_name, guild.name))
            logging.info(f"Created role {role_name} on {guild.name}")
        except Exception as e:
            c_error(get_translation("role_creation_error", e))
            logging.error(f"Role creation error: {e}\n{traceback.format_exc()}")
    else:
        c_warning(get_translation("role_exists", role_name))
        logging.warning(f"Role {role_name} already exists")
    logging.debug(f"Exiting create_bot_role: duration={time.time() - start_time:.2f}s")
    return bot_role


async def remove_user_roles(guild, bot_role, semaphore):
    logging.debug("Entering remove_user_roles")
    start_time = time.time()
    c_remove_user_roles()
    members = [m for m in guild.members if not m.bot]
    if not members:
        c_info(get_translation("no_users_to_remove_roles"))
        logging.info("No non-bot users to remove roles from")

    processed_members = 0
    total_members = len(members)
    progress_step = max(1, total_members // 5)

    for member in members:
        logging.debug(f"remove_user_roles: processing member {member.name}")
        roles_to_remove = [
            role for role in member.roles
            if role != guild.default_role and (bot_role is None or role != bot_role)
        ]
        if roles_to_remove:
            try:
                await handle_discord_request(
                    member.remove_roles(*roles_to_remove),
                    get_translation("user_roles_removal", member.name),
                    semaphore
                )
                STATS["removed_user_roles"].append({
                    "user": member.name,
                    "roles": [r.name for r in roles_to_remove]
                })
                logging.info(f"Removed roles {', '.join(r.name for r in roles_to_remove)} from {member.name}")
            except Exception as e:
                c_error(get_translation("user_roles_error", member.name, e))
                logging.error(f"User role removal error for {member.name}: {e}\n{traceback.format_exc()}")
        processed_members += 1
        if processed_members % progress_step == 0 or processed_members == total_members:
            percentage = (processed_members / total_members) * 100 if total_members > 0 else 100
            c_info(get_translation(
                "remove_user_roles_progress") + f": {processed_members}/{total_members} ({percentage:.0f}%)")

    c_success(get_translation("user_roles_done"))
    logging.info(f"User role removal completed, total duration={time.time() - start_time:.2f}s")
    logging.debug(f"Exiting remove_user_roles: completed")


async def list_guilds_with_details(bot):
    logging.debug("Entering list_guilds_with_details")
    start_time = time.time()
    try:
        await asyncio.sleep(2)
        if not bot.is_ready():
            c_warning(get_translation("waiting_for_ready"))
            logging.warning("Bot is not ready, waiting...")
            await bot.wait_until_ready()
        guilds = bot.guilds
        logging.debug(f"list_guilds_with_details: found {len(guilds)} guilds")
        if not guilds:
            c_error(get_translation("no_guilds"))
            logging.error("Bot is not in any servers")
            logging.debug("Exiting list_guilds_with_details: no guilds")
            return None
        print("\n" + CYAN + get_translation("guilds_header") + RESET)
        for idx, guild in enumerate(guilds, 1):
            member_count = len(guild.members)
            owner = guild.owner.name if guild.owner else get_translation("unknown_owner")
            print(f"[{idx}] {guild.name}")
            print(f"  ID: {guild.id}")
            print(f"  {get_translation('members')}: {member_count}")
            print(f"  {get_translation('owner')}: {owner}")
            print()
        print(CYAN + get_translation("guilds_footer") + RESET)
        logging.info(f"Listed {len(guilds)} servers")
        c_input(get_translation("select_guild", len(guilds)))
        while True:
            try:
                choice = input("> ").strip()
                logging.debug(f"list_guilds_with_details: input choice={choice}")
                choice_idx = int(choice)
                if 1 <= choice_idx <= len(guilds):
                    selected_guild = guilds[choice_idx - 1]
                    c_success(get_translation("guild_selected", selected_guild.name))
                    logging.info(f"Selected server: {selected_guild.name} (ID: {selected_guild.id})")
                    logging.debug(
                        f"Exiting list_guilds_with_details: selected guild={selected_guild.name}, duration={time.time() - start_time:.2f}s")
                    return selected_guild
                c_error(get_translation("invalid_guild_number", len(guilds)))
            except ValueError:
                c_error(get_translation("invalid_number"))
            logging.warning(f"Invalid server selection input: {choice}")
    except Exception as e:
        c_error(get_translation("list_guilds_error", e))
        logging.error(f"Error listing servers: {e}\n{traceback.format_exc()}")
        logging.debug(f"Exiting list_guilds_with_details: error, duration={time.time() - start_time:.2f}s")
        return None


async def run_one_cycle(bot, CONFIG, selected_guild):
    logging.debug("Entering run_one_cycle")
    start_time = time.time()
    guild = selected_guild
    semaphore = asyncio.Semaphore(30)
    logging.debug(f"run_one_cycle: semaphore created, limit=30")

    async def change_guild_icon():
        logging.debug("Entering change_guild_icon")
        start_time_icon = time.time()
        if CONFIG.get("CHANGE_GUILD_ICON") and CONFIG.get("GUILD_ICON_PATH"):
            try:
                with open(CONFIG["GUILD_ICON_PATH"], "rb") as f:
                    icon_bytes = f.read()
                await handle_discord_request(
                    guild.edit(icon=icon_bytes),
                    get_translation("guild_icon_change"),
                    semaphore
                )
                STATS["changed_icon"] = CONFIG["GUILD_ICON_PATH"]
                c_success(get_translation("guild_icon_changed"))
                logging.info("Guild icon changed successfully")
            except Exception as e:
                c_error(get_translation("guild_icon_error", e))
                logging.error(f"Guild icon change error: {e}\n{traceback.format_exc()}")
        else:
            logging.info("Guild icon change skipped: CHANGE_GUILD_ICON or GUILD_ICON_PATH not set")
        logging.debug(f"Exiting change_guild_icon: duration={time.time() - start_time_icon:.2f}s")

    async def change_guild_name():
        logging.debug("Entering change_guild_name")
        start_time_name = time.time()
        if CONFIG.get("CHANGE_GUILD_NAME") and CONFIG.get("NEW_GUILD_NAME"):
            try:
                old_name = guild.name
                await handle_discord_request(
                    guild.edit(name=CONFIG["NEW_GUILD_NAME"]),
                    get_translation("guild_name_change"),
                    semaphore
                )
                STATS["renamed_guild"] = {"from": old_name, "to": CONFIG["NEW_GUILD_NAME"]}
                c_success(get_translation("guild_name_changed", old_name, CONFIG["NEW_GUILD_NAME"]))
                logging.info(f"Guild name changed: {old_name} -> {CONFIG['NEW_GUILD_NAME']}")
            except Exception as e:
                c_error(get_translation("guild_name_error", e))
                logging.error(f"Guild name change error: {e}\n{traceback.format_exc()}")
        else:
            logging.info("Guild name change skipped: CHANGE_GUILD_NAME or NEW_GUILD_NAME not set")
        logging.debug(f"Exiting change_guild_name: duration={time.time() - start_time_name:.2f}s")

    parallel_tasks = []
    if CONFIG.get("CHANGE_GUILD_ICON") and CONFIG.get("GUILD_ICON_PATH"):
        parallel_tasks.append(change_guild_icon())
        logging.info("Added task: change_guild_icon")
    if CONFIG.get("CHANGE_GUILD_NAME") and CONFIG.get("NEW_GUILD_NAME"):
        parallel_tasks.append(change_guild_name())
        logging.info("Added task: change_guild_name")
    if CONFIG.get("REMOVE_ALL_ROLES", True):
        parallel_tasks.append(remove_all_roles(guild, semaphore))
        logging.info("Added task: remove_all_roles")
    else:
        logging.info("Skipped remove_all_roles: REMOVE_ALL_ROLES is False")

    if parallel_tasks:
        c_info(get_translation("parallel_tasks_start"))
        logging.info("Starting parallel tasks: guild name, icon, role deletion")
        try:
            await asyncio.gather(*parallel_tasks)
            c_success(get_translation("parallel_tasks_done"))
            logging.info("Parallel tasks completed")
        except Exception as e:
            c_error(get_translation("parallel_tasks_error", e))
            logging.error(f"Parallel tasks error: {e}\n{traceback.format_exc()}")
    else:
        logging.info("No parallel tasks to execute")

    bot_role = None
    if CONFIG.get("CREATE_BOT_ROLE", True):
        logging.info("Executing create_bot_role")
        bot_role = await create_bot_role(guild, CONFIG["ROLE_NAME"], semaphore)
        await asyncio.sleep(1)
        logging.debug("run_one_cycle: paused 1s after create_bot_role")
    else:
        logging.info("Skipped create_bot_role: CREATE_BOT_ROLE is False")

    if CONFIG.get("REMOVE_USER_ROLES", True):
        logging.info("Executing remove_user_roles")
        await remove_user_roles(guild, bot_role, semaphore)
        await asyncio.sleep(1)
        logging.debug("run_one_cycle: paused 1s after remove_user_roles")
    else:
        logging.info("Skipped remove_user_roles: REMOVE_USER_ROLES is False")

    if CONFIG.get("REMOVE_CHANNELS", True):
        logging.info("Executing delete_channels_fast")
        await delete_channels_fast(guild, semaphore, batch_size=50, pause=0.05)
        await asyncio.sleep(1)
        logging.debug("run_one_cycle: paused 1s after delete_channels_fast")
    else:
        logging.info("Skipped delete_channels_fast: REMOVE_CHANNELS is False")

    created_channels = 0
    if CONFIG.get("CREATE_CHANNELS", False):
        logging.info("Executing create_channels_and_send_messages")
        created_channels = await create_channels_and_send_messages(
            guild,
            min(CONFIG.get("MAX_CHANNELS", 50), 500),
            CONFIG.get("CHANNEL_NAME", "default-channel"),
            CONFIG.get("CHANNEL_GREETING", "Default message"),
            CONFIG.get("CHANNEL_GREETING_COUNT", 10),
            semaphore,
            batch_size=5,
            pause=0.01,
            delay=0.05
        )
        await asyncio.sleep(1)
        logging.debug("run_one_cycle: paused 1s after create_channels_and_send_messages")
    else:
        logging.info("Skipped create_channels_and_send_messages: CREATE_CHANNELS is False")

    total_time = time.time() - start_time
    c_success(get_translation("cycle_completed", total_time))
    logging.info(f"One cycle completed in {total_time:.2f} seconds")
    logging.debug(f"Exiting run_one_cycle: duration={total_time:.2f}s")
    return created_channels


# Остановка слушателя логов при завершении программы
def shutdown_logging():
    listener.stop()