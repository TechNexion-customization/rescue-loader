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

# model:
# This library wraps input output objects and provides task based logic to
# operation handler
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import re
import os
import stat
import fcntl
import psutil
import array
import binascii
import base64
import hashlib
import platform
import pyudev
import socket
import struct
import subprocess
import signal
import logging
import pyqrcode
from html.parser import HTMLParser
from urllib.parse import urlparse
from defconfig import IsATargetBoard
from inputoutput import BlockInputOutput, FileInputOutput, BaseInputOutput, WebInputOutput

_logger = logging.getLogger(__name__)



class HtmlFileLinkParser(HTMLParser):
    """
    Html a href link parser, inherited from HTMLParser (framework)
    and only looks for sub-directory links as well as xz/txt files
    """
    def __init__(self, host, path):
        super().__init__()
        self.mHost = host
        self.mPath = path
        self.mTagFlag = False
        self.mLink = None
        self.mData = {}

    def handle_starttag(self, tag, attrs):
        if tag != 'a': return
        for name, value in attrs:
            if name == 'href':
                if value.endswith('xz') or value.endswith('.txt'):
                    self.mTagFlag = True
                    self.mLink = self.mHost + self.mPath + value
                elif (value.startswith('/') and value.endswith('/')):
                    self.mTagFlag = True
                    self.mLink = self.mHost + value
                elif (value.endswith('/')):
                    self.mTagFlag = True
                    self.mLink = self.mHost + self.mPath + value

    def handle_data(self, data):
        if self.mTagFlag:
            self.mData.update({data: self.mLink})

    def handle_endtag(self, tag):
        if tag != 'a': return
        self.mTagFlag = False



class BaseActionModeller(object):
    """
    Base Action Model for modelling actions to be taken from users commands
    """

    def __init__(self):
        super().__init__()
        self.mParam = {}
        self.mResult = {}
        self.mInterruptedFlag = False

    def checkInterruptAndExit(self):
        if self.mInterruptedFlag:
            raise Exception("Interrupted by User Request")

    def getResult(self):
        return self.mResult

    def setActionParam(self, param):
        if isinstance(param, dict):
            if len(param) > 0:
                self.mParam.clear()
                self.mParam.update(param)
                _logger.debug('{} - set mParam: {}'.format(type(self).__name__, self.mParam))
        else:
            raise ValueError('wrong action params')

    def performAction(self):
        self.mResult.clear()
        ret = False
        try:
            ret = self._preAction()
            _logger.debug('{} _preAction(): {}'.format(type(self).__name__, ret))
            if (ret):
                ret = self._mainAction()
                _logger.debug('{} _mainAction(): {}'.format(type(self).__name__, ret))
                if(ret):
                    ret = self._postAction()
                    _logger.debug('{} _postAction(): {}'.format(type(self).__name__, ret))
        except Exception as ex:
            _logger.error('{} performAction error: {}'.format(type(self).__name__, ex))
            ret = False
        finally:
            return ret

    def interruptAction(self, parsedInputs):
        # set the interrupted flag
        self.mInterruptedFlag = True

    def _preAction(self):
        """
        To be overriden
        """
        return True

    def _mainAction(self):
        """
        To be overriden
        """
        return True

    def _postAction(self):
        """
        To be overriden
        """
        return True



