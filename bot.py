from os import getenv
from re import match
from discord.ext import commands
from discord import Embed, Game
from aiohttp import ClientSession
from dotenv import load_dotenv

load_dotenv(verbose=True)


bot = commands.Bot(command_prefix='$')


session = ClientSession(loop=bot.loop)
build_url = f"https://api.heroku.com/apps/{getenv('APP_NAME')}/builds"
versions_url = f'https://api.github.com/repos/kyb3r/modmail/tags'
latest_url = f'https://api.github.com/repos/kyb3r/modmail/releases/latest'

headers = {
    'Accept': 'application/vnd.heroku+json; version=3',
    'Content-Type': 'application/json',
    'Authorization': f"Bearer {getenv('HEROKU_TOKEN')}"
}


@bot.event
async def on_ready():
    print('Bot Started.')
    await bot.change_presence(activity=Game('$help for commands!'))


async def get_versions():
    async with session.get(url=versions_url) as resp:
        data = await resp.json()
        return {version['name']: version['tarball_url'] for version in data}


async def get_latest():
    async with session.get(url=latest_url) as resp:
        return (await resp.json()).get('tag_name')


def get_payload(url):
    return {'source_blob': {'url': url}}


@bot.command(name='versions')
async def versions_(ctx: commands.Context):
    """
    View all available versions releases for the repo.
    """
    versions = await get_versions()
    em = Embed(title='Versions:')
    for num, (version, tarball) in enumerate(versions.items()):
        if num % 25 == 0 and num > 0:
            await ctx.send(embed=em)
            em = Embed(title='Versions:')
        em.add_field(name=version, value=tarball)
    return await ctx.send(embed=em)


@bot.command()
@commands.has_permissions(administrator=True)
async def checkout(ctx: commands.Context, *, version: str):
    """
    Checkout a specific version.

    See "$versions" for a list of versions or
    "$checkout latest" for the latest version.
    """
    if version == 'latest':
        version = await get_latest()

    versions = await get_versions()
    m = match(r'(v?[\d.\w\-]+)', str(version))
    if m is None:
        raise commands.BadArgument('Invalid Version')
    version = m.group(0)
    if not version.startswith('v'):
        version = 'v' + version

    if version not in versions:
        return await ctx.send(embed=Embed(
            title="Invalid Version",
            description=f'Cannot find {version}'
        ))

    async with session.post(url=build_url, headers=headers,
                            json=get_payload(versions[version])) as resp:

        em = Embed(title="Output Stream", description='starting...')
        msg = await ctx.send(embed=em)
        current = ''

        output_url = (await resp.json()).get('output_stream_url')
        async with session.get(url=output_url) as resp2:
            async for data, _ in resp2.content.iter_chunks():
                data = data.decode()
                if len(data) + len(current) >= 2048:
                    current = data
                    if not current.strip(' \n\r'):
                        current = '...'

                    em = Embed(title='Output Stream',
                               description=current[:2048])
                    msg = await ctx.send(embed=em)
                else:
                    if current == '...':
                        current = data
                    else:
                        current += data
                    if not current.strip(' \n\r'):
                        current = '...'
                    em = Embed(title='Output Stream', description=current)
                    await msg.edit(embed=em)
        if msg.embeds[0].description == 'starting...':
            em = Embed(title='Output Stream',
                       description=f'Failed to stream output. {output_url}')
            await msg.edit(em)


bot.run(getenv('BOT_TOKEN'))
