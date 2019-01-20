from os import getenv
from re import match
from discord.ext import commands
from discord import Embed, Game, Color
from aiohttp import ClientSession
from dotenv import load_dotenv


load_dotenv()


bot = commands.Bot(command_prefix='$')
session = ClientSession(loop=bot.loop)

heroku_base = f"https://api.heroku.com/apps/{getenv('APP_NAME')}"
github_base = 'https://api.github.com/repos/kyb3r/modmail'

build_url = heroku_base + '/builds'
versions_url = github_base + '/tags'
latest_release_url = github_base + '/releases/latest'
latest_commit_url = github_base + '/commits'
restart_url = heroku_base + '/dynos'
config_url = heroku_base + '/config-vars'
tarball_url = github_base + '/tarball/{sha}'

# from https://github.com/semver/semver/issues/232
semantic_version_regex = r'^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-(0|[' \
                         r'1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(\.(0|[' \
                         r'1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?(\+[' \
                         r'0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*)?$'

headers = {
    'Accept': 'application/vnd.heroku+json; version=3',
    'Content-Type': 'application/json',
    'Authorization': f"Bearer {getenv('HEROKU_TOKEN')}"
}


@bot.event
async def on_ready():
    print('Bot Started.')
    await bot.change_presence(activity=Game('$help for commands!'))


@bot.event
async def on_command_error(ctx: commands.Context,
                           error: commands.CommandError):
    if isinstance(error, commands.BadArgument):
        return await ctx.send(embed=Embed(
            title="Failed",
            color=Color.red(),
            description=error.args[0]
        ))
    else:
        return await ctx.send(embed=Embed(
            title="An unexpected error had occurred.",
            color=Color.red(),
            description=f'{type(error)}: {error.args}'
        ))


async def get_versions():
    async with session.get(versions_url) as resp:
        data = await resp.json()
        return {version['name']: version['tarball_url'] for version in data}


async def get_latest_release():
    async with session.get(latest_release_url) as resp:
        return (await resp.json()).get('tag_name')


async def get_latest_commit():
    async with session.get(latest_commit_url) as resp:
        return (await resp.json())[0]['sha']


@bot.command(name='versions')
async def versions_(ctx: commands.Context):
    """
    View all available versions releases for the repo.
    """
    versions = await get_versions()
    em = Embed(title='Versions:', color=Color.blue())
    for num, (version, tarball) in enumerate(versions.items()):
        if num % 25 == 0 and num > 0:
            await ctx.send(embed=em)
            em = Embed(title='Versions:', color=Color.blue())
        em.add_field(name=version, value=tarball)
    return await ctx.send(embed=em)


async def send_success_or_fail(ctx, status):
    if str(status).startswith('2'):
        return await ctx.send(embed=Embed(
            title='Success', color=Color.green()
        ))
    else:
        return await ctx.send(embed=Embed(
            title='Failed', color=Color.red()
        ))


@bot.command()
@commands.has_permissions(administrator=True)
async def restart(ctx: commands.Context):
    """
    Restarts the bot.
    """
    async with session.delete(restart_url, headers=headers) as resp:
        return await send_success_or_fail(ctx, str(resp.status))


