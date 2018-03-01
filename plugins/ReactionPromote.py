import discord

from discord.ext import commands

from BotCore import BOT_CONFIG
from WolfBot.WolfEmbed import Colors
import logging

LOG = logging.getLogger("DiyBot.Plugin." + __name__)


class ReactionPromote:
    def __init__(self, bot):
        self.bot = bot
        self.roleRemovalBlacklist = []

    async def on_ready(self):
        LOG.info("Enabled plugin!")

    async def on_raw_reaction_add(self, emoji, message_id, channel_id, user_id):
        promotion_config = BOT_CONFIG.get('promotions', {})

        channel = self.bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            return

        message = await channel.get_message(message_id)
        guild = message.guild
        user = guild.get_member(user_id)
        
        emoji_slug = emoji.name
        if emoji.is_custom_emoji():
            emoji_slug = str(emoji)

        try:
            group_to_add = discord.utils.get(guild.roles,
                                             id=promotion_config[str(channel_id)][str(message_id)][emoji_slug])
            await user.add_roles(group_to_add)
            LOG.info("Added user " + user.display_name + " to role " + str(group_to_add))
        except KeyError:
            if promotion_config.get(str(channel_id)) is None:
                LOG.warn("Not configured for this channel. Ignoring.")
                return

            if promotion_config.get(str(channel_id)).get(str(message_id)) is None \
                    and not promotion_config.get(str(channel_id)).get('strictReacts'):
                LOG.warn("Not configured for this message. Ignoring.")
                return

            LOG.warn("Got bad emoji " + emoji_slug + " (" + str(hex(ord(emoji_slug))) + ")")
            self.roleRemovalBlacklist.append(str(user_id) + str(message_id))
            await message.remove_reaction(emoji, user)

    async def on_raw_reaction_remove(self, emoji, message_id, channel_id, user_id):
        promotion_config = BOT_CONFIG.get('promotions', {})

        if (str(user_id) + str(message_id)) in self.roleRemovalBlacklist:
            LOG.warn("Removal throttled.")
            self.roleRemovalBlacklist.remove(str(user_id) + str(message_id))
            return

        channel = self.bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            return

        message = await channel.get_message(message_id)
        guild = message.guild
        user = guild.get_member(user_id)
        
        emoji_slug = emoji.name
        if emoji.is_custom_emoji():
            emoji_slug = str(emoji)

        try:
            group_to_remove = discord.utils.get(guild.roles,
                                                id=promotion_config[str(channel_id)][str(message_id)][emoji_slug])
            await user.remove_roles(group_to_remove)
            LOG.info("Removed user " + user.display_name + " from role " + str(group_to_remove))
        except KeyError:
            if promotion_config.get(str(channel_id)) is None:
                LOG.warn("Not configured for this channel. Ignoring.")
                return

            if promotion_config.get(str(channel_id)).get(str(message_id)) is None:
                LOG.warn("Not configured for this message. Ignoring.")
                return

            LOG.warn("Got bad emoji " + emoji_slug + " (" + str(hex(ord(emoji_slug))) + ")")


    @commands.group(pass_context=True, brief="Control the promotions plugin", hidden=True)
    @commands.has_permissions(administrator=True)
    async def rpromote(self, ctx: discord.ext.commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send(embed=discord.Embed(
                title="Reaction Promotes",
                description="The command you have requested is not available.",
                color = Colors.DANGER
            ))
            return
            
    @rpromote.command(name="addPromotion", brief="Add a new promotion to the configs")
    async def addPromotion(self, ctx: discord.ext.commands.Context, channel: discord.TextChannel, messageId: int, emoji: str, role: discord.Role):
        promotion_config = BOT_CONFIG.get('promotions', {})
        
        print(promotion_config)
        message_config = promotion_config.setdefault(str(channel.id), {}).setdefault(str(messageId), {})
         
        print(promotion_config)
        message_config[emoji] = role.id
        BOT_CONFIG.set('promotions', promotion_config)
        print(promotion_config)
        
        await ctx.send(embed=discord.Embed(
            title="Reaction Promotes",
            description="The promotion " + emoji + " => `" + role.name + "` has been registered for promotions!",
            color = Colors.SUCCESS
        ))

def setup(bot):
    bot.add_cog(ReactionPromote(bot))
