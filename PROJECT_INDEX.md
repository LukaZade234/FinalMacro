# MudaeBot — Project index

This document maps modules, functions, and features so you can reuse them as blocks when building a new version.

---

## Discord connection (`discord` library)

Uses `discord.Client` (imported as `DiscordClient`) from **discord.py-self** / discord.py user-token stack. Connection lifecycle is implemented in `bot_client.py`; `event_coordinator.py` creates clients, calls `connect()` / `disconnect()` on the coordinator’s asyncio loop, and on GUI stop schedules `disconnect()` via `asyncio.run_coroutine_threadsafe`.

### Imports (`bot_client.py`)

```python
import discord
from discord import Client as DiscordClient
```

### `EventCoordinator.stop` — schedule disconnect on the bot loop

```196:216:event_coordinator.py
    def stop(self):
        """Stop the coordinator gracefully."""
        self.log("Stop requested", "Coordinator", "INFO")
        self.is_stopping = True
        self._stop_event.set()
        
        # Cancel current event if running
        if self.current_event:
            self.current_event.mark_cancelled()
        
        # Close all clients
        if self._loop and not self._loop.is_closed():
            for client in self.clients.values():
                asyncio.run_coroutine_threadsafe(client.disconnect(), self._loop)
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        
        self.is_running = False
        self.log("Coordinator stopped", "Coordinator", "INFO")
```

### `EventCoordinator._connect_all_accounts` / `_disconnect_all_accounts`

```306:366:event_coordinator.py
    async def _connect_all_accounts(self):
        """Connect all configured accounts."""
        # Collect all allowed channel IDs from servers
        all_channel_ids = [server.channel_id for server in self.servers]
        
        for account_name, config in self.accounts.items():
            if self._stop_event.is_set():
                break
            
            self.log(f"Connecting {account_name}...", account_name, "INFO")
            
            client = BotClient(
                account_name=account_name,
                token=config.token,
                log_function=self.log_function
            )
            
            # Set allowed channels BEFORE connecting (so listeners are filtered from start)
            client.set_allowed_channels(all_channel_ids)
            
            success = await client.connect()
            
            if success:
                self.clients[account_name] = client
                
                # Attach listeners
                listener_config = ListenerConfig(
                    kakera_enabled=config.kakera_reaction_enabled,
                    kakera_delay=config.kakera_reaction_delay,
                    kakera_target_users=config.kakera_target_users,
                    only_chaos=config.only_chaos,
                    kakera_types_filter=config.kakera_types_filter,
                    wish_snipe_enabled=bool(config.wishlist),
                    wish_snipe_delay=config.snipe_delay,
                    wishlist=config.wishlist,
                    series_snipe_enabled=bool(config.series_wishlist),
                    series_snipe_delay=config.series_snipe_delay,
                    series_wishlist=config.series_wishlist,
                    value_snipe_enabled=config.kakera_snipe_threshold > 0,
                    value_snipe_threshold=config.kakera_snipe_threshold,
                    value_snipe_delay=config.snipe_delay,
                )
                self.listener_manager.attach_to_client(client, listener_config)
                
                self.log(f"Connected: {account_name}", account_name, "INFO")
            else:
                self.log(f"Failed to connect: {account_name}", account_name, "ERROR")
            
            # Small delay between connections
            await asyncio.sleep(1)
    
    async def _disconnect_all_accounts(self):
        """Disconnect all accounts."""
        for account_name, client in self.clients.items():
            try:
                await client.disconnect()
                self.log(f"Disconnected: {account_name}", account_name, "INFO")
            except Exception as e:
                self.log(f"Error disconnecting {account_name}: {e}", account_name, "ERROR")
        
        self.clients.clear()
```

### `BotClient.connect` / `disconnect` / `get_channel` / `_refresh_session_id`

Registers gateway events on `self.client`, starts the session with `asyncio.create_task(self.client.start(self.token))`, and resolves channels through `self.client.get_channel` after the connection is ready.

```159:231:bot_client.py
    async def connect(self) -> bool:
        """
        Create and connect the Discord client.
        Returns True if connection successful.
        """
        # Suppress discord.py logging
        discord_logger = logging.getLogger('discord')
        discord_logger.setLevel(logging.WARNING)
        
        # Create client
        self.client = DiscordClient(chunk_guilds_at_startup=False)
        
        # Set up event handlers
        @self.client.event
        async def on_ready():
            self.is_ready = True
            self.is_connected = True
            self._refresh_session_id()
            if self.client and self.client.user:
                self.log(f"Connected as {self.client.user}", "INFO")
        
        @self.client.event
        async def on_disconnect():
            self.is_connected = False
            self.log("Disconnected from Discord", "RESET")
        
        @self.client.event
        async def on_message(message):
            await self._handle_message(message)
        
        @self.client.event
        async def on_message_edit(before, after):
            await self._handle_message_edit(before, after)
        
        # Start client in background
        try:
            asyncio.create_task(self.client.start(self.token))
            
            # Wait for ready with timeout
            for _ in range(30):  # 30 second timeout
                if self.is_ready:
                    return True
                await asyncio.sleep(1)
            
            self.log("Connection timeout", "ERROR")
            return False
            
        except discord.errors.LoginFailure as e:
            self.log(f"Login failed: {e}", "ERROR")
            return False
        except Exception as e:
            self.log(f"Connection error: {e}", "ERROR")
            return False
    
    async def disconnect(self):
        """Disconnect the Discord client."""
        # Immediately mark as not ready to stop listener processing
        self.is_ready = False
        self.is_connected = False
        
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass
    
    def get_channel(self, channel_id: int) -> Optional[discord.TextChannel]:
        """Get a channel by ID."""
        if not self.client:
            return None
        channel = self.client.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None
```

