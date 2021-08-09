#!/usr/bin/python3

import subprocess
import os
import os.path
import random
import argparse
import csv
from pymediainfo import MediaInfo

parser = argparse.ArgumentParser()
parser.add_argument('--path','-p', default='./Videos')
args = parser.parse_args()

allowed_extensions = ('.mp4','.mkv','.avi')

with open(os.path.join(args.path,'times.csv'), mode='w', newline='') as csvfile:
  csvwriter = csv.writer(csvfile)
  csvwriter.writerow(['file','duration'])
  for root, dirs, files in os.walk(args.path):
    if root == args.path:
      pool_keys = dirs
    for file in files:
      if file.endswith(allowed_extensions):
        #print(file)
        info = MediaInfo.parse(os.path.join(root,file))
        duration = None
        for track in info.tracks:
          if track.duration is not None:
            duration = track.duration
            break
        csvwriter.writerow([os.path.relpath(os.path.join(root,file),args.path),int(duration / 1000)])
