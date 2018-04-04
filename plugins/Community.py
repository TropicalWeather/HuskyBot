import logging

import discord
from discord.ext import commands

from WolfBot import WolfConfig
from WolfBot.WolfStatics import *

LOG = logging.getLogger("DiyBot.Plugin." + __name__)


class Community:
    """
    The Community plugin gives users the ability to get information about the community itself.

    This plugin is meant to inform users about staff, policies, rules, changes, etc. Basically, it answers questions to
    keep mods from actually talking to users.
    """
    def __init__(self, bot: discord.ext.commands.Bot):
        self.bot = bot
        self._config = WolfConfig.getConfig()
        LOG.info("Loaded plugin!")

    @commands.command(name="staff", aliases=["stafflist"], brief="Get an up-to-date list of all staff on the guild")
    async def stafflist(self, ctx: commands.Context):
        """
        Get an up-to-date list of staff members on the guild.

        This command will dynamically retrieve a list of staff members currently in roles on the guild. It may be
        re-run at any time to get a new list of staff members.
        """

        mod_role = discord.utils.get(ctx.guild.roles, id=self._config.get("specialRoles", {})
                                     .get(SpecialRoleKeys.MODS.value))
        admin_role = discord.utils.get(ctx.guild.roles, id=self._config.get("specialRoles", {})
                                       .get(SpecialRoleKeys.ADMINS.value))

        embed = discord.Embed(
            title=Emojis.SHIELD + " Staff List",
            description="The following users are currently staff members on {}.".format(ctx.guild.name),
            color=Colors.INFO
        )

        embed.add_field(name="Owner", value=ctx.guild.owner.mention, inline=False)

        admins = []
        if admin_role is not None:
            for staff in admin_role.members:
                if (staff == ctx.guild.owner) or staff.bot:
                    continue

                admins.append(staff.mention)

            if len(admins) > 0:
                embed.add_field(name=admin_role.name, value=", ".join(admins[::-1]), inline=False)

        mods = []
        if mod_role is not None:
            for staff in mod_role.members:
                # no dupes
                if (staff.mention in admins) or (staff == ctx.guild.owner) or staff.bot:
                    continue

                mods.append(staff.mention)

            if len(mods) > 0:
                embed.add_field(name=mod_role.name, value=", ".join(mods[::-1]), inline=False)

        await ctx.send(embed=embed)

    @commands.group(name="rules", brief="Get a copy of the guild rules")
    async def rules(self, ctx: commands.Context):
        """
        Retrieve the current rules list for the Discord guild.

        By default, this command willy simply return the existing rules in an easy-to-parse embed. If a user is an
        administrator, additional commands exist that allow setting/altering rules.
        """
        if ctx.invoked_subcommand is not None:
            return

        rules_list = self._config.get("guildRules", [])

        if len(rules_list) == 0:
            await ctx.send(embed=discord.Embed(
                title="Guild Rules",
                description="No guild rules have been defined! Administrators can use `/rules add` to create new "
                            "rules",
                color=Colors.DANGER
            ))
            return

        rule_embed = discord.Embed(
            title=Emojis.BOOKMARK2 + " Guild Rules for {}".format(ctx.guild.name),
            description="The following rules have been defined by the staff members. Please make sure you understand "
                        "them before participating.",
            color=Colors.INFO
        )

        for i in range(len(rules_list)):
            rule = rules_list[i]

            rule_embed.add_field(name="{}. {}".format(i + 1, rule['title']), value=rule['description'], inline=False)

        await ctx.send(embed=rule_embed)

    @rules.command(name="add", brief="Add a new rule to the system")
    @commands.has_permissions(administrator=True)
    async def add_rule(self, ctx: commands.Context, title: str, *, description: str):
        """
        Add a new rule to the Discord guild.

        This command takes two arguments - a Title, and a Description. If the title has spaces in it, it must be
        "surrounded with quotes". The Description does not require quotes in any cases.

        When a new rule is added, it will be appended to the end of the list.
        """

        rules_list = self._config.get("guildRules", [])

        rules_list.append({"title": title, "description": description})

        self._config.set("guildRules", rules_list)

        await ctx.send(embed=discord.Embed(
            title="Guild Rule Added!",
            description="Your rule (titled **{}**) has been successfully added to the rules list.".format(title),
            color=Colors.SUCCESS
        ))

    @rules.command(name="remove", brief="Remove a rule from the system")
    @commands.has_permissions(administrator=True)
    async def remove_rule(self, ctx: commands.Context, index: int):
        """
        Remove an existing rule from the Discord guild.

        This command takes a single argument - an index. This may be retrieved by looking at /rules and choosing the
        rule number you would like to delete.

        All existing rules are shifted up one position.
        """

        rules_list = self._config.get("guildRules", [])

        try:
            rules_list.remove(index - 1)
        except KeyError:
            await ctx.send(embed=discord.Embed(
                title="Guild Rule Removal Failed",
                description="Guild Rule number {} does not exist.".format(index),
                color=Colors.SUCCESS
            ))
            return

        self._config.set("guildRules", rules_list)

        await ctx.send(embed=discord.Embed(
            title="Guild Rule Removed!",
            description="Guild Rule number {} was removed from the rules list.".format(index),
            color=Colors.SUCCESS
        ))

    @rules.command(name="edit", brief="Change the description of a rule")
    @commands.has_permissions(administrator=True)
    async def edit_rule(self, ctx: commands.Context, index: int, *, new_description: str):
        """
        Edit the description of an existing guild rule.

        This command takes two arguments - an index and a new description. No quotations are required. If the title
        requires updating, see /help rules rename.

        The index may be determined by looking at /rules and selecting the rule to update.
        """

        rules_list = self._config.get("guildRules", [])

        try:
            rule = rules_list[index - 1]
        except KeyError:
            await ctx.send(embed=discord.Embed(
                title="Guild Rule Edit Failed",
                description="Guild Rule number {} does not exist.".format(index),
                color=Colors.SUCCESS
            ))
            return

        rule['description'] = new_description

        self._config.set("guildRules", rules_list)

        await ctx.send(embed=discord.Embed(
            title="Guild Rule Description Updated!",
            description="Your rule (index {}) has had its description updated.".format(index),
            color=Colors.SUCCESS
        ))

    @rules.command(name="rename", brief="Rename a rule")
    @commands.has_permissions(administrator=True)
    async def rename_rule(self, ctx: commands.Context, index: int, *, new_title: str):
        """
        Edit the title of an existing guild rule.

        This command takes two arguments - an index and a new title. No quotations are required. If the description
        needs to be updated instead, see /help rules edit

        The index may be determined by looking at /rules and selecting the rule to update.
        """

        rules_list = self._config.get("guildRules", [])

        try:
            rule = rules_list[index - 1]
        except KeyError:
            await ctx.send(embed=discord.Embed(
                title="Guild Rule Rename Failed",
                description="Guild Rule number {} does not exist.".format(index),
                color=Colors.SUCCESS
            ))
            return

        rule['title'] = new_title

        self._config.set("guildRules", rules_list)

        await ctx.send(embed=discord.Embed(
            title="Guild Rule Title Updated!",
            description="Your rule (index {}) has had its title updated.".format(index),
            color=Colors.SUCCESS
        ))

    @rules.command(name="move", brief="Move a rule")
    @commands.has_permissions(administrator=True)
    async def move_rule(self, ctx: commands.Context, old_index: int, new_index: int):
        """
        Move a rule to another position in the list.

        This command takes two arguments - the old and new index. To determine the old index, use /rules and select the
        number you wish to move.

        The new index will be the new place for the rule. The indexes will not swap - only the existing rule will be
        moved.
        """
        rules_list = self._config.get("guildRules", [])

        try:
            rules_list.insert(new_index - 1, rules_list.pop(old_index - 1))
        except KeyError:
            await ctx.send(embed=discord.Embed(
                title="Guild Rule Move Failed",
                description="Could not move the rule!",
                color=Colors.SUCCESS
            ))
            return

        self._config.set("guildRules", rules_list)

        await ctx.send(embed=discord.Embed(
            title="Guild Rule Location Updated!",
            description="Your rule has been successfully moved.",
            color=Colors.SUCCESS
        ))

    @commands.group(name="invite", brief="Get this guild's invite link")
    async def get_invite(self, ctx: commands.Context):
        """
        See the current guild invite link.

        If the guild has a vanity invite, it will be returned. Otherwise, an administrator configured invite will be
        returned instead.
        """
        if ctx.invoked_subcommand is not None:
            return

        embed = discord.Embed(
            title="{} Invite Link".format(ctx.guild.name),
            description="Want to invite your friends? Awesome! Share this handy invite link with them to get them into "
                        "the fun.",
            color=Colors.INFO
        )

        embed.set_thumbnail(url=ctx.guild.icon_url)

        try:
            invite = await ctx.guild.vanity_invite()
            invite_url = invite.url

            invite_url = invite_url.replace("http", "https")
        except discord.HTTPException:
            invite_fragment = self._config.get("inviteKey")

            if invite_fragment is None:
                await ctx.send(embed=discord.Embed(
                    title="No Invite Link defined!",
                    description="This guild doesn't appear to have a configured vanity URL or preferred invite key. "
                                "Please ask an administrator for assistance.",
                    color=Colors.DANGER
                ))
                return

            invite_url = "https://discord.gg/{}".format(invite_fragment)

        embed.add_field(name="Invite Link", value="[`{}`]({})".format(invite_url, invite_url), inline=False)

        await ctx.send(embed=embed)

    @get_invite.command(name="set", brief="Set a preferred invite URL")
    @commands.has_permissions(administrator=True)
    async def set_invite(self, ctx: commands.Context, fragment: str):
        """
        Set the invite code used by the guild.

        This command only takes a single argument - a fragment for an invite. It saves immediately.
        """
        self._config.set("inviteKey", fragment)

        await ctx.send(embed=discord.Embed(
            title="Invite Link Set!",
            description="The guild invite link was set to https://discord.gg/{}.".format(fragment),
            color=Colors.SUCCESS
        ))


def setup(bot: discord.ext.commands.Bot):
    bot.add_cog(Community(bot))