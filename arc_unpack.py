#!/usr/bin/env python3
from pathlib import Path
import sys, shutil, json, subprocess, re
from time import time
from hashlib import sha1

DIFFICULTY_NAMES = ['Past', 'Present', 'Future', 'Beyond']
DIFFICULTY_COLORS = ['#3A6B78FF', '#566947FF', '#482B54FF', '#7C1C30FF']


class Message:
    ALL_OFF = '\033[0m'
    BOLD = '\033[1m'
    BLUE = f'{BOLD}\033[34m'
    GREEN = f'{BOLD}\033[32m'
    RED = f'{BOLD}\033[31m'
    YELLOW = f'{BOLD}\033[33m'

    def plain(self, message):
        print(f'{self.BOLD}   {message}{self.ALL_OFF}')

    def msg(self, message):
        print(f'{self.GREEN}==>{self.ALL_OFF}{self.BOLD} {message}{self.ALL_OFF}')

    def msg2(self, message):
        print(f'{self.BLUE}  ->{self.ALL_OFF}{self.BOLD} {message}{self.ALL_OFF}')

    def ask(self, message):
        print(f'{self.BLUE}::{self.ALL_OFF}{self.BOLD} {message}{self.ALL_OFF}')

    def warning(self, message):
        print(f'{self.YELLOW}==> WARNING:{self.ALL_OFF}{self.BOLD} {message}{self.ALL_OFF}', file=sys.stderr)

    def error(self, message):
        print(f'{self.RED}==> ERROR:{self.ALL_OFF}{self.BOLD} {message}{self.ALL_OFF}', file=sys.stderr)


msg = Message()

litedb_path = Path('./ArcUnpack.LiteDB/bin/Release/net7.0/linux-x64/publish/ArcUnpack.LiteDB')


class LiteDB:
    def __init__(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f'LiteDB not found at {path}')
        self.path = path

    def pack_count(self) -> int:
        proc = subprocess.Popen(
            [
                litedb_path,
                self.path,
                'PackCount'
            ],
            stdout=subprocess.PIPE,
        )
        proc.wait()
        return int(proc.stdout.read().strip().decode('utf-8'))

    def level_count(self) -> int:
        proc = subprocess.Popen(
            [
                litedb_path,
                self.path,
                'LevelCount'
            ],
            stdout=subprocess.PIPE,
        )
        proc.wait()
        return int(proc.stdout.read().strip().decode('utf-8'))

    def subcommand(self, subcommand: str, content: str):
        # For AddPack, AddLevel, AddFile
        proc = subprocess.Popen(
            [
                litedb_path,
                self.path,
                subcommand,
                content
            ],
            stdout=subprocess.PIPE,
        )
        proc.wait()


input_romfs_path = Path(sys.argv[1])  # romfs
extracted_romfs_path = Path('./extracted_romfs')
arc_create_db_input_path = Path(sys.argv[2])  # arccreate.litedb
final_path = Path('./final')

msg.ask('Preparing ...')

# Check for required files
if not litedb_path.exists():
    msg.error('ArcUnpack.LiteDB not found!')
    sys.exit(1)

if not input_romfs_path.exists():
    if extracted_romfs_path.exists():
        msg.warning('Extracted romfs found, skipping extraction...')
    else:
        msg.error('Input romfs not found!')
        sys.exit(1)

# Make folders
extracted_romfs_path.mkdir(parents=True, exist_ok=True)
final_path.mkdir(parents=True, exist_ok=True)

# Copy database file
arc_create_db_path = final_path / 'arccreate.litedb'
if not arc_create_db_path.exists():
    shutil.copy(arc_create_db_input_path, arc_create_db_path)

# LiteDB instance
litedb = LiteDB(arc_create_db_path)

# File list to extract
pack_list: list[Path] = []
for pack in input_romfs_path.glob('*.pack'):
    pack_list.append(pack)
pack_list.sort()

msg.ask('Extracting romfs...')