```931:938:bot_client.py
    def _refresh_session_id(self):
        """Refresh the session ID for slash commands."""
        try:
            ws = getattr(self.client, 'ws', None)
            if ws:
                self._session_id = getattr(ws, 'session_id', None)
        except Exception:
            pass
```

### Other `discord.Client` usage (requires active session)

| Area | Library API |
|------|-------------|
| Send Mudae text commands | `await channel.send(...)` on `discord.TextChannel` |
| Claim / kakera verification | `await self.client.wait_for('message', check=..., timeout=...)` |
| Identity checks | `self.client.user` (name, display_name, `global_name`) |
| Reactions | `await message.add_reaction(...)` |

---

## Reading chat and processing messages (`bot_client.py`)

Inbound traffic is almost entirely **Mudae** (`TARGET_BOT_ID` from `config.py`), not “your” typing. The self-account sends commands via `channel.send`; Mudae replies as normal Discord messages (plain `content` and/or `embeds` + `components`). Processing paths:

1. **Polling history** after a command (`wait_for_mudae_response`) — used heavily by `$tu`.
2. **`client.wait_for('message', ...)`** — next Mudae line in channel (claim marriage line, kakera `($k)` line).
3. **`on_message` / `on_message_edit`** — `_handle_message` / `_handle_message_edit` for listeners, embeds, and opportunistic kakera CSV logging.

### Poll channel history for a Mudae text line

```262:286:bot_client.py
    async def wait_for_mudae_response(
        self,
        channel: discord.TextChannel,
        timeout: float = 10.0,
        check_func: Optional[Callable] = None
    ) -> Optional[discord.Message]:
        """
        Wait for a response from Mudae in the channel.
        Returns the message if found, None if timeout.
        """
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            # Check recent messages
            try:
                async for msg in channel.history(limit=10):
                    if msg.author.id == TARGET_BOT_ID:
                        if check_func is None or check_func(msg):
                            return msg
            except Exception:
                pass
            
            await asyncio.sleep(0.5)
        
        return None
```

### `$tu`: find Mudae’s reply, then regex-parse `message.content`

`is_tu_response` filters Mudae’s plain-text status; parsing updates `self.state` (rolls, claims, RT, kakera react, DK, power).

```288:414:bot_client.py
    async def send_tu_and_parse(
        self,
        channel: discord.TextChannel,
        prefix: str = "$"
    ) -> Dict[str, Any]:
        """
        Send $tu and parse the response.
        Returns parsed status information.
        """
        result = {
            "success": False,
            "claim_available": False,
            "claim_reset_minutes": 0,
            "rolls_left": 0,
            "rolls_reset_minutes": 0,
            "rt_available": False,
            "kakera_available": False,
            "dk_stock": 0,
            "power": 100,
            "power_consumption": 0,
            "raw_content": ""
        }
        
        # Send $tu
        if not await self.send_command(channel, "tu", prefix):
            return result
        
        await asyncio.sleep(2.5)
        
        # Find the $tu response
        def is_tu_response(msg):
            if not msg.content:
                return False
            content_lower = msg.content.lower()
            # Check for roll info
            has_rolls = re.search(r"rolls?.*(?:left|restantes)", content_lower)
            # Check for claim info
            has_claim = re.search(r"(?:you __can__|can't claim|você __pode__|calma aí)", content_lower)
            return has_rolls and has_claim
        
        tu_msg = await self.wait_for_mudae_response(channel, timeout=5.0, check_func=is_tu_response)
        
        if not tu_msg:
            self.log("Could not find $tu response", "ERROR")
            return result
        
        result["success"] = True
        result["raw_content"] = tu_msg.content
        
        # Parse the response
        content_lower = tu_msg.content.lower()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        # Parse claim status
        can_claim_en = re.search(r"you __can__ claim", content_lower)
        can_claim_pt = re.search(r"você __pode__ se casar", content_lower)
        cant_claim_en = re.search(r"can't claim for another \*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
        cant_claim_pt = re.search(r"calma aí.*\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
        
        if can_claim_en or can_claim_pt:
            result["claim_available"] = True
            self.state.claim_available = True
            self.state.claim_cooldown_until = None
        elif cant_claim_en or cant_claim_pt:
            match = cant_claim_en or cant_claim_pt
            h, m = self._parse_hours_minutes(match)
            result["claim_reset_minutes"] = h * 60 + m
            result["claim_available"] = False
            self.state.claim_available = False
            self.state.claim_cooldown_until = now_utc + datetime.timedelta(minutes=result["claim_reset_minutes"])
        
        # Parse next claim reset
        reset_match = re.search(r"next claim reset.*\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
        if reset_match:
            h, m = self._parse_hours_minutes(reset_match)
            self.state.next_claim_reset = now_utc + datetime.timedelta(minutes=h * 60 + m)
        
        # Parse rolls
        rolls_match = re.search(r"(?:you have|você tem)\s*\*{0,2}([\d,.]+)\*{0,2}\s*rolls?", content_lower)
        if rolls_match:
            result["rolls_left"] = int(re.sub(r"[^\d]", "", rolls_match.group(1)))
            self.state.rolls_left = result["rolls_left"]
        
        # Parse roll reset time
        roll_reset_match = re.search(r"(?:next rolls? reset|próxima reinicialização).*\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
        if roll_reset_match:
            h, m = self._parse_hours_minutes(roll_reset_match)
            result["rolls_reset_minutes"] = h * 60 + m
            self.state.rolls_reset_minutes = result["rolls_reset_minutes"]
        
        # Parse RT status
        if "$rt is available" in content_lower or "$rt está pronto" in content_lower:
            result["rt_available"] = True
            self.state.rt_available = True
        else:
            self.state.rt_available = False
        
        # Parse kakera react status
        if "you __can__ react to kakera" in content_lower or "você __pode__" in content_lower and "kakera" in content_lower:
            result["kakera_available"] = True
            self.state.kakera_react_available = True
            self.state.kakera_cooldown_until = None
        else:
            kakera_wait = re.search(r"can't react to kakera.*\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
            if kakera_wait:
                h, m = self._parse_hours_minutes(kakera_wait)
                self.state.kakera_react_available = False
                self.state.kakera_cooldown_until = now_utc + datetime.timedelta(minutes=h * 60 + m)
        
        # Parse DK stock
        dk_match = re.search(r"\*\*(\d+)\*\*\s*\$dk\s*(?:available|dispon)", content_lower)
        if dk_match:
            result["dk_stock"] = int(dk_match.group(1))
            self.state.dk_stock = result["dk_stock"]
        
        # Parse power
        power_match = re.search(r"power:\s*\*\*(\d+)%\*\*", content_lower)
        if power_match:
            result["power"] = int(power_match.group(1))
            self.state.current_power = result["power"]
        
        consumption_match = re.search(r"(?:each kakera reaction consumes|cada reação de kakera consume)\s*(\d+)%", content_lower)
        if consumption_match:
            result["power_consumption"] = int(consumption_match.group(1))
            self.state.power_consumption = result["power_consumption"]
        
        return result
```

