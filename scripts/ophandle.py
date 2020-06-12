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

# operation handle:
# This library combines different task based models into useful jobs execution
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import logging
import urllib.parse
from defconfig import DefConfig
from threading import Thread, Event, RLock
from model import CopyBlockActionModeller, \
                  QueryMemActionModeller, \
                  QueryFileActionModeller, \
                  QueryBlockDevActionModeller, \
                  WebDownloadActionModeller, \
                  QueryWebFileActionModeller, \
                  QueryLocalFileActionModeller, \
                  ConfigMmcActionModeller, \
                  DriverActionModeller, \
                  ConfigNicActionModeller, \
                  CheckBlockActionModeller, \
                  QRCodeActionModeller

_logger = logging.getLogger(__name__)

class BaseOperationHandler(object):
    """
    Base Operation Handler that handles the Action Models and further IO actions
    """

    def __init__(self, cbUserRequest):
        super().__init__()
        # setup the callback function for further user decisions
        self.mUserRequestHandler = cbUserRequest if callable(cbUserRequest) else None
        self.mActionModellers = []
        self.mActionParam = {}
        self.mRunningModel = None
        self.mResult = {}
        self.mStatus = {}
        self.mEvent = Event()
        self.mEvent.set()
        self.mReentryLock = RLock()

    def waitEvent(self):
        _logger.info('wait for handler event to set')
        self.mReentryLock.acquire()
        self.mEvent.wait()
        self.mEvent.clear()
        self.mReentryLock.release()
        _logger.info('clear handler event to go ahead')

    def setEvent(self):
        _logger.info('set handler event')
        self.mEvent.set()

    def getStatus(self):
        _logger.info('return handler status: {}'.format(self.mStatus))
        return self.mStatus

    def getResult(self):
        # self.mResult would only contain success results from __run()
        # need to find out which of model is running, and extract status from it.
        if self.mRunningModel:
            self.mResult.update(self.mRunningModel.getResult())
            _logger.info('return current result: {} current status: {}'.format(self.mResult, self.mStatus))
        return self.mResult

    def __run(self):
        successFlag = False
        for model in self.mActionModellers:
            # get the current running model
            self.mRunningModel = model
            # append the executed action models to the recover list
            if model.performAction():
                # update successful result per model (may have more than 1 success
                self.mResult.update(model.getResult())
                successFlag = True
        # no more running model
        self.mRunningModel = None
        # check if any of the model successfully execute the actions
        if successFlag:
            self.mStatus.update({'status': 'success'})
            _logger.info('call performAction success: {}'.format(self.mStatus))
            return True
        else:
            # when all model fail, update status to failure
            self.mStatus.update({'status': 'failure'})
            _logger.info('call performAction failed for all models: {}'.format(self.mStatus))
            return False

    def performOperation(self, OpParams):
        try:
            # set the status to processing first, it will be overridden if success or failure
            self.mActionParam.clear()
            self.mResult.clear()
            self.mStatus.clear()
            self.mStatus.update({'status': 'processing'}, **OpParams)

            # clear old action models for next command
            if len(self.mActionModellers): del self.mActionModellers[:]
            # setup necessary models to handle the command
            if self._parseParam(OpParams):
                if self._setupActions():
                    # if successfully setup an action model, do the work, else exception
                    if self.__run():
                        return True
        except Exception as ex:
            # handles all lower level exceptions here, except IS NOT raised further to uppre level.
            _logger.error('{} handler performOperation error: {}'.format(type(self).__name__, ex))
            self.mStatus.update({'status': 'error', 'error': '{}'.format(ex)})
        return False

    def updateUserResponse(self, userInputs):
        try:
            # Store, Parse and Check the user inputs and pass them to models
            # after the user request returns by calling DBus I/F interrupt, check the user input
            parsedInputs = {}
            parsedInputs.update(self._parseUserResponse(userInputs))
            if parsedInputs:
                _logger.debug("Has valid user inputs, so interrupts model accordingly")
                # Retry or Recover or Interrupt
                if self.__interruptOperation(parsedInputs):
                    return True
        except Exception as ex:
            # handles all lower level exceptions here.
            _logger.error('{} handler updateUserResponse error: {}'.format(type(self).__name__, ex))
            self.mStatus.update({'status': 'error', 'error': '{}'.format(ex)})
        else:
            return False

    def __interruptOperation(self, parsedInputs):
        # set whatever actions/flags needed to set in all the models.
        # so the actions/flags can be checked within the WorkerThread and
        # terminate gracefully.
        try:
            if self.mRunningModel:
                if callable(self.mRunningModel.interruptAction):
                    self.mRunningModel.interruptAction(parsedInputs)
                    return True
        except:
            raise
        else:
            return False
        finally:
            self.mStatus.update({'status': 'interrupted', 'parsed_input': '{}'.format(parsedInputs)})

    def isOpSupported(self, OpParams):
        """
        To be overridden
        """
        return False

    def _setupActions(self):
        """
        To be overridden
        """
        return False

    def _parseParam(self, OpParams):
        """
        To be overridden
        """
        return False

    def _parseUserResponse(self, userInputs):
        """
        To be overridden
        """
        return userInputs



class ReadWriteOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams:
            if OpParams['cmd'] == 'read' or OpParams['cmd'] == 'write':
                return True
        return False

    def _setupActions(self):
        # setup "read/write" cmd operations
        if self.mActionParam:
            self.mActionModellers.append(BasicBlockActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(type(self).__name__, OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            self.mActionParam['chunk_size'] = int(OpParams['chunk_size']) if 'chunk_size' in OpParams else -1
            self.mActionParam['coding'] = OpParams['coding'] if 'coding' in OpParams else None
            if 'src_filename' in OpParams:
                # check for source start sector, number of chunks
                self.mActionParam['src_filename'] = str(OpParams['src_filename'])
                self.mActionParam['src_start_sector'] = int(OpParams['src_start_sector']) if 'src_start_sector' in OpParams else 0
                self.mActionParam['num_chunks'] = int(OpParams['num_chunks']) if 'num_chunks' in OpParams else -1
                _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
                return True
            elif 'tgt_filename' in OpParams:
                # check for target start sector, and data to be written
                self.mActionParam['tgt_filename'] = str(OpParams['tgt_filename'])
                self.mActionParam['tgt_start_sector'] = int(OpParams['tgt_start_sector']) if 'tgt_start_sector' in OpParams else 0
                if 'tgt_data' in OpParams:
                    if isinstance(OpParams['tgt_data'], str):
                        self.mActionParam['tgt_data'] = OpParams['tgt_data'][:]
                    elif isinstance(OpParams['tgt_data'], bytes):
                        self.mActionParam['tgt_data'] = OpParams['tgt_data'].decode()
                    else:
                        return False
                else:
                    return False
                _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
                return True
        return False



class FlashOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)
        self.mArgs = ['src_filename', 'tgt_filename']

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams:
            if OpParams['cmd'] == 'flash':
                return True
        return False

    def _setupActions(self):
        # setup "flash" cmd operations
        if self.mActionParam:
            self.mActionModellers.append(CopyBlockActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(self, OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            if all(s in OpParams for s in self.mArgs):
                # check for copy from source file to target file
                self.mActionParam['src_filename'] = str(OpParams['src_filename'])
                self.mActionParam['tgt_filename'] = str(OpParams['tgt_filename'])
                if 'src_start_sector' in OpParams:
                    self.mActionParam['src_start_sector'] = int(OpParams['src_start_sector'])
                else:
                    self.mActionParam['src_start_sector'] = 0
                if 'tgt_start_sector' in OpParams:
                    self.mActionParam['tgt_start_sector'] = int(OpParams['tgt_start_sector'])
                else:
                    self.mActionParam['tgt_start_sector'] = 0
                if 'src_total_sectors' in OpParams:
                    self.mActionParam['src_total_sectors'] = int(OpParams['src_total_sectors'])
                else:
                    self.mActionParam['src_total_sectors'] = -1
                if 'chunk_size' in OpParams:
                    self.mActionParam['chunk_size'] = int(OpParams['chunk_size'])
                else:
                    self.mActionParam['chunk_size'] = -1
                _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
                return True
        else:
            return False



class QRCodeOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)
        self.mArgs = ['dl_url', 'tgt_filename']

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams:
            if OpParams['cmd'] == 'qrcode':
                return True
        return False

    def _setupActions(self):
        # setup "qrcode" cmd operations
        if self.mActionParam:
            self.mActionModellers.append(QRCodeActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(type(self).__name__, OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            if all(s in OpParams for s in self.mArgs):
                # check for copy from source file to target file
                self.mActionParam['dl_url'] = str(OpParams['dl_url'])
                self.mActionParam['tgt_filename'] = str(OpParams['tgt_filename'])
                if 'receiver' in OpParams and len(OpParams['receiver']):
                    self.mActionParam['mailto'] = str(OpParams['receiver'])
                if 'lvl' in OpParams:
                    self.mActionParam['errlvl'] = str(OpParams['lvl'])
                if 'mode' in OpParams:
                    self.mActionParam['encmode'] = str(OpParams['mode'])
                if 'img_filename' in OpParams:
                    self.mActionParam['img_filename'] = str(OpParams['img_filename'])
                _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
                return True
        else:
            return False



class InfoOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)
        self.mArgs = ['target', 'location']
        self.mConf = self.mUserRequestHandler('setting') if callable(self.mUserRequestHandler) else {}
        self.mHosts = []

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams:
            if OpParams['cmd'] == 'info':
                return True
        return False

    def _setupActions(self):
        # setup "info" cmd operations
        if self.mActionParam:
            self.mActionModellers.append(QueryBlockDevActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(QueryWebFileActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(QueryFileActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(QueryLocalFileActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(QueryMemActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(type(self).__name__, OpParams))
        self.mActionParam.clear()

        if self.mHosts == [] and self.mConf:
            # gets rescue hosts from installer.xml config
            if isinstance(self.mConf.getSettings('rescue')['rescue']['host'], list):
                self.mHosts = self.mConf.getSettings('rescue')['rescue']['host']
            else:
                self.mHosts = [self.mConf.getSettings('rescue')['rescue']['host']]

        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            for k, v in OpParams.items():
                # target options
                if k==self.mArgs[0] and v=='emmc':
                    # check for the correct /dev/mmcblk[x]p[x] path and set it
                    self.mActionParam['tgt_type'] = 'mmc'
                elif k==self.mArgs[0] and v=='sdcard':
                    # check for the correct /dev/mmcblk[x]p[x] path and set it
                    self.mActionParam['tgt_type'] = 'sd'
                elif k==self.mArgs[0] and v=='hd':
                    # check for the correct /dev/sd[x] path and set it
                    self.mActionParam['tgt_type'] = 'sd'
                elif k==self.mArgs[0] and v=='mem':
                    self.mActionParam['tgt_type'] = 'mem'
                elif k==self.mArgs[0] and v=='som':
                    self.mActionParam['src_filename'] = '/proc/device-tree/model'
                    self.mActionParam['re_pattern'] = '\w+ (\w+)-([imx|IMX]\w+) .* (\w+) \w*board'
                elif k==self.mArgs[0] and v=='cpu':
                    self.mActionParam['src_filename'] = '/sys/devices/soc0/soc_id'
                    self.mActionParam['re_pattern'] = '^(.*)[\s|\n]$'
                elif k==self.mArgs[0] and v=='form':
                    self.mActionParam['src_filename'] = '/proc/device-tree/model'
                    self.mActionParam['re_pattern'] = '\w+ (\w+)-\w+'
                elif k==self.mArgs[0] and v=='baseboard':
                    self.mActionParam['src_filename'] = '/proc/device-tree/model'
                    self.mActionParam['re_pattern'] = '.* (\w+) \w*board'
                elif k==self.mArgs[0] and v.startswith('http'):
                    # check for the correct url, e.g. http://xxx and set it
                    self.mActionParam['host_name'] = v # web host address
                elif k==self.mArgs[0] and v == socket.gethostname():
                    # check for local_fs, which client will send as hostname()
                    self.mActionParam['local_fs'] = v # local file system
                elif k==self.mArgs[0] and v != socket.gethostname() and \
                     'msger_type' in OpParams and OpParams['msger_type'] == 'serial':
                    self.mActionParam['local_fs'] = v
                # location options
                elif k==self.mArgs[1] and v=='spl':
                    self.mActionModellers['dst_pos'] = 2 # sector 2 for spl
                elif k==self.mArgs[1] and v=='bootloader':
                    self.mActionParam['dst_pos'] = 2 # image for android uboot.imx
                elif k==self.mArgs[1] and v=='controller':
                    self.mActionParam['dst_pos'] = 'c' # controller
                elif k==self.mArgs[1] and v=='disk':
                    self.mActionParam['dst_pos'] = 'd' # disk
                elif k==self.mArgs[1] and v=='partition':
                    self.mActionParam['dst_pos'] = 'p' # partition
                elif k==self.mArgs[1] and v=='file':
                    self.mActionParam['src_filename'] = OpParams['target']
                    self.mActionParam['get_stat'] = True;
                elif k==self.mArgs[1] and v.startswith('/') and v.endswith('/'):
                    self.mActionParam['src_directory'] = v # directory/folder
                    for host in self.mHosts:
                        if host['name'] in OpParams['target']:
                            self.mActionParam['host_dir'] = host['path']
                elif k==self.mArgs[1] and v.startswith('/') and v.endswith('xz'):
                    self.mActionParam['src_directory'] = v # directory/folder
                    for host in self.mHosts:
                        if host['name'] in OpParams['target']:
                            self.mActionParam['host_dir'] = host['path']
                elif k==self.mArgs[1] and v.endswith('/'):
                    self.mActionParam['src_directory'] = v # local directory
                elif k==self.mArgs[1] and v in ['total', 'available', 'percent', 'used', \
                                         'free', 'active', 'inactive', 'buffers', \
                                         'cached', 'shared', 'all']:
                    self.mActionParam['mem_type'] = v

            if 'tgt_type' in self.mActionParam and 'dst_pos' not in self.mActionParam:
                self.mActionParam['dst_pos'] = -1

        # determine if we have parsed the info command successfully
        if all(s in self.mActionParam for s in ['tgt_type', 'dst_pos']):
            _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
            return True
        elif all(s in self.mActionParam for s in ['host_name', 'src_directory']):
            _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
            return True
        elif all(s in self.mActionParam for s in ['local_fs', 'src_directory']):
            _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
            return True
        elif all(s in self.mActionParam for s in ['src_filename', 'get_stat']):
            _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
            return True
        elif all(s in self.mActionParam for s in ['src_filename', 're_pattern']):
            _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
            return True
        else:
            return False



class DownloadOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)
        self.mArgs = ['dl_module',  'dl_baseboard', 'dl_os', 'dl_version', \
                           'dl_display', 'dl_filetype', 'dl_host', 'dl_protocol']

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams:
            if OpParams['cmd'] == 'download':
                return True
        return False

    def _setupActions(self):
        # setup "download" cmd operations
        if self.mActionParam:
            self.mActionModellers.append(WebDownloadActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(type(self).__name__, OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            if 'tgt_filename' in OpParams:
                self.mActionParam['tgt_filename'] = str(OpParams['tgt_filename'])
            else:
                self.mActionParam['tgr_filename'] = '/tmp/download.tmp'
            if 'tgt_start_sector' in OpParams:
                self.mActionParam['tgt_start_sector'] = int(OpParams['tgt_start_sector'])
            else:
                self.mActionParam['tgt_start_sector'] = 0
            if 'src_total_sectors' in OpParams:
                self.mActionParam['src_total_sectors'] = int(OpParams['src_total_sectors'])
            else:
                self.mActionParam['src_total_sectors'] = -1
            if 'chunk_size' in OpParams:
                self.mActionParam['chunk_size'] = int(OpParams['chunk_size'])

            if all(s in OpParams for s in self.mArgs):
                # check for download from web and flash to target file
                # check for copy from source file to target file
                # 'chunk_size': 65536, 'src_directory': '/pico-imx7/pi-050/',
                # 'src_filename': 'ubuntu-16.04.xz', 'host_name': 'rescue.technexion.net',
                # 'host_protocol': 'http', 'tgt_filename': 'ubuntu-16.04.img', 'tgt_start_sector': 0
                self.mActionParam['host_protocol'] = OpParams['dl_protocol']
                self.mActionParam['host_name'] = OpParams['dl_host']
                self.mActionParam['src_filename'] = str(OpParams['dl_os']) + '-' + \
                                                str(OpParams['dl_version']) + '.' + \
                                                str(OpParams['dl_filetype'])
                self.mActionParam['src_directory'] = str(OpParams['dl_module']) + '/' + \
                                                 str(OpParams['dl_baseboard']) + '-' + \
                                                 str(OpParams['dl_display'])
                _logger.debug('{}: __parseParam: mActionParam: {}'.format(type(self).__name__, self.mActionParam))
                return True
            elif 'dl_url' in OpParams:
                urlobj = urllib.parse.urlparse(OpParams['dl_url'])
                self.mActionParam['host_protocol'] = urlobj.scheme
                self.mActionParam['host_name'] = urlobj.hostname
                self.mActionParam['host_port'] = urlobj.port
                self.mActionParam['src_filename'] = urlobj.path.split('/')[-1]
                self.mActionParam['src_directory'] = '/'.join(urlobj.path.split('/')[:-1])
                _logger.debug('{}: __parseParam: mActionParam: {}'.format(self, self.mActionParam))
                return True
        else:
            return False



class ConfigOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams and 'subcmd' in OpParams:
            if OpParams['cmd'] == 'config':
                if any(k in OpParams['subcmd'] for k in ['mmc', 'nic']):
                    return True
        return False

    def _setupActions(self):
        # setup "config" cmd operation:
        if self.mActionParam:
            self.mActionModellers.append(ConfigMmcActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(ConfigNicActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(type(self).__name__, OpParams))
        self.mActionParam.clear()
        # Parse the OpParams and Setup mActionParams
        # e.g. {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart',
        #       'config_setting': 'enable', 'boot_part_no': 1, 'send_ack': '1',
        #       'target': '/dev/mmcblk2'}
        if isinstance(OpParams, dict):
            # required params
            for k in ['subcmd', 'target', 'config_id', 'config_action']:
                if k in OpParams:
                    self.mActionParam.update({k: OpParams[k]})
            # optional params depending on config_id
            if OpParams['config_id'] == 'bootpart' and 'boot_part_no' in OpParams and 'send_ack' in OpParams:
                self.mActionParam.update({'boot_part_no': OpParams['boot_part_no'], 'send_ack': OpParams['send_ack']})
            elif OpParams['config_id'] == 'readonly' and 'boot_part_no' in OpParams:
                self.mActionParam.update({'boot_part_no': OpParams['boot_part_no']})

        # verify the ActionParam to pass to modeller
        if all(s in self.mActionParam for s in ['subcmd', 'target', 'config_id', 'config_action']):
            _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
            return True
        else:
            return False


class ConnectOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB, ConnectCB):
        super().__init__(UserRequestCB)
        self.mConnectCbHandler = ConnectCB

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams.keys() and 'type' in OpParams.keys():
            if OpParams['cmd'] in ['connect', 'disconnect'] and \
                OpParams['type'] in ['serial', 'web', 'storage', 'serialstorage', 'multi']:
                return True
        return False

    def _setupActions(self):
        # setup "config" cmd operation:
        if self.mActionParam:
            self.mActionModellers.append(DriverActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(self, OpParams))
        self.mActionParam.clear()
        # Parse the OpParams and Setup mActionParams
        # e.g. {'cmd': 'start', 'cmd': 'stop', 'type': 'serial | web | storage'}
        if isinstance(OpParams, dict):
            # required params
            for k in ['cmd', 'type']:
                if k in OpParams:
                    self.mActionParam.update({k: OpParams[k]})

            if 'src_filename' in OpParams and OpParams['src_filename'] != '':
                self.mActionParam.update({'src_filename': OpParams['src_filename']})

            if OpParams['type'] in ['serial', 'serialstorage', 'multi'] and \
                'mac_addr' in OpParams and len(OpParams['mac_addr'].split(':')) == 6:
                self.mActionParam.update({'mac_addr': OpParams['mac_addr']})

        # verify the ActionParam to pass to modeller
        if all(s in self.mActionParam for s in ['cmd', 'type']):
            _logger.debug('{}: __parseParam: mActionParam:{}'.format(self, self.mActionParam))
            if 'src_filename' in self.mActionParam:
                if 'mac_addr' in self.mActionParam:
                    if self.mActionParam['type'] in ['serial', 'serialstorage', 'multi']:
                        return True
                    else:
                        return False
                return True
        return False

    def performOperation(self, OpParams):
        """
        override performOperation
        """
        ret = False
        if callable(self.mConnectCbHandler):
            if OpParams['cmd'] == 'disconnect':
                _logger.debug('disconnect: callback to remove messenger before modprobe')
                self.mConnectCbHandler(OpParams)
            ret = super().performOperation(OpParams)
            if ret and OpParams['cmd'] == 'connect':
                _logger.debug('connect: callback to create messenger after modprobe')
                return self.mConnectCbHandler(OpParams)
        return ret



class CheckOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)
        self.mArgs = ['src_filename', 'tgt_filename']

    def isOpSupported(self, OpParams):
        # Check if cmd is supported
        if isinstance(OpParams, dict) and 'cmd' in OpParams:
            if OpParams['cmd'] == 'check':
                return True
        return False

    def _setupActions(self):
        # setup "flash" cmd operations
        if self.mActionParam:
            self.mActionModellers.append(CheckBlockActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        return False

    def _parseParam(self, OpParams):
        _logger.debug('{}: __parseParam: OpParams: {}'.format(self, OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            if all(s in OpParams for s in self.mArgs):
                # check for copy from source file to target file
                self.mActionParam['src_filename'] = str(OpParams['src_filename'])
                self.mActionParam['tgt_filename'] = str(OpParams['tgt_filename'])
                if 'src_start_sector' in OpParams:
                    self.mActionParam['src_start_sector'] = int(OpParams['src_start_sector'])
                if 'tgt_start_sector' in OpParams:
                    self.mActionParam['tgt_start_sector'] = int(OpParams['tgt_start_sector'])
                if 'total_sectors' in OpParams:
                    self.mActionParam['total_sectors'] = int(OpParams['total_sectors'])
                _logger.debug('{}: __parseParam: mActionParam:{}'.format(type(self).__name__, self.mActionParam))
                return True
        else:
            return False



if __name__ == "__main__":
    def opcb(req):
        conf = DefConfig()
        conf.loadConfig("/etc/installer.xml")
        if req == 'setting':
            print ('called back req:{} conf:{}'.format(req, conf))
            return conf

    import sys

    if sys.argv[1] == 'local':
        hdlr = FlashOperationHandler(opcb, use_thread=True)
        param = {'cmd': 'flash', 'src_filename': './test.bin', 'src_start_sector': 0, 'src_total_sectors': 64, 'tgt_filename': './target.bin', 'tgt_start_sector': 32}
    elif sys.argv[1] == 'som':
        hdlr = InfoOperationHandler(opcb)
        param = {'cmd': 'info', 'target': 'som'}
    elif sys.argv[1] == 'cpu':
        hdlr = InfoOperationHandler(opcb)
        param = {'cmd': 'info', 'target': 'cpu'}
    elif sys.argv[1] == 'form':
        hdlr = InfoOperationHandler(opcb)
        param = {'cmd': 'info', 'target': 'form'}
    elif sys.argv[1] == 'baseboard':
        hdlr = InfoOperationHandler(opcb)
        param = {'cmd': 'info', 'target': 'baseboard'}
    elif sys.argv[1] == 'web':
        hdlr = InfoOperationHandler(opcb)
        param = {'cmd': 'info', 'target': 'http://rescue.technexion.net', 'location': '/pico-imx6/'} #dwarf-hdmi/'}
    elif sys.argv[1] == 'fs':
        hdlr = InfoOperationHandler(opcb)
        param = {'cmd': 'info', 'target': 'PoMachine', 'location': '/home/po/Downloads/'} #dwarf-hdmi/'}
    elif sys.argv[1] == 'dl':
        hdlr = DownloadOperationHandler(opcb)
        # python3 view.py {download -u http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz -t ./ubuntu.img}
        param = {'cmd': 'download', 'dl_url': 'http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz', 'tgt_filename': './ubuntu.img'}
    elif sys.argv[1] == 'mmcconfig':
        hdlr = ConfigOperationHandler(opcb)
        # python3 view.py {'config' -t mmc -c 'bootpart' -i 'enable', -n 1, -k 1, -l '/dev/mmcblk2'}
        param = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', 'config_action': 'enable', 'boot_part_no': '1', 'send_ack': '1', 'target': '/dev/mmcblk2'}
    elif sys.argv[1] == 'mmcreadonly':
        hdlr = ConfigOperationHandler(opcb)
        # python3 view.py {'config' -t mmc -c 'bootpart' -i 'enable', -n 1, -k 1, -l '/dev/mmcblk2'}
        param = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', 'config_action': 'enable', 'boot_part_no': '1', 'target': '/dev/mmcblk2'}
    elif sys.argv[1] == 'nicifflag':
        hdlr = ConfigOperationHandler(opcb)
        # python3 view.py {'config' -t mmc -c 'bootpart' -i 'enable', -n 1, -k 1, -l '/dev/mmcblk2'}
        param = {'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifflags', 'config_action': 'get', 'target': 'enp3s0'}
    else:
        exit(1)

    if (hdlr.isOpSupported(param)):
        hdlr.performOperation(param)
    print(hdlr.getStatus())
    print(hdlr.getResult())
    exit(0)
