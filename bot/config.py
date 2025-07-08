import os
import json
import re
from .translations import get_translation
from .ui import c_input, c_error, c_success


def yes_no_input(prompt, c_input, c_error):
    c_input(prompt)
    while True:
        answer = input("> ").strip().lower()
        if answer in ("y", "n", ""):
            return answer == "y"
        c_error(get_translation("invalid_yes_no"))


def get_config_from_console(c_input, c_error, c_success):
    config = {
        "REMOVE_ALL_ROLES": True,
        "CREATE_BOT_ROLE": True,
        "REMOVE_USER_ROLES": True,
        "REMOVE_CHANNELS": True,
        "CREATE_CHANNELS": False,
        "CHANGE_GUILD_NAME": False,
        "CHANGE_GUILD_ICON": False,
        "ROLE_NAME": "BotAdmin",
        "CHANNEL_NAME": "auto-channel",
        "MAX_CHANNELS": 50,
        "CHANNEL_GREETING": "",
        "CHANNEL_GREETING_COUNT": 1,
        "NEW_GUILD_NAME": "",
        "GUILD_ICON_PATH": ""
    }

    c_input(get_translation("config_prompt"))

    config["REMOVE_ALL_ROLES"] = yes_no_input(get_translation("remove_all_roles"), c_input, c_error)
    config["CREATE_BOT_ROLE"] = yes_no_input(get_translation("create_bot_role"), c_input, c_error)
    config["REMOVE_USER_ROLES"] = yes_no_input(get_translation("remove_user_roles"), c_input, c_error)
    config["REMOVE_CHANNELS"] = yes_no_input(get_translation("remove_channels"), c_input, c_error)
    config["CREATE_CHANNELS"] = yes_no_input(get_translation("create_channels"), c_input, c_error)

    if config["CREATE_CHANNELS"]:
        c_input(get_translation("channel_name"))
        channel_name = input("> ").strip() or "auto-channel"
        config["CHANNEL_NAME"] = channel_name

        c_input(get_translation("max_channels"))
        while True:
            try:
                max_channels = input("> ").strip() or "50"
                max_channels = int(max_channels)
                if 1 <= max_channels <= 500:
                    config["MAX_CHANNELS"] = max_channels
                    if max_channels > 250:
                        c_error(get_translation("channel_limit_warning"))
                    break
                c_error(get_translation("invalid_channel_count"))
            except ValueError:
                c_error(get_translation("invalid_number"))

        c_input(get_translation("channel_greeting"))
        config["CHANNEL_GREETING"] = input("> ").strip()

        c_input(get_translation("num_messages"))
        while True:
            try:
                num_messages = input("> ").strip() or "1"
                num_messages = int(num_messages)
                if 1 <= num_messages <= 100:
                    config["CHANNEL_GREETING_COUNT"] = num_messages
                    break
                c_error(get_translation("invalid_message_count"))
            except ValueError:
                c_error(get_translation("invalid_number"))

    config["CHANGE_GUILD_NAME"] = yes_no_input(get_translation("change_guild_name"), c_input, c_error)
    if config["CHANGE_GUILD_NAME"]:
        c_input(get_translation("enter_new_guild_name"))
        config["NEW_GUILD_NAME"] = input("> ").strip()

    config["CHANGE_GUILD_ICON"] = yes_no_input(get_translation("change_guild_icon"), c_input, c_error)
    if config["CHANGE_GUILD_ICON"]:
        c_input(get_translation("enter_icon_path"))
        while True:
            icon_path = input("> ").strip()
            try:
                with open(icon_path, "rb"):
                    config["GUILD_ICON_PATH"] = icon_path
                    break
            except Exception as e:
                c_error(get_translation("invalid_icon_file", e))

    if config["CREATE_BOT_ROLE"]:
        c_input(get_translation("role_name"))
        config["ROLE_NAME"] = input("> ").strip() or "BotAdmin"

    c_success(get_translation("config_selected"))
    return config


def save_config(config, language, config_name, c_success, c_error):
    """Сохранить конфигурацию в файл."""
    try:
        # Создаём папку config, если её нет
        os.makedirs("config", exist_ok=True)

        # Добавляем язык в конфигурацию
        config_with_language = config.copy()
        config_with_language["LANGUAGE"] = language

        # Путь к файлу конфига
        config_path = os.path.join("config", f"{config_name}.akqcfg")

        # Сохраняем в формате JSON
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_with_language, f, indent=4, ensure_ascii=False)
        c_success(get_translation("config_saved", config_name))
    except Exception as e:
        c_error(get_translation("config_save_error", str(e)))


def load_config(config_name, c_success, c_error):
    """Загрузить конфигурацию из файла."""
    try:
        config_path = os.path.join("config", f"{config_name}.akqcfg")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        c_success(get_translation("config_loaded", config_name))
        return config
    except Exception as e:
        c_error(get_translation("config_load_error", config_name, str(e)))
        return None


def list_configs(c_info):
    """Получить список доступных конфигов."""
    try:
        os.makedirs("config", exist_ok=True)
        configs = [f for f in os.listdir("config") if f.endswith(".akqcfg")]
        return configs
    except Exception:
        return []


def select_config_to_load(configs, c_input, c_error):
    """Выбрать конфиг для загрузки."""
    c_input(get_translation("select_config", len(configs)))
    while True:
        try:
            choice = input("> ").strip()
            choice_idx = int(choice)
            if 1 <= choice_idx <= len(configs):
                return configs[choice_idx - 1].replace(".akqcfg", "")
            c_error(get_translation("invalid_config_number", len(configs)))
        except ValueError:
            c_error(get_translation("invalid_number"))


def validate_config_name(name, c_error):
    """Проверить корректность имени конфига."""
    if not name or not re.match(r'^[\w-]+$', name):
        c_error(get_translation("invalid_config_name"))
        return False
    return True