```955:967:bot_client.py
    def _parse_hours_minutes(self, match) -> tuple:
        """Parse hours and minutes from regex match."""
        if not match:
            return 0, 0
        
        groups = match.groups()
        h_str = groups[0] if len(groups) > 0 else ""
        m_str = groups[1] if len(groups) > 1 else ""
        
        h = int(re.sub(r"\D", "", h_str or "0") or "0")
        m = int(re.sub(r"\D", "", m_str or "0") or "0")
        
        return h, m
```

### Wait for Mudae’s next line after a claim click (marriage text)

```497:537:bot_client.py
    async def _verify_claim_success(self, original_message: discord.Message) -> bool:
        """Wait for marriage message to verify claim."""
        try:
            # Wait for Mudae's response message
            def check(m):
                return (m.channel.id == original_message.channel.id and 
                        m.author.id == TARGET_BOT_ID and
                        "are now married" in m.content)
            
            # Wait up to 3 seconds for the marriage message
            response = await self.client.wait_for('message', check=check, timeout=3.0)
            
            content = response.content.lower()
            my_names = self._get_own_names()
            
            # Extract username part before " and "
            # Handles: "💖 User and Char..." or "User and Char..."
            # Also handles display names with spaces
            match = re.search(r"(?:💖\s*)?(.*?)\s+and\s+.*?\s+are now married", response.content, re.IGNORECASE)
            
            if match:
                winner_name = match.group(1).strip().lower()
                
                # Check if winner matches any of our names
                if winner_name in my_names:
                    return True
                    
                # Also check if our name is contained in winner name (or vice versa)
                # to handle display name variations
                for name in my_names:
                    if name in winner_name or winner_name in name:
                        return True
            
            return False
            
        except asyncio.TimeoutError:
            # No marriage message seen - assume we didn't get it
            return False
        except Exception as e:
            self.log(f"Claim verification error: {e}", "DEBUG")
            return False
```

### After kakera clicks: wait for any Mudae line, parse `+N ($k)` text

Full `click_kakera_buttons` also reads **`embed.description`** via `parse_individual_kakera` before clicking; verification uses the next Mudae **`message.content`** and `_parse_kakera_claim`.

