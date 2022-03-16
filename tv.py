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
import datetime
import sys
import re

allowed_extensions = ('.mp4','.mkv','.avi')
image_duration = 10

def wall_time(d):
    return '{:>02.0f}:{:>02.0f}'.format(
        (d//(60*60))%24,
        (d//60)%60
    )

def rounded_wall_time(d):
    t = wall_time(d)
    if t.split(':')[1] in ('59','58'):
        return '{:>02.0f}:{:>02.0f}'.format(int(t.split(':')[0])+1,0)
    if t.split(':')[1] in ('29','28'):
        return '{:>02.0f}:{:>02.0f}'.format(int(t.split(':')[0]),30)
    return t

class SequentialPool:
    def __init__(self,path,offset=0):
        self._videos = []
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith(allowed_extensions):
                        self._videos.append(os.path.join(root,file))
        else:
            self._videos.append(path)
        self._videos.sort()
        self._index = offset % len(self._videos)

    def get(self):
        return self._videos[self._index]

    def advance(self):
        self._index = (self._index + 1) % len(self._videos)

    def reject(self):
        return self.advance()


class ShuffledPool:
    def __init__(self,path,seed):
        self._videos = []
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith(allowed_extensions):
                        self._videos.append(os.path.join(root,file))
        else:
            self._videos.append(path)
        self._videos.sort()
        r = random.Random(seed)
        r.shuffle(self._videos)
        self._index = 0

    def get(self):
        return self._videos[self._index]

    def advance(self):
        self._index = (self._index + 1) % len(self._videos)

    def reject(self):
        return self.advance()


class RandomPool:
    def __init__(self,path,seed,memory,history=None):
        self._videos = []
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith(allowed_extensions):
                        self._videos.append(os.path.join(root,file))
        else:
            self._videos.append(path)
        self._videos.sort()
        self._random = random.Random(seed)
        self._memory = memory
        self._index = self._random.randrange(len(self._videos))
        if history is None:
            history = []
        self._history = history

    def get(self):
        if self._videos[self._index] in self._history:
            self.advance()
        return self._videos[self._index]

    def advance(self):
        while True:
            self._index = self._random.randrange(len(self._videos))
            if self._videos[self._index] not in self._history:
                break
        self._history.append(self._videos[self._index])
        if len(self._history) > self._memory:
            self._history.pop(0)

    def reject(self):
        if self._videos[self._index] in self._history:
            self._history.remove(self._videos[self._index])
        return self.advance()


def wrongMonth(video,month):
    if month is None:
        return False
    if '(halloween)' in video and month != 10:
        return True
    if '(thanksgiving)' in video and month != 11:
        return True
    if '(xmas)' in video and month != 12:
        return True
    return False


class TVProgramError(Exception):
    def __init__(self,message):
        self.message = message


class Program:
    def __init__(self, file, times):
        self._times = times
        self._pools = {}
        self._histories = {}
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
                    elif tokens[0] == 'pool':
                        parser = argparse.ArgumentParser(prog='pool')
                        parser.add_argument('file')
                        parser.add_argument('--shuffled',action='store_const',const='shuffled',dest='pool_type')
                        parser.add_argument('--randomized',action='store_const',const='randomized',dest='pool_type')
                        parser.add_argument('--memory',type=int,default=5)
                        parser.add_argument('--shared-history')
                        parser.add_argument('--seed')
                        parser.add_argument('--offset',type=int,default=0)
                        pargs = parser.parse_args(tokens[1:])
                        sub_path = pargs.file.split('#')[0]
                        seed = pargs.seed if pargs.seed else sub_path
                        path = os.path.join(videos_path,sub_path)

                        if pargs.pool_type == 'randomized':
                            if pargs.shared_history:
                                if pargs.shared_history not in self._histories:
                                    self._histories[pargs.shared_history] = []
                                self._pools[pargs.file] = RandomPool(
                                    path,
                                    seed,
                                    pargs.memory,
                                    self._histories[pargs.shared_history]
                                )
                            else:
                                self._pools[pargs.file] = RandomPool(
                                    path,
                                    seed,
                                    pargs.memory
                                )
                        elif pargs.pool_type == 'shuffled':
                            self._pools[pargs.file] = ShuffledPool(
                                path,
                                seed
                            )
                        else:
                            self._pools[pargs.file] = SequentialPool(
                                path,
                                pargs.offset
                            )
                    elif len(tokens) > 2:
                        params[tokens[0]] = tokens[1:]
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

    def run(self,date=None,entrypoint=None,verbose=False,epg=[]):
        wdays = [
            '__monday__',
            '__tuesday__',
            '__wednesday__',
            '__thursday__',
            '__friday__',
            '__saturday__',
            '__sunday__'
        ]
        pools = self._pools
        if date is not None:
            print(wdays[date.weekday()])
        class ProgramState:
            def __init__(self):
                self.current_time = 0

        def primitive(tokens,playlist,state):
            def play(video):
                playlist.append(video)
                state.current_time += self._times.get(video,image_duration)
            command, *args = tokens
            if command == 'repeat':
                for i in range(int(args[0])):
                    primitive(args[1:],playlist,state)
            elif command == 'play':
                parser = argparse.ArgumentParser(prog='play')
                parser.add_argument('file')
                parser.add_argument('--repeat',default=1,nargs='?',type=int)
                parser.add_argument('--until')
                parser.add_argument('--ignore',default=0,type=float)
                parser.add_argument('--suppress','-q',action='store_true'),
                parser.add_argument('--min',type=int,default=1)
                parser.add_argument('--max',type=int,default=None)
                parser.add_argument('--verbose','-v',action='store_true')
                pargs = parser.parse_args(args)
                repeat = 1
                if pargs.file not in pools:
                    #raise TVProgramError('Pool "{}" not defined'.format(pargs.file))
                    path = pargs.file.split('#')[0]
                    self._pools[pargs.file] = SequentialPool(os.path.join(videos_path,path))
                pool = self._pools[pargs.file]
                if pargs.until:
                    if not pargs.verbose and (verbose or not pargs.suppress):
                        t = wall_time(state.current_time + self.params['start_hour']*60*60)
                        p = pargs.file
                        epg.append({
                            'time':state.current_time + self.params['start_hour']*60*60,
                            'path':p
                        })
                        print('{} '.format(t),end='')
                    if pargs.until.startswith(':'):
                        target_amount = int(pargs.until[1:])
                        current_minutes = state.current_time//60
                        target = (current_minutes - (current_minutes % target_amount) + target_amount)*60
                        if current_minutes % target_amount <= pargs.ignore:
                            target = state.current_time
                    else:
                        target_amount = float(pargs.until) - self.params['start_hour']
                        current_hours = state.current_time//(60*60)
                        target = (current_hours - (current_hours % 24) + target_amount)*(60*60)
                    count = 0
                    while True:
                        if pargs.max is not None and count >= pargs.max:
                            break
                        video = pool.get()
                        if date is not None:
                            while wrongMonth(video,date.month):
                                pool.reject()
                                video = pool.get()
                        video_time = self._times.get(video,image_duration)
                        if count >= pargs.min and state.current_time + video_time > target:
                            break
                        if pargs.verbose:
                            t = wall_time(state.current_time + self.params['start_hour']*60*60)
                            p = os.path.relpath(video,videos_path)
                            print(
                                '{} {:<72}'.format(
                                    t,
                                    p[:72]
                                )
                            )
                            epg.append({
                                'time':state.current_time + self.params['start_hour']*60*60,
                                'path':os.path.split(p)[-2],
                                'file': os.path.splitext(os.path.split(p)[-1])[0]
                            })
                        elif verbose:
                            print('  {}'.format(video))
                        pool.advance()
                        play(video)
                        count += 1
                    if verbose or not pargs.suppress:
                        print('played {} {} times'.format(pargs.file,count))
                else:
                    for i in range(pargs.repeat):
                        video = pool.get()
                        if date is not None:
                            while wrongMonth(video,date.month):
                                pool.reject()
                                video = pool.get()
                        pool.advance()
                        if not pargs.suppress:
                            t = wall_time(state.current_time + self.params['start_hour']*60*60)
                            p = os.path.relpath(video,videos_path)
                            print(
                                '{} {:<72}'.format(
                                    t,
                                    p[:72]
                                )
                            )
                            epg.append({
                                'time':state.current_time + self.params['start_hour']*60*60,
                                'path':os.path.split(p)[-2],
                                'file': os.path.splitext(os.path.split(p)[-1])[0]
                            })
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


        if entrypoint is None:
            entrypoint = wdays[date.weekday()]

        playlist = []
        state = ProgramState()
        for item in self.defs[entrypoint]:
            try:
                primitive(item,playlist,state)
            except Exception as error:
                print(item,state)
                raise error

        return playlist

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--program','-i', default='./program.tv')
    parser.add_argument('--sources','-s', default='./Videos')
    parser.add_argument('--times','-t', default='./Videos/times.csv')
    parser.add_argument('--dry-run','-N', action='store_true')
    parser.add_argument('--verbose','-V', action='store_true')
    parser.add_argument('--no-wait', action='store_true')
    parser.add_argument('--date')
    parser.add_argument('--epg')
    parser.add_argument('--show-titles', action='store_true')
    args = parser.parse_args()

    vlc_args = [
        'cvlc',
        '--play-and-exit',
        '--video-title-show' if args.show_titles else '--no-video-title-show',
        '--audio-replay-gain-mode','track',
        #'--audio-filter', 'normvol',
        #'--norm-max-level','2.0',
        #'--norm-buff-size','10',
        '--audio-filter', 'compressor',
        '--compressor-rms-peak=0.0',
        '--compressor-attack=50.0',
        '--compressor-threshold=-30.0',
        '--compressor-ratio=20.0',
        '--compressor-knee=1.0',
        '--compressor-makeup-gain=18.0',
        '--image-duration={}'.format(image_duration)
    ]

    print(vlc_args)

    def play(playlist,marquee,start_time=None):
        args = vlc_args + [
            '--sub-source='+marquee,
        ]
        if start_time is not None:
            args += ['--start-time',str(start_time)]
        subprocess.run(args+playlist)

    def off_air(playlist):
        subprocess.run(vlc_args + [
            '--sub-source=marq{marquee=%I:%M%p,size=32,color=0xffffff,position=8,x=20,y=20}',
        ] + playlist)


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

    off_air_playlist = program.run(entrypoint='__off_air__')

    #wait for NTP sync
    if not args.no_wait:
        print('Waiting for accurate time...')
        off_air(off_air_playlist)

    #fastforward on first boot
    start_tm = time.strptime(start_day,'%Y-%m-%d')
    days = int(
        (time.mktime(time.strptime(args.date,'%Y-%m-%d')) if args.date else time.time())
        - time.mktime(start_tm)
    )//(60*60*24)
    print('fastforwarded {} days'.format(days))
    epg = []
    for i in range(days):
        date = datetime.date(start_tm.tm_year,start_tm.tm_mon,start_tm.tm_mday) + datetime.timedelta(days=i)
        if date >= datetime.date.today():
            epg_day = {
                'day':calendar.day_name[date.weekday()],
                'date':date.isoformat(),
                'program':[]
            }
            epg.append(epg_day)
            playlist = program.run(date=date,verbose=args.verbose,epg=epg_day['program'])
        else:
            playlist = program.run(date=date,verbose=args.verbose)
        print()
    if args.epg:
        with open(args.epg, mode='w') as f:
            f.write('<html><body><table border=1>')
            for epg_day in epg:
                f.write('<tr><th colspan=2>{} {}</th></tr>'.format(epg_day['day'],epg_day['date']))
                for item in epg_day['program']:
                    t = list(map(int,rounded_wall_time(item['time']).split(':')))
                    pm = False
                    if t[0] >= 12:
                        pm = True
                    if t[0] > 12:
                        t[0] -= 12
                    if t[0] == 0:
                        t[0] = 12
                    time = '{:02}:{:02}{}'.format(t[0],t[1],'pm' if pm else 'am')
                    if 'file' in item:
                        name = item['file'].replace('_',' ')
                        if name.startswith(item['path']):
                            name = name[len(item['path']):].strip()
                        name = re.sub(r' (?:(?:xvid(?: edit)?)|(?:low)|(?:med)|(?:highTV)|(?:HDmed))$','',name)
                        name = re.sub(r'([a-z])-?([A-Z])',r'\1 \2',name)
                        f.write('<tr><th>{}</th><td>{}<br><i>"{}"</i></td></tr>'.format(time,os.path.split(item['path'])[-1],name))
                    else:
                        f.write('<tr><th>{}</th><td>{}<br><br></td></tr>'.format(time,item['path'].split('#')[0]))
            f.write('</table></body></html>')
    last_day = None
    while True:
        while last_day == datetime.date.today():
            print('Waiting for next day...')
            off_air(off_air_playlist)
        last_day = datetime.date.today()
        playlist = program.run(date=last_day)
        if args.dry_run:
            exit()
        def get_fast_forward():
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
            return current_time - objective_time
        fast_forward = get_fast_forward()
        while fast_forward < 0:
            print('Waiting for program start...')
            off_air(off_air_playlist)
            fast_forward = get_fast_forward()
        whole_time = 0
        start_index = 0
        start_time = 0
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
