from imports import tk, messagebox, winsound, re, logging
from .translations import get_translation, CURRENT_LANGUAGE
from .ui import c_input, c_success, c_error, c_warning

def show_popup(title, message):
    if tk and messagebox:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(title, message)
            root.destroy()
            logging.info(f"Popup shown: {title} - {message}")
        except Exception as e:
            c_warning(get_translation("invalid_icon_file", e))
    else:
        c_warning("Tkinter not available, cannot show popup")

def beep():
    if winsound:
        try:
            winsound.Beep(1000, 500)
            logging.info("Beep sound played")
        except Exception as e:
            print('\a')
            logging.info("Beep sound triggered via terminal")
    else:
        print('\a')
        logging.info("Beep sound triggered via terminal")

def validate_token(token):
    logging.debug("Entering validate_token")
    result = bool(re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', token))
    logging.debug(f"Exiting validate_token: result={result}")
    return result

def ask_yes_no(prompt, default=True):
    logging.debug(f"Entering ask_yes_no: prompt={prompt}, default={default}")
    c_input(prompt)
    while True:
        val = input(f"{prompt} [{'Y' if default else 'y'}/{'n' if default else 'N'}]: ").strip().lower()
        logging.debug(f"ask_yes_no input: {val}")
        if val == '':
            logging.debug(f"Exiting ask_yes_no: default={default}")
            return default
        if val in ('y', 'yes', 'д', 'да') if CURRENT_LANGUAGE == "ru" else ('y', 'yes'):
            logging.debug("Exiting ask_yes_no: True")
            return True
        if val in ('n', 'no', 'н', 'нет') if CURRENT_LANGUAGE == "ru" else ('n', 'no'):
            logging.debug("Exiting ask_yes_no: False")
            return False
        c_error(get_translation("invalid_yes_no"))
        logging.warning(f"Invalid input for {prompt}: {val}")