```631:769:bot_client.py
        # If verification is enabled and we clicked something, wait for Mudae's response
        if verify_claim and result['count'] > 0 and self.client:
            try:
                # Wait for Mudae's response message (usually within 2 seconds)
                def check(m):
                    # We relax the check to not require a reference/reply, as Mudae sometimes doesn't reply
                    # Just check it's from Mudae in the same channel
                    return (m.channel.id == message.channel.id and 
                            m.author.id == TARGET_BOT_ID)
                
                # Wait up to 3 seconds for the marriage message
                response = await self.client.wait_for('message', check=check, timeout=3.0)
                
                # DEBUG: Log kakera response
                try:
                    with open("mudae_debug.log", "a", encoding="utf-8") as f:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"[{timestamp}] [KAKERA RESPONSE] Content: {response.content!r}\n")
                except Exception:
                    pass

                # Parse the response to see who got the kakera
                if response.content:
                    # Parse detailed info
                    claim_info = self._parse_kakera_claim(response.content)
                    
                    result['claimed_by'] = claim_info.get('claimed_by')
                    # Add extra info to result
                    result['claimed_amount'] = claim_info.get('amount', 0)
                    result['claimed_type'] = claim_info.get('kakera_type')
                    
                    # Check if we got it (compare with our username)
                    if (result['claimed_by'] and self.client.user):
                        my_name = self.client.user.name.lower()
                        claimed_lower = result['claimed_by'].lower()
                        
                        # Direct match or containment (for display names vs usernames)
                        if claimed_lower == my_name or my_name in claimed_lower or claimed_lower in my_name:
                            result['verified'] = True
                        else:
                            result['verified'] = False
                            self.log(f"Kakera verification failed: claimed_by='{result['claimed_by']}' vs me='{my_name}'", "INFO")
                    else:
                        result['verified'] = False
                        if not result['claimed_by']:
                            self.log(f"Kakera verification failed: Could not parse claimed_by from '{response.content}'", "INFO")
                        
                    # Clear kakera list if we didn't get it
                    if not result['verified']:
                        result['count'] = 0
                        result['kakera_list'] = []
                
            except asyncio.TimeoutError:
                # No response from Mudae, assume failed
                result['verified'] = False
                result['count'] = 0
                result['kakera_list'] = []
            except Exception as e:
                self.log(f"Kakera verification error: {e}", "DEBUG")
                result['verified'] = False
        
        return result
    
    def _parse_kakera_claim(self, content: str) -> Dict[str, Any]:
        """
        Parse Mudae's kakera claim message to extract details.
        Redesigned to be robust against markdown and emojis.
        """
        result = {
            'claimed_by': None,
            'kakera_type': None,
            'amount': 0
        }
        
        try:
            # 1. Identify Kakera Type
            # Try standard format first :kakeraT:
            type_match = re.search(r':(kakera[A-Z]*):', content, re.IGNORECASE)
            if type_match:
                result['kakera_type'] = type_match.group(1)
            else:
                # Try unicode emojis from config
                for k_type, info in KAKERA_INFO.items():
                    if info['emoji'] in content:
                        result['kakera_type'] = k_type
                        break
            
            # 2. Clean content for easier parsing
            # Remove bold (**), italics (*), underline (__), strike (~~)
            clean_content = content.replace('**', '').replace('__', '').replace('~~', '')
            # Don't replace single * yet as it might be part of a name, but usually markdown is **
            
            # 3. Find Amount and Username
            # Look for the anchor: "+NUMBER ($k)"
            # Matches: "+546 ($k)" or "+1,000 ($k)"
            amount_match = re.search(r'\+([\d,]+)\s*\(\$k\)', clean_content, re.IGNORECASE)
            
            if amount_match:
                # Extract amount
                result['amount'] = int(amount_match.group(1).replace(',', ''))
                
                # Username is whatever is before the +Amount
                # content: "<:kakeraT:123> User +546 ($k)"
                # pre_match: "<:kakeraT:123> User "
                pre_match = clean_content[:amount_match.start()].strip()
                
                # 4. Clean up the username part
                # Remove "breaks down into" segments if present (take the last part)
                if "breaks down into" in pre_match:
                    parts = pre_match.split("breaks down into")
                    pre_match = parts[-1].strip()
                
                # Remove emojis from the START of the string
                # Remove custom discord emojis <...:123>
                pre_match = re.sub(r'^<a?:[\w~]+:\d+>', '', pre_match).strip()
                # Remove standard discord emojis :name:
                pre_match = re.sub(r'^:[\w~]+:', '', pre_match).strip()
                # Remove => arrow if present
                pre_match = re.sub(r'^=>', '', pre_match).strip()
                
                # Remove unicode emojis from start
                for info in KAKERA_INFO.values():
                    if pre_match.startswith(info['emoji']):
                        pre_match = pre_match[len(info['emoji']):].strip()
                
                result['claimed_by'] = pre_match.strip()
                
                # Log for debug
                try:
                    with open("mudae_debug.log", "a", encoding="utf-8") as f:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"[{timestamp}] [PARSE SUCCESS] Content: {content!r} -> User: {result['claimed_by']}, Amount: {result['amount']}\n")
                except:
                    pass

        except Exception as e:
            self.log(f"Error parsing kakera claim: {e}", "DEBUG")
            
        return result
```

### Gateway listener: every Mudae message → debug log, kakera CSV, embed listeners

Wired in `connect()` as `on_message` → `_handle_message`. Uses `message.content` and `message.embeds[0]` for character/kakera listener callbacks.

```793:883:bot_client.py
    async def _handle_message(self, message: discord.Message):
        """Handle incoming messages (for listeners)."""
        # Stop processing if we are disconnecting/not ready
        if not self.is_ready:
            return

        # CRITICAL: Only process messages from allowed channels
        if not self.is_channel_allowed(message.channel.id):
            return
        
        # Only process Mudae messages
        if message.author.id != TARGET_BOT_ID:
            return

        # Deduplicate: multiple clients in same channel all receive the same message - process only once
        global _PROCESSED_MUDAE_MESSAGE_IDS
        msg_id = message.id
        if msg_id in _PROCESSED_MUDAE_MESSAGE_IDS:
            return
        _PROCESSED_MUDAE_MESSAGE_IDS.add(msg_id)
        if len(_PROCESSED_MUDAE_MESSAGE_IDS) > _MAX_PROCESSED_IDS:
            _PROCESSED_MUDAE_MESSAGE_IDS.clear()

        # DEBUG: Log all Mudae messages to file
        try:
            with open("mudae_debug.log", "a", encoding="utf-8") as f:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] [{message.channel.name}] Content: {message.content!r}\n")
                if message.embeds:
                    for i, embed in enumerate(message.embeds):
                        title = getattr(embed, 'title', '') or ''
                        desc = getattr(embed, 'description', '') or ''
                        footer = getattr(embed.footer, 'text', '') or '' if embed.footer else ''
                        f.write(f"  Embed {i} Title: {title!r}\n")
                        f.write(f"  Embed {i} Desc: {desc!r}\n")
                        f.write(f"  Embed {i} Footer: {footer!r}\n")
                f.write("-" * 50 + "\n")
        except Exception as e:
            self.log(f"Debug log error: {e}", "ERROR")
        
        # Write kakera claims to CSV in the same place we write to log - no verification chain
        if message.content and "+" in message.content and "($k)" in message.content:
            claim_info = self._parse_kakera_claim(message.content)
            if claim_info.get("claimed_by") and claim_info.get("amount", 0) > 0:
                try:
                    os.makedirs("logs", exist_ok=True)
                    csv_path = os.path.join("logs", "kakera_history.csv")
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    server = getattr(message.channel, "name", "Unknown")
                    account = claim_info["claimed_by"]
                    ktype = claim_info.get("kakera_type") or "Unknown"
                    amount = claim_info["amount"]
                    header_needed = not os.path.isfile(csv_path) or os.path.getsize(csv_path) == 0
                    with open(csv_path, "a", newline="", encoding="utf-8") as f:
                        if header_needed:
                            f.write("Timestamp,Server,Account,Type,Amount\n")
                        f.write(f"{ts},{server},{account},{ktype},{amount}\n")
                except Exception as e:
                    self.log(f"Kakera CSV write error: {e}", "ERROR")
        
        if not message.embeds:
            return
        
        embed = message.embeds[0]
        
        # Check if it's a character embed
        if is_character_embed(embed):
            # Notify character listener
            if self.on_character_detected:
                try:
                    await self.on_character_detected(self, message, embed)
                except Exception as e:
                    self.log(f"Character listener error: {e}", "ERROR")
        
        # Check for kakera buttons
        has_kakera = False
        if message.components:
            for c in message.components:
                if isinstance(c, discord.ActionRow):
                    for b in c.children:
                        if isinstance(b, discord.Button) and b.emoji and getattr(b.emoji, 'name', None) in KAKERA_EMOJIS:
                            has_kakera = True
                            break
                if has_kakera:
                    break
        
        if has_kakera and self.on_kakera_detected:
            try:
                await self.on_kakera_detected(self, message, embed)
            except Exception as e:
                self.log(f"Kakera listener error: {e}", "ERROR")
```