class BasicBlockActionModeller(BaseActionModeller):
    """
    Basic Block Action Model to read/write blocks to/from files/storage
    """

    def __init__(self):
        super().__init__()
        self.mIO = None
        self.mChunkSize = 0

    def _preAction(self):
        # setup the input/output objects
        # if no chunksize specified, set chunk_size to default 512 bytes
        if 'chunk_size' not in self.mParam or int(self.mParam['chunk_size']) < 0:
            self.mChunkSize = 512
        else:
            self.mChunkSize = int(self.mParam['chunk_size'])

        if all(s not in self.mParam for s in ['src_filename', 'tgt_filename']) or \
            all(s in self.mParam for s in ['src_filename', 'tgt_filename']):
            raise ValueError('preAction: Neither src/tgt file specified or both specified')
        else:
            if 'src_filename' in self.mParam:
                self.mResult['bytes_read'] = 0
                if 'src_start_sector' not in self.mParam or int(self.mParam['src_start_sector']) < 0:
                    self.mParam['src_start_sector'] = 0
                elif int(self.mParam['src_start_sector']) % 512 != 0:
                    raise ValueError('preAction: source start sector must be multiples of 512 sector size')
                if 'num_chunks' not in self.mParam or self.mParam['num_chunks'] < 0:
                    self.mParam['num_chunks'] = 1
                # default mode is rb+
                self.mIO = BlockInputOutput(self.mChunkSize, self.mParam['src_filename'], 'rb')
                if stat.S_ISCHR(os.stat(self.mParam['src_filename']).st_mode):
                    # setup different total size for char dev
                    # special case where source is a char device, because it is
                    # mostly read only, and have no total sectors
                    self.mParam['chunk_size'] = 4096 # reset to 4096
                    self.mParam['src_start_sector'] = 0 # reset to beginning
                    # i.e. reset to 0 instead of -1/any passed in from handler
                    self.mParam['src_total_chunks'] = 0
                else:
                    filesize = self.mIO.getFileSize()
                    blksize = self.mIO.getBlockSize()
                    if ('chunk_size' not in self.mParam or int(self.mParam['chunk_size']) < 0):
                        # if no chunk_size is specified, then assign the os blocksize
                        self.mIO.mChunkSize = blksize
                        self.mParam['chunk_size'] = blksize
                        self.mParam['src_total_chunks'] = -(-filesize // blksize)
                    else:
                        self.mParam['src_total_chunks'] = -(-filesize // int(self.mParam['chunk_size']))

            elif 'tgt_filename' in self.mParam:
                self.mResult['bytes_written'] = 0
                if 'tgt_start_sector' not in self.mParam or int(self.mParam['tgt_start_sector']) < 0:
                    self.mParam['tgt_start_sector'] = 0
                elif int(self.mParam['tgt_start_sector']) % 512 != 0:
                    raise ValueError('preAction: target start sector must be multiples of 512 sector size')
                self.mIO = BlockInputOutput(self.mChunkSize, self.mParam['tgt_filename'], 'wb+')
                if 'tgt_data' not in self.mParam or len(self.mParam['tgt_data']) == 0:
                    raise ValueError('preAction: No data to be written')
                # if no coding and data is hexdecimal, then unhex it,
                # otherwise leave the data as it is for b64 or rle coding
                if 'coding' in self.mParam and (self.mParam['coding'] == 'no' or self.mParam['coding'] is None):
                    if self.mIO.isHexData(self.mParam['tgt_data']):
                        self.mParam['tgt_data'] = binascii.unhexlify(self.mParam['tgt_data'].encode())
                if stat.S_ISCHR(os.stat(self.mParam['tgt_filename']).st_mode):
                    raise IOError('preAction: target filename/device cannot be a char dev')
                else:
                    filesize = self.mIO.getFileSize()
                    blksize = self.mIO.getBlockSize()
                    if ('chunk_size' not in self.mParam or int(self.mParam['chunk_size']) < 0):
                        self.mIO.mChunkSize = blksize
                        self.mParam['chunk_size'] = blksize
                        self.mParam['tgt_total_chunks'] = -(-filesize // blksize)
                    else:
                        self.mParam['tgt_total_chunks'] = -(-filesize // int(self.mParam['chunk_size']))

        if self.mIO:
            self.mResult.update(self.mParam)
            _logger.debug('{}: preAction: {}'.format(type(self).__name__, self.mParam))
            return True
        return False

    def _mainAction(self):
        ret = False
        # read or write specified address range from src file or target data to target file
        if all(s in self.mParam for s in ['src_start_sector', 'num_chunks']):
            _logger.debug('{}: mainAction: Read {} chunks from sector {}'.format(type(self).__name__, self.mParam['num_chunks'], self.mParam['src_start_sector']))
            data = self.mIO.Read(int(self.mParam['src_start_sector']), int(self.mParam['num_chunks']))
            if data:
                if self.mParam['coding'] == 'rle':
                    retdata = base64.urlsafe_b64encode(binascii.rlecode_hqx(data))
                elif self.mParam['coding'] == 'b64':
                    retdata = base64.urlsafe_b64encode(data)
                else:
                    retdata = data
                self.mResult.update({'src_data': retdata.decode('ascii')})
                self.mResult.update({'bytes_read': len(data)})
                ret = True
        elif all(s in self.mParam for s in ['tgt_start_sector', 'tgt_data']):
            # write() returns number of bytes written
            if self.mParam['coding'] == 'rle':
                rawdata = binascii.rledecode_hqx(base64.urlsafe_b64decode(self.mParam['tgt_data'].encode('ascii')))
            elif self.mParam['coding'] == 'b64':
                rawdata = base64.urlsafe_b64decode(self.mParam['tgt_data'].encode('ascii'))
            else:
                rawdata = self.mParam['tgt_data'].encode()
            _logger.debug('{}: mainAction: write data size: {} to sector: {}'.format(type(self).__name__, len(rawdata), rawdata))
            self.mResult['bytes_written'] = self.mIO.Write(rawdata, self.mParam['tgt_start_sector'])
            if self.mResult['bytes_written'] == len(rawdata):
                ret = True
        else:
            raise ValueError('mainAction: Invalid parameter values.')

        # close the block input/output device
        self.mIO._close()
        del self.mIO
        return ret



class CopyBlockActionModeller(BaseActionModeller):
    """
    Copy Block Action Model to copy blocks of files
    """

    def __init__(self):
        super().__init__()
        self.mIOs = []
        self.isSrcCharDev = False

    def _preAction(self):
        self.mResult['bytes_read'] = 0
        self.mResult['bytes_written'] = 0
        # setup the chunksize for input/output objects
        self.isSrcCharDev = stat.S_ISCHR(os.stat(self.mParam['src_filename']).st_mode)
        if ('chunk_size' in self.mParam and self.mParam['chunk_size'] > 0):
            chunksize = self.mParam['chunk_size']
        else:
            # chunk_size in bytes default 1MB, i.e. 1048576
            chunksize = 1048576 # 1MB
            self.mParam['chunk_size'] = chunksize

        if all(s in self.mParam for s in ['src_filename', 'tgt_filename']):
            try:
                # default mode is rb+
                self.mIOs.append(BlockInputOutput(chunksize, self.mParam['src_filename'], 'rb'))
                self.mIOs.append(BlockInputOutput(chunksize, self.mParam['tgt_filename'], 'wb+'))
                filesize = self.mIOs[-1].getFileSize()
                if self.isSrcCharDev:
                    # special case where source is a char device and target is a block device, e.g. dd if=/dev/zero of=/dev/mmcblk2boot0
                    # self.mIOs[-1].getBlockSize() => 4096
                    blksize = chunksize
                    self.mParam['src_start_sector'] = 0
                    self.mParam['tgt_start_sector'] = 0
                else:
                    # setup different size params
                    blksize = self.mIOs[-1].getBlockSize()
                if ('src_total_sectors' not in self.mParam) or (self.mParam['src_total_sectors'] == -1):
                    chunks, remainder = divmod(filesize, blksize)
                    self.mParam['src_total_sectors'] = chunks + (0 if remainder == 0 else 1)
            except Exception as ex:
                raise IOError('Cannot create block inputoutput: {}'.format(ex))
        else:
            raise ValueError('preAction: Neither src nor tgt file specified')

        if len(self.mIOs) > 0 and all(isinstance(ioobj, BaseInputOutput) for ioobj in self.mIOs):
            return True
        return False

    def _mainAction(self):
        # copy specified address range from src file to target file
        try:
            if all(s in self.mParam for s in ['src_start_sector', 'src_total_sectors', 'tgt_start_sector']):
                chunksize = self.mParam['chunk_size'] if ('chunk_size' in self.mParam) else 1048576 # 1MB
                if self.isSrcCharDev:
                    blksize = chunksize
                else:
                    blksize = self.mIOs[0].getBlockSize()
                srcstart = self.mParam['src_start_sector'] * blksize
                tgtstart = self.mParam['tgt_start_sector'] * blksize
                totalbytes = self.mParam['src_total_sectors'] * blksize
                self.mResult['total_size'] = totalbytes
                # sector addresses of a very large file for looping
                address = self.__chunks(srcstart, tgtstart, totalbytes, chunksize)
                _logger.debug('total_size: {} block_size: {} list of addresses {} to copy: {}'.format(totalbytes, blksize, len(address), [addr for addr in address]))
                if len(address) > 1:
                    for (srcaddr, tgtaddr) in address:
                        self.checkInterruptAndExit()
                        self.__copyChunk(srcaddr, tgtaddr, 1)
                else:
                    self.__copyChunk(srcstart, tgtstart, totalbytes)
                return True
            else:
                self.__copyChunk(srcstart, tgtstart, totalbytes)
            ret = True
        except:
            raise ValueError('mainAction: No specified src/tgt start sector, nor total sectors')

        # close the block device
        for ioobj in self.mIOs:
            ioobj._close()
        del self.mIOs
        return ret

    def __copyChunk(self, srcaddr, tgtaddr, numChunks):
        # read src and write to the target
        data = self.mIOs[0].Read(srcaddr, numChunks)
        self.mResult['bytes_read'] += len(data)
        written = self.mIOs[1].Write(data, self.mResult['bytes_written'])
        _logger.debug('{} read: @{} size:{}, written: @{} size:{}'.format(type(self).__name__, hex(srcaddr), len(data), hex(tgtaddr), written))
        # write should return number of bytes written
        if (written > 0):
            self.mResult['bytes_written'] += written
        del data # hopefully this would clear the write data buffer

    def __chunks(self, srcstart, tgtstart, totalbytes, chunksize):
        # breaks up data into blocks, with source/target sector addresses
        chunks, remainder = divmod(totalbytes, chunksize)
        parts = chunks + (0 if remainder == 0 else 1)
        if stat.S_ISCHR(os.stat(self.mParam['src_filename']).st_mode):
            return [(0, tgtstart + i*chunksize) for i in range(parts)]
        else:
            return [(srcstart+i*chunksize, tgtstart + i*chunksize) for i in range(parts)]



class QueryMemActionModeller(BaseActionModeller):
    """
    Query Memory Action Model to query system information
    """

    def __init__(self):
        super().__init__()
        self.mIO = None

    def _preAction(self):
        # setup the input output
        if all(s in self.mParam for s in ['tgt_type', 'mem_type']) and \
            self.mParam['tgt_type'] == 'mem' and \
            self.mParam['mem_type'] in ['total', 'available', 'percent', 'used', \
                                         'free', 'active', 'inactive', 'buffers', \
                                         'cached', 'shared', 'all']:
            return True
        else:
            raise ReferenceError('No Valid Params')
        return False

    def _mainAction(self):
        # read the file, and return read lines
        # TODO: should implement writing files in the future
        try:
            self.mIO = dict(psutil.virtual_memory()._asdict())
            if self.mIO:
                if self.mParam['mem_type'] == 'all':
                    self.mResult.update(self.mIO)
                    return True
                else:
                    if self.mParam['mem_type'] in self.mIO.keys():
                        self.mResult[self.mParam['mem_type']] = self.mIO[self.mParam['mem_type']]
                        return True
                    else:
                        raise IOError('Cannot get spefic system memory info: {}'.format(self.mParam['mem_type']))
            raise IOError('Cannot get system memory info')
        except Exception:
            raise
        return False



class QueryMemActionModeller(BaseActionModeller):
    """
    Query Memory Action Model to query system information
    """

    def __init__(self):
        super().__init__()
        self.mIO = None

    def _preAction(self):
        # setup the input output
        if all(s in self.mParam for s in ['tgt_type', 'mem_type']) and \
            self.mParam['tgt_type'] == 'mem' and \
            self.mParam['mem_type'] in ['total', 'available', 'percent', 'used', \
                                         'free', 'active', 'inactive', 'buffers', \
                                         'cached', 'shared', 'all']:
            return True
        else:
            raise ReferenceError('No Valid Params')
        return False

    def _mainAction(self):
        # read the file, and return read lines
        # TODO: should implement writing files in the future
        try:
            self.mIO = dict(psutil.virtual_memory()._asdict())
            if self.mIO:
                if self.mParam['mem_type'] == 'all':
                    self.mResult.update(self.mIO)
                    return True
                else:
                    if self.mParam['mem_type'] in self.mIO.keys():
                        self.mResult[self.mParam['mem_type']] = self.mIO[self.mParam['mem_type']]
                        return True
                    else:
                        raise IOError('Cannot get spefic system memory info: {}'.format(self.mParam['mem_type']))
            raise IOError('Cannot get system memory info')
        except Exception:
            raise
        return False



class QueryFileActionModeller(BaseActionModeller):
    """
    Query File Action Model to query information from a file
    """

    def __init__(self):
        super().__init__()
        self.mIO = None

    def _preAction(self):
        self.mResult['lines_read'] = 0
        self.mResult['lines_written'] = 0
        # setup the input output
        if 'src_filename' in self.mParam and stat.S_ISREG(os.stat(self.mParam['src_filename']).st_mode):
            self.mIO = FileInputOutput(self.mParam['src_filename'], 'rt')
            if self.mIO:
                return True
            else:
                raise IOError('preAction: Cannot create FileInputOutput')
        elif 'src_filename' in self.mParam and stat.S_ISBLK(os.stat(self.mParam['src_filename']).st_mode):
            self.mIO = BlockInputOutput(512, self.mParam['src_filename'], 'rb')
            if self.mIO:
                return True
            else:
                raise IOError('preAction: Cannot create BlockInputOutput')
        else:
            raise ValueError('preAction: No valid source file')
        return False

    def _mainAction(self):
        # read the file, and return read lines
        # TODO: should implement writing files in the future
        if all(s in self.mParam for s in ['src_start_line', 'src_totallines']):
            # start from start line and read src_totallines
            data = self.mIO.Read(int(self.mParam['src_start_line']), int(self.mParam['src_totallines']))
        elif 'src_start_line' in self.mParam and not 'src_totallines' in self.mParam:
            # only src_start_line, start from start line and read rest
            data = self.mIO.Read(int(self.mParam['src_start_line']))
        elif 'src_total_lines' in self.mParam:
            # only src_total_lines, read from start with total lines
            data = self.mIO.Read(0, int(self.mParam['src_total_lines']))
        else:
            # guess file type, if text file, then read all, otherwise skip
            if self.mIO.isBinFile():
                data = b''
                self.mResult['lines_read'] = -1
            else:
                # no src_start_line and no src_totallines, start from beginning and read all
                data = self.mIO.Read(0)
                self.mResult['lines_read'] = len(data)
        _logger.debug('{} read data: {}'.format(type(self).__name__, data))
        self.mResult.update({'file_content': data})
        return True if self.mResult['lines_read'] != 0 else False

    def _postAction(self):
        ret = False
        if 're_pattern' in self.mParam:
            # if there is a regular express pattern passed in, return the
            # found regular express pattern
            p = re.compile(self.mParam['re_pattern'], re.IGNORECASE)
            for line in self.mResult['file_content']:
                m = p.match(line)
                if m:
                    _logger.debug('{} from pattern {} found_match: {}'.format(type(self).__name__, self.mParam['re_pattern'], m.groups()))
                    self.mResult['found_match'] = ','.join([g for g in m.groups()])
                    ret = True
        elif 'get_stat' in self.mParam and self.mParam['get_stat'] == True:
            _logger.debug('{} file stat: {}'.format(type(self).__name__, self.mIO.getStat()))
            self.mResult.update(self.mIO.getStat())
            if 'size' in self.mResult and self.mResult['size'] == 0:
                self.mIO._open()
                self.mResult['size'] = self.mIO.getFileSize()
            ret = True

        # clear the mIO
        if self.mIO: del self.mIO
        return ret



class QueryBlockDevActionModeller(BaseActionModeller):
    """
    A wrapper class for pyudev to get block device info
    """
    def __init__(self):
        super().__init__()
        self.mContext = pyudev.Context()
        self.mFound = []
        self.mCtrls = []
        self.mDisks = []
        self.mPartitions = []

    def _preAction(self):
        if all(s in self.mParam for s in ['tgt_type', 'dst_pos']):
            self.__gatherStorage()
            _logger.debug('{} controllers: {}\ndisks: {}\npartitions: {}'.format(type(self).__name__, self.mCtrls, self.mDisks, self.mPartitions))
            if len(self.mPartitions) > 0 and len(self.mDisks) > 0 and len(self.mCtrls) > 0:
                return True
        else:
            return False

    def _mainAction(self):
        # check the actparams against the udev info
        # find self.mParam['tgt_type'] from ctrller's attributes('type') or driver()
        for o in self.mCtrls:
            _logger.debug('{} tgt_type: {}, attributes: {}, driver: {}'.format(type(self).__name__, self.mParam['tgt_type'], self.__getDevAttributes(o).values(), o.driver))
            if (self.mParam['tgt_type'] in self.__getDevAttributes(o).values() \
                or self.mParam['tgt_type'] == o.driver):
                _logger.debug('{} found controller: {}'.format(type(self).__name__, o))
                self.mFound.append(o)
        # if found any controllers that match the target type, record it
        if len(self.mFound) > 0:
            return True
        else:
            return False

    def _postAction(self):
        # set results to found controller and its children disk/partitions
        if len(self.mFound) > 0:
            for o in self.mFound if (len(self.mFound) > 0) else self.mCtrls:
                if (not self.__extract_info(o)):
                    return False
            # only set the required output from mParam['dst_pos']
            if (self.mParam['dst_pos'] == 'c'):
                self.mResult = self.mResult.pop('controllers')
            elif (self.mParam['dst_pos'] == 'd'):
                self.mResult = self.mResult.pop('disks')
            elif (self.mParam['dst_pos'] == 'p'):
                self.mResult = self.mResult.pop('partitions')
        return True

    def __getDevAttributes(self, dev):
        ret = {}
        if isinstance(dev, pyudev.Device):
            for att in dev.attributes.available_attributes:
                data = dev.attributes.get(att)
                ret.update({att:data.decode('utf-8', 'ignore').replace('\n', ' ') if data is not None else ''})
        return ret

    def __gatherStorage(self):
        self.__gatherPartitions()
        self.__gatherDisks()
        self.__gatherCtrller()

    def __gatherCtrller(self):
#         if len(self.mDisks) > 0:
#             self.mCtrls = list(set([d.parent for d in self.mDisks if d.parent]))
#         else:
        self.mCtrls.extend(list(set( [d.parent for d in self.mContext.list_devices(subsystem='block', DEVTYPE='disk') \
                                     if (d.find_parent('mmc') or d.find_parent('scsi'))] )))
            # self.mCtrls = list(set([d for d in self.context.list_devices(subsystem='mmc')]))
            # self.mCtrls.append(d for d in list(set([d for d in self.context.list_devices(subsystem='scsi')])))

    def __gatherDisks(self):
#         if len(self.mPartitions) > 0:
#             self.mDisks = list(set([p.parent for p in self.mPartitions if p.parent]))
#         else:
        self.mDisks.extend(list(set( [d for d in self.mContext.list_devices(subsystem='block', DEVTYPE='disk') \
                                     if (d.find_parent('mmc') or d.find_parent('scsi'))] )))

    def __gatherPartitions(self):
        self.mPartitions.extend(list(d for d in self.mContext.list_devices(subsystem='block', DEVTYPE='partition')))

    def __extract_info(self, cdev):
        partsinfo = {}
        disksinfo = {}
        ctrlsinfo = {}

        if cdev is None:
            return False
        else:
            c = cdev

        ctrlsinfo.update({c.sys_name: {'device_node': c.device_node, \
                                             'device_number': c.device_number, \
                                             'device_path': c.device_path, \
                                             'device_type': c.device_type, \
                                             'driver': c.driver, \
                                             'subsystem': c.subsystem, \
                                             'sys_name': c.sys_name, \
                                             'sys_number': c.sys_number, \
                                             'sys_path': c.sys_path, \
                                             'attributes': self.__getDevAttributes(c)}})

        for d in self.mDisks:
            if d.parent == c:
                disksinfo.update({d.sys_name: {'device_node': d.device_node, \
                                               'device_number': d.device_number, \
                                               'device_path': d.device_path, \
                                               'device_type': d.device_type, \
                                               'driver': d.driver, \
                                               'subsystem': d.subsystem, \
                                               'sys_name': d.sys_name, \
                                               'sys_number': d.sys_number, \
                                               'sys_path': d.sys_path, \
                                               'attributes': self.__getDevAttributes(d), \
                                               'id_bus': d.get('ID_BUS'), \
                                               'serial': d.get('ID_SERIAL'), \
                                               'id_model': d.get('ID_MODEL')}})
                for p in self.mPartitions:
                    if p.parent == d:
                        mpt = [m.mountpoint for m in psutil.disk_partitions() if m.device == p.device_node]
                        partsinfo.update({p.sys_name: {'device_node': p.device_node, \
                                                       'device_number': p.device_number, \
                                                       'device_path': p.device_path, \
                                                       'device_type': p.device_type, \
                                                       'driver': p.driver, \
                                                       'subsystem': p.subsystem, \
                                                       'sys_name': p.sys_name, \
                                                       'sys_number': p.sys_number, \
                                                       'sys_path': p.sys_path, \
                                                       'attributes': self.__getDevAttributes(p), \
                                                       'mount_point': mpt[0] if (len(mpt) == 1) else None}})

        if 'partitions' in self.mResult.keys() and isinstance(self.mResult['partitions'], dict):
            self.mResult['partitions'].update(partsinfo)
        else:
            self.mResult.update({'partitions': partsinfo})
        if 'disks' in self.mResult.keys() and isinstance(self.mResult['disks'], dict):
            self.mResult['disks'].update(disksinfo)
        else:
            self.mResult.update({'disks': disksinfo})
        if 'controllers' in self.mResult.keys() and isinstance(self.mResult['controllers'], dict):
            self.mResult['controllers'].update(ctrlsinfo)
        else:
            self.mResult.update({'controllers': ctrlsinfo})
        return True



class WebDownloadActionModeller(BaseActionModeller):
    def __init__(self):
        super().__init__()
        self.mIOs = []

    def _preAction(self):
        self.mResult['bytes_read'] = 0
        self.mResult['bytes_written'] = 0
        # get memory information from the system
        #self.__meminfo = psutil.virtual_memory()

        # setup options, chunk_size in bytes default 64KB, i.e. 65535
        chunksize = self.mParam['chunk_size'] if ('chunk_size' in self.mParam) else 65535 # 64K
        srcPath = '{}/{}'.format(self.mParam['src_directory'].strip('/'), self.mParam['src_filename'].lstrip('/'))
        host = self.mParam['host_name'] if ('host_name' in self.mParam) else 'rescue.technexion.net'
        port = self.mParam['host_port'] if ('host_port' in self.mParam) else None
        protocol = self.mParam['host_protocol'] if ('host_protocol' in self.mParam) else 'http'
        if port is not None:
            dlhost = '{}://{}:{}'.format(protocol.rstrip('://'), host.rstrip('/'), port)
        else:
            dlhost = '{}://{}'.format(protocol.rstrip('://'), host.rstrip('/'))
        _logger.debug('chunksize: {}, srcPath: {}, host: {}'.format(chunksize, srcPath, dlhost))

        if os.path.exists(self.mParam['tgt_filename']):
            # ensure target path exists, and then setup the input/output objects
            if 'tgt_filename' in self.mParam:
                self.mIOs.append(WebInputOutput(chunksize, srcPath, host=dlhost))
                self.mIOs.append(BlockInputOutput(chunksize, self.mParam['tgt_filename'], 'wb+'))
            else:
                raise ValueError('preAction: No tgt file specified')
        else:
            raise IOError('preAction: {} does not existed'.format(self.mParam['tgt_filename']))

        if len(self.mIOs) == 2:
            return True
        return False

    def _mainAction(self):
        # copy specified address range from downloaded src file to target file
        ret = False
        try:
            self.mResult['total_uncompressed'] = self.mIOs[0].getUncompressedSize()

            # shell subprocess Popen
            DecompCmd = {'tar': 'tar xvf', 'zip':'zip -d', 'xz':'xz -d', 'bz':'bzip2 -d', 'gz':'gzip -d'}
            decompcmd = 'xz -d'
            for k, v in DecompCmd.items():
                if k in self.mIOs[0].getFileType():
                    decompcmd = v
            wgetcmd = 'wget -q -O - {}'.format(self.mIOs[0].mUrl)
            ddcmd = 'dd of={} bs=4096 conv=notrunc,fsync'.format(self.mIOs[1].mFilename)

            # python lzma method
            chunksize = self.mParam['chunk_size'] if ('chunk_size' in self.mParam) else 65535 # 64K
            srcstart = 0
            tgtstart = self.mParam['tgt_start_sector']
            totalbytes = self.mIOs[0].getFileSize()
            # sector addresses of a very large file for looping
            if totalbytes > 0:
                address = self.__chunks(srcstart, tgtstart, totalbytes, chunksize)
            else:
                raise IOError('There is 0 Total Bytes to download')

            # if self.__meminfo.available > 671088640: # 640 * 1024 * 1024 bytes
            if not IsATargetBoard(): # if is not a target board use inputoutput else use subprocess.popen
                _logger.debug('list of addresses {} to copy: {}'.format(len(address), address))
                if len(address) > 1:
                    for count, (srcaddr, tgtaddr) in enumerate(address):
                        self.checkInterruptAndExit()
                        self.__copyChunk(srcaddr, tgtaddr, 1, wgetcmd, decompcmd, ddcmd)
                else:
                    self.__copyChunk(srcstart, tgtstart, totalbytes, wgetcmd, decompcmd, ddcmd)
            else:
                # otherwise use subprocess's Popen
                self.__copyChunk(srcstart, tgtstart, totalbytes, wgetcmd, decompcmd, ddcmd)
            return True
        except Exception as ex:
            _logger.error('WebDownload main-action exception: {}'.format(ex))
            raise

    def __chunks(self, srcstart, tgtstart, totalbytes, chunksize):
        # breaks up data into blocks, with source/target sector addresses
        parts = -(-totalbytes // chunksize) # int ceiling division
        return [(srcstart+i*chunksize, tgtstart + i*chunksize) for i in range(parts)]

    def __parseProgress(self, pid, line, rex):
        # extract percentage and size downloaded from web
        _logger.debug('parseProgress: regex: {} on {}'.format(rex, line))
        p = re.compile(rex, re.IGNORECASE)
        m = p.match(line)
        if m:
            _logger.debug('matched: {}'.format(m.groups()))
            if pid == self.__pddpid:
                recin, partin, recout, partout = m.groups()
                self.mResult['bytes_read'] = int(recin) * 4096
                self.mResult['bytes_written'] = int(recout) * 4096
            else:
                percent, read, eta = m.groups()
                self.mResult['bytes_read'] = read
                self.mResult['bytes_written'] = self.mResult['total_uncompressed'] * int(percent) // 100
                self.mResult['eta'] = eta

    def __copyChunk(self, srcaddr, tgtaddr, numChunks, wgetcmd, decompcmd, ddcmd):
        def read_stream(fd):
            try:
                # set non-blocking flag while preserving old flags
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
                fd.seek(0)
                line = fd.readlines()
                if line is not None:
                    lastline = '{}-{}'.format(line[-2].strip(), line[-1].strip())
                    _logger.debug('last progress line: {}'.format(lastline))
                    self.__parseProgress(self.__pddpid, lastline, '(.*)\+(.*) records in-(.*)\+(.*) records out')
            except Exception as ex:
                # waiting for data to be available on stderr
                _logger.error('read_stream exception: {}'.format(ex))
                return False
            return True

        try:
            # if self.__meminfo.available > 671088640: # 640 * 1024 * 1024 bytes
            if not IsATargetBoard(): # if is not a target board use inputoutput else use subprocess.popen
                # read src and write to the target
                data = self.mIOs[0].Read(srcaddr, numChunks)
                self.mResult['bytes_read'] += len(data)
                written = self.mIOs[1].Write(data, self.mResult['bytes_written'])
                _logger.debug('read: @{} size:{}, written: @{} size:{}'.format(hex(srcaddr), len(data), hex(self.mResult['bytes_written']), written))
                # write should return number of bytes written
                if (written > 0):
                    self.mResult['bytes_written'] += written
                del data # hopefully this would clear the write data buffer
            else:
                timeout_counter = 0
                last_written =  0
                fd = open('/tmp/progress.log', 'w+')
                _logger.info('copyChunk: {}, {}, {}'.format(wgetcmd, decompcmd, ddcmd))
                pwget = subprocess.Popen(
                    [wgetcmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
                pxz = subprocess.Popen(
                    [decompcmd],
                    stdin=pwget.stdout,
                    stdout=subprocess.PIPE,
                    shell=True,
                )
                pdd = subprocess.Popen(
                    [ddcmd],
                    stdin=pxz.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
                fd.flush()
                ptee = subprocess.Popen(
                    ['tee'],
                    stdin=pdd.stderr,
                    stdout=fd,
                    shell=True,
                )
                self.__pddpid = pdd.pid
                while True:
                    try:
                        out, err = ptee.communicate(timeout=1)
                        break
                    except subprocess.TimeoutExpired as ex:
                        self.__signal_subproc(pdd)
                        if timeout_counter > 180: # timed out after 3 minutes
                            self.__kill_subproc([pwget, pxz, pdd, ptee])
                            raise ex
                        else:
                            _logger.info('last written:{} bytes_written: {} timeout_counter: {}'.format(last_written, self.mResult['bytes_written'], timeout_counter))
                            if read_stream(fd) and last_written != self.mResult['bytes_written']:
                                last_written = self.mResult['bytes_written']
                                timeout_counter = 0
                            else:
                                timeout_counter += 1
                            continue
                    except:
                        read_stream(fd)
                        fd.close()
                        raise BlockingIOError('Subprocess Popen failed')
                read_stream(fd)
                fd.close()

        except Exception:
            raise

    def __signal_subproc(self, proc):
        proc.send_signal(signal.SIGUSR1)

    def __kill_subproc(self, procs):
        for proc in procs:
            proc.kill()



class QueryWebFileActionModeller(BaseActionModeller):
    """
    Query Action Model to query file information on a website
    """

    def __init__(self):
        super().__init__()

    def _preAction(self):
        self.mResult['lines_read'] = 0
        self.mResult['lines_written'] = 0
        if all(s in self.mParam for s in ['host_name', 'src_directory']):
            # parse host name
            if ('host_name' in self.mParam) and self.mParam['host_name'].lower().startswith('http'):
                self.mWebHost = self.mParam['host_name']
            else:
                self.mWebHost = 'http://rescue.technexion.net'
            # parse host directory
            if ('src_directory' in self.mParam):
                if self.mParam['host_dir'] in self.mParam['src_directory']:
                    self.mSrcPath = '{}'.format(self.mParam['src_directory'])
                elif '/rescue/' in self.mParam['src_directory']:
                    self.mSrcPath = '{}'.format(self.mParam['src_directory'])
                else:
                    if self.mParam['src_directory'] == '/':
                        self.mSrcPath = '/rescue/'
                    elif self.mParam['src_directory'].endswith('/'):
                        self.mSrcPath = '/rescue/{}/'.format(self.mParam['src_directory'].strip('/'))
                    else:
                        self.mSrcPath = '/rescue/{}'.format(self.mParam['src_directory'].lstrip('/'))
            if self.mWebHost and self.mSrcPath:
                return True
        return False

    def _mainAction(self):
        # TODO: should implement writing files in the future
        # setup the web input output
        webIO = WebInputOutput(0, self.mSrcPath, host=self.mWebHost)
        if webIO:
            _logger.debug('{} Host: {} Path: {} File Type: {}'.format(type(self).__name__, self.mWebHost, self.mSrcPath, webIO.getFileType()))
            if 'html' in webIO.getFileType():
                webpage = webIO.Read(0, 0)
                # parse the web pages
                dctFiles = self.__parseWebPage(webpage)
                if len(dctFiles) > 0:
                    self.mResult['file_list'] = dctFiles
                    self.mResult['lines_read'] += len(webpage)
                    return True
            elif 'xz' in webIO.getFileType():
                self.mResult['header_info'] = webIO.getHeaderInfo()
                self.mResult['file_type'] = webIO.getFileType()
                self.mResult['total_size'] = webIO.getFileSize()
                self.mResult['total_uncompressed'] = webIO.getUncompressedSize()
                return True
            else:
                raise IOError('mainAction: Cannot read non-text based web files')
        else:
            raise ValueError('mainAction: Cannot create WebInputOutput with {} {}'.format(self.mSrcPath, self.mWebHost))

        return False

    def __parseWebPage(self, page):
        """
        parse the web page, and extract downloadable xz files and info into
        {'filename': 'full_url', ...} format
        """
        ret = {}
        parser = HtmlFileLinkParser(self.mWebHost, self.mSrcPath)
        strPage = str(page, 'utf-8')
#         start = strPage.find('<table>')
#         end = strPage.find('</table>', start + len('<table>')) + len('</table>')
#         strTbl = strPage[start:end]
        parser.feed(strPage)
        ret.update(parser.mData)
        return ret



class QueryLocalFileActionModeller(BaseActionModeller):
    def __init__(self):
        super().__init__()
        self.mIO = None

    def _preAction(self):
        self.mResult['file_list'] = {}
        if all(s in self.mParam for s in ['local_fs', 'src_directory']):
            if ('src_directory' in self.mParam):
                self.mSrcPath = self.mParam['src_directory']
            else:
                self.mSrcPath = '/'
            # search xz files from self.mSrcPath
            _logger.debug('{} QueryLocalFile: self.mSrcPath: {}'.format(type(self).__name__, self.mSrcPath))
            return True
        else:
            return False

    def _mainAction(self):
        try:
            for dirpath, dirnames, filenames in os.walk(self.mSrcPath):
                for file in filenames:
                    if file.endswith(".xz"):
                        # setup the web input output
                        if self.mIO is None:
                            try:
                                self.mIO = BlockInputOutput(65535, os.path.join(dirpath, file))
                                if self.mIO and 'xz' in self.mIO.getFileType():
                                    self.mResult['file_list'].update({file: {'file_name': file, \
                                                                             'file_path': os.path.join(dirpath, file), \
                                                                             'total_size': self.mIO.getFileSize(), \
                                                                             'total_uncompressed': self.mIO.getUncompressedSize()}})
                                else:
                                    self.mResult['file_list'].update({file: {'file_name': file, \
                                                                             'file_path': os.path.join(dirpath, file)}})
                            except Exception as ex:
                                raise IOError('mainAction: Cannot create BlockInputOutput with {}, error:{}'.format(self.mSrcPath, ex))
                            finally:
                                if self.mIO: del self.mIO
                                self.mIO = None
                        _logger.debug('QueryLocalFile: {}: {}'.format(file, os.path.join(dirpath, file)))
            return True
        except Exception as ex:
            raise IOError('mainAction error: {}'.format(ex))
        return False



class ConfigMmcActionModeller(BaseActionModeller):
    """
    Configures emmc boot partition option
    for androidthings:
        set boot partition 1 to enable
    for other TechNexion OSes"
        set boot partition options to disable
    """
    def __init__(self):
        super().__init__()
        self.mResult['retcode'] = 0
        self.mSubProcCmd = []

    def _preAction(self):
        if all(s in self.mParam for s in ['subcmd', 'target', 'config_id', 'config_action']) and self.mParam['subcmd'] == 'mmc':
            # i.e. subprocess.check_call(['mmc', 'bootpart', 'enable', '0', '1', '/dev/mmcblk2'])
            if any(value in self.mParam['config_id'] for value in ['bootpart', 'bootbus', 'bkops', 'cache', 'csd', 'cid', 'extcsd', \
                                                                   'enh_area', 'hwreset', 'rpmb', 'scr', 'ffu', 'sanitize', 'status', \
                                                                   'write_reliability', 'writeprotect']):
                self.mSubProcCmd.append('mmc')
            else:
                self.mSubProcCmd.append('echo')

            if stat.S_ISBLK(os.stat(self.mParam['target']).st_mode):
                if self.mParam['config_id'] == 'bootpart':
                    self.mSubProcCmd.extend([self.mParam['config_id'], "enable", \
                                             "0" if self.mParam['config_action'] == "disable" else self.mParam['boot_part_no'], \
                                             self.mParam['send_ack'], self.mParam['target']])
                elif self.mParam['config_id'] == 'readonly':
                    if 'boot' in self.mParam['target']:
                        tgtfile = self.mParam['target'][:self.mParam['target'].find('boot')].replace('/dev/', '')
                    else:
                        tgtfile = self.mParam['target'].replace('/dev/', '')

                    self.mSubProcCmd.extend(['0' if self.mParam['config_action'] == 'disable' else '1',
                                             '>', '/sys/block/' + tgtfile + 'boot' + str(int(self.mParam['boot_part_no']) - 1) + '/force_ro'])
                elif self.mParam['config_id'] == 'extcsd':
                    self.mSubProcCmd.extend([self.mParam['config_id'], self.mParam['config_action'], self.mParam['target']])
                _logger.info('{} preAction: subprocess cmd: {}'.format(type(self).__name__, self.mSubProcCmd))
                return True
        return False

    def _mainAction(self):
        # do something to query mmc
        if len(self.mSubProcCmd):
            if self.mSubProcCmd[0] == 'mmc':
                #self.mResult['retcode'] = subprocess.check_call(self.mSubProcCmd)
                p = subprocess.Popen(' '.join(self.mSubProcCmd), stdout=subprocess.PIPE, shell=True)
                output, err = p.communicate()
                p_status = p.wait()
                self.mResult['retcode'] = p_status
                if err is None:
                    self.mResult['output'] = str(output[:], 'utf-8')
                else:
                    self.mResult['err'] = str(err[:], 'utf-8')
            else:
                self.mResult['retcode'] = subprocess.check_call(' '.join(self.mSubProcCmd), shell=True)
            _logger.info('{} mainAction: retcode: {}'.format(type(self).__name__, self.mResult['retcode']))
        return self.mResult['retcode'] == 0 # 0 means success



class ConfigNicActionModeller(BaseActionModeller):
    """
    Config Network Interfaces for the current network status
    Using IOCTL on socket fd
    e.g. ioctl
    fcntl.ioctl(sock.fileno(), 0x8915,  # SIOCGIFADDR, struct.pack('256s', ifname[:15]))

    struct socladdr {
         unsigned short sa_family;
         char sa_data[16];
    }

    parse results according to C struct below

    # define IF_NAMESIZE    16
    # define IFHWADDRLEN    6
    # define IFNAMSIZ       IF_NAMESIZE
    struct ifreq {
        /* Interface name, e.g. "en0".  */
        char ifrn_name[IFNAMSIZ];                     16
        union {
            struct sockaddr ifru_addr;                16
            struct sockaddr ifru_dstaddr;
            struct sockaddr ifru_broadaddr;
            struct sockaddr ifru_netmask;
            struct sockaddr ifru_hwaddr;
            short int ifru_flags;
            int ifru_ivalue;
            int ifru_mtu;
            struct ifmap ifru_map;
            char ifru_slave[IFNAMSIZ];    /* Just fits the size */
            char ifru_newname[IFNAMSIZ];
            __caddr_t ifru_data;
        } ifr_ifru;
    };
    """
    def __init__(self):
        super().__init__()
        self.mIoctlCmd = None
        self.mIoctlArg = struct.pack('256s', b'\0')
        self.mNames = array.array('B', b'\0' * 4096)

    def getHostIPByName(self):
        try:
            IP = socket.gethostbyname(self.mParam['target'])
        except:
            IP = None
        return IP

    def getNetIP(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable, so use DNS
            s.connect(('8.8.8.8', 53))
            with open('/etc/resolv.conf', 'a') as f:
                f.write('nameserver 8.8.8.8\n')
            IP = s.getsockname()[0]
        except:
            with open('/etc/hosts', 'a') as f:
                f.write('203.75.190.59\trescue.technexion.net\n')
            IP = None
        finally:
            s.close()
        return IP

    def _preAction(self):
        if all(s in self.mParam for s in ['subcmd', 'target', 'config_id', 'config_action']) and self.mParam['subcmd'] == 'nic':
            # get the target to put into binary struct
            if 'target' in self.mParam:
                tgt = b'eth0' if self.mParam['target'] == 'any' else self.mParam['target'][:15].encode()
            # parse the config_id and setup appropriate IOCTL commands and Arguments
            if self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'iflink':
                self.mIoctlCmd = 0x8911 # SIOCSIFLINK
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifconf':
                self.mIoctlCmd = 0x8912 # SIOCGIFCONF
                names_address, names_length = self.mNames.buffer_info()
                self.mIoctlArg = struct.pack('iL', 4096, names_address)
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifname':
                self.mIoctlCmd = 0x8910 # SIOCGIFNAME
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifname':
                self.mIoctlCmd = 0x8923 # SIOCSIFNAME
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifflags':
                self.mIoctlCmd = 0x8913 # SIOCGIFFLAGS
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifflags':
                self.mIoctlCmd = 0x8914 # SIOCSIFFLAGS
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifaddr':
                self.mIoctlCmd = 0x8915 # SIOCGIFADDR
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifaddr':
                self.mIoctlCmd = 0x8916 # SIOCSIFADDR
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifdstaddr':
                self.mIoctlCmd = 0x8917 # SIOCGIFDSTADDR
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifdstaddr':
                self.mIoctlCmd = 0x8918 # SIOCSIFDSTADDR
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifbraddr':
                self.mIoctlCmd = 0x8919 # SIOCGIFBRDADDR
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifbraddr':
                self.mIoctlCmd = 0x891a # SIOCSIFBRDADDR
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifnetmask':
                self.mIoctlCmd = 0x891b # SIOCGIFNETMASK
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifnetmask':
                self.mIoctlCmd = 0x891c # SIOCSIFNETMASK
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifmetric':
                self.mIoctlCmd = 0x891d # SIOCGIFMETRIC
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifmetric':
                self.mIoctlCmd = 0x891e # SIOCSIFMETRIC
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifmem':
                self.mIoctlCmd = 0x891f # SIOCGIFMEM
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifmem':
                self.mIoctlCmd = 0x8920 # SIOCSIFMEM
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifmtu':
                self.mIoctlCmd = 0x8921 # SIOCGIFMTU
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifmtu':
                self.mIoctlCmd = 0x8922 # SIOCSIFMTU
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifencap':
                self.mIoctlCmd = 0x8925 # SIOCGIFENCAP
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifencap':
                self.mIoctlCmd = 0x8926 # SIOCSIFENCAP
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifhwaddr':
                self.mIoctlCmd = 0x8927 # SIOCGIFHWADDR
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifhwaddr':
                self.mIoctlCmd = 0x8924 # SIOCSIFHWADDR
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifslave':
                self.mIoctlCmd = 0x8929 # SIOCGIFSLAVE
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifslave':
                self.mIoctlCmd = 0x8930 # SIOCSIFSLAVE
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifpflags':
                self.mIoctlCmd = 0x8935 # SIOCGIFPFLAGS
                self.mIoctlArg = struct.pack('256s', tgt)
            elif self.mParam['config_action'] == 'set' and self.mParam['config_id'] == 'ifpflags':
                self.mIoctlCmd = 0x8934 # SIOCSIFPFLAGS
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ip':
                return True
            elif self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'dns':
                return True
            else:
                return False

            _logger.info('{} _preAction: ioctl cmd: {:#x} arg: {}'.format(type(self).__name__, self.mIoctlCmd, self.mIoctlArg))
            return True
        return False

    def _mainAction(self):
        if self.mParam['config_id'] == 'dns' and len(self.mParam['target']) > 0:
            self.mResult['host_ip'] = self.getHostIPByName()
            if self.mResult['host_ip'] is not None:
                return True
        elif self.mParam['config_id'] == 'ip':
            self.mResult['ip'] = self.getNetIP()
            if self.mResult['ip'] is not None:
                return True
        else:
            try:
                # do ioctl to get/set NIC related information
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.mResult['retcode'] = fcntl.ioctl(s.fileno(), self.mIoctlCmd, self.mIoctlArg)
                _logger.info('{} fcntl.ioctl() returned: {}'.format(type(self).__name__, self.mResult['retcode']))
                return True
            except Exception as ex:
                _logger.error('ConfigNic Exception: {}'.format(ex))
                raise
        return False

    def _postAction(self):
        """
        Convert the returned ioctl info usable information and store in self.mResults
        for ifflags:
            IFF_UP = 0x1,              /* interface is up. Can be toggled through sysfs. */
            IFF_BROADCAST = 0x2,       /* broadcast address valid. Volatile. */
            IFF_DEBUG = 0x4,           /* turn on debugging. Can be toggled through sysfs. */
            IFF_LOOPBACK = 0x8,        /* is a loopback net. Volatile. */
            IFF_POINTOPOINT = 0x10,    /* interface is has p-p link. Volatile. */
            IFF_NOTRAILERS = 0x20,     /* avoid use of trailers. Can be toggled through sysfs. Volatile. */
            IFF_RUNNING = 0x40,        /* Resources allocated. interface RFC2863 OPER_UP. Volatile. */
            IFF_NOARP = 0x80,          /* no ARP protocol. Can be toggled through sysfs. Volatile. */
            IFF_PROMISC = 0x100,       /* receive all packets. Can be toggled through sysfs. */
            IFF_ALLMULTI = 0x200,      /* receive all multicast packets. Can be toggled through sysfs. */
            IFF_MASTER = 0x400,        /* master of a load balancer. Volatile. */
            IFF_SLAVE = 0x800,         /* slave of a load balancer. Volatile. */
            IFF_MULTICAST = 0x1000,    /* Supports multicast. Can be toggled through sysfs. */
            IFF_PORTSEL = 0x2000,      /* can set media type. Can be toggled through sysfs. */
            IFF_AUTOMEDIA = 0x4000,    /* auto media select active. Can be toggled through sysfs. */
            IFF_DYNAMIC = 0x8000       /* dialup device with changing addresses. Can be toggled through sysfs. */
            IFF_LOWER_UP = 0x10000     /* driver signals L1 up. Volatile. */
            IFF_DORMENT = 0x20000      /* driver signals dormant. Volatile. */
            IFF_ECHO = 0x40000         /* echo sent packets. Volatile. */
        """
        if self.mParam['config_action'] == 'get':
            if self.mParam['config_id'] == 'ifflags':
                self.mResult['ifname'], self.mResult['flags'] = struct.unpack('16si236x', self.mResult['retcode'])
                _logger.info('flags: {}'.format(self.mResult['flags']))
                self.mResult['state'] = []
                if self.mResult['flags'] & 0x1:
                    self.mResult['state'].append('UP')
                if self.mResult['flags'] & 0x2:
                    self.mResult['state'].append('BOARDCAST')
                if self.mResult['flags'] & 0x40:
                    self.mResult['state'].append('RUNNING')
                if self.mResult['flags'] & 0x1000:
                    self.mResult['state'].append('MULTICAST')
                if self.mResult['flags'] & 0x10000:
                    self.mResult['state'].append('LOWER_UP')
                return True
            elif self.mParam['config_id'] == 'ifconf':
                max_bytes_out, names_address_out = struct.unpack('iL', self.mResult['retcode'])
                _logger.info('{}: ifconfig: names:{} max_bytes:{} names_addr:{}'.format(type(self).__name__, self.mNames.tostring(), max_bytes_out, names_address_out))
                namestr = self.mNames.tostring()
                self.mResult['iflist'] = {}
                for i in range(0, max_bytes_out, 40 if '64bit' in platform.architecture()[0] else 32): # 32bits 32, 64bits:40
                    name = namestr[ i : i+16 ].split(b'\0', 1)[0].decode('utf-8') # ifr_name
                    ip = []
                    for netaddr in namestr[ i+20 : i+24 ]: # ifr_addr
                        if isinstance(netaddr, int):
                            ip.append(str(netaddr))
                        elif isinstance(netaddr, str):
                            ip.append(str(ord(netaddr)))
                    if self.mParam['target'] == 'any' or self.mParam['target'] == name:
                        self.mResult['iflist'].update({name: '.'.join(ip)})
                for dname in os.listdir('/sys/class/net/'):
                    if dname not in self.mResult['iflist']:
                        if self.mParam['target'] == 'any' or self.mParam['target'] == dname:
                            self.mResult['iflist'].update({dname: 'unknown'})
                return True
            elif self.mParam['config_id'] == 'ifhwaddr':
                self.mResult['ifname'], macaddr = struct.unpack('16s8s232x', self.mResult['retcode'])
                self.mResult['hwaddr'] = "".join(["%02x:" % ch for ch in macaddr[2:]])[:-1]
                _logger.info('ifname: {} mac: {}'.format(self.mResult['ifname'], self.mResult['hwaddr']))
                return True
            elif self.mParam['config_id'] == 'dns':
                return True
            elif self.mParam['config_id'] == 'ip':
                return True
        return False



class DriverActionModeller(BaseActionModeller):
    """
    modprobe or remove Linux drivers
    """
    def __init__(self):
        super().__init__()
        self.mResult['retcode'] = 0
        self.mSubProcCmd = []
        self.mMacAddr = '00:00:00:00:00:00' # '00:1F:7B:B6:AB:BA'

    def _preAction(self):
        if all(s in self.mParam for s in ['cmd', 'type']):
            if self.mParam['cmd'] == 'connect':
                self.mSubProcCmd.extend(['modprobe'])
            elif self.mParam['cmd'] == 'disconnect':
                self.mSubProcCmd.extend(['rmmod'])
            if self.mParam['type'] == 'serial':
                self.mSubProcCmd.extend(['g_serial'])
            elif self.mParam['type'] == 'storage':
                if self.mParam['cmd'] == 'connect':
                    if 'src_filename' in self.mParam:
                        self.mSubProcCmd.extend(['g_mass_storage', \
                                'file={}'.format(self.mParam['src_filename']), \
                                'stall=0', 'removable=1'])
                elif self.mParam['cmd'] == 'disconnect':
                    self.mSubProcCmd.extend(['g_mass_storage'])
            elif self.mParam['type'] == 'serialstorage':
                if self.mParam['cmd'] == 'connect':
                    if 'src_filename' in self.mParam:
                        self.mSubProcCmd.extend(['g_acm_ms', \
                                'file={}'.format(self.mParam['src_filename']), \
                                'stall=0', \
                                'removable=1', \
                                'iSerialNumber={}'.format(self.mParam['mac_addr'] if 'mac_addr' in self.mParam else self.mMacAddr), \
                                'iManufacturer=TechNexion'])
                elif self.mParam['cmd'] == 'disconnect':
                    self.mSubProcCmd.extend(['g_acm_ms'])
            elif self.mParam['type'] == 'multi':
                if self.mParam['cmd'] == 'connect':
                    if 'src_filename' in self.mParam:
                        self.mSubProcCmd.extend(['g_multi', \
                                'file={}'.format(self.mParam['src_filename']), \
                                'stall=0', \
                                'removable=1', \
                                'iSerialNumber={}'.format(self.mParam['mac_addr'] if 'mac_addr' in self.mParam else self.mMacAddr), \
                                'iManufacturer=TechNexion', \
                                'dev_addr={}'.format(self.mParam['mac_addr'] if 'mac_addr' in self.mParam else self.mMacAddr)])
                elif self.mParam['cmd'] == 'disconnect':
                    self.mSubProcCmd.extend(['g_multi'])
            _logger.info('preAction: subprocess cmd: {}'.format(self.mSubProcCmd))
            return True
        return False

    def _mainAction(self):
        # probe or remove the driver
        if len(self.mSubProcCmd):
            if self.mSubProcCmd[0] == 'modprobe':
                #self.mResult['retcode'] = subprocess.check_call(self.mSubProcCmd)
                p = subprocess.Popen(' '.join(self.mSubProcCmd), stdout=subprocess.PIPE, shell=True)
                output, err = p.communicate()
                p_status = p.wait()
                self.mResult['retcode'] = p_status
                if err is None:
                    self.mResult['output'] = str(output[:], 'utf-8')
                else:
                    self.mResult['err'] = str(err[:], 'utf-8')
            else:
                self.mResult['retcode'] = subprocess.check_call(' '.join(self.mSubProcCmd), shell=True)
        else:
            raise ValueError('mainAction: No process commands')
        _logger.info('{} mainAction: retcode: {}'.format(type(self).__name__, self.mResult['retcode']))
        return self.mResult['retcode'] == 0 # 0 means success


class CheckBlockActionModeller(BaseActionModeller):
    def __init__(self):
        super().__init__()
        self.mIOs = []

    def _preAction(self):
        # setup the input/output objects
        # chunk_size in bytes default 1MB, i.e. 1048576
        if 'chunk_size' not in self.mParam or int(self.mParam['chunk_size']) < 0:
            self.mParam['chunk_size'] = 1048576 # 1MB

        if all(s in self.mParam for s in ['src_filename', 'tgt_filename']):
            if 'http://' in self.mParam['src_filename']:
                o = urlparse(self.mParam['src_filename'])
                self.mIOs.append(WebInputOutput(0, o.path))
            elif stat.S_ISBLK(os.stat(self.mParam['src_filename']).st_mode) or \
                stat.S_ISREG(os.stat(self.mParam['src_filename']).st_mode):
                self.mIOs.append(BlockInputOutput(self.mParam['chunk_size'], self.mParam['src_filename'], 'rb'))
            elif stat.S_ISCHR(os.stat(self.mParam['src_filename']).st_mode):
                _logger.error("cannot checksum on char device")

            if 'http://' in self.mParam['tgt_filename']:
                o = urlparse(self.mParam['tgt_filename'])
                self.mIOs.append(WebInputOutput(0, o.path))
            elif stat.S_ISBLK(os.stat(self.mParam['tgt_filename']).st_mode) or \
                stat.S_ISREG(os.stat(self.mParam['tgt_filename']).st_mode):
                self.mIOs.append(BlockInputOutput(self.mParam['chunk_size'], self.mParam['tgt_filename'], 'rb'))
            elif stat.S_ISCHR(os.stat(self.mParam['tgt_filename']).st_mode):
                _logger.error("cannot checksum on char device")
        else:
            raise ValueError('preAction: Neither src nor tgt file specified')

        if len(self.mIOs) > 0 and all(isinstance(ioobj, BaseInputOutput) for ioobj in self.mIOs):
            return True
        return False

    def _mainAction(self):
        # copy specified address range from src file to target file
        ret = False
        for ioobj in self.mIOs:
            if isinstance(ioobj, WebInputOutput):
                # read the content of the web url.md5
                md5 = ioobj.Read(0, 0).strip().decode()
                self.mResult.update({ioobj.mFilename[ioobj.mFilename.rfind('/') + 1:]: md5})
                ret = True
            elif isinstance(ioobj, BlockInputOutput):
                self.mResult.update({'bytes_read': 0})
                hasher = hashlib.md5()

                blksize = ioobj.getBlockSize()
                if self.mParam['chunk_size'] > blksize  and \
                    self.mParam['chunk_size'] % blksize == 0:
                    chunksize = int(self.mParam['chunk_size'])
                else:
                    chunksize = int(blksize)
                    ioobj.mChunkSize = chunksize

                if 'total_sectors' in self.mParam and int(self.mParam['total_sectors']) > 0:
                    totalsize = int(self.mParam['total_sectors']) * 512
                else:
                    totalsize = ioobj.getFileSize()

                if ioobj.mFilename == self.mParam['src_filename']:
                    if 'src_start_sector' in self.mParam and self.mParam['src_start_sector'] > 0:
                        startaddr = int(self.mParam['src_start_sector']) * 512
                    else:
                        startaddr = 0
                elif ioobj.mFilename == self.mParam['tgt_filename']:
                    if 'tgt_start_sector' in self.mParam and self.mParam['tgt_start_sector'] > 0:
                        startaddr = int(self.mParam['tgt_start_sector']) * 512
                    else:
                        startaddr = 0

                totalchunks = -(-totalsize // chunksize)
                # loop through the range of sectors and read from Block IO
                for addr in range (0, totalchunks):
                    data = ioobj.Read(startaddr + (addr * chunksize), 1)
                    #_logger.debug('ioobj:{} addr:{:#x} data len:{}'.format(ioobj.mFilename, startaddr + (addr * chunksize), len(data)))
                    self.mResult['bytes_read'] += len(data)
                    hasher.update(data)

                self.mResult.update({ioobj.mFilename: hasher.hexdigest()})
                ret = True

        # close the block device again
        for ioobj in self.mIOs:
            ioobj._close()
        del self.mIOs
        return ret



class QRCodeActionModeller(BaseActionModeller):
    def __init__(self):
        super().__init__()
        self.mIO = io.BytesIO()
        self.mErrLvl = 'L'
        self.mCapVer = 8
        self.mEncMode = 'binary'
        self.mImage = None
        self.mMailTo = ''

    def _preAction(self):
        # 'cmd': 'qrcode', 'mailto': 'youremail@yourdomain.com', 'dl_url': 'http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz', 'tgt_filename': './ubuntu.img'
        if all(s in self.mParam for s in ['dl_url', 'tgt_filename']):
            self.mMailTo = self.mParam['mailto'] if 'mailto' in self.mParam and len(self.mParam['mailto']) else 'rescue@technexion.com'
            self.mErrLvl = self.mParam['errlvl'] if 'errlvl' in self.mParam and self.mParam in ['L', 'M', 'Q', 'H'] else 'L'
            self.mEncMode = self.mParam['encmode'] if 'encmode' in self.mParam and self.mParam['encmode'] in ['numeric', 'kanji', 'binary', 'alphanumeric'] else 'binary'
            self.mImage = self.mParam['img_filename'] if 'img_filename' in self.mParam else 'tmp/qecode.svg'
            return True
        return False

    def _mainAction(self):
        try:
            # big_code = pyqrcode.create('0987654321', error='L', version=27, mode='binary')
            # big_code.png('code.png', scale=6, module_color=[0, 0, 0, 128], background=[0xff, 0xff, 0xcc])
            #strEmail = '<mailto:{}%3Fsubject=Flash%20Image%20Details&cc=recsue@technexion.com&body=Download%20URL:{}%0AStorage:{}%0A>'.format( \
            #            self.mMailTo, self.mParam['dl_url'], self.mParam['tgt_filename'])
            strEmail = 'MATMSG:TO:{};SUB:Rescue Image Details;BODY:Download URL:{}\nStorage:{};;'.format(self.mMailTo, self.mParam['dl_url'], self.mParam['tgt_filename'])
            # make sure we get appropriate size for our message content
            for ver, tbl in pyqrcode.tables.data_capacity.items():
                if tbl[self.mErrLvl][pyqrcode.tables.modes[self.mEncMode]] > len(strEmail):
                    self.mCapVer = ver
                    break
            # generate QR code and display on LED grid
            #code = pyqrcode.create(strEmail, error=self.mErrLvl, version=self.mCapVer, mode=self.mEncMode)
            code = pyqrcode.create(strEmail, error=self.mErrLvl, version=self.mCapVer, mode=self.mEncMode, encoding='ASCII')
            code.svg(self.mIO, scale=1, background="white") #, module_color="#7D007D")
            if self.mImage:
                code.svg(self.mImage, scale=8)
            self.mResult['svg_buffer'] = self.mIO.getvalue()[:] # copy the whole bytes
            return True

        except Exception as ex:
            raise IOError('mainAction error: {}'.format(ex))
        return False

    def _postAction(self):
        # clear the mIO
        if self.mIO:
            self.mIO.close()
        del self.mIO
        return True



if __name__ == "__main__":
    def __find_attr(self, key, dic):
        for k, v in dic.items():
            if k == key:
                yield v
            elif isinstance(v, dict):
                for result in self.__find_attr(key, v):
                    yield result

    def __flatten(value, key=''):
        ret = {}
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, dict):
                    ret.update(__flatten(v, k if len(key) == 0 else key+'|'+k))
                else:
                    ret[k if len(key) == 0 else key+'|'+k] = v
        return ret

    import sys
    _logger.setLevel(logging.DEBUG)

    if len(sys.argv) == 2:
        if sys.argv[1] == 'copy':
            model = CopyBlockActionModeller()
            actparam = {'src_filename': './ubuntu-16.04.xz', 'src_start_sector': 0, 'src_total_sectors': -1, \
                        'tgt_filename': './ubuntu.img', 'tgt_start_sector': 0}
            model.setActionParam(actparam)
            model.performAction()
        elif sys.argv[1] == 'erase':
            model = CopyBlockActionModeller()
            actparam = {'src_filename': '/dev/zero', \
                        'tgt_filename': '/dev/mmcblk2boot0'}
            model.setActionParam(actparam)
            model.performAction()
        elif sys.argv[1] == 'qmodel':
            query = QueryFileActionModeller()
            qryparam = {'src_filename': './model', 'src_start_line': 0, 'src_totallines': 5, 're_pattern': '\w+\ (\w+)-\w+'}
            query.setActionParam(qryparam)
            query.performAction()
            print(query.getResult())
        elif sys.argv[1] == 'qmmc':
            blk = QueryBlockDevActionModeller()
            blkparam = {'tgt_type': 'mmc'}
            blk.setActionParam(blkparam)
            blk.performAction()
            info = {}
            info.update(__flatten(blk.getResult()))
            for i in sorted(info):
                print('{0} ===> {1}'.format(i, info[i]))
        elif sys.argv[1] == 'webdl':
            dlmodel = WebDownloadActionModeller()
            dlparam = {'chunk_size': 65536, 'src_directory': '/pico-imx7/pi-050/',
                       'src_filename': 'ubuntu-16.04.xz', 'host_name': 'rescue.technexion.net', \
                       'host_protocol': 'http', 'tgt_filename': 'ubuntu-16.04.img', 'tgt_start_sector': 0}
            dlmodel.setActionParam(dlparam)
            dlmodel.performAction()
            print(dlmodel.getResult())
        elif sys.argv[1] == 'webqr':
            # python3 view.py {qrcode -u http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz -t ./ubuntu.img -i ./qrcode.svg}
            qrparam = {'cmd': 'qrcode', 'mailto': 'youremail@yourdomain.com', 'dl_url': 'http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz', 'tgt_filename': './ubuntu.img', 'img_filename': './qrcode.svg'}
            qrmodel = QRCodeActionModeller()
            qrmodel.setActionParam(qrparam)
            qrmodel.performAction()
            print(qrmodel.getResult())
        elif sys.argv[1] =='qweb':
            querywebmodel = QueryWebFileActionModeller()
            querywebparam = {'src_directory': '/pico-imx6/dwarf-hdmi/',
                             'host_name': 'http://rescue.technexion.net', }
            querywebmodel.setActionParam(querywebparam)
            querywebmodel.performAction()
            print(querywebmodel.getResult())
        elif sys.argv[1] == 'clrboot':
            flashmodel = CopyBlockActionModeller()
            flashparam = {'src_filename': '/dev/zero', 'tgt_filename': '/dev/mmcblk2boot0'}
            flashmodel.setActionParam(flashparam)
            flashmodel.performAction()
            print(flashmodel.getResult())
        elif sys.argv[1] == 'mmcboot':
            cfgmodel = ConfigMmcActionModeller()
            cfgparam = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', 'config_action': 'disable', 'boot_part_no': '1', 'send_ack': '1', 'target': '/dev/mmcblk2'}
            cfgmodel.setActionParam(cfgparam)
            cfgmodel.performAction()
            print(cfgmodel.getResult())
        elif sys.argv[1] == 'mmccsd':
            cfgmodel = ConfigMmcActionModeller()
            cfgparam = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'extcsd', 'config_action': 'read', 'target': '/dev/mmcblk2'}
            cfgmodel.setActionParam(cfgparam)
            cfgmodel.performAction()
            print(cfgmodel.getResult())
        elif sys.argv[1] == 'mmcreadonly':
            cfgmodel = ConfigMmcActionModeller()
            cfgparam = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', 'config_action': 'disable', 'boot_part_no': '1', 'target': '/dev/mmcblk2'}
            cfgmodel.setActionParam(cfgparam)
            cfgmodel.performAction()
            print(cfgmodel.getResult())
        elif sys.argv[1] == 'nicflags':
            nicmodel = ConfigNicActionModeller()
            # self.mParam['subcmd'] == 'nic' and self.mParam['config_action'] == 'get' and self.mParam['config_id'] == 'ifflags':
            nicparam = {'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifflags', 'config_action': 'get', 'target': 'enp3s0'}
            nicmodel.setActionParam(nicparam)
            nicmodel.performAction()
            print(nicmodel.getResult())
    exit()
