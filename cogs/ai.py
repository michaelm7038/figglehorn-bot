import nextcord
from nextcord.ext import commands
import os
import requests
import logging
from datetime import datetime

class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_chats = {}
        self.conversation_memory = {}
        
        self.SYSTEM_PROMPT = "You are Figglehorn, the helpful Discord bot of the Coffee Shop server."
        self.DM_SYSTEM_PROMPT = "You are Figglehorn chatting privately with a friend."
        self.THREAD_SYSTEM_PROMPT = "You are Figglehorn participating in a thread discussion."

        self.PROMPT_DOC_PATH = os.path.join(os.path.dirname(__file__), "..", "prompt-doc.md")
        try:
            with open(self.PROMPT_DOC_PATH, "r", encoding="utf-8") as f:
                self.PROMPT_DOC = f.read()
        except Exception:
            self.PROMPT_DOC = ""

        self.MAX_HISTORY_MESSAGES = 15
        self.MAX_RESPONSE_LENGTH = 1900 

        self.OLLAMA_API_URL = "http://localhost:11434/api/chat"
        self.OLLAMA_MODEL = "llama3"

    def get_message_context(self, message):
        context_info = {
            'type': 'regular',
            'is_dm': False,
            'is_thread': False,
            'channel_name': getattr(message.channel, 'name', 'DM'),
            'thread_starter': None,
        }
        
        # If the message is in DM
        if isinstance(message.channel, nextcord.DMChannel):
            context_info['type'] = 'dm'
            context_info['is_dm'] = True

        # If the message is in a thread
        elif isinstance(message.channel, nextcord.Thread):
            context_info['is_thread'] = True
            context_info['thread_starter'] = message.channel.owner
            context_info['type'] = 'thread'
            
        return context_info

    def get_system_prompt(self, context_info):
        base_prompt = ""
        
        if context_info['is_dm']:
            base_prompt = self.DM_SYSTEM_PROMPT
        elif context_info['is_thread']:
            base_prompt = self.THREAD_SYSTEM_PROMPT
        else:
            base_prompt = self.SYSTEM_PROMPT
     
        # Add context-specific guidance
        context_guidance = ""
        if context_info['is_thread'] and context_info['thread_starter']:
            context_guidance = f"\n\nThis is a thread started by {context_info['thread_starter'].display_name}. Keep the discussion relevant to the thread topic."
        elif context_info['guild_name']:
            context_guidance = f"\n\nYou're in the {context_info['guild_name']} server, channel #{context_info['channel_name']}."
            
        return base_prompt + context_guidance

    async def build_message_history(self, message, context_info):
        history = []
        message_count = 0
        
        # Get more messages for threads and DMs where context is more important
        limit = self.MAX_HISTORY_MESSAGES if context_info['is_dm'] or context_info['is_thread'] else 10

        async for msg in message.channel.history(limit=limit, oldest_first=False):
            if message_count >= limit:
                break
                
            # Skip bot messages except our own recent responses
            if msg.author.bot and msg.author != self.bot.user:
                continue
            elif msg.author == self.bot.user and message_count > 5:
                continue
                
            role = "assistant" if msg.author == self.bot.user else "user"
            
            # Clean content based on context
            content = msg.content.strip()
            if not context_info['is_dm']:
                # Remove bot mentions but keep the rest of the message
                content = content.replace(f'<@{self.bot.user.id}>', '').strip()
                
            # Add author context for multi-user conversations
            if not context_info['is_dm'] and role == "user":
                author_name = msg.author.display_name
                content = f"[{author_name}]: {content}"
                
            if content:
                history.append({"role": role, "content": content})
                message_count += 1
                
        return list(reversed(history))
        
    def should_respond_to_message(self, message, context_info):
        # Always respond in DMs
        if context_info['is_dm']:
            return True

        # Always respond in threads
        if context_info['is_thread']:
            return True

        # Respond if mentioned
        if self.bot.user in message.mentions:
            return True

        return False

    async def get_ai_response(self, messages):
        # Use Ollama API for all responses
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": self.OLLAMA_MODEL,
            "messages": messages,
            "stream": False
        }
        try:
            response = requests.post(self.OLLAMA_API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            # Ollama returns 'message' or 'choices', handle both
            if "message" in data and "content" in data["message"]:
                return data["message"]["content"]
            elif "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                return "[Ollama API did not return a valid response.]"
        except Exception as e:
            logging.error(f"Ollama API error: {e}")
            return f"[Ollama API error: {e}]"
    
    # Main bot function: listen to every single message, and later determine if the user is prompting the bot
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages sent by the bot itself to prevent infinite loop
        if message.author == self.bot.user:
            return

        context_info = self.get_message_context(message)

        # Check if user is trying to prompt the bot in a forbidden channel
        if not self.should_respond_to_message(message, context_info):
            return

        try:
            async with message.channel.typing():
                history = await self.build_message_history(message, context_info)

                # Build messages array
                messages = []

                # Add prompt doc
                if self.PROMPT_DOC.strip():
                    messages.append({"role": "system", "content": self.PROMPT_DOC.strip()})

                # Add message history with clear separation SO IT ACTUALLY READS THE PROMPT
                if history:
                    messages.append({"role": "system", "content": "--- Previous conversation history for context ---"})
                    messages.extend(history)
                    messages.append({"role": "system", "content": "--- End of history. The user's current message is below ---"})

                # Add current message with emphasis
                current_content = message.content.strip()
                if not context_info['is_dm']:
                    current_content = current_content.replace(f'<@{self.bot.user.id}>', '').strip()

                # Add the current message to the messages array
                messages.append({"role": "user", "content": current_content})
                logging.info(f"Added current message to API call: {current_content[:100]}...")

                # Make API request based on provider
                response_text = await self.get_ai_response(messages)

                # Clean up response
                response_text = response_text.strip()
                if (response_text.startswith('"') and response_text.endswith('"')) or \
                   (response_text.startswith("'") and response_text.endswith("'")):
                    response_text = response_text[1:-1].strip()

                # Ensure response isn't too long
                if len(response_text) > self.MAX_RESPONSE_LENGTH:
                    response_text = response_text[:self.MAX_RESPONSE_LENGTH-3] + "..."

                # Send response
                await message.reply(response_text, mention_author=False)

        except Exception as e:
            logging.error(f"Error in on_message: {e}")

            error_msg = "An error occurred while processing your request."
            if "timeout" in str(e).lower():
                error_msg += " [ Timeout. ]"
            elif "rate limit" in str(e).lower():
                error_msg += " [ Rate limit. ]"
            await message.reply(error_msg, mention_author=False)

async def setup(bot):
    bot.add_cog(AI(bot))