### Message edits: footer “belongs to” / PT → optional `on_claim_success`

```885:914:bot_client.py
    async def _handle_message_edit(self, before: discord.Message, after: discord.Message):
        """Handle message edits (for claim confirmation)."""
        # CRITICAL: Only process messages from allowed channels
        if not self.is_channel_allowed(after.channel.id):
            return
        
        if after.author.id != TARGET_BOT_ID:
            return
        
        if not after.embeds:
            return
        
        embed = after.embeds[0]
        footer = (embed.footer.text or "") if embed.footer else ""
        
        # Check for ownership change
        if "belongs to" in footer.lower() or "pertence a" in footer.lower():
            # Check if we own it now
            own_names = self._get_own_names()
            is_ours = any(n in footer.lower() for n in own_names)
            
            if is_ours and self.on_claim_success:
                char_name = "Unknown"
                if embed.author and hasattr(embed.author, 'name'):
                    char_name = embed.author.name or "Unknown"
                
                try:
                    await self.on_claim_success(self, after, char_name)
                except Exception as e:
                    self.log(f"Claim success handler error: {e}", "ERROR")
```

### Embed text parsing (rolls / coordinator / listeners)

Used on **`embed.description`** (and keys), not Mudae plain chat:

```988:1061:bot_client.py
    @staticmethod
    def parse_keys(description: str) -> List[Dict[str, Any]]:
        """
        Parse keys from embed description.
        Discord format: <:bronzekey:123456> (**1**) or <:silverkey:123> (2)
        Returns list of dicts: {'type': 'silver', 'level': 3}
        """
        if not description:
            return []
        
        keys = []
        # Match <:typekey:ID> (level) or <:typekey:ID> (**level**)
        pattern = r'<:(bronze|silver|gold|chaos)key:\d+>\s*\(\*{0,2}(\d+)\*{0,2}\)'
        
        matches = re.finditer(pattern, description, re.IGNORECASE)
        for match in matches:
            keys.append({
                'type': match.group(1).lower(),
                'level': int(match.group(2))
            })
            
        return keys

    @staticmethod
    def parse_kakera_value(description: str) -> int:
        """Parse total kakera value from embed description."""
        if not description:
            return 0
        
        # Match patterns like: **510** <:kakera: or 510<:kakera:
        match = re.search(
            r"\*{0,2}(\d{1,3}(?:,\d{3})*|\d+)\*{0,2}\s*(?:<:kakera:|:kakera:|kakera)",
            description,
            re.IGNORECASE
        )
        
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                pass
        
        return 0
    
    @staticmethod
    def parse_individual_kakera(description: str) -> Dict[str, int]:
        """
        Parse individual kakera values and types from embed description.
        Returns dict mapping kakera type to value.
        
        Example description:
        "**145** <:kakera:469835869059153940> **715** <:kakeraO:469835869190905876>"
        Returns: {'kakera': 145, 'kakeraO': 715}
        """
        if not description:
            return {}
        
        kakera_map = {}
        
        # Pattern to match: **value** <:kakeraType:id>
        # Matches patterns like: **145** <:kakera:123456> or 145 <:kakeraY:789>
        pattern = r'\*{0,2}(\d{1,3}(?:,\d{3})*|\d+)\*{0,2}\s*<:(kakera[A-Z]?|kakeraP|kakeraT|kakeraG|kakeraL|kakeraW|kakeraR|kakeraO|kakeraY):\d+>'
        
        matches = re.finditer(pattern, description, re.IGNORECASE)
        
        for match in matches:
            try:
                value = int(match.group(1).replace(",", ""))
                kakera_type = match.group(2)
                kakera_map[kakera_type] = value
            except (ValueError, IndexError):
                continue
        
        return kakera_map
```

### Post-roll: scan recent channel messages (`event_coordinator.py`)