@bot.command()
@commands.has_permissions(administrator=True)
async def checkout(ctx: commands.Context, *, version: str):
    """
    Checkout a specific version or commit.

    See "$versions" for a list of versions. Trail the version or commit with
    "silently" to mute output.

     - "$checkout 122ef24" or "$checkout v1.2.1"
     - "$checkout latest release" for the latest release.
     - "$checkout latest" or "$checkout latest commit" for the latest commit.
     - "$checkout v2.3.5 silently" will mute output.
    """
    async def send_info(type_, val, url):
        await ctx.send(embed=Embed(title=f'Checking out {type_}:',
                                   description=f'[`{val}`]({url})',
                                   color=Color.gold()))

    version = version.strip()
    if version.endswith(' silently'):
        verbose = False
        version = version[:-9]
    else:
        verbose = True

    versions = await get_versions()

    if version == 'latest release':
        version = await get_latest_release()
        url = versions[version]
        await send_info('version', version, url)
        
    elif version in {'latest', 'latest commit'}:
        sha = await get_latest_commit()
        url = tarball_url.format(sha=sha)
        await send_info('commit', sha, url)

    else:
        m = match(semantic_version_regex, version)
        if m is None:
            m = match(r'^[a-z\d]{7,}$', version)
            if m is None:
                raise commands.BadArgument('Invalid Version/Commit SHA.')
            sha = m.group(0)
            url = tarball_url.format(sha=sha)
            await send_info('commit', sha, url)

        else:
            version = m.group(0)
            if not version.startswith('v'):
                version = 'v' + version
            if version not in versions:
                raise commands.BadArgument(f'Cannot find version: {version}.')
            url = versions[version]
            await send_info('version', version, url)        

    payload = {
        'source_blob': {
            'url': url
        }
    }

    async with session.post(build_url, headers=headers,
                            json=payload) as resp:

        output_url = (await resp.json()).get('output_stream_url')

        if verbose:
            em = Embed(title="Output Stream",
                       color=Color.blue(),
                       description='starting...')
            msg = await ctx.send(embed=em)
            current = ''

            async with session.get(output_url) as resp2:
                async for data, _ in resp2.content.iter_chunks():
                    data = data.decode()
                    if len(data) + len(current) >= 2042:
                        current = data
                        if not current.strip(' \n\r'):
                            current = '...'

                        em = Embed(title='Output Stream',
                                   color=Color.blue(),
                                   description=f'```{current[:2046]}```')
                        msg = await ctx.send(embed=em)
                    else:
                        if current == '...':
                            current = data
                        else:
                            current += data
                        if not current.strip(' \n\r'):
                            current = '...'
                        em = Embed(title='Output Stream',
                                   color=Color.blue(),
                                   description=f'```{current}```')
                        await msg.edit(embed=em)

            if msg.embeds[0].description == 'starting...':
                em = Embed(title='Output Stream',
                           color=Color.blue(),
                           description=f'[Failed to stream output]({output_url}).')
                await msg.edit(embed=em)
        else:
            em = Embed(title='View Outputs:',
                       color=Color.blue(),
                       description=output_url)
            await ctx.send(embed=em)


async def send_env(payload):
    async with session.patch(config_url,
                             headers=headers,
                             json=payload) as resp:
        return str(resp.status)


@bot.command()
@commands.has_permissions(administrator=True)
async def setenv(ctx: commands.Context, key: str, *, value: str):
    """
    Sets an environment variable.
    """
    payload = {
        key: value
    }
    if key == 'TOKEN':
        raise commands.BadArgument('Cannot mess with TOKEN.')

    return await send_success_or_fail(ctx, await send_env(payload))


@bot.command()
@commands.has_permissions(administrator=True)
async def rmenv(ctx: commands.Context, key: str):
    """
    Removes an environment variable.
    """
    payload = {
        key: None
    }
    if key == 'TOKEN':
        raise commands.BadArgument('Cannot mess with TOKEN.')

    return await send_success_or_fail(ctx, await send_env(payload))


@bot.command(name='getenv')
@commands.has_permissions(administrator=True)
async def getenv_(ctx: commands.Context):
    """
    View all environment variables.
    """
    async with session.get(config_url, headers=headers) as resp:
        envs = await resp.json()
        em = Embed(title='Environment Variables:', color=Color.blue())
        for num, (key, val) in enumerate(envs.items()):
            if num % 25 == 0 and num > 0:
                await ctx.send(embed=em)
                em = Embed(title='Environment Variables:', color=Color.blue())
            em.add_field(name=key + ':', value=f'`{val}`')
        return await ctx.send(embed=em)

bot.run(getenv('BOT_TOKEN'))
