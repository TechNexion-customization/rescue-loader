#!/usr/bin/env python3

#----------------------------------------------------------
# installer cli
#
# To run the installer cli commands, type in the shell
#
# $ installer.py help
#
# for help usage of the installer cli tool
#
#----------------------------------------------------------

import re
import time
import math
import logging
import subprocess
from threading import Thread, Event
from urllib.parse import urlparse

from defconfig import SetupLogging
from view import CliViewer

SetupLogging('/tmp/installer_cli.log')
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

def _prettySize(n,pow=0,b=1024,u='B',pre=['']+[p+'i'for p in'KMGTPEZY']):
    r,f=min(int(math.log(max(n*b**pow,1),b)),len(pre)-1),'{:,.%if} %s%s'
    return (f%(abs(r%(-r-1)),pre[r],u)).format(n*b**pow/b**float(r))

def findAttrs(keys, dc):
    """
    For dictionary and dictionary within a dictionary
    """
    for k, v in dc.items():
        if k in keys:
            yield (k, v)
        elif isinstance(v, dict):
            for ret in findAttrs(keys, v):
                yield ret

# def parseTargetList(result):
#     ret = {}
#     for k, v in result.items():
#         data = []
#         if isinstance(v, dict):
#             data.append(k)
#             for att in findAttrs(['device_node', 'size'], v):
#                 data.append(att)
#         ret.update({data})
#     return [(i, k, v) for i, (k, v) in enumerate(data)]

def parseTargetList(result):
    data = {}
    for k, v in result.items():
        if isinstance(v, dict):
            data.update({k: {att[0]:att[1] for att in findAttrs(['device_node', 'size'], v)}})
    return [(i, k, v) for i, (k, v) in enumerate(data.items())]

def parseWebList(result):
    if 'file_list' in result and isinstance(result['file_list'], dict):
        # We know that file_list is a dictionary because we send it from the server
        return [(i, k, v) for i, (k, v) in enumerate(sorted(result['file_list'].items()))]

def checkUrl(url):
    try:
        result = urlparse(url)
        return result if all([result.scheme, result.netloc]) else None
    except:
        return None

def crawlWeb(link, result):
#    print('link: {}'.format(link))
    cliWeb = CliViewer()
    cliWeb.request({'cmd': 'info', 'target': 'http://rescue.technexion.net', 'location': link })
    parsedList = parseWebList(cliWeb.getResult())
    del cliWeb
    for i in parsedList:
        if i[1].endswith('/'):
            pobj = checkUrl(i[2])
            if pobj is not None:
                crawlWeb(pobj.path.replace('/rescue/', '/'), result)
        elif i[1].endswith('.xz'):
            result.update({link+i[1]: i[2]})

def loopResult(viewer, ev):
    while not ev.wait(1):
        result = viewer.queryResult()
        if 'total_uncompressed' in result and 'bytes_written'  in result:
            pcent = float(int(result['bytes_written']) / int(result['total_uncompressed']))
            hashes = '#' * int(round(pcent * 40))
            spaces = ' ' * (40 - len(hashes))
            outstr = 'Percent: [{}] {}% ({}/{})'.format(hashes + spaces, int(round(pcent * 100)), _prettySize(int(result['bytes_written'])), _prettySize(int(result['total_uncompressed'])))
            print(outstr, end=((' ' * (80 - len(outstr))) + '\r'))
        else:
            print('Processing: ...', end='\r')

def disable_guiclientd():
    print('Disable guiclientd first...')
    subprocess.check_call(['systemctl', 'stop', 'guiclientd.service'])