After rolls, the coordinator does **not** rely on live `on_message` for those embeds; it **polls `channel.history`** for recent Mudae character messages and then runs the same embed checks / `BotClient` parsers on each candidate.

```687:696:event_coordinator.py
    async def _process_post_roll(self, client: BotClient, channel, event: RollCycleEvent):
        """Process characters after rolling - decide what to claim."""
        # Fetch recent messages
        messages = []
        try:
            async for msg in channel.history(limit=event.rolls_sent * 2 + 10):
                if msg.author.id == TARGET_BOT_ID and msg.embeds:
                    if is_character_embed(msg.embeds[0]):
                        messages.append(msg)
```

### Related helpers in `config.py`

`is_character_embed`, `has_claim_option`, `get_character_owner`, `count_chaos_keys` classify Mudae **embeds** for listeners and `_process_post_roll` in `event_coordinator.py` (not duplicated here — see `config.py`).

---

## 1. Program map (how pieces connect)

| Block | Role |
|--------|------|
| `mudae_bot_gui.py` | Entry: instantiates `MudaeBotGUI` and calls `run_async()`. |
| `gui/main_window.py` | CustomTkinter shell: navigation, logging queue, start/stop, dialogs/tabs. |
| `gui/deployment.py` | Builds `EventCoordinator` from JSON (`deploy_all_configured` vs `deploy_bots`). |
| `gui/state.py` | Global `coordinator` handle for GUI ↔ backend. |
| `event_coordinator.py` | **Orchestrator**: thread + asyncio loop, scheduling, roll cycles, stats hooks. |
| `event_types.py` | Event model + **priority queue** (`EventQueue`). |
| `bot_client.py` | One Discord self-client per account: commands, parsing, buttons, listeners. |
| `listeners.py` | **Fast path**: kakera + wish/series/value snipes via callbacks (parallel to the event queue). |
| `config.py` | Constants, JSON loaders, Mudae embed helpers, logging helpers. |
| `stats_recorder.py` | Append/read CSV histories (claims, kakera, keys). |
| `display_image.py` | Standalone CTk viewer for cached run files (separate from main GUI). |
| `debug_assets.py` | One-off script: scans a hardcoded path for `.cache.json` files. |
| `depreciated/ascii_art_pane.py` | Legacy UI component (not wired to current flow). |

---

## 2. Core runtime (`event_coordinator.py`)

### Data structures

- **`ServerConfig`** — `channel_id`, `channel_name`, `accounts`, optional `mudae_prefix`.
- **`AccountConfig`** — token + preset mirror: rolls, snipes, kakera, dk, persrare, delays, `rolling`, etc.

### `EventCoordinator` — lifecycle

| Method | Purpose |
|--------|---------|
| `configure(accounts, servers)` | Store configs; init per-server account indices. |
| `start()` / `stop()` | Daemon thread; graceful disconnect. |
| `_run_thread` | Creates event loop; runs `_main_loop`. |
| `_main_loop` | Connect → initial setup → schedule → dequeue/process events. |
| `_interruptible_wait(seconds)` | Long waits with periodic stop checks. |

### Connection and listeners

| Method | Purpose |
|--------|---------|
| `_connect_all_accounts` | `BotClient` per account; `set_allowed_channels`; `ListenerManager.attach_to_client`. |
| `_disconnect_all_accounts` | Close clients; clear `self.clients`. |

### Initial setup

| Method | Purpose |
|--------|---------|
| `_run_initial_setup` | Per account, **each** server they use: `$limroul`, `$daily`, optional `$persrare`, `$dk` unless `dk_power_management`. |

### Scheduling (“Option B” style)

| Method | Purpose |
|--------|---------|
| `_schedule_initial_events` | Prime `_schedule_next_round`. |
| `_schedule_next_round` | Round-robin **servers**; only accounts past roll cooldown get events. |
| `_schedule_server_events` | Enqueue `RollCycleEvent` for every account on a server (skips `rolling: false`). |
| `_schedule_server_events_for_accounts` | Same for a subset of account names. |
| `_get_next_available_time` | Earliest time in `roll_cooldowns`. |
| `_schedule_followup` | Placeholder after roll cycle (minimal logic today). |

### Event execution

| Method | Purpose |
|--------|---------|
| `_process_event` | Dispatch by type; retries; `on_event_started` / `on_event_completed`. |
| `_process_roll_cycle` | `$tu` → optional `$dk` (power management) → `send_rolls` → `_process_post_roll`. |
| `_process_post_roll` | History scan; claim ranking (wishlist → series → kakera → “claim expiring”); `$rt`; kakera clicks; `record_*` stats. |
| `_process_status_check` | `$daily`, `$dk`. |
| `_process_claim_attempt` | Fetch message; `click_claim_button` (for queued snipes — **see gaps**). |
| `_process_kakera_react` | Fetch message; `click_kakera_buttons` (for queued kakera — **see gaps**). |

### Introspection

| Method | Purpose |
|--------|---------|
| `get_status()` | Running state, queue size, listener stats, etc. |
| `get_account_states()` | `Dict[str, AccountState]`. |

### Factory functions

| Function | Purpose |
|----------|---------|
| `create_coordinator_from_config(...)` | One **shared** preset for selected accounts; optional `server_filter` (channel names). |
| `create_coordinator_from_deployments(...)` | Per deployment: account + channel + preset. **Note:** first preset seen wins for `AccountConfig` if one account uses different presets per channel. |

---

## 3. Event model (`event_types.py`)

### Enums

