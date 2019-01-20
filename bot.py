from os import getenv
from re import match
from discord.ext import commands
from discord import Embed, Game
from aiohttp import ClientSession
from dotenv import load_dotenv

load_dotenv(verbose=True)


bot = commands.Bot(command_prefix='$')
session = ClientSession(loop=bot.loop)

heroku_base = f"https://api.heroku.com/apps/{getenv('APP_NAME')}"
github_base = 'https://api.github.com/repos/kyb3r/modmail'

build_url = heroku_base + '/builds'
versions_url = github_base + '/tags'
latest_url = github_base + '/releases/latest'
restart_url = heroku_base + '/dynos'
config_url = heroku_base + '/config-vars'

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
    async with session.get(versions_url) as resp:
        data = await resp.json()
        return {version['name']: version['tarball_url'] for version in data}


async def get_latest():
    async with session.get(url=latest_url) as resp:
        return (await resp.json()).get('tag_name')


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
async def restart(ctx: commands.Context):
    async with session.delete(restart_url, headers=headers) as resp:
        status = 'Success' if str(resp.status).startswith('2') else 'Failed'
        return await ctx.send(embed=Embed(title=status))


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

    payload = {
        'source_blob': {
            'url': versions[version]
        }
    }
    async with session.post(build_url, headers=headers,
                            json=payload) as resp:

        em = Embed(title="Output Stream", description='starting...')
        msg = await ctx.send(embed=em)
        current = ''

        output_url = (await resp.json()).get('output_stream_url')
        async with session.get(output_url) as resp2:
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


async def send_env(payload):
    async with session.patch(config_url,
                             headers=headers,
                             json=payload) as resp:
        return 'Success' if str(resp.status).startswith('2') else 'Failed'


@bot.command()
@commands.has_permissions(administrator=True)
async def setenv(ctx: commands.Context, key: str, *, value: str):
    payload = {
        key: value
    }
    if key == 'TOKEN':
        return await ctx.send(embed=Embed(title='Cannot mess with TOKEN.'))

    return await ctx.send(embed=Embed(title=await send_env(payload)))


@bot.command()
@commands.has_permissions(administrator=True)
async def rmenv(ctx: commands.Context, key: str):
    payload = {
        key: None
    }
    if key == 'TOKEN':
        return await ctx.send(embed=Embed(title='Cannot mess with TOKEN.'))

    return await ctx.send(embed=Embed(title=await send_env(payload)))


@bot.command(name='getenv')
@commands.has_permissions(administrator=True)
async def getenv_(ctx: commands.Context):
    async with session.get(config_url, headers=headers) as resp:
        envs = await resp.json()
        em = Embed(title='Environment Variables:')
        for num, (key, val) in enumerate(envs.items()):
            if num % 25 == 0 and num > 0:
                await ctx.send(embed=em)
                em = Embed(title='Environment Variables:')
            em.add_field(name=key + ':', value=f'`{val}`')
        return await ctx.send(embed=em)

bot.run(getenv('BOT_TOKEN'))
