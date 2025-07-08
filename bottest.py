import sys
import asyncio
import logging
import traceback
from bot.translations import select_language, get_translation
from bot.ui import c_info, c_success, c_error, c_warning, print_banner, print_stats, c_input
from bot.utils import validate_token, show_popup, beep
from bot.discord_utils import check_token_and_connect, list_guilds_with_details, run_one_cycle, STATS
from bot.config import get_config_from_console, save_config, load_config, list_configs, select_config_to_load, validate_config_name, yes_no_input
from bot.discord_utils import discord

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

async def main():
    print_banner()
    c_info(get_translation("bot_start", sys.version.split()[0]))

    # Выбор языка
    language = select_language(c_input, c_success, c_error)

    # Проверяем наличие конфигов и предлагаем загрузить после выбора языка
    configs = list_configs(c_info)
    config = None

    if configs:
        c_info(get_translation("config_folder_detected"))
        c_info(get_translation("available_configs"))
        for idx, cfg in enumerate(configs, 1):
            print(f"[{idx}] {cfg}")
        if yes_no_input(get_translation("load_config_prompt"), c_input, c_error):
            config_name = select_config_to_load(configs, c_input, c_error)
            loaded_config = load_config(config_name, c_success, c_error)
            if loaded_config:
                config = loaded_config

    # Выбор способа загрузки
    c_info(get_translation("select_start_mode"))
    print(get_translation("mode_1_description"))
    print(get_translation("mode_2_description"))
    c_input(get_translation("enter_mode"))
    while True:
        choice = input("> ").strip()
        if choice in ["1", "2"]:
            break
        c_error(get_translation("invalid_mode"))

    token = input(get_translation("enter_token") + " ").strip()
    if not validate_token(token):
        c_error(get_translation("invalid_token_format"))
        return
    c_info(get_translation("checking_token"))
    bot = await check_token_and_connect(token)

    if choice == "1":
        # Способ 1: Бот уже на сервере
        selected_guild = None

        @bot.event
        async def on_ready():
            nonlocal selected_guild
            try:
                c_success(get_translation("bot_connected", bot.user.name))
                # Выбираем сервер после подключения
                selected_guild = await list_guilds_with_details(bot)
                if not selected_guild:
                    c_error(get_translation("no_guild_selected"))
                    await bot.close()
                    return

                # Настройка после выбора сервера
                nonlocal config
                if not config:
                    config = get_config_from_console(c_input, c_error, c_success)
                    if yes_no_input(get_translation("create_config_prompt"), c_input, c_error):
                        c_input(get_translation("enter_config_name"))
                        while True:
                            config_name = input("> ").strip()
                            if validate_config_name(config_name, c_error):
                                break
                        save_config(config, language, config_name, c_success, c_error)

                # Удаляем LANGUAGE из config перед использованием
                config_to_use = config.copy()
                config_to_use.pop("LANGUAGE", None)

                c_info(get_translation("bot_config"))
                for key, value in config_to_use.items():
                    c_info(f"{key}: {value}")

                await run_one_cycle(bot, config_to_use, selected_guild)
                print_stats(STATS)
                show_popup(get_translation("popup_title"), get_translation("popup_message"))
                beep()
                c_success(get_translation("bot_shutdown"))
            except Exception as e:
                c_error(get_translation("on_ready_error", e))
                logging.error(f"{e}\n{traceback.format_exc()}")
            finally:
                await bot.close()

    else:
        # Способ 2: Новый бот через токен
        # Настройка перед генерацией ссылки
        if not config:
            config = get_config_from_console(c_input, c_error, c_success)
            if yes_no_input(get_translation("create_config_prompt"), c_input, c_error):
                c_input(get_translation("enter_config_name"))
                while True:
                    config_name = input("> ").strip()
                    if validate_config_name(config_name, c_error):
                        break
                save_config(config, language, config_name, c_success, c_error)

        # Удаляем LANGUAGE из config перед использованием
        config_to_use = config.copy()
        config_to_use.pop("LANGUAGE", None)

        c_info(get_translation("bot_config"))
        for key, value in config_to_use.items():
            c_info(f"{key}: {value}")

        @bot.event
        async def on_ready():
            try:
                c_success(get_translation("bot_connected", bot.user.name))
                # Генерируем ссылку после подключения
                permissions = discord.Permissions(administrator=True)
                invite_url = discord.utils.oauth_url(bot.user.id, permissions=permissions)
                c_info(get_translation("invite_link_message", invite_url))
                c_info(get_translation("waiting_for_invite"))
            except Exception as e:
                c_error(get_translation("on_ready_error", e))
                logging.error(f"{e}\n{traceback.format_exc()}")
                await bot.close()

        @bot.event
        async def on_guild_join(guild):
            try:
                c_success(get_translation("bot_joined_guild", guild.name))
                # Запускаем процесс с ранее сохраненными настройками
                await run_one_cycle(bot, config_to_use, guild)
                print_stats(STATS)
                show_popup(get_translation("popup_title"), get_translation("popup_message"))
                beep()
                c_success(get_translation("bot_shutdown"))
            except Exception as e:
                c_error(get_translation("on_ready_error", e))
                logging.error(f"{e}\n{traceback.format_exc()}")
            finally:
                await bot.close()

    try:
        # Запускаем бота, он автоматически вызовет on_ready или on_guild_join
        async with bot:
            await bot.start(token)
    except KeyboardInterrupt:
        c_warning(get_translation("bot_interrupted"))
        logging.warning(get_translation("ctrl_c"))
    except Exception as e:
        c_error(get_translation("bot_error", e))
        logging.error(f"{e}\n{traceback.format_exc()}")
    finally:
        c_info(get_translation("bot_stopped"))
        input()

if __name__ == "__main__":
    asyncio.run(main())