- **`EventType`** — `ROLL_CYCLE`, `STATUS_CHECK`, `CLAIM_ATTEMPT`, `KAKERA_REACT`.
- **`EventStatus`** — lifecycle including retry semantics.

### `Event` base

- `mark_started`, `mark_completed`, `mark_failed`, `mark_skipped`, `mark_cancelled`, `is_timed_out`, `should_retry`, `duration` (property).

### Concrete events

- **`RollCycleEvent`** — preset fields + results (`rolls_sent`, `characters_seen`, `claim_attempted`, `rt_used`, etc.).
- **`StatusCheckEvent`** — `check_rt` / `check_daily` / `check_dk` flags (handler uses daily/dk in practice).
- **`ClaimAttemptEvent`** — immediate snipe target (message id, character, reasons).
- **`KakeraReactEvent`** — kakera button target.

### `EventQueue`

| Method | Purpose |
|--------|---------|
| `add` | Priority insert (claim → kakera → roll → status). |
| `pop` / `peek` | FIFO among same priority via insertion order. |
| `is_empty`, `size`, `clear` | Queue housekeeping. |
| `get_pending_for_account`, `remove_for_account` | Per-account filtering. |

---

## 4. Discord account layer (`bot_client.py`)

### `AccountState`

- Fields: claim / roll / RT / kakera reaction / DK / power; `processed_messages`.
- **`can_claim()`**, **`can_react_kakera()`**.

### `BotClient` — connection and channels

| Method | Purpose |
|--------|---------|
| `connect` / `disconnect` | `discord.Client`, `on_message`, `on_message_edit`. |
| `set_allowed_channels`, `add_allowed_channel`, `is_channel_allowed` | Scope listener + command context. |
| `get_channel` | Resolve `TextChannel` by id. |

### Commands and rolls

| Method | Purpose |
|--------|---------|
| `send_command` | Text `prefix+command`; `use_slash` delegates to `_send_slash_command` (stub — see gaps). |
| `send_tu_and_parse` | Parse EN/PT `$tu`; update `AccountState`. |
| `send_rolls` | Send N rolls with throttle `max(roll_speed, 0.6)`. |
| `send_rt`, `send_daily`, `send_dk` | Utility Mudae commands. |
| `wait_for_mudae_response` | Poll history with optional check function. |

### Interactions

| Method | Purpose |
|--------|---------|
| `click_claim_button` | Component buttons; optional delay; verify via edit. |
| `click_kakera_buttons` | Filters, verification, structured result dict. |

### Internal pipeline

| Method | Purpose |
|--------|---------|
| `_handle_message` | Mudae filter, dedup across clients, debug log, optional CSV from `($k)` lines, listener callbacks. |
| `_handle_message_edit` | Ownership footer → `on_claim_success` if self. |
| `_add_claim_reaction` | Emoji fallback. |
| `_send_slash_command` | **Returns False** (placeholder). |
| `_refresh_session_id`, `_get_own_names`, `_parse_hours_minutes` | Helpers. |
| `is_owner_me` | Compare owner string to self names. |

### Parsing (used by coordinator and listeners)

| Method | Purpose |
|--------|---------|
| `parse_keys`, `parse_kakera_value`, `parse_individual_kakera` | Embed/description parsing. |
| `_parse_kakera_claim` | Mudae text line after reaction. |

---

## 5. Fast listeners (`listeners.py`)

### `ListenerConfig`

Dataclass: kakera enable/delay/targets/only_chaos/types filter; wish/series/value snipe toggles, delays, thresholds.

### `KakeraListener`

| Method | Purpose |
|--------|---------|
| `log` | Routed through injected log function. |
| `on_message(bot_client, message, embed)` | Detect kakera buttons; filters; cooldown; `click_kakera_buttons`; stats + CSV. |

### `WishSnipeListener`

| Method | Purpose |
|--------|---------|
| `log` | Same pattern. |
| `on_message(bot_client, message, embed)` | Wishlist → series → value; `can_claim`; delayed `click_claim_button`; `record_claim`. |

### `ListenerManager`

| Method | Purpose |
|--------|---------|
| `create_listeners_for_account` | Build kakera + wish listeners. |
| `attach_to_client` | Sets `bot_client.on_kakera_detected` / `on_character_detected`. |
| `get_stats` | Aggregate listener counters. |
| `clear_account` | Remove listener entries for an account. |

---

## 6. Shared config and Mudae helpers (`config.py`)

### Constants

- `BOT_NAME`, `TARGET_BOT_ID`, `CLAIM_EMOJIS`, `KAKERA_EMOJIS`, `KAKERA_INFO`, `LOG_FILES`.

### Loading

- `load_account_info`, `load_presets` — module-level `account_info`, `presets` after import.

### Validation

- `validate_preset` — expects `token` + `channel_id` on preset object (**legacy** vs split `Account_info.json` + `presets.json`).

### Logging

- `ensure_log_directory`, `log_session_start`, `write_log_to_file`, `color_log`, `print_log`.

### Embed/message helpers

- `is_character_embed`, `has_claim_option`, `count_chaos_keys`, `get_character_owner`.

---

## 7. Statistics (`stats_recorder.py`)

| Function | Purpose |
|----------|---------|
| `ensure_log_directory` | Create `logs/` if missing. |
| `record_claim` / `get_claim_history` | `logs/claim_history.csv` |
| `record_kakera_claim` / `get_kakera_history` | `logs/kakera_history.csv` |
| `record_key` / `get_key_history` | `logs/key_history.csv` |

---

## 8. GUI layer

### `gui/main_window.py` — `MudaeBotGUI`

- **Settings:** `load_user_settings`, `save_user_settings`, `set_last_preset`, `reset_all_settings`, `reset_window_size`.
- **Theme:** `apply_theme`, `update_log_tags`, `update_theme_colors`.
- **Layout:** `setup_ui`, `create_sidebar`, `create_top_bar`, `create_dashboard`, `create_statistics`, `create_kakera_stats`, `create_key_stats`, `switch_view`.
- **Logging:** `process_log_queue`, `log_message`, `show_notification`.
- **Navigation:** `show_dashboard`, `show_statistics`, `show_kakera_stats`, `show_key_stats`, `show_accounts`, `show_presets`, `show_preset_editor`, `show_servers`, `show_deployments`, `open_settings`.
- **Bots:** `start_bots`, `on_deployment_configured`, `run_async_deployment`, `run_configured_deployment`, `_run_configured_deployment_thread`, `stop_all_bots`, `update_status`.
- **Lifecycle:** `on_close`, `run_async`, `start_loop`, `_batch_ui_update`.

### Dialogs (`gui/dialogs/`)

| File | Classes / main roles |
|------|----------------------|
| `account_dialogs.py` | `AccountSelectionDialog`, `AccountManagementDialog`, `AddEditAccountDialog` |
| `server_dialogs.py` | `ServerSelectionDialog`, `ServerManagementDialog` (drag reorder), `AddEditChannelDialog` |
| `preset_dialogs.py` | `PresetSelectionDialog`, `PresetManagementDialog`, `PresetEditorDialog` |
| `settings_dialog.py` | `SettingsDialog` |
| `deployment_dialogs.py` | `EditAccountDeploymentsDialog`, `DeploymentManagerDialog` |

### Tabs (`gui/tabs/`)

- `statistics_tab.py` — `StatisticsTab`
- `kakera_stats_tab.py` — `KakeraStatsTab`
- `key_stats_tab.py` — `KeyStatsTab`

Shared patterns: `setup_ui`, `refresh_data`, filters, search, `sort_data`, pagination, `on_show`.

### `gui/utils.py`

- `_hex_to_bgr_int`, `_set_windows_titlebar_theme`, `_apply_dialog_titlebar`, `setup_logging`.

### `gui/state.py`

- `get_coordinator`, `set_coordinator`.

### `gui/deployment.py`

- `deploy_all_configured(main_gui)` — full JSON-driven deployments → `create_coordinator_from_deployments`.
- `deploy_bots(main_gui, account_presets, selected_servers=None)` — wizard → `create_coordinator_from_config`.

---

## 9. Ancillary tools

### `display_image.py`

- `_load_runs_from_cache(path)`
- `SettingsWindow`, `App` — browse cache JSON, grid sizing, `_render_runs_to_textbox`, resize handlers.

### `debug_assets.py`

- Standalone scan of a fixed Windows `ASSETS_DIR` for `.cache.json`.

### `depreciated/ascii_art_pane.py`

- `ArtTheme`, `AsciiArtPane`.

---

## 10. Feature status (implemented vs gaps)

### Implemented (coordinator + client + listeners)

- Multi-account self-sessions; channel allowlists.
- Global sequential event loop + typed priority queue.
- Roll cycle: `$tu` (EN/PT), roll cooldowns, optional DK when power low, batched rolls, post-roll analysis.
- Claim priority: wishlist → series → min kakera → “claim resets within ~60m” fallback.
- Optional `$rt` when `min_kakera_rt > 0`.
- Kakera collection on rolled characters (with verification and stats).
- External sniping: wishlist, series, kakera value (`WishSnipeListener`).
- External kakera: owner filter, chaos-only, type filter (`KakeraListener`).
- Startup: `$limroul`, `$daily`, `$persrare`, conditional `$dk`.
- Snipe-only: `rolling: false` skips scheduled roll cycles; listeners still apply if enabled.
- CSV stats + categorized log files + GUI log queue + optional `mudae_debug.log`.

### Partial, stub, or documentation drift

| Item | Notes |
|------|--------|
| Slash rolls | `use_slash_rolls` exists; `_send_slash_command` always fails → text only. |
| `ClaimAttemptEvent` / `KakeraReactEvent` | Handlers exist; **listeners call `BotClient` directly** — these events are not enqueued in current code. |
| `key_mode` | Present on config/event types; **no gating logic** found in roll path. |
| `StatusCheckEvent` | Not scheduled in main coordinator flow reviewed; `_process_status_check` does not use all event flags. |
| Humanization / reactive snipe | Fields in **preset editor** / README; **not wired** in coordinator or `BotClient`. |
| `validate_preset` | Expects monolithic preset shape; app uses split JSON files. |
| Per-channel presets | Deployments list multiple presets per account; **first preset** seeds `AccountConfig` for that account. |

---

## 11. Suggested boundaries for a rewrite

1. **Config schema + validation** — single model for accounts, channels, presets, deployments.
2. **Transport** — Discord client, rate limits, optional slash.
3. **Mudae protocol** — `$tu` parsing, embed classification, buttons, locales.
4. **Scheduler** — ordering, cooldowns, optional humanization, key mode.
5. **Strategies** — post-roll ranking, RT policy, kakera policy.
6. **Realtime vs queue** — unify listeners with priority queue or keep dual path explicitly.
7. **Observability** — logs, metrics, persistence (CSV vs DB).
8. **UI** — reuse or replace CustomTkinter shell.

---

## 12. Related docs in repo

- `information and guides/README.md` — product overview and preset examples (may exceed current code in places).
- `information and guides/*.md` — logging, kakera filters, smart claiming, preset editor, refactoring notes.

---

*Generated as a structural index of the codebase; adjust as you refactor.*
