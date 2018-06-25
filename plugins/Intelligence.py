import datetime
import logging

import discord
from discord.ext import commands
from discord.http import Route

from WolfBot import WolfConfig
from WolfBot import WolfConverters
from WolfBot import WolfUtils
from WolfBot.WolfStatics import *

LOG = logging.getLogger("DakotaBot.Plugin." + __name__)


class Intelligence:
    """
    Intelligence is a plugin focusing on gathering information from Discord.

    It is used to query data about users (or roles/guilds) from guilds. Commands are generally open to execution for
    all users, and only expose information provided by the Discord API, not information generated by the bot or bot
    commands.

    All commands here query their information directly from the Discord API in near realtime.
    """

    def __init__(self, bot):
        self.bot = bot
        self._config = WolfConfig.get_config()
        LOG.info("Loaded plugin!")

    @commands.command(name="guildinfo", aliases=["sinfo", "ginfo"], brief="Get information about the current guild")
    @commands.guild_only()
    async def guild_info(self, ctx: discord.ext.commands.Context):
        """
        Get an information dump for the current guild.

        This command returns basic core information about a guild for reporting purposes.
        """

        guild = ctx.guild

        guild_details = discord.Embed(
            title="Guild Information for " + guild.name,
            color=guild.owner.color
        )

        guild_details.set_thumbnail(url=guild.icon_url)
        guild_details.add_field(name="Guild ID", value=guild.id, inline=True)
        guild_details.add_field(name="Owner", value=guild.owner.display_name + "#" + guild.owner.discriminator,
                                inline=True)
        guild_details.add_field(name="Members", value=str(len(guild.members)) + " users", inline=True)
        guild_details.add_field(name="Text Channels", value=str(len(guild.text_channels)) + " channels", inline=True)
        guild_details.add_field(name="Roles", value=str(len(guild.roles)) + " roles", inline=True)
        guild_details.add_field(name="Voice Channels", value=str(len(guild.voice_channels)) + " channels", inline=True)
        guild_details.add_field(name="Created At", value=guild.created_at.strftime(DATETIME_FORMAT), inline=True)
        guild_details.add_field(name="Region", value=guild.region, inline=True)

        if len(guild.features) > 0:
            guild_details.add_field(name="Features", value=", ".join(guild.features))

        await ctx.send(embed=guild_details)

    @commands.command(name="roleinfo", aliases=["rinfo"], brief="Get information about a specified role.")
    @commands.guild_only()
    async def role_info(self, ctx: discord.ext.commands.Context, *, role: discord.Role):
        """
        Get basic information about a specific role in this guild.

        This command will dump configuration information (with the exception of permissions) for the selected role. It
        will also attempt to count the number of users with the specified role.

        Parameters:
            role - A uniquely identifying role string. This can be a role mention, a role ID, or name.
                   This parameter is case-sensitive, but does not need to be "quoted in case of spaces."

        Example Command:
            /roleinfo Admins - Get information about the role "Admins"
        """

        role_details = discord.Embed(
            title="Role Information for " + role.name,
            color=role.color
        )

        role_details.add_field(name="Role ID", value=role.id, inline=True)

        if role.color.value == 0:
            role_details.add_field(name="Color", value="None", inline=True)
        else:
            role_details.add_field(name="Color", value=str(hex(role.color.value)).replace("0x", "#"), inline=True)

        role_details.add_field(name="Mention Preview", value=role.mention, inline=True)
        role_details.add_field(name="Hoisted", value=role.hoist, inline=True)
        role_details.add_field(name="Managed Role", value=role.managed, inline=True)
        role_details.add_field(name="Mentionable", value=role.mentionable, inline=True)
        role_details.add_field(name="Position", value=role.position, inline=True)
        role_details.add_field(name="Member Count", value=str(len(role.members)), inline=True)

        await ctx.send(embed=role_details)

    @commands.command(name="userinfo", aliases=["uinfo", "memberinfo", "minfo", "whois"],
                      brief="Get information about self or specified user")
    async def user_info(self, ctx: discord.ext.commands.Context, *,
                        user: WolfConverters.OfflineMemberConverter = None):
        """
        Get basic information about a calling user.

        This command will attempt to return join dates, name status, roles, and the index number of the user in the
        current guild. The bot will attempt to get information for users not in the guild, but information in this case
        is somewhat limited.

        Parameters:
            user - A uniquely identifying user string, such as a mention, a user ID, a username, or a nickname.
                   This parameter is case-sensitive, but does not need to be "quoted in case of spaces."

        Example Command:
            /uinfo SomeUser#1234 - Get information for user "SomeUser#1234".
        """

        user = user or ctx.author

        if isinstance(user, discord.User):
            member_details = discord.Embed(
                title="User Information for " + user.name + "#" + user.discriminator,
                color=Colors.INFO,
                description="Currently **not a member of any shared guild!**\nData may be limited."
            )
        elif isinstance(user, discord.Member):
            member_details = discord.Embed(
                title="User Information for " + user.name + "#" + user.discriminator,
                color=user.color,
                description="Currently in **" + str(user.status) + "** mode " + WolfUtils.get_fancy_game_data(user)
            )
        else:
            raise ValueError("Illegal state!")

        roles = []
        if isinstance(user, discord.Member) and ctx.guild is not None:
            for r in user.roles:
                if r.name == "@everyone":
                    continue

                roles.append(r.mention)

            if len(roles) == 0:
                roles.append("None")

        member_details.add_field(name="User ID", value=user.id, inline=True)

        if isinstance(user, discord.Member) and ctx.guild is not None:
            member_details.add_field(name="Display Name", value=user.display_name, inline=True)

        member_details.add_field(name="Joined Discord", value=user.created_at.strftime(DATETIME_FORMAT), inline=True)
        member_details.set_thumbnail(url=user.avatar_url)

        if isinstance(user, discord.Member) and ctx.guild is not None:
            member_details.add_field(name="Joined Guild", value=user.joined_at.strftime(DATETIME_FORMAT), inline=True)
            member_details.add_field(name="Roles", value=", ".join(roles), inline=False)

            member_details.set_footer(text="Member #{} on the guild"
                                      .format(str(sorted(ctx.guild.members,
                                                         key=lambda m: m.joined_at).index(user) + 1)))

        await ctx.send(embed=member_details)

    @commands.command(name="avatar", brief="Get a link/high-resolution version of a user's avatar")
    async def avatar(self, ctx: commands.Context, *, user: WolfConverters.OfflineUserConverter = None):
        """
        Get a high-resolution version of a user's avatar.

        This command will attempt to find and return the largest possible version of a user's avatar that it can, as
        well as the avatar hash.

        This command takes a single (optional) argument - a member identifier. This may be a User ID, a ping, a
        username, a nickname, etc. If this argument is not specified, the bot will return the avatar of the calling
        user.

        Parameters:
            user - A uniquely identifying user string, such as a mention, a user ID, a username, or a nickname.
                   This parameter is case-sensitive, but does not need to be "quoted in case of spaces."


        Example Commands:
            /avatar               - Get the calling user's avatar.
            /avatar SomeUser#1234 - Get avatar for user "SomeUser#1234"
        """

        user = user or ctx.author

        embed = discord.Embed(
            title="Avatar for {}".format(user),
            color=Colors.INFO
        )

        embed.add_field(name="Avatar ID", value="`{}`".format(user.avatar), inline=False)
        embed.add_field(name="Avatar URL", value="[Open In Browser >]({})".format(user.avatar_url), inline=False)
        embed.set_image(url=user.avatar_url)

        await ctx.send(embed=embed)

    @commands.command(name="msgcount", brief="Get a count of messages in a given context")
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def message_count(self, ctx: commands.Context,
                            search_context: WolfConverters.ChannelContextConverter = "public",
                            timedelta: WolfConverters.DateDiffConverter = "24h"):
        """
        Get a count of messages in any given context.

        A context/area is defined as a single channel, the keyword "all", or the keyword "public". If a channel name is
        specified, only that channel will be searched. "all" will attempt to search every channel that exists in the
        guild. "public" will search every channel in the guild that can be seen by the @everyone user.

        Timedelta is a time string formatted in 00d00h00m00s format. This may only be used to search back.

        CAVEATS: It is important to know that this is a *slow* command, because it needs to iterate over every message
        in the search channels in order to successfully operate. Because of this, the "Typing" indicator will display.
        Also note that this command may not return accurate results due to the nature of the search system. It should be
        used for approximation only.

        Parameters:
            search_context - A search context as described above. Default "public".
            timedelta      - A timedelta string as described above. Default 24h.

        Example Commands:
            /msgcount public 7d   - Get a count of all public messages in the last 7 days
            /msgcount all 2d      - Get a count of all messages in the last two days.
            /msgcount #general 5h - Get a count of all messages in #general within the last 5 hours.

        See also:
            /help activeusercount - Get the count of active users on the guild.
        """

        if search_context == "public":
            converter = WolfConverters.ChannelContextConverter()
            search_context = await converter.convert(ctx, "public")

        if timedelta == "24h":
            timedelta = datetime.timedelta(hours=24)

        message_count = 0

        now = datetime.datetime.utcnow()
        search_start = now - timedelta

        async with ctx.typing():
            for channel in search_context['channels']:
                if not channel.permissions_for(ctx.me).read_message_history:
                    LOG.info("I don't have permission to get information for channel %s", channel)
                    continue

                LOG.info("Getting history for %s", channel)
                hist = channel.history(limit=None, after=search_start)

                async for _ in hist:
                    message_count += 1

            await ctx.send(embed=discord.Embed(
                title="Message Count Report",
                description="Since `{} UTC`, the channel context `{}` has seen about **{} "
                            "messages**.".format(search_start.strftime(DATETIME_FORMAT), search_context['name'],
                                                 message_count),
                color=Colors.INFO
            ))

    @commands.command(name="activeusercount", brief="Get a count of active users on the guild", aliases=["auc"])
    @commands.has_permissions(view_audit_log=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def active_user_count(self, ctx: commands.Context,
                                search_context: WolfConverters.ChannelContextConverter = "all",
                                delta: WolfConverters.DateDiffConverter = "24h",
                                threshold: int = 20):
        """
        Get an active user count for the current guild.

        This command will look back through message history and attempt to find the number of active users in the guild.
        By default, it will look for all users with (on average) 20 or more messages per hour.

        This command operates on "context" logic, much like /msgcount. Context are the same as there - either a channel,
        the word "public", or the word "all".

        Bots do not count towards the "active user" count.

        CAVEAT: It is important to know that this is a *slow* command, because it needs to iterate over every message
        in the search context in order to successfully operate. Because of this, the "Typing" indicator will display.
        Also note that this command may not return accurate results due to the nature of the search system. It should be
        used for approximation only.

        Parameters:
            search_context - A string (or channel ID) that resolves to a channel ctx. See /help msgcount. Default "all"
            delta          -  A string in ##d##h##m##s format to capture. Default 24h.
            threshold      -  The minimum number of messages a user should send per hour (on average). Default 20.

        See also:
            /help usercount - Get a count of users on the guild
            /help msgcount  - Get a count of messages in the current context
        """
        if search_context == "all":
            converter = WolfConverters.ChannelContextConverter()
            search_context = await converter.convert(ctx, "all")

        if delta == "24h":
            delta = datetime.timedelta(hours=24)

        message_counts = {}
        active_user_count = 0

        now = datetime.datetime.utcnow()
        search_start = now - delta

        min_messages = max(threshold * (delta.seconds // 3600), threshold)

        async with ctx.typing():
            for channel in search_context['channels']:
                if not channel.permissions_for(ctx.me).read_message_history:
                    LOG.info("I don't have permission to get information for channel %s", channel)
                    continue

                LOG.info("Getting history for %s", channel)
                hist = channel.history(limit=None, after=search_start)

                async for m in hist:  # type: discord.Message
                    if m.author.bot:
                        continue

                    message_counts[m.author.id] = message_counts.get(m.author.id, 0) + 1

            for user in message_counts:
                if message_counts[user] >= min_messages:
                    active_user_count += 1

        await ctx.send(embed=discord.Embed(
            title="Active User Count Report",
            description="Since `{} UTC`, the channel context `{}` has seen about **{}"
                        " active users** (sending on average {} or more messages per hour)."
                        "".format(search_start.strftime(DATETIME_FORMAT), search_context['name'], active_user_count,
                                  threshold),
            color=Colors.INFO
        ))

    @commands.command(name="prunesim", brief="Get a number of users scheduled for pruning")
    @commands.has_permissions(manage_guild=True)
    async def check_prune(self, ctx: commands.Context, days: int = 7):
        """
        Simulate a prune on the server.

        This command will simulate a prune on the server and return a count of members expected to be lost. A member is
        considered for pruning if they have not spoken in the specified number of days *and* they have no roles.

        Parameters:
            days - The "prune cutoff" value for a user to be eligible for pruning. Defaults to 7.

        Example Command:
            /prunesim 5 - Get the count of users who have not talked in the last 5 days, and have no roles
        """

        if days < 1 or days > 180:
            raise commands.BadArgument("The `days` argument must be between 1 and 180.")

        prune_count = await ctx.guild.estimate_pruned_members(days=days)

        if days == 1:
            days = "1 day"
        else:
            days = "{} days".format(days)

        if prune_count == 1:
            prune_count = "1 user"
        else:
            prune_count = "{} users".format(prune_count)

        await ctx.send(embed=discord.Embed(
            title="Simulated Prune Report",
            description="With a simulated cutoff of {}, an estimated **{} users** will be pruned from the guild. "
                        "\n\nThis number represents the count of members who have not spoken in the last {}, and "
                        "do not have a role (including self-assigned roles).".format(days, prune_count, days),
            color=Colors.INFO
        ))

    @commands.command(name="usercount", brief="Get a count of users on the guild", aliases=["uc"])
    async def user_count(self, ctx: commands.Context):
        """
        Get a count of users on the guild.

        This command will return a count of all members on the guild. It's really that simple.

        See also:
            /help activeusercount - Get a count of active users on the guild.
        """
        await ctx.send(embed=discord.Embed(
            title="User Count Report",
            description="This guild currently has **{} total users**.".format(len(ctx.guild.members)),
            color=Colors.INFO
        ))

    @commands.command(name="invitespy", brief="Find information about Guild invite", aliases=["invspy"])
    @commands.has_permissions(view_audit_log=True)
    async def invitespy(self, ctx: commands.Context, fragment: WolfConverters.InviteLinkConverter):
        """
        Get information about a guild invite.

        This command allows moderators to pull information about any given (valid) invite. It will display all
        publicly-gleanable information about the invite such as user count, verification level, join channel names,
        the invite's creator, and other such information.

        This command calls the API directly, and will validate an invite's existence. If either the bot's account
        or the bot's IP are banned, the system will act as though the invite does not exist.

        Parameters:
            fragment - Either a Invite URL or fragment (aa1122) for the invite you wish to target.

        Example Commands:
            /invitespy aabbcc                       - Get invite data for invite aabbcc
            /invitespy https://discord.gg/someguild - Get invite data for invite someguild
        """
        try:
            invite_data = await self.bot.http.request(
                Route('GET', '/invite/{invite_id}?with_counts=true', invite_id=fragment))  # type: dict
            invite_guild = discord.Guild(state=self.bot, data=invite_data['guild'])

            if invite_data.get("inviter") is not None:
                invite_user = discord.User(state=self.bot, data=invite_data["inviter"])
            else:
                invite_user = None
        except discord.NotFound:
            await ctx.send(embed=discord.Embed(
                title="Could Not Retrieve Invite Data",
                description="This invite does not appear to exist, or the bot has been banned from the guild.",
                color=Colors.DANGER
            ))
            return

        embed = discord.Embed(
            description="Information about invite slug `{}`".format(fragment),
            color=Colors.INFO
        )

        embed.set_thumbnail(url=invite_guild.icon_url)

        embed.add_field(name="Guild Name", value="**{}**".format(invite_guild.name), inline=False)

        if invite_user is not None:
            embed.set_author(
                name="Invite for {} by {}".format(invite_guild.name, invite_user),
                icon_url=invite_user.avatar_url
            )
        else:
            embed.set_author(name="Invite for {}".format(invite_guild.name))

        embed.add_field(name="Invited Guild ID", value=invite_guild.id, inline=True)

        ch_type = {0: "#", 2: "[VC] ", 4: "[CAT] "}
        embed.add_field(name="Join Channel Name",
                        value=ch_type[invite_data['channel']['type']] + invite_data['channel']['name'],
                        inline=True)

        embed.add_field(name="Guild Creation Date",
                        value=invite_guild.created_at.strftime(DATETIME_FORMAT),
                        inline=True)

        if invite_data.get('approximate_member_count', -1) != -1:
            embed.add_field(name="User Count",
                            value="{} ({} online)".format(invite_data.get('approximate_member_count', -1),
                                                          invite_data.get('approximate_presence_count', -1)))

        vl_map = {
            0: "No Verification",
            1: "Verified Email Needed",
            2: "User for 5+ minutes",
            3: "Member for 10+ minutes",
            4: "Verified Phone Needed"
        }
        embed.add_field(name="Verification Level", value=vl_map[invite_guild.verification_level])

        if invite_user is not None:
            embed.add_field(name="Invite Creator", value=str(invite_user), inline=True)

        if len(invite_guild.features) > 0:
            embed.add_field(name="Guild Features",
                            value=', '.join(list('`{}`'.format(f) for f in invite_guild.features)))

        if invite_guild.splash is not None:
            embed.add_field(name="Splash Image",
                            value="[Open in Browser >]({})".format(invite_guild.splash_url),
                            inline=False)
            embed.set_image(url=invite_guild.splash_url)

        embed.set_footer(text="Report generated at {} UTC".format(WolfUtils.get_timestamp()))

        await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Intelligence(bot))
