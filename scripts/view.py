# Copyright (c) 2018 TechNexion,Inc. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, 
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. The names of the authors may not be used to endorse or promote products 
#    derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESSED OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL
# TECHNEXION, INC. OR ANY CONTRIBUTORS TO THIS SOFTWARE BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

# view:
# This library defines the base Installer/Rescue client object
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import abc
import logging
from urllib.parse import urlparse

from os import uname
from os.path import isfile
from threading import Thread, Event
#from ConfigParser import ConfigParser # read/write config files

from defconfig import DefConfig
from messenger import DbusMessenger, WebMessenger

# get the handler to the current module, and setup logging options
_logger = logging.getLogger(__name__)



class BaseViewer(object):
    """
    Base Viewer Class
    """

    def __init__(self, confname = ''):
        super().__init__()
        self.mResponseEvent = Event()
        self.mDefConfig = DefConfig()
        self.__initialize(confname)

    def __initialize(self, confname):
        # standard initialization for all Viewers
        if isinstance(confname, str) and isfile(confname):
            self.mDefConfig.loadConfig(confname)
        else:
            self.mDefConfig.loadConfig('/etc/installer.xml')

    def _preExec(self):
        """
        To be overriden
        """
        return True

    def _mainExec(self):
        """
        To be overriden
        """
        return True

    def _postExec(self):
        """
        To be overriden
        """
        return True

    def _parseResult(self):
        """
        To be overriden
        """
        return True

    def _parseCmd(self, params):
        """
        To be overriden
        """
        return True

    def _waitForEventTimeout(self, t):
        isSet = False
        while not self.mResponseEvent.is_set():
            isSet = self.mResponseEvent.wait(t)
            if not isSet:
                _logger.debug('response event timed out, so return out')
                break
        return isSet

    def _setEvent(self):
        self.mResponseEvent.set()

    def _clearEvent(self):
        self.mResponseEvent.clear()

    def _unflatten(self, value):
        ret = {}
        for k, v in value.items():
            keys = k.split('|')
            d = ret
            for key in keys[:-1]:
                if key not in d:
                    d[str(key)] = dict()
                d = d[str(key)]
            d[str(keys[-1])] = str(v)
        return ret