def main():
    def parseSOMInfo(path):
        p = re.compile('\/(\w+)[_|-](\w+)\/(\w+)-(\w+)\/(.+)\.xz', re.IGNORECASE)
        m = p.match(path)
        if m:
            return m.groups()

    def parseFilename(fname):
        if '-' in fname:
            os, ver = fname.split('-', 1)
        else:
            os = fname
            ver = ''
        return os, ver


    menuResult = {}
    tgtResult = {}

    # step 0: find out the module and baseboard of the target device
    print('Find target device cpu, and form-factor...')
    cliSom = CliViewer()
    cliSom.request({'cmd': 'info', 'target': 'som'})
    if 'found_match' in cliSom.getResult():
        form, cpu, baseboard = cliSom.getResult()['found_match'].split(',')
        print('Found: {} {} {}'.format(cpu, form, baseboard))
    else:
        form = cpu = baseboard = '' # same reference
        print('Target Device SOM info not found.')

    # step 1: request for list of download-able files from https://rescue.technexion.net/rescue/
    # spider crawl through the url links to find all .xz files in sub directory links
    print('Crawl through rescue server for xz files...')
    crawlWeb('/', menuResult) # /pico-imx7/pi-070/

    print('Find matching xz files for the target device...')
    # step 2: find menu items that matches as cpu, form, but not baseboard
    for k, v in sorted(menuResult.items()):
        if not (cpu[0:4].lower() in k.lower() or cpu.lower() in k.lower()):
            menuResult.pop(k)
        else:
            if form.lower() not in k.lower():
                menuResult.pop(k)

    # step 3: ask user to choose the file to download
    menus = [(i, k, v) for i, (k, v) in enumerate(sorted(menuResult.items()))]
    print('{:>4} {:<8} {:<6} {:<8} {:<14} {:<14} {:<10} {:<8}'.format('#', 'cpu', 'form', 'board', 'display', 'os', 'ver', 'size'))
    for menu in menus:
        cliInfo = CliViewer()
        cliInfo.request({'cmd': 'info', 'target': 'http://rescue.technexion.net', 'location': menu[1]})
        if 'total_uncompressed' in cliInfo.getResult():
            uncompsize = int(cliInfo.getResult()['total_uncompressed'])
        elif 'total_size' in cliInfo.getResult():
            uncompsize = int(cliInfo.getResult()['total_size'])
        else:
            uncompsize = 0
        del cliInfo
        if menu[1].endswith('.xz'):
            form, cpu, board, disp, fname = parseSOMInfo(menu[1])
            os, ver = parseFilename(fname.rstrip('.xz'))
            print('{:>4} {:<8} {:<6} {:<8} {:<14} {:<14} {:<10} {:<8}'.format(menu[0], cpu, form, board, disp, os, ver, _prettySize(uncompsize)))
    while True:
        srcNum = input('Choose a file to download ([Q]uit): ')
        if srcNum.isdecimal() and (int(srcNum) >= 0 and int(srcNum) < len(menus)):
            break
        elif srcNum.isalpha() and srcNum.lower() == 'q':
            exit(1)
        else:
            print('Invalid Inputs')

    # step 4: request for list of targets storage device
    cliTgt = CliViewer()
    cliTgt.request({'cmd': 'info', 'target': 'emmc', 'location': 'disk'})
    tgtResult.update(cliTgt.getResult())
    del cliTgt

    # step 5: ask user to choose the target to flash
    targets = parseTargetList(tgtResult)
    print('{:>4} {:<16} {:<24} {:<24}'.format('#', 'name', 'node path', 'disk size'))
    for tgt in targets:
        print('{:>4} {:<16} {:<24} {:<24}'.format(tgt[0], tgt[1], tgt[2]['device_node'], _prettySize(int(tgt[2]['size']) * 512)))
    while True:
        tgtNum = input('Choose a storage to flash ([Q]uit): ')
        if tgtNum.isdecimal() and (int(tgtNum) >= 0 and int(tgtNum) < len(targets)):
            break
        elif tgtNum.isalpha() and tgtNum.lower() == 'q':
            exit(1)
        else:
            print('Invalid Inputs')

    # step 6: make up the command to download and flash and execute it
    cliDl = CliViewer()
    # python3 view.py {download -u http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz -t /dev/mmcblk2}
    dlparam = {'cmd': 'download', 'dl_url': menus[int(srcNum)][2], 'tgt_filename': targets[int(tgtNum)][2]['device_node']}
    print("Download {}, and flash to {}".format(menus[int(srcNum)][2], targets[int(tgtNum)][2]['device_node']))
    # print("with cmd: {}".format(dlparam))
    while True:
        yn = input("[Y]es/[N]o ([Q]uit)? ")
        if yn.lower() == 'yes' or yn.lower() == 'y':
            break
        elif yn.lower() == 'no' or yn.lower() == 'n' or yn.lower() == 'quit' or yn.lower() == 'q':
            exit(1)

    # step 7: parse the result in a loop until result['status'] != 'processing'
    endEvent = Event()
    endEvent.clear()
    resultThread = Thread(name='ResultThread', target=loopResult, args=(cliDl, endEvent))
    resultThread.start()
    cliDl.request(dlparam)
    time.sleep(1)
    endEvent.set()
    resultThread.join()
    print('Flash complete...', end=((' '*60) + '\r\n'))
    del cliDl

    # step 8: enable/disable the mmc boot option
    cliCfg = CliViewer()
    # python3 view.py {config mmc -c bootpart -s enable/disable -n 1 -k 1 /dev/mmcblk2}
    cfgparam = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', \
                'config_action': 'enable' if 'androidthings' in dlparam['dl_url'] else 'disable', \
                'boot_part_no': '1', 'send_ask': '1', 'target': dlparam['tgt_filename']}
    print('{} mmc boot partition 1 configuration...'.format('Enable' if 'androidthings' in dlparam['dl_url'] else 'Disable'))
    cliCfg.request(cfgparam)
    del cliCfg

    # step 9: a message to tell user what to do next
    print('Please set the boot jumper to BOOT MODE and reboot your board...')



if __name__ == "__main__":
    disable_guiclientd()
    main()