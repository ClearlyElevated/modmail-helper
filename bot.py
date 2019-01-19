from os import getenv
from re import match
from discord.ext import commands
from aiohttp import ClientSession


class Helper(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = ClientSession(loop=self.loop)
        self.url = f"https://api.heroku.com/apps/{getenv('APP_NAME')}/builds"
        self.headers = {
            'Accept': 'application/vnd.heroku+json; version=3',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer  0adcedc7-f568-42d3-907c-09560ba3e45f'
        }

    @staticmethod
    def get_payload(version):
        m = match(r'(v?[\d.-]+)', str(version))
        if m is None:
            raise commands.BadArgument('Invalid Version')
        version = m.group(0)
        if not version.startswith('v'):
            version = 'v' + version

        return {
            'source_blob': {
                'url': 'https://github.com/kyb3r/modmail/'
                       f'archive/{version}.tar.gz'
            }
        }

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def checkout(self, ctx, version):

        async with self.session.post(url=self.url, headers=self.headers,
                                     json=self.get_payload(version)) as r:
            msg = await r.json()
            await ctx.send(msg)
            print(msg)


bot = Helper(command_prefix='%')
bot.run(getenv('BOT_TOKEN'))