# Extract romfs
for pack_path in pack_list:
    with open(pack_path, 'rb') as pack:
        msg.msg(f'Extracting pack {pack_path.name}...')
        index_file = pack_path.with_suffix('.json')
        with open(index_file) as index_f:
            index: dict = json.load(index_f)
            for group in index['Groups']:
                msg.msg2(f'Extracting group {group["Name"]}...')
                group_path = extracted_romfs_path / group['Name']
                group_path.mkdir(parents=True, exist_ok=True)

                for ordered_entry in group['OrderedEntries']:
                    file_path = group_path / ordered_entry['OriginalFilename']
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    pack.seek(ordered_entry['Offset'])
                    with open(file_path, 'wb') as out_f:
                        out_f.write(pack.read(ordered_entry['Length']))
                        out_f.close()
        index_f.close()
    pack.close()

converted_songs: list[dict] = []
converted_packs: list[dict] = []
converted_files: list[dict] = []
level_identifiers: dict[str, list[str]] = {}

msg.ask('Converting songs...')

# Convert songs
level_count = litedb.level_count()
song_list_path = extracted_romfs_path / 'not_audio_or_images' / 'songs' / 'songlist'
song_list: dict = json.load(open(song_list_path, 'r'))
charts_root_path = extracted_romfs_path / 'charts' / 'songs'
audio_root_path = extracted_romfs_path / 'Fallback' / 'songs'
jacket_root_path = extracted_romfs_path / 'jackets_large' / 'songs'
background_root_path = extracted_romfs_path / 'not_audio' / 'img' / 'bg'

i: int = level_count + 1
for song in song_list['songs']:
    msg.msg2(f'Converting song {song["id"]}...')
    original_id: str = f"dl_{song['id']}" if 'remote_dl' in song and song['remote_dl'] else song['id']
    new_id: str = f"{song['set']}.{song['id']}"
    song_root_path = final_path / 'Level' / new_id
    song_root_path.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(  # Copy audio
        audio_root_path / original_id / 'base.ogg',
        song_root_path / 'base.ogg'
    )
    shutil.copyfile(  # Copy jacket
        jacket_root_path / original_id / 'base.jpg',
        song_root_path / 'base.jpg'
    )
    converted_song: dict = {
        '_id': i,
        'Type': 'Level',
        'Identifier': new_id,
        'IsDefaultAsset': True,
        'AddedDate': f"d{song['date']}",
        'Version': 0
    }
    charts: list[dict] = []
    background_paths: list[Path] = []
    for diff in song['difficulties']:
        chart_path = charts_root_path / original_id / f"{diff['ratingClass']}.aff"
        shutil.copyfile(  # Copy chart
            chart_path,
            song_root_path / chart_path.name
        )
        chart: dict = {
            'ChartPath': chart_path.name,
            'AudioPath': 'base.ogg',
            'JacketPath': 'base.jpg',
            'BaseBpm': float(song['bpm_base']),
            'Title': song['title_localized']['en'],
            'Composer': song['artist'],
            'Charter': diff['chartDesigner'],
            'Illustrator': diff['jacketDesigner'],
            'Difficulty': f"{DIFFICULTY_NAMES[diff['ratingClass']]} {diff['rating']}",
            'ChartConstant': float(diff['rating']),
            'DifficultyColor': DIFFICULTY_COLORS[diff['ratingClass']],
        }
        if song['side'] in [0, 1]:
            chart['Skin'] = {
                'Side': 'light' if song['side'] == 0 else 'conflict',
            }
        if song['bpm'] == str(song['bpm_base']):
            chart['SyncBaseBpm'] = True
        else:
            chart['SyncBaseBpm'] = False
            chart['BpmText'] = song['bpm'].replace(' ', '').replace('-', ' - ')
        if song['bg'] != '':
            # Song-specific background
            background_path = background_root_path / f"{song['bg']}.jpg"
        else:
            # Use default background
            base_background_type = 'byd' if diff['ratingClass'] == 3 else 'base'
            base_background_name = 'light' if song['side'] == 0 else 'conflict'
            background_path = background_root_path / f"{base_background_type}_{base_background_name}.jpg"
        if not (song_root_path / background_path.name).exists():
            shutil.copyfile(  # Copy background
                background_path,
                song_root_path / background_path.name
            )
            background_paths.append(background_path)
        chart['BackgroundPath'] = background_path.name
        charts.append(chart)
    converted_song['Settings'] = {
        'Charts': charts,
        'LastOpenedChartPath': charts[-1]['ChartPath'],
    }
    converted_song['FileReferences'] = [
        'base.ogg',
        'base.jpg',
        *map(lambda x: x.name, background_paths),
        *map(lambda x: x['ChartPath'], charts),
    ]
    converted_songs.append(converted_song)
    if song['set'] not in level_identifiers:
        level_identifiers[song['set']] = []
    level_identifiers[song['set']].append(new_id)
    i += 1

msg.ask('Converting packs...')

# Convert packs
pack_count = litedb.pack_count()
pack_list_path = extracted_romfs_path / 'not_audio_or_images' / 'songs' / 'packlist'
pack_list: dict = json.load(open(pack_list_path, 'r'))
pack_cover_root_path = extracted_romfs_path / 'packs' / 'songs' / 'pack'
singles_cover_path = extracted_romfs_path / 'not_large_png' / 'layouts' / 'songselect' / 'folder_singles.png'
i: int = pack_count + 1

for pack in pack_list['packs']:
    msg.msg2(f'Converting pack {pack["id"]}...')
    new_id: str = pack['pack_parent'] if 'pack_parent' in pack else pack['id']
    pack_root_path = final_path / 'Pack' / new_id
    pack_root_path.mkdir(parents=True, exist_ok=True)
    pack_cover_path = pack_cover_root_path / f"select_{new_id}.png"
    if new_id == 'single':  # Copy cover (Memory Archive)
        pack_cover_path = singles_cover_path
    else:
        shutil.copyfile(  # Copy cover (Pack)
            pack_cover_path,
            pack_root_path / pack_cover_path.name
        )
    converted_pack: dict = {
        '_id': i,
        'Type': 'Pack',
        'PackName': pack['name_localized']['en'],
        'ImagePath': pack_cover_path.name,
        'LevelIdentifiers': level_identifiers[pack['id']],
        'Identifier': new_id,
        'Version': 0,
        'FileReferences': [pack_cover_path.name],
        'AddedDate': f"d{int(time())}",
        "IsDefaultAsset": True,
    }
    converted_packs.append(converted_pack)
    i += 1

msg.ask('Moving files...')

# Move files
storage_root_path = final_path / 'storage'
storage_root_path.mkdir(parents=True, exist_ok=True)

for type_name in ['Level', 'Pack']:
    for file in (final_path / type_name).glob('**/*'):
        if file.is_file():
            file_real_path: str = file.relative_to(final_path).as_posix()
            file_hash_path = storage_root_path / f"{sha1(open(file, 'rb').read()).hexdigest()}{file.suffix}"
            if not file_hash_path.exists():
                file.rename(file_hash_path)
            converted_files.append({
                '_id': file_real_path,
                'RealPath': file_hash_path.name,
                'CorrectHashPath': file_hash_path.name,
            })
    shutil.rmtree(final_path / type_name)

msg.ask("Updating database...")

# Update database
msg.msg('Inserting songs...')
for song in converted_songs:
    litedb.subcommand(
        'AddLevel',
        re.sub(r'"(d\d+)"', r'\1', json.dumps(song))
    )
msg.msg('Inserting packs...')
for pack in converted_packs:
    litedb.subcommand(
        'AddPack',
        re.sub(r'"(d\d+)"', r'\1', json.dumps(pack))
    )
msg.msg('Inserting files...')
for file in converted_files:
    litedb.subcommand(
        'AddFile',
        json.dumps(file)
    )

msg.ask('Done!')