class CliViewer(BaseViewer):
    def __init__(self, confname=''):
        super().__init__(confname)
        self.mThread = None
        self.mCmd = {}
        self.mInputs = {}
        self.mResponse = {}
        self.__setupMsger()

    def __setupMsger(self):
        # check the DefConfig, and create mMsger as the dbus client
        conf = self.mDefConfig.getSettings(flatten=True)
        self.mMsger = DbusMessenger(conf, self.response)

    def __run(self):
        self.mThread = Thread(name='DBusThread', target=self.mMsger.run)
        self.mThread.start()

    def _parseCmd(self, params):
        # do the user commands checking here, and convert it into proper
        # recognizable dictionary to send to the dbus server
        self.mCmd.clear()

        if 'cmd' in params.keys():
            # FORMAT for server parsing dictionary
            # {cmd: {options}}
            if 'verbose' in params and params.pop('verbose'):
                params.update({'verbose': 'True'})
            else:
                params.update({'verbose': 'False'})

            if params['cmd'] is None:
                params.pop('cmd')

            #self.mCmd.update({params.pop('cmd'): params})
            self.mCmd.update(params)
        if len(self.mCmd) > 0:
            return True
        else:
            return False

    def _isStillProcessing(self):
        status = {}
        status.update(self._unflatten(self.mMsger.getStatus()))
        _logger.info('Job Status: {}'.format(status))
        if 'status' in status and status['status'] == 'processing':
            return True
        return False

    def _parseResult(self, result = None):
        if result:
            self.__dump(result)
        else:
            self.__dump(self.mResponse)

    def _preExec(self):
        """
        Override BaseView::_preExec()
        """
        if 'cmd' in self.mCmd and self.mCmd['cmd'] == 'stop':
            # use interrupt
            return self.mMsger.setInterrupt(self.mCmd)
        return True

    def _mainExec(self):
        """
        Override BaseViewer::_mainExec()
        """
        try:
            if isinstance(self.mCmd, dict):
                # clear the event before sending message over to dbus
                self._clearEvent()
                _logger.debug('send cmd via DBus')
                self.mMsger.sendMsg(self.mCmd)
                return True
            else:
                raise TypeError('cmd must be in a dictionary format')
        except Exception as ex:
            _logger.error('Error: {}'.format(ex))
        return False

    def _postExec(self):
        """
        Override BaseViewer::_postExec()
        """
        while True:
            # loop to wait for dbus response
            # wait for dbus server response for 25 seconds, same as DBus timeout
            self._waitForEventTimeout(1)
            if self.mResponseEvent.is_set():
                # handle what is received from the (dbus) server after Response Event is set
                # The server will signal a 'pending' response first.
                # Then a 'processing' response
                # and finally a 'success' or a 'failure' response
                if 'status' in self.mResponse:
                    if self.mResponse['status'] == 'pending':
                        # clear the event and wait until server send another response with status==processing
                        _logger.debug('status just becomes pending')
                        self._clearEvent()
                        continue
                    elif self.mResponse['status'] == 'processing':
                        # keep getting results after it becomes 'processing'
                        # and until status in success or failure, so don't clear the event
                        # but continue the loop to come back here again
                        _logger.debug('status just becomes processing')
                        self._clearEvent()
                        continue
                    else:
                        if self._isStillProcessing():
                            _logger.debug("event is set, but still processing")
                            self._parseResult(self._unflatten(self.mMsger.getResult()))
                            self._clearEvent()
                            continue
                        else:
                            # get and parse the result, and break out of loop
                            if self.mResponse['status'] == 'success':
                                _logger.debug("status just become success, so parse result")
                                self._parseResult()
                            else:
                                # idle, pending, processing, failure, etc.
                                _logger.debug("status just becomes {}, so get and parse result".format(self.mResponse['status']))
                                self._parseResult(self._unflatten(self.mMsger.getResult()))
                            break
            else:
                if 'status' in self.mResponse:
                    _logger.debug("Waiting for server response timed out. status: {}".format(self.mResponse['status']))
                    if self.mResponse['status'] == 'processing':
                        self._parseResult(self._unflatten(self.mMsger.getResult()))
                        self._clearEvent()
                        continue

    def __dump(self, value):
        for k in value.keys():
            if isinstance(value[k], dict):
                self.__dump(value[k])
            else:
                _logger.info('{:>24.24} {}'.format(k.strip(), value[k].strip().replace('\n', ' ')))

    def __getUserInput(self, prompt):
        return input(prompt)

    def getResult(self):
        return self.mResponse

    def queryResult(self):
        return self.mMsger.getResult()

    def request(self, arguments):
        """
        Handles command requests from the passed in arguments
        """
        params = {}
        params.update(arguments)
        # run the client signal handler, i.e. dbus response, on a separate thread
        self.__run()
        # execute parsed commands
        if self._parseCmd(params):
            if (self._preExec()):
                if (self._mainExec()):
                    self._postExec()
        # stop the messenger thread loop, and join the thread
        self.mMsger.stop()
        self.mThread.join()

    def response(self, response):
        """
        Callback to be called from the DBus Client's signal handler
        update the server response and set the response event before return out
        """
        self.mResponse.clear()
        self.mResponse.update(self._unflatten(response))
        self._setEvent()



if __name__ == "__main__":
    fmtr = logging.Formatter('%(asctime)s %(name)-12s (%(threadName)-10s):%(levelname)-8s %(message)s', datefmt='%m-%d %H:%M')
    hdlr = logging.FileHandler('/tmp/installer_cli.log')
    hdlr.setFormatter(fmtr)
    hdlr.setLevel(logging.DEBUG)
    _logger.addHandler(hdlr)
    # define a console handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    consolefmtr = logging.Formatter('%(name)-12s: (%(threadName)-10s):%(levelname)-8s %(message)s')
    console.setFormatter(consolefmtr)
    _logger.addHandler(console)

    def QueryTargetType(tgtstr):
        def CheckUrl(url):
            try:
                result = urlparse(url)
                return True if all([result.scheme, result.netloc]) else False
            except:
                return False

        supported_targets = ['emmc', 'sdcard', 'hd', 'som']
        if any(s == tgtstr for s in supported_targets):
            return tgtstr
        else:
            if CheckUrl(tgtstr):
                # --target can be a valid URL host
                return tgtstr
            elif tgtstr == uname()[1]:
                # --target can be the hostname of the local machine
                return tgtstr
            else:
                raise argparse.ArgumentTypeError('Invalid Host URL')

    def QueryLocationType(locstr):
        supported_locs = ['all', 'spl', 'bootloader', \
                          'controller', 'disk', 'partition', \
                          'bus', 'device', 'sensor', 'connection', \
                          'kernel', 'dtb', 'rootfs', 'os', 'cpu', 'form', 'baseboard']
        if any(s == locstr for s in supported_locs):
            return locstr
        else:
            if locstr.startswith('/') and locstr.endswith('/'):
                return locstr
            elif locstr.startswith('/') and locstr.endswith('xz'):
                return locstr
            else:
                raise argparse.ArgumentTypeError('Invalid Location Directory')

    def QRCodeModeType(modestr):
        supported_modes = ['numeric', 'kanji', 'binary', 'alphanumeric']
        if any(s == modestr for s in supported_modes):
            return modestr
        else:
            raise argparse.ArgumentTypeError('Invalid QRCode mode, must be numeric | kanji | binary | alphanumeric')

    def QRCodeErrLevel(lvlstr):
        supported_lvls = ['L', 'M', 'Q', 'H']
        if any(s == lvlstr for s in supported_lvls):
            return lvlstr
        else:
            raise argparse.ArgumentTypeError('Invalid QRCode error level, must be L | M | Q | H')

    import argparse
    parser = argparse.ArgumentParser(description='Technexion Installer Program: CLI')
    subparsers = parser.add_subparsers(dest='cmd', help='commands')

    ############################################################################
    # info commands
    # 'target', 'location'
    ############################################################################
    info_parser = subparsers.add_parser('info', help='information queries')
    info_parser.add_argument('-t', '--target', type=QueryTargetType, \
                             action='store', dest='target', default='emmc', \
                             help='Specify target storage media, choices are: \
                                 [emmc, sdcard, hd, or a valid web host URL]')
    info_parser.add_argument('-l', '--location', type=QueryLocationType, \
                             action='store', dest='location', default='all', \
                             help='Information of target storage media, choices are: \
                                 [all, spl, bootloader, controller, disk, partition, \
                                 bus, device, sensor, connection, kernel, dtb, rootfs, \
                                 os, or a valid URL directory]')
    ############################################################################
    # read commands
    # 'src_filename', src_start_sector, src_total_sectors, chunk_size
    ############################################################################
    read_parser = subparsers.add_parser('read', help='read src file and present read data')
    read_parser.add_argument('-s', '--source-filename', dest='src_filename', \
                              action='store', metavar='FILENAME', \
                              help='Specify source storage media')
    read_parser.add_argument('-f', '--src-start-sector', dest='src_start_sector', \
                              action='store', default='0', \
                              help='Specify starting sector (512 bytes/sector) on the source storage media')
    read_parser.add_argument('-n', '--num-of-chunks', dest='num_chunks', \
                              action='store', default='-1', \
                              help='Specify total number of chunks to read')
    read_parser.add_argument('-c', '--chunk-size', dest='chunk_size', \
                              action='store', default='-1', \
                              help='Specify the chunk size (or sector size) in bytes to read')
    read_parser.add_argument('-i', '--coding', dest='coding', default='no', \
                              action='store', choices=('no', 'b64', 'rle'), \
                              help='Specify the coding to return the read data')
    ############################################################################
    # write commands
    # 'tgt_filename', tgt_start_sector, tgt_total_sectors, chunk_size
    ############################################################################
    write_parser = subparsers.add_parser('write', help='write data to target file')
    write_parser.add_argument('-t', '--target-filename', dest='tgt_filename', \
                              action='store', metavar='FILENAME', \
                              help='Specify target storage media')
    write_parser.add_argument('-b', '--target-start-sector', dest='tgt_start_sector', \
                              action='store', default='0', \
                              help='Specify starting sector (512 bytes/sector) on the target storage media')
    write_parser.add_argument('-d', '--target-chunk-data', dest='tgt_data', \
                              action='store', default='', \
                              help='Specify the data to write to the target file/storage media')
    write_parser.add_argument('-c', '--chunk-size', dest='chunk_size', \
                              action='store', default='-1', \
                              help='Specify the chunk size (or sector size) in bytes to write')
    write_parser.add_argument('-i', '--coding', dest='coding', default='no', \
                              action='store', choices=('no', 'rle'), \
                              help='Specify the coding of the written data')
    ############################################################################
    # flash commands
    # 'src_filename', 'tgt_filename', src_start_sector, tgt_start_sector, src_total_sectors
    ############################################################################
    flash_parser = subparsers.add_parser('flash', help='flash local file to local storage media')
    flash_parser.add_argument('-t', '--target-filename', dest='tgt_filename', \
                              action='store', metavar='FILENAME', \
                              help='Specify target storage media')
    flash_parser.add_argument('-b', '--target-start-sector', dest='tgt_start_sector', \
                              action='store', default='0', \
                              help='Specify starting locations on the target storage media')
    flash_parser.add_argument('-s', '--source-filename', dest='src_filename', \
                              action='store', metavar='FILENAME', \
                              help='Specify source storage media')
    flash_parser.add_argument('-f', '--src-start-sector', dest='src_start_sector', \
                              action='store', default='0', \
                              help='Specify starting locations on the source storage media')
    flash_parser.add_argument('-n', '--total-sectors', dest='src_total_sectors', \
                              action='store', default='-1', \
                              help='Specify total number of sectors (512 bytes/sector) to copy')
    flash_parser.add_argument('-c', '--chunk-size', dest='chunk_size', \
                              action='store', default='-1', \
                              help='Specify the chunk size (sector size) in bytes to copy')
    ############################################################################
    # qrcode commands
    # 'dl_url', 'tgt_filename', receiver, lvl, mode
    ############################################################################
    qrcode_parser = subparsers.add_parser('qrcode', help='get the qrcode of the download file image info')
    qrcode_parser.add_argument('-u', '--download-url', dest='dl_url', \
                              action='store', metavar='URL', type=str, \
                              help='Specify download url of the xz file')
    qrcode_parser.add_argument('-t', '--target-filename', dest='tgt_filename', \
                              action='store', metavar='FILENAME', type=str, \
                              help='Specify target storage media')
    qrcode_parser.add_argument('-i', '--image-file', dest='img_filename', \
                              action='store', type=str, \
                              help='Specify the svg file_name to save')
    qrcode_parser.add_argument('-r', '--receiver', dest='receiver', \
                              action='store', default='', metavar='MAILTO', type=str, \
                              help='Specify receiver email address')
    qrcode_parser.add_argument('-m', '--encode-mode', dest='mode', \
                              action='store', default='binary', type=QRCodeModeType, \
                              help='Specify encoding mode for qrcode')
    qrcode_parser.add_argument('-l', '--error-level', dest='lvl', \
                              action='store', default='H', type=QRCodeErrLevel, \
                              help='Specify error level for qrcode')
    ############################################################################
    # config commands
    # 'load'/'save' subcommand with required 'configfile' argument
    ############################################################################
    config_parser = subparsers.add_parser('config', help='Save/Load configuration or configure mmc/nic')
    config_subparser = config_parser.add_subparsers(dest='subcmd', help='sub configuration command')
    config_subloadparser = config_subparser.add_parser('load', help="Load the configuration file")
    config_subloadparser.add_argument('configfile', metavar='FILENAME', action='store', help='Specify the configuration file')
    config_subsaveparser = config_subparser.add_parser('save', help="Save the configuration file")
    config_subsaveparser.add_argument('configfile', metavar='FILENAME', action='store', help='Specify the configuration file')
    #config_parser.add_argument('subcmd', choices=('load', 'save'), default='load', action='store', help='Load/Save the configuration')
    #config_parser.add_argument('-c', '--config-file', dest='configfile', action='store', metavar='FILENAME', help='Specify the configuration file')
    #config_parser.add_argument('-t', '--target-device', dest='target', choices=('mmc', 'i2c', 'gpio'), default='mmc', action='store', help='Specify target device to configure, choices are: [mmc, i2c, gpio, ...]')
    #config_parser.add_argument('-l', '--location', dest='location', default='/dev/mmcblk2', action='store', help='Specify the mmc dev path')
    ############################################################################
    # 'mmc' 'target' subcommands with following syntax
    # python3 view.py {'config' 'mmc' -c 'bootpart' -s 'enable', -n 1, -k 1, -l '/dev/mmcblk2'}
    # param = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', 'config_action': 'enable',
    #          'boot_part_no': '1', 'send_ack': '1', 'target': '/dev/mmcblk2'}
    ############################################################################
    config_submmcparser = config_subparser.add_parser('mmc', help='Specify MMC configure settings')
    config_submmcparser.add_argument('-c', '--config-opt', dest='config_id', \
                                     metavar='CONFIG_OPTION_NAME', action='store', \
                                     help='Specify the mmc configuration option')
    config_submmcparser.add_argument('-s', '--config-action', dest='config_action', \
                                     metavar='CONFIG_ACTION', action='store', \
                                     help='Specify the mmc action for the configuration option')
    config_submmcparser.add_argument('-n', '--boot-partition-number', dest='boot_part_no', \
                                     metavar='BOOT_OPTION_NUMBER', default='1', \
                                     action='store', type=str, help='Specify the mmc boot partition number')
    config_submmcparser.add_argument('-k', '--send-acknowledge', dest='send_ack', \
                                     metavar='SEND_ACK', default='1', action='store', \
                                     help='Specify whether to send acknowledge or not {0, 1}')
    config_submmcparser.add_argument('target', metavar='TARGET_MMC_NODEPATH', action='store', \
                                     help='Specify the mmc device path to configure')
    ############################################################################
    # 'nic' subcommand with required 'target' argument, others are options
    # python3 view.py {'config' 'nic' -c 'ifflags' -s 'get' enp3s0'}
    # param = {'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifflags', 'config_action': 'get', 'target': 'enp3s0'}
    ############################################################################
    config_subnicparser = config_subparser.add_parser('nic', help='Specify network configure settings')
    config_subnicparser.add_argument('-c', '--config-opt', dest='config_id', \
                                     metavar='CONFIG_NAME', action='store', \
                                     help='Specify the network configuration option')
    config_subnicparser.add_argument('-s', '--config-action', dest='config_action', \
                                     metavar='CONFIG_ACTION', action='store', \
                                     help='Specify the network configure action for the configuration option')
    config_subnicparser.add_argument('-d', '--config-data', dest='config_data', \
                                     metavar='CONFIG_DATA', action='store', default='', \
                                     help='Specify the network configuration data')
    config_subnicparser.add_argument('target', metavar='TARGET_NIC_IFNAME', action='store', \
                                     nargs='?', default='any', \
                                     help='Specify the nic device path to configure')
    ############################################################################
    # verify commands
    ############################################################################

    ############################################################################
    # connect commands
    ############################################################################
    connect_parser = subparsers.add_parser('connect', help='connect serial, web, mass storage, serial + mass storage or multi')
    connect_parser.add_argument('-t', dest='type', choices=('serial', 'web', 'storage', 'serialstorage', 'multi'), \
                                action='store', default='cli', \
                                help='connect serial, web or mass storage')
    connect_parser.add_argument('-s', '--source-filename', dest='src_filename', \
                              action='store', metavar='FILENAME', default='', \
                              help='Specify source storage media to use as mass storage device')
    ############################################################################
    # disconnect commands
    ############################################################################
    disconnect_parser = subparsers.add_parser('disconnect', help='disconnect, serial, web, mass storage, serial + mass storage or multi')
    disconnect_parser.add_argument('-t', dest='type', choices=('serial', 'web', 'storage', 'serialstorage', 'multi'), \
                                   action='store', default='serial', \
                                   help='disconnect serial, web or mass storage')
    ############################################################################
    # start commands
    # 'start' command to start client/server
    ############################################################################
