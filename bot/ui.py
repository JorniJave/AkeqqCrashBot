from imports import Figlet, shutil, datetime, colorama_init, logging
from colorama import Fore, Style
from .translations import get_translation

# Инициализация colorama с autoreset=True для автоматического сброса цветов
colorama_init(autoreset=True)

RESET = Style.RESET_ALL
ORANGE = Fore.LIGHTYELLOW_EX  # Оранжевый (приближённый)
BLUE = Fore.LIGHTBLUE_EX
RED = Fore.RED
YELLOW = Fore.YELLOW
GREEN = Fore.GREEN
PURPLE = Fore.MAGENTA
CYAN = Fore.CYAN

def c_info(msg): 
    print(f"{ORANGE}{get_translation('info_prefix')}{RESET} {msg}")
    logging.info(msg)

def c_success(msg): 
    print(f"{GREEN}{get_translation('success_prefix')}{RESET} {msg}")
    logging.info(msg)

def c_warning(msg): 
    print(f"{YELLOW}{get_translation('warning_prefix')}{RESET} {msg}")
    logging.warning(msg)

def c_error(msg): 
    print(f"{RED}{get_translation('error_prefix')}{RESET} {msg}")
    logging.error(msg)

def c_input(msg): 
    print(f"{CYAN}{get_translation('input_prefix')}{RESET} {msg}")
    logging.info(msg)

def c_delete_roles(): 
    print(f"{BLUE}{get_translation('delete_roles')}{RESET}")
    logging.info("Starting role deletion")

def c_delete_channels(): 
    print(f"{RED}{get_translation('delete_channels')}{RESET}")
    logging.info("Starting channel deletion")

def c_create_channels(): 
    print(f"{YELLOW}{get_translation('create_channels')}{RESET}")
    logging.info("Starting channel creation, webhook creation, and message sending")

def c_create_role(): 
    print(f"{GREEN}{get_translation('create_role')}{RESET}")
    logging.info("Starting role creation")

def c_remove_user_roles(): 
    print(f"{PURPLE}{get_translation('remove_user_roles')}{RESET}")
    logging.info("Starting user role removal")

def print_banner():
    f = Figlet(font='banner3')
    banner = f.renderText(get_translation('banner_title'))
    banner_lines = banner.splitlines()
    try:
        term_width = shutil.get_terminal_size((100, 20)).columns
    except Exception:
        term_width = 100
    gradient = [
        (255, 0, 0), (255, 128, 0), (255, 255, 0),
        (0, 255, 0), (0, 255, 255), (0, 0, 255), (128, 0, 255)
    ]
    n = len(banner_lines)
    color_steps = []
    for i in range(n):
        pos = i * (len(gradient) - 1) / max(n - 1, 1)
        idx = int(pos)
        frac = pos - idx
        if idx == len(gradient) - 1:
            r, g, b = gradient[-1]
        else:
            r1, g1, b1 = gradient[idx]
            r2, g2, b2 = gradient[idx + 1]
            r = int(r1 + (r2 - r1) * frac)
            g = int(g1 + (g2 - g1) * frac)
            b = int(b1 + (b2 - b1) * frac)
        color_steps.append((r, g, b))
    reset = Style.RESET_ALL
    print()
    for line, (r, g, b) in zip(banner_lines, color_steps):
        colored_line = f"\033[38;2;{r};{g};{b}m{line.center(term_width)}{reset}"
        print(colored_line)
    now = datetime.now()
    date_str = now.strftime(get_translation("current_date"))
    date_color = "\033[38;2;180;180;180m"
    print(date_color + date_str.center(term_width) + reset)
    print()
    logging.info("Banner printed")

def print_stats(STATS):
    print("\n" + YELLOW + get_translation("stats_header") + RESET)
    stats_lines = [
        f"{BLUE}{get_translation('stats_deleted_roles', len(STATS['deleted_roles']))}{RESET}",
        f"{RED}{get_translation('stats_deleted_channels', len(STATS['deleted_channels']))}{RESET}",
        f"{RED}{get_translation('stats_deleted_categories', len(STATS['deleted_categories']))}{RESET}",
        f"{PURPLE}{get_translation('stats_removed_user_roles', sum(len(x['roles']) for x in STATS['removed_user_roles']))}{RESET}",
        f"{YELLOW}{get_translation('stats_created_channels', len(STATS['created_channels']))}{RESET}",
        f"{GREEN}{get_translation('stats_created_roles', len(STATS['created_roles']))}{RESET}",
        f"{CYAN}{get_translation('stats_sent_messages', STATS['sent_messages'])}{RESET}"
    ]
    if STATS.get('renamed_guild'):
        stats_lines.append(f"{CYAN}{get_translation('stats_renamed_guild', STATS['renamed_guild']['from'], STATS['renamed_guild']['to'])}{RESET}")
    if STATS.get('changed_icon'):
        stats_lines.append(f"{CYAN}{get_translation('stats_changed_icon', STATS['changed_icon'])}{RESET}")
    stats_lines.append(YELLOW + get_translation("stats_footer") + RESET)
    
    for line in stats_lines:
        print(line)
        logging.info(line.strip().replace(RESET, '').replace(YELLOW, '').replace(BLUE, '').replace(RED, '').replace(PURPLE, '').replace(GREEN, '').replace(CYAN, ''))