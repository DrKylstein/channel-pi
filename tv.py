#!/usr/bin/python3

import subprocess
import os
import os.path
import random
import argparse
import time
import shlex
import csv

parser = argparse.ArgumentParser()
parser.add_argument('--program','-i', default='./program.tv')
parser.add_argument('--sources','-s', default='./Videos')
parser.add_argument('--times','-t', default='./Videos/times.csv')
parser.add_argument('--dry-run','-N', action='store_true')
parser.add_argument('--no-wait', action='store_true')
args = parser.parse_args()

videos_path = args.sources
program_path = args.program
bg_path = './bg'
logo_path='./ident_overlay.png'

seed_mutator = ':0001'
start_day = '2021-04-05'
start_hour = 11
marquee = 'marq{marquee=TEST,color=0xFFFF,size=24,position=10,x=20,y=20}'

def set_fixed_seed(seed):
    random.seed(seed+seed_mutator, 2)

def in_dir(prefix,f):
    return os.path.dirname(f) == prefix

class MetaPool:
    def __init__(self,l,seed):
        prefixes = sorted(list(set(map(lambda f: f.rsplit('/',1)[0],l))))
        self._children = []
        self._index = 0
        for prefix in prefixes:
            self._children.append(Pool(list(filter(lambda f: in_dir(prefix,f),l)),seed=prefix))
        set_fixed_seed(seed)
        random.shuffle(self._children)

    def pick(self):
        self._index = (self._index + 1) % len(self._children)

    def shuffle(self):
        random.shuffle(self._children)
        self._index = 0
        for child in self._children:
            child.shuffle()

    def grab(self):
        return self._children[self._index].grab()

class Pool:
    def __init__(self,l,seed=None):
        self._sequential = False
        self._videos = l.copy()
        self._index = 0
        for item in self._videos:
            if item.endswith('.sequential'):
                self._sequential = True
                self._videos.remove(item)
                break
        if self._sequential:
            self._videos.sort()
        else:
            set_fixed_seed(seed)
            random.shuffle(self._videos)

    def pick(self):
        pass

    def shuffle(self):
        random.shuffle(self._videos)
        self._index = 0

    def grab(self):
        while True:
            item = self._videos[self._index]
            self._index = (self._index + 1) % len(self._videos)
            if time.localtime().tm_mon == 12 or '(xmas)' not in item:
                return item


times_db = {}
videos = []
pools = {}
pool_keys = None

with open(args.times,newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        times_db[os.path.join(videos_path,row['file'])] = int(row['duration'])

for root, dirs, files in os.walk(videos_path):
    if root == videos_path:
        pool_keys = dirs
    for file in files:
        if file.endswith('.mp4') or file.endswith('.mkv') or file.endswith('.avi') or file.endswith('.sequential'):
            videos.append(os.path.join(root,file))

for k in pool_keys:
    pools[k] = MetaPool(list(filter(lambda f: '/{}/'.format(k) in f, videos)),k)

current_pool = None
pool_stack = []
defs = {}

def primitive(tokens,playlist):
    global current_pool
    command, *args = tokens
    if command == 'using':
        current_pool = args[0]
    elif command == 'play':
        for i in range(int(args[0])):
            playlist.append(pools[current_pool].grab())
    elif command == 'shuffle':
        pools[current_pool].shuffle()
    elif command == 'pick':
        pools[current_pool].pick()
    elif command == 'file':
        playlist.append(os.path.join(videos_path,args[0]))
    elif command == 'oneof':
        primitive([random.choice(args)],playlist)
    else:
        pool_stack.append(current_pool)
        for tokens in defs[command]:
            primitive(tokens,playlist)
        current_pool = pool_stack.pop()

with open(program_path) as file:
    current_def = None
    for line in file:
        indented = line[0] == ' ' or line[0] == '\t'
        line = line.strip()
        if current_def is not None and not indented:
            current_def = None
        if line.endswith(':'):
            current_def = []
            key = line[:-1]
            defs[key] = current_def
            continue
        tokenized = list(map(lambda a: shlex.split(a), line.split(';')))
        if current_def is not None:
            current_def.extend(tokenized)
        else:
            for tokens in tokenized:
                if tokens[0] == 'start_hour':
                    #global start_hour
                    start_hour = int(tokens[1])
                elif tokens[0] == 'seed_mutator':
                    #global seed_mutator
                    seed_mutator = tokens[1]
                elif tokens[0] == 'start_day':
                    #global start_day
                    start_day = tokens[1]
                elif tokens[0] == 'marquee':
                    #global marquee
                    marquee = tokens[1]

def build_playlist():
    playlist = []
    for item in defs['every_day']:
        primitive(item,playlist)
    return playlist

def play(playlist,start_time=None):
    args = [
        'cvlc',
        '--play-and-exit',
        '--no-video-title-show',
        '--audio-filter', 'normvol',
        '--norm-max-level','10',
        '--audio-filter', 'compressor',
        '--sub-source='+marquee,
    ]
    if start_time is not None:
        args += ['--start-time',str(start_time)]
    subprocess.run(args+playlist)

def off_air():
    playlist = []
    for item in defs['off_air']:
        primitive(item,playlist)
    subprocess.run([
        'cvlc',
        '--play-and-exit',
        '--no-video-title-show',
        '--sub-source=marq{marquee=%I:%M%p,size=32,color=0xffffff,position=8,x=20,y=20}'
        '--image-duration=60'
    ]+playlist)

#wait for NTP sync
if not args.no_wait:
    off_air()

#fastforward on first boot
days = int(time.time() - time.mktime(time.strptime(start_day,'%Y-%m-%d'))) // (60*60*24)
print(days)
set_fixed_seed('root')
for i in range(days):
    playlist = build_playlist()
if args.dry_run:
    total_time = 0
    for item in playlist:
        print('{:>02.0f}:{:>02.0f} {}'.format(total_time/(60*60) + start_hour,(total_time/60)%60,item))
        total_time += times_db[item]
    print('{:>02.0f}:{:>02.0f}'.format(total_time/(60*60),(total_time/60)%60))
    exit()
current_time = time.time()
current_struct = time.localtime(current_time)
objective_time = time.mktime((
    current_struct.tm_year,
    current_struct.tm_mon,
    current_struct.tm_mday,
    start_hour,0,0,
    current_struct.tm_wday,
    current_struct.tm_yday,
    current_struct.tm_isdst
))
fast_forward = current_time - objective_time
whole_time = 0
start_index = 0
start_time = 0
if fast_forward >= 0 and fast_forward:
    for item in playlist:
        duration = times_db[item]
        if whole_time + duration > fast_forward:
            break
        whole_time += duration
        start_index += 1
    if start_index in range(len(playlist)):
        start_time = fast_forward - whole_time
        play([playlist[start_index]],start_time)
        play(playlist[start_index+1:])

#main loop
while True:
    bg_index = 0
    while time.localtime().tm_hour != start_hour:
        off_air()
    play(build_playlist())