#     start_parser = subparsers.add_parser('start', help='start client/server')
#     start_parser.add_argument('-t', dest='type', choices=('srv', 'cli'), \
#                               default='cli', help='start the server, client')
    ############################################################################
    # stop commands
    # 'stop' command to stop client/server, and interrupt long running jobs
    ############################################################################
    stop_parser = subparsers.add_parser('stop', help='stop server, client, or jobs')
    stop_parser.add_argument('-t', dest='type', choices=('srv', 'cli', 'job'), \
                             action='store', default='job', \
                             help='stop the server, client, or job')
    ############################################################################
    # upload commands
    ############################################################################

    ############################################################################
    # download commands
    # 'dl_module',  'dl_baseboard', 'dl_os', 'dl_version', 'dl_display', \
    # 'dl_filetype', 'dl_host', 'dl_protocol', 'tgt_filename'
    ############################################################################
    dl_parser = subparsers.add_parser('download', help='download rescue files and flash to local storage media')
    dl_parser.add_argument('-t', '--target-filename', dest='tgt_filename', \
                           action='store', metavar='FILENAME', \
                           help='Specify target storage media')
    dl_parser.add_argument('-b', '--target-start-sector', dest='tgt_start_sector', \
                           type=str, action='store', default='0', \
                           help='Specify starting sector on the target storage media')
    dl_parser.add_argument('-p', '--host-protocol', dest='dl_protocol', choices=('http', 'ftp'), \
                           action='store', default='http', \
                           help='Specify host protocol to use for downloads')
    dl_parser.add_argument('-s', '--host-name', dest='dl_host', \
                           action='store', metavar='HOST', default='rescue.technexion.net', \
                           help='Specify host/URL to download from')
    dl_parser.add_argument('-m', '--module', dest='dl_module', type=str, \
                           choices=('edm1_cf_imx6all', 'pico-imx6', 'pico-imx6ul', \
                                    'pico-imx7', 'pico_imx6', 'tek3_imx6', \
                                    'tep5-imx6', 'tep5_imx6'), \
                           action='store', default=argparse.SUPPRESS, \
                           help='Specify the module of target device')
    dl_parser.add_argument('-d', '--baseboard', dest='dl_baseboard', \
                           choices=('dwarf', 'hobbit', 'nymph', 'fairy', 'pi', \
                                    'toucan', 'tek3', 'tep5'), \
                           action='store', default=argparse.SUPPRESS, \
                           help='Specify the baseboard of target device')
    dl_parser.add_argument('-o', '--operating-system', dest='dl_os', \
                           choices=('ubuntu', 'android', 'yocto'),\
                           action='store', default=argparse.SUPPRESS, \
                           help='Specify the operating system to download for target device')
    dl_parser.add_argument('-v', '--os-version', dest='dl_version', type=str, \
                           action='store', default=argparse.SUPPRESS, \
                           metavar='OS_VERSION', help='Specify the version of operating system to download')
    dl_parser.add_argument('-y', '--display', dest='dl_display', \
                           choices=('lcd800x480', 'lvds1024x600', '070', '050', \
                                    'vga', 'hdmi'), \
                           action='store', default=argparse.SUPPRESS, \
                           help='Specify the display version of target device')
    dl_parser.add_argument('-e', '--file-extension', dest='dl_filetype', \
                           choices=('xz', 'imx', 'img', 'bin'), \
                           action='store', default=argparse.SUPPRESS, \
                           help='Specify the file extension of the download file')
    dl_parser.add_argument('-f', '--src-start-sector', dest='src_start_sector', \
                           type=str, action='store', default='0', \
                           help='Specify starting locations on the source storage media')
    dl_parser.add_argument('-n', '--src-total-sectors', dest='src_total_sectors', \
                           type=str, action='store', default='-1', \
                           help='Specify total number of sectors to download')
    dl_parser.add_argument('-c', '--chunk-size', dest='chunk_size', type=str, \
                           action='store', default='65536', \
                           help='Specify the block size to read/write per I/O')
    dl_parser.add_argument('-u', '--url', dest='dl_url', default=argparse.SUPPRESS, \
                           action='store', metavar='DOWNLOAD_URL', \
                           help='Specify the proper URL of the download file')
    ############################################################################
    # install commands - to be implemented
    ############################################################################

    ############################################################################
    # Global Options
    ############################################################################
    parser.add_argument('--verbose', dest='verbose', action='store_true', default=False, \
                        help='Show more information')
    parser.add_argument('--version', action='version', version='%(prog)s 2018.6.30.2')
    args = parser.parse_args() # by default, arguments taken from sys.argv[1:]
    if args.verbose:
        _logger.setLevel(logging.DEBUG)
    else:
        _logger.setLevel(logging.INFO)

    cli = CliViewer()
    _logger.info('Parsed arguments: {}'.format(args))
    cli.request(args.__dict__)
    exit(0)
