#!/usr/bin/python3

import subprocess
import os
import os.path
import random
import argparse
import time
import shlex
import csv
import calendar
import sys

allowed_extensions = ('.mp4','.mkv','.avi')
image_duration = 10

def wall_time(d):
    return '{:>02.0f}:{:>02.0f}'.format(
        (d//(60*60))%24,
        (d//60)%60
    )

class Pool:
    def __init__(self,path,shuffled,seed=None,offset=0):
        self._videos = []
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith(allowed_extensions):
                        self._videos.append(os.path.join(root,file))
        else:
            self._videos.append(path)
        self._index = offset % len(self._videos)
        self._videos.sort()
        if shuffled:
            r = random.Random(seed if seed else path)
            r.shuffle(self._videos)

    def peek(self):
        index = self._index
        while True:
            item = self._videos[index]
            index = (index + 1) % len(self._videos)
            if time.localtime().tm_mon == 12 or '(xmas)' not in item:
                return item

    def grab(self):
        while True:
            item = self._videos[self._index]
            self._index = (self._index + 1) % len(self._videos)
            if time.localtime().tm_mon == 12 or '(xmas)' not in item:
                return item

class Program:
    def __init__(self, file, times):
        self._times = times
        self._pools = {}
        defs = {}
        params = {
            'start_day':'2021-04-05',
            'start_hour':11,
            'marquee':'marq{marquee=TEST,color=0xFFFF,size=24,position=10,x=20,y=20}'
        }
        current_def = None
        for line in file:
            if line.isspace() or line.strip().startswith('#'):
                continue
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
                        params['start_hour'] = int(tokens[1])
                    else:
                        params[tokens[0]] = tokens[1]
        weekdays = [
            '__monday__',
            '__tuesday__',
            '__wednesday__',
            '__thursday__',
            '__friday__'
        ]
        weekends = [
            '__saturday__',
            '__sunday__'
        ]
        for day in weekdays:
            if day not in defs:
                defs[day] = defs['__weekday__'] if '__weekday__' in defs else defs['__every_day__']
        for day in weekends:
            if day not in defs:
                defs[day] = defs['__weekend__'] if '__weekend__' in defs else defs['__every_day__']

        self.defs = defs
        self.params = params

    def run(self,entrypoint=None,wday=None):
        pools = self._pools

        class ProgramState:
            def __init__(self):
                self.current_time = 0

        def primitive(tokens,playlist,state):
            def play(video):
                playlist.append(video)
                state.current_time += self._times.get(video,image_duration)
            command, *args = tokens
            if command == 'play':
                parser = argparse.ArgumentParser(prog='play')
                parser.add_argument('file')
                parser.add_argument('--shuffled',action='store_true')
                parser.add_argument('--repeat',default=1,nargs='?',type=int)
                parser.add_argument('--until')
                parser.add_argument('--ignore',default=0,type=float)
                parser.add_argument('--suppress','-q',action='store_true'),
                parser.add_argument('--no_min',action='store_true'),
                pargs = parser.parse_args(args)
                repeat = 1
                if pargs.file not in pools:
                    path = pargs.file.split('#')[0]
                    pools[pargs.file] = Pool(
                        os.path.join(videos_path,path),
                        pargs.shuffled
                    )
                if pargs.until:
                    if not pargs.suppress:
                        print('  {} '.format(wall_time(state.current_time + self.params['start_hour']*60*60)),end='')
                    if pargs.until.startswith(':'):
                        target_amount = int(pargs.until[1:])
                        current_minutes = state.current_time//60
                        target = (current_minutes - (current_minutes % target_amount) + target_amount)*60
                        if current_minutes % target_amount <= pargs.ignore:
                            target = state.current_time
                    else:
                        target_amount = int(pargs.until) - self.params['start_hour']
                        current_hours = state.current_time//(60*60)
                        target = (current_hours - (current_hours % 24) + target_amount)*(60*60)
                    count = 0
                    while True:
                        video = pools[pargs.file].peek()
                        video_time = self._times.get(video,image_duration)
                        if (count > 0 or pargs.no_min) and state.current_time + video_time > target:
                            break
                        play(pools[pargs.file].grab())
                        count += 1
                    if not pargs.suppress:
                        print('played {} {} times'.format(pargs.file,count))
                else:
                    for i in range(pargs.repeat):
                        video = pools[pargs.file].grab()
                        if not pargs.suppress:
                            print(
                                '{} {:<72}'.format(
                                    wall_time(state.current_time + self.params['start_hour']*60*60),
                                    os.path.relpath(video,videos_path)[:72]
                                )
                            )
                        play(video)
            elif command == 'print':
                print(' '.join(args))
            else:
                for sub_tokens in self.defs[command]:
                    replaced_tokens = []
                    for sub_token in sub_tokens:
                        for i in range(len(tokens)):
                            sub_token = sub_token.replace('${}'.format(i),tokens[i])
                        if '$' not in sub_token:
                            replaced_tokens.append(sub_token)
                    primitive(replaced_tokens,playlist,state)

        wdays = [
            '__monday__',
            '__tuesday__',
            '__wednesday__',
            '__thursday__',
            '__friday__',
            '__saturday__',
            '__sunday__'
        ]

        if entrypoint is None:
            entrypoint = wdays[wday]

        playlist = []
        state = ProgramState()
        for item in self.defs[entrypoint]:
            try:
                primitive(item,playlist,state)
            except Exception as error:
                print(item,state)
                raise error

        return playlist


def play(playlist,marquee,start_time=None):
    args = [
        'cvlc',
        '--play-and-exit',
        '--no-video-title-show',
        '--audio-filter', 'compressor',
        '--sub-source='+marquee,
        '--image-duration={}'.format(image_duration)
    ]
    if start_time is not None:
        args += ['--start-time',str(start_time)]
    subprocess.run(args+playlist)

def off_air(playlist):
    subprocess.run([
        'cvlc',
        '--play-and-exit',
        '--no-video-title-show',
        '--audio-filter', 'compressor',
        '--sub-source=marq{marquee=%I:%M%p,size=32,color=0xffffff,position=8,x=20,y=20}',
        '--image-duration={}'.format(image_duration)
    ]+playlist)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--program','-i', default='./program.tv')
    parser.add_argument('--sources','-s', default='./Videos')
    parser.add_argument('--times','-t', default='./Videos/times.csv')
    parser.add_argument('--dry-run','-N', action='store_true')
    parser.add_argument('--no-wait', action='store_true')
    parser.add_argument('--date')
    args = parser.parse_args()

    videos_path = args.sources
    program_path = args.program
    times_db = {}
    videos = []

    with open(args.times,newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            times_db[os.path.join(videos_path,row['file'])] = int(row['duration'])

    with open(program_path) as file:
        program = Program(file,times_db)

    start_day = program.params['start_day']
    start_hour = program.params['start_hour']
    marquee = program.params['marquee']

    off_air_playlist = program.run('__off_air__')

    #wait for NTP sync
    if not args.no_wait:
        off_air(off_air_playlist)

    #fastforward on first boot
    start_tm = time.strptime(start_day,'%Y-%m-%d')
    days = int(
        (time.mktime(time.strptime(args.date,'%Y-%m-%d')) if args.date else time.time())
        - time.mktime(start_tm)
    )//(60*60*24)
    print('fastforwarded {} days'.format(days))
    for i in range(days+1):
        playlist = program.run(wday=(start_tm.tm_wday + i)%7)
        print()
    if args.dry_run:
        # total_time = 0
        # print('start weekday {}, end weekday {}'.format(
        #     calendar.day_name[start_tm.tm_wday],
        #     calendar.day_name[(start_tm.tm_wday + days)%7]
        # ))
        # for item in playlist:
        #     print('{:>02.0f}:{:>02.0f} {:<74}'.format((total_time/(60*60) + start_hour)%23,(total_time/60)%59,os.path.relpath(item,videos_path)[:74]))
        #     total_time += times_db.get(item,image_duration)
        # print('{:>02.0f}:{:>02.0f}'.format(total_time/(60*60),(total_time/60)%59))
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
    if fast_forward >= 0:
        for item in playlist:
            duration = times_db[item]
            if whole_time + duration > fast_forward:
                break
            whole_time += duration
            start_index += 1
        if start_index in range(len(playlist)):
            start_time = fast_forward - whole_time
            play([playlist[start_index]],marquee,start_time)
            play(playlist[start_index+1:],marquee)

    #main loop
    while True:
        bg_index = 0
        while time.localtime().tm_hour != start_hour:
            off_air(off_air_playlist)
        play(program.run(wday=time.localtime().tm_wday),marquee)
