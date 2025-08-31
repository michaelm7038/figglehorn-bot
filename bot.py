import nextcord
import os
import logging
from nextcord.ext import commands
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(message)s')
nextcord_logger = logging.getLogger('nextcord')
nextcord_logger.propagate = False

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Load all intents just for now
intents = nextcord.Intents.all()

bot = commands.Bot(command_prefix="$", intents=intents)

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")
    
    # Load cogs after bot is ready
    logging.info("Loading cogs started.")
    for cog in ["ai"]:
        try:
            bot.load_extension(f"cogs.{cog}")
            logging.info(f"Loaded cog: {cog}")
        except Exception as e:
            logging.error(f"Failed to load cog {cog}: {e}")
    logging.info("All cogs loaded.")

if __name__ == "__main__":
    bot.run(TOKEN)