import discord
from discord.ext import commands
import asyncio
import logging
import sys
import traceback
import re
from datetime import datetime
from pyfiglet import Figlet
import shutil
from colorama import init as colorama_init, Fore, Style
import aiohttp
from tqdm import tqdm
import time
try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    tk = None
    messagebox = None
try:
    import winsound
except ImportError:
    winsound = None