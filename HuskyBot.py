#!/usr/bin/env python3

import datetime
# System imports
import logging
import os
import ssl
import sys
import traceback
from typing import *

# discord.py imports
import discord
import discord.http
from discord.ext import commands

# Database imports
try:
    import sqlalchemy
    from sqlalchemy.exc import DatabaseError
    from sqlalchemy import orm
except ImportError:
    sqlalchemy = None
    DatabaseError = None
    orm = None

# aiohttp/web api support
from aiohttp import web

from libhusky import HuskyConfig
from libhusky import HuskyHTTP
from libhusky import HuskyUtils
from libhusky.HuskyStatics import *
from libhusky.discord.HuskyHelpFormatter import HuskyHelpFormatter

LOG = logging.getLogger("HuskyBot.Core")


class HuskyBot(commands.Bot, metaclass=HuskyUtils.Singleton):
    def __init__(self):
        self.init_stage = -1

        # Load in configuration and other important things here.
        self.config = HuskyConfig.get_config()
        self.session_store = HuskyConfig.get_session_store()

        self.developer_mode = self.__check_developer_mode()
        self.superusers = []

        # Private variables used for init only
        self.__daemon_mode = (os.getppid() == 1)
        self.session_store.set("daemonMode", self.__daemon_mode)

        self.__log_path = 'logs/huskybot.log'
        self.session_store.set('logPath', self.__log_path)

        # Database things
        # noinspection PyTypeChecker
        self.db: Optional[sqlalchemy.engine.Engine] = None
        self.session_factory = None

        # Load in HuskyBot's logger
        self.logger = self.__initialize_logger()

        # Load in HuskyBot's API
        self.webapp = web.Application()

        # Allow setting custom routes (litecord/canary/apiv7 support)
        discord.http.Route.BASE = os.getenv('DISCORD_API_URL', discord.http.Route.BASE)

        super().__init__(
            command_prefix=self.config.get('prefix', '/'),
            status=discord.Status.idle,
            activity=self.__build_stage0_activity(),
            command_not_found="**Error:** The bot could not find the command `/{}`.",
            command_has_no_subcommands="**Error:** The command `/{}` has no subcommands.",
            help_command=HuskyHelpFormatter()
        )

        self.init_stage = 0

    def entrypoint(self):
        if os.environ.get('DISCORD_TOKEN'):
            LOG.debug("Loading API key from environment variable DISCORD_TOKEN.")
        elif self.config.get('apiKey'):
            LOG.warning("DEPRECATION WARNING - The Discord API key is being retrieved from the config file. "
                        "This capability will be removed in a future release. Please move the token to the "
                        "DISCORD_TOKEN environment variable.")
        else:
            LOG.critical("The API key for HuskyBot must be loaded via the DISCORD_TOKEN environment variable.")
            exit(1)

        LOG.info("The bot's log path is: {}".format(self.__log_path))

        if HuskyUtils.is_docker():
            LOG.info("The bot has detected it is running in Docker. Some internal systems have been changed in order "
                     "to better suit the container land.")

        if self.__daemon_mode:
            LOG.info("The bot is currently loaded in Daemon Mode. In Daemon Mode, certain functionalities are "
                     "slightly altered to better utilize the headless environment.")

        if self.developer_mode:
            LOG.info("The bot is running in DEVELOPER MODE! Some features may behave in unexpected ways or may "
                     "otherwise break. Some bot safety checks are disabled with this mode on.")

        self.run(os.getenv('DISCORD_TOKEN', self.config.get('apiKey')))

        LOG.info("Shutting down HuskyBot...")

        self.config.save()
        LOG.debug("Config file saved/written to disk.")

        if self.db:
            self.db.dispose()
            LOG.debug("DB connection shut down")

        if self.config.get("restartReason") is not None:
            LOG.info("Bot is ready for restart...")
            os.execl(sys.executable, *([sys.executable] + sys.argv))

    async def logout(self):
        LOG.info("Shutting down HuskyBot...")

        await super().logout()

    def __check_developer_mode(self):
        return bool(os.environ.get('HUSKYBOT_DEVMODE', self.config.get('developerMode', False)))

    def __build_stage0_activity(self):
        mapping = {
            "admin": "Restarting...",
            "update": "Updating...",
            None: "Starting..."
        }

        restart_reason = self.config.get("restartReason")

        if restart_reason is not None:
            self.config.delete("restartReason")

        return discord.Activity(
            name=mapping.get(restart_reason, "Starting..."),
            type=discord.ActivityType.playing
        )

    def __initialize_logger(self):
        # Build the to-file logger HuskyBot uses.
        file_log_handler = HuskyUtils.CompressingRotatingFileHandler(self.session_store.get('logPath'),
                                                                     maxBytes=(1024 ** 2) * 5,
                                                                     backupCount=5,
                                                                     encoding='utf-8')
        file_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

        # Build the to-stream logger
        stream_log_handler = logging.StreamHandler(sys.stdout)
        if self.__daemon_mode:
            stream_log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

        # noinspection PyArgumentList
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[file_log_handler, stream_log_handler]
        )

        bot_logger = logging.getLogger("HuskyBot")
        bot_logger.setLevel(logging.INFO)

        if self.developer_mode:
            bot_logger.setLevel(logging.DEBUG)
            LOG.setLevel(logging.DEBUG)

        return bot_logger

    async def __init_guild_lock(self):
        locked_guild = self.config.get('guildId')

        if locked_guild:
            for guild in self.guilds:  # type: discord.Guild
                if guild.id != locked_guild:
                    LOG.warning(f"Bot was in unauthorized guild {guild.name} ({guild.id}). "
                                f"Leaving the guild.")
                    await guild.leave()
        elif len(self.guilds) == 1:
            LOG.info(f"The bot did not have a guild locked, but was a member of one. Locking the bot to guild ID "
                     f"{self.guilds[0].id}.")
            self.config.set('guildId', self.guilds[0].id)
        elif len(self.guilds) > 1:
            LOG.critical("The bot is in multiple guilds without being locked to a guild. Please remove the bot from "
                         "extra guilds, or specify a guildId in the configuration.")
            exit(127)
        else:
            LOG.info("The bot is not associated with any guilds yet. The next guild joined by the bot will be locked.")

    async def __initialize_webserver(self):
        http_config = self.config.get('httpConfig', {
            "host": "127.0.0.1",
            "port": "9339",
            "ssl_cert": None
        })

        ssl_context = None
        if http_config.get('ssl_cert', None) is not None:
            with open(http_config.get('ssl_cert', 'certs/cert.pem'), 'r') as cert:
                ssl_context = ssl.SSLContext()
                ssl_context.load_cert_chain(cert.read())

        for method in ["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE", "VIEW"]:
            # Abuse the hell out of aiohttp's own router to load in HuskyRouter.
            self.webapp.router.add_route(method, '/{tail:.*}', HuskyHTTP.get_router().handle(self))

        runner = web.AppRunner(self.webapp)
        await runner.setup()
        site = web.TCPSite(runner, host=http_config['host'], port=http_config['port'], ssl_context=ssl_context)
        await site.start()
        LOG.info(f"Started {'HTTPS' if ssl_context is not None else 'HTTP'} server at "
                 f"{http_config['host']}:{http_config['port']}, now listening...")

    async def __initialize_database(self):
        if not sqlalchemy:
            LOG.warning("SQLAlchemy is not present on this installation of HuskyBot. Database support is disabled.")
            return

        try:
            c = f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}" \
                f"@db:5432/{os.environ['POSTGRES_DB']}"
            self.db = sqlalchemy.create_engine(c)
        except KeyError:
            LOG.warning("No database configuration was set for Husky. Database support is disabled.")
            return
        except DatabaseError as s:
            LOG.error(f"Could not connect to the database! The error is as follows: \n{s}")

        self.session_factory = sqlalchemy.orm.sessionmaker(bind=self.db)

    async def __init_load_plugins(self):
        # Note: Custom plugins come *before* default plugins. This means you can swap out any plugin for your own ver
        sys.path.insert(1, os.getcwd() + "/plugins/custom/")
        sys.path.insert(2, os.getcwd() + "/plugins/")

        self.load_extension('Base')
        self.load_extension('BotAdmin')

        plugin_list = self.config.get('plugins', [])

        if self.developer_mode:
            plugin_list = ["Debug"] + plugin_list

        for plugin in plugin_list:
            # noinspection PyBroadException
            try:
                self.load_extension(plugin)
            except Exception:
                await self.on_error('initialize/load_plugin/' + plugin)

    async def __init_inform_restart(self):
        if self.config.get("restartNotificationChannel") is not None:
            channel = self.get_channel(self.config.get("restartNotificationChannel"))
            await channel.send(embed=discord.Embed(
                title=Emojis.REFRESH + " Bot Manager",
                description="The bot has been successfully restarted, and is now online.",
                color=Colors.SUCCESS
            ))
            self.config.delete("restartNotificationChannel")

    async def __get_superusers(self, app_info: discord.AppInfo = None) -> []:
        su_list = self.config.get('superusers', [])

        if not app_info:
            app_info: discord.AppInfo = await self.application_info()

        if app_info.team:
            for team_member in app_info.team.members:
                if team_member.membership_state == discord.TeamMembershipState.accepted and not team_member.bot:
                    su_list.append(team_member.id)
        else:
            su_list.append(app_info.owner.id)

        return list(set(su_list))

    # noinspection PyBroadException
    async def init(self):
        if self.init_stage != 0:
            LOG.warning("The bot attempted to re-run initialization. Did the network or similar die?")
            return

        try:
            await self.init_stage1()
            await self.init_stage2()
        except Exception as e:
            try:
                await self.init_recovery()
            except Exception:
                LOG.critical("Failed to launch recovery mode, flailing...")
                exit(127)  # just crash at this point, something is very very bad.
            raise e

    async def init_stage1(self):
        """
        Initialize the bot logger and other critical services. Init stage 1 will *not* re-run if it has executed.
        """

        # Load in application information
        app_info = await self.application_info()
        self.session_store.set("appInfo", app_info)

        # Load in superusers
        self.superusers = await self.__get_superusers(app_info)
        LOG.info(f"Superusers loaded: {self.superusers}")

        LOG.info(f"HuskyBot is online, running discord.py {discord.__version__}. Initializing and "
                 f"loading modules...")

        self.init_stage = 1

    async def init_stage2(self):
        if not self.developer_mode:
            await self.__init_guild_lock()

        await self.__initialize_webserver()
        await self.__initialize_database()
        await self.__init_load_plugins()

        await self.__init_inform_restart()

        self.session_store.set('initTime', datetime.datetime.now())
        LOG.info("The bot has been initialized. Ready to process commands and events.")

        self.init_stage = 2

    async def init_recovery(self):
        LOG.critical("The bot has loaded into recovery mode due to an unrecoverable initialization failure.")
        sys.path.insert(2, os.getcwd() + "/plugins/")

        recovery_plugins = ['Base', 'BotAdmin', 'Debug']

        for plugin in recovery_plugins:
            LOG.info(f"Loaded recovery mode plugin {plugin}")
            self.load_extension(plugin)

        await self.change_presence(
            activity=discord.Activity(name="< RECOVERY MODE >", type=discord.ActivityType.playing),
            status=discord.Status.dnd
        )

        self.init_stage = -127

    async def on_ready(self):
        await self.init()

        ready_presence = self.config.get('presence', {"game": "HuskyBot", "type": 2, "status": "dnd"})

        await self.change_presence(
            activity=discord.Activity(name=ready_presence['game'], type=ready_presence['type']),
            status=discord.Status[ready_presence['status']]
        )

    async def on_guild_join(self, guild: discord.Guild):
        if self.config.get('guildId') is None:
            self.config.set('guildId', guild.id)
            LOG.info(f"This bot has been locked to {guild.name} (ID {guild.id})!")
            return

        if not self.developer_mode:
            if guild.id != self.config.get("guildId"):
                LOG.warning(f"The bot has joined an unauthorized guild {guild.name} ({guild.id}). "
                            f"The bot is leaving the guild...")
                await guild.leave()

    async def on_message(self, message: discord.Message):
        author = message.author
        if not HuskyUtils.should_process_message(message):
            return

        if message.content.startswith(self.command_prefix):
            if (author.id in self.config.get('userBlacklist', [])) and (author.id not in self.superusers):
                LOG.info("Blacklisted user %s attempted to run command %s", message.author, message.content)
                return

            if message.content.lower().split(' ')[0][1:] in self.config.get('ignoredCommands', []):
                LOG.info("User %s ran an ignored command %s", message.author, message.content)
                return

            if message.content.lower().split(' ')[0].startswith('/r/'):
                LOG.info("User %s linked to subreddit %s, ignoring command", message.author, message.content)
                return

            if self.session_store.get('lockdown', False) and (author.id not in self.superusers):
                LOG.info("Lockdown mode is enabled for the bot. Command blocked.")
                return

            if message.channel.id in self.config.get("disabledChannels", []) and isinstance(author, discord.Member) \
                    and not author.permissions_in(message.channel).manage_messages:
                LOG.info(f"Got a command from a disabled channel {message.channel}. Command blocked.")
                return

            LOG.info("User %s ran %s", author, message.content)

            await self.process_commands(message)

    async def on_error(self, event_method, *args, **kwargs):
        exception = sys.exc_info()

        channel = self.config.get('specialChannels', {}).get(ChannelKeys.STAFF_LOG.value, None)

        if channel is None:
            LOG.warning('A logging channel is not set up! Error messages will not be forwarded to '
                        'Discord.')
            raise exception

        channel = self.get_channel(channel)

        if isinstance(exception, discord.HTTPException) and exception.code == 502:
            LOG.error(f"Got HTTP status code {exception.code} for method {event_method} - Discord is "
                      f"likely borked now.")
        else:
            LOG.error('Exception in method %s:\n%s', event_method, traceback.format_exc())

            try:
                embed = discord.Embed(
                    title="Bot Exception Handler",
                    description="Exception in method `{}`:\n```{}```".format(
                        event_method,
                        HuskyUtils.trim_string(traceback.format_exc().replace('```', '`\u200b`\u200b`'), 1500)
                    ),
                    color=Colors.DANGER
                )

                owner_id = self.session_store.get('appInfo', None).owner.id
                dev_ping = self.config.get("specialRoles", {}).get(SpecialRoleKeys.BOT_DEVS.value, owner_id)

                await channel.send("<@{}>, an error has occurred with the bot. See attached "
                                   "embed.".format(dev_ping),
                                   embed=embed)
            except Exception as e:
                LOG.critical("There was an error sending an error to the error channel.\n " + str(e))
                raise e

    async def on_command_error(self, ctx, error: commands.CommandError):
        p = self.command_prefix
        command_name = HuskyUtils.trim_string(ctx.message.content.split(' ')[0][1:], 32, True, '...')

        error_string = HuskyUtils.trim_string(str(error).replace('```', '`\u200b`\u200b`'), 128)

        # Handle cases where the calling user is missing a required permission.
        if isinstance(error, commands.MissingPermissions):
            if self.developer_mode:
                await ctx.send(embed=discord.Embed(
                    title="Command Handler",
                    description=f"**You are not authorized to run `{p}{command_name}`:**\n```{error_string}```\n\n"
                                f"Please ask a staff member for assistance.",
                    color=Colors.DANGER
                ))

            LOG.error("Encountered permission error when attempting to run command %s: %s",
                      command_name, str(error))

        # Handle cases where the command is disabled.
        elif isinstance(error, commands.DisabledCommand):
            if self.developer_mode:
                embed = discord.Embed(
                    title="Command Handler",
                    description=f"**The command `{p}{command_name}` is disabled.** See `{p}help` for valid "
                                f"commands.",
                    color=Colors.DANGER
                )

                await ctx.send(embed=embed)

            LOG.error("Command %s is disabled.", command_name)

        # Handle cases where the command does not exist.
        elif isinstance(error, commands.CommandNotFound):
            if self.developer_mode:
                await ctx.send(embed=discord.Embed(
                    title="Command Handler",
                    description=f"**The command `{p}{command_name}` does not exist.** See `{p}help` for valid "
                                f"commands.",
                    color=Colors.DANGER
                ))

            LOG.error("Command %s does not exist to the system.", command_name)

        # Handle cases where a prerequisite command check failed to execute
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(embed=discord.Embed(
                title="Command Handler",
                description=f"**The command `{p}{command_name}` failed an execution check.** Additional information "
                            f"may be provided below.",
                color=Colors.DANGER
            ).add_field(name="Error Log", value="```" + error_string + "```", inline=False))

            LOG.error("Encountered check failure when attempting to run command %s: %s",
                      command_name, str(error))

        # Handle cases where a command is run over a Direct Message without working over DMs
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=discord.Embed(
                title="Command Handler",
                description=f"**The command `{p}{command_name}` may not be run in a DM.** See `{p}help` for valid "
                            f"commands.",
                color=Colors.DANGER
            ))

            LOG.error("Command %s may not be run in a direct message!", command_name)

        # Handle cases where a command is run missing a required argument
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(
                title="Command Handler",
                description=f"**The command `{p}{command_name}` could not run, because it is missing arguments.**\n"
                            f"See `{p}help {command_name}` for the arguments required.",
                color=Colors.DANGER
            ).add_field(name="Missing Parameter", value="`" + error_string.split(" ")[0] + "`", inline=True))
            LOG.error("Command %s was called with the wrong parameters.", command_name)
            return

        # Handle cases where an argument can not be parsed properly.
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=discord.Embed(
                title="Command Handler",
                description=f"**The command `{p}{command_name}` could not understand the arguments given.**\n"
                            f"See `{p}help {command_name}` and the error below to fix this issue.",
                color=Colors.DANGER
            ).add_field(name="Error Log", value="```" + error_string + "```", inline=False))

            LOG.error("Command %s was unable to parse arguments: %s", command_name, str(error))
            LOG.error(''.join(traceback.format_exception(type(error), error, error.__traceback__)))

        # Handle cases where the bot is missing a required execution permission.
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(embed=discord.Embed(
                title="Command Handler",
                description=f"**The command `{p}{command_name}` could not execute successfully, as the bot does not "
                            f"have a required permission.**\nPlease make sure that the bot has the following "
                            f"permissions: " +
                            "`{}`".format(', '.join(error.missing_perms)),
                color=Colors.DANGER
            ))

            LOG.error("Bot is missing permissions %s to execute command %s", error.missing_perms, command_name)

        # Handle commands on cooldown
        elif isinstance(error, commands.CommandOnCooldown):
            seconds = round(error.retry_after)
            tx = "{} {}".format(seconds, "second" if seconds == 1 else "seconds")

            await ctx.send(embed=discord.Embed(
                title="Command Handler",
                description=f"**The command `{p}{command_name}` has been run too much recently!**\n"
                            f"Please wait **{tx}** until trying again.",
                color=Colors.DANGER
            ))

            LOG.error("Command %s was on cooldown, and is unable to be run for %s seconds. Cooldown: %s",
                      command_name, round(error.retry_after, 0), error.cooldown)

        # Handle any and all other error cases.
        else:
            await ctx.send(embed=discord.Embed(
                title="Bot Error Handler",
                description="The bot has encountered a fatal error running the command given. Logs are below.",
                color=Colors.DANGER
            ).add_field(name="Error Log", value="```" + error_string + "```", inline=False))
            LOG.error("Error running command %s. See below for trace.\n%s",
                      ctx.message.content,
                      ''.join(traceback.format_exception(type(error), error, error.__traceback__)))

            # ToDo: Clean this up a bit more so these commands don't have hardcoded exemptions.
            if command_name.lower() in ["eval", "feval", "requestify"]:
                LOG.info(f"Suppressed critical error reporting for command {command_name}")
                return

            # Send it over to the main error logger as well.
            raise error


if __name__ == '__main__':
    if os.name != "posix":
        # Critical logging isn't the best way to do this, as this is (technically) before the logger is initialized,
        # but it's still somewhat there. We just haven't hooked in our fancy features yet.
        LOG.critical("This application may only run on POSIX-compliant operating systems such as Linux or macOS.")
        exit(1)

    bot = HuskyBot()
    bot.entrypoint()
    LOG.info("Left entrypoint, bot has shut down. Goodbye, everybody!")
