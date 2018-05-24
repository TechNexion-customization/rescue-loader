#!/usr/bin/env python3

import abc
import re
import os
import stat
import psutil
import pyudev
import subprocess
import logging
from argparse import ArgumentTypeError
from html.parser import HTMLParser

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
        self.mRecoverable = False

    def isRecoverable(self):
        return self.mRecoverable

    def getResult(self):
        return self.mResult

    def setActionParam(self, param):
        if isinstance(param, dict):
            if len(param) > 0:
                self.mParam.clear()
                self.mParam.update(param)
                _logger.debug('Model mParam: {}'.format(self.mParam))
        else:
            raise TypeError('Param must be a dictionary')
    
    def performAction(self):
        self.mResult.clear()
        ret = False
        try:
            ret = self._preAction()
            _logger.debug('_preAction(): {}'.format(ret))
            if (ret):
                ret = self._mainAction()
                _logger.debug('_mainAction(): {}'.format(ret))
                if(ret):
                    ret = self._postAction()
                    _logger.debug('_postAction(): {}'.format(ret))
        except Exception as ex:
            _logger.info('performAction exception: {}'.format(ex))
            ret = False
            raise
        finally:
            return ret

    def recoverAction(self):
        """
        To be overriden
        """
        # no need to recover
        return False

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



class CopyBlockActionModeller(BaseActionModeller):
    """
    Copy Block Action Model to copy blocks of files
    """

    def __init__(self):
        super().__init__()
        self.mIOs = []
        self.mOrigData = {}
    
    def recoverAction(self):
        # recover from the self.mOrigData
        try:
            self.mIOs[1].Write(self.mOrigData, self.mParam['src_start_sector'])
            return True
        except Exception:
            raise

    def _preAction(self):
        self.mResult['bytes_read'] = 0
        self.mResult['bytes_written'] = 0
        # setup the input/output objects
        # chunk_size in bytes default 1MB, i.e. 1048576
        chunksize = self.mParam['chunk_size'] if ('chunk_size' in self.mParam) else 1048576

        if all(s in self.mParam for s in ['src_filename', 'tgt_filename']):
            try:
                if stat.S_ISCHR(os.stat(self.mParam['src_filename']).st_mode) and stat.S_ISBLK(os.stat(self.mParam['tgt_filename']).st_mode):
                    # special case where source is a char device and target is a block device, e.g. dd if=/dev/zero of=/dev/mmcblk2boot0
                    self.mParam['chunk_size'] = 4096 #  self.mIOs[-1].getBlockSize()
                    self.mIOs.append(BlockInputOutput(self.mParam['chunk_size'], self.mParam['src_filename'], 'rb'))
                    self.mIOs.append(BlockInputOutput(self.mParam['chunk_size'], self.mParam['tgt_filename'], 'wb+'))
                    self.mParam['src_total_sectors'] = int(self.mIOs[-1].getFileSize() / self.mParam['chunk_size'])
                    self.mParam['src_start_sector'] = 0
                    self.mParam['tgt_start_sector'] = 0
                else:
                    # default mode is rb+
                    self.mIOs.append(BlockInputOutput(chunksize, self.mParam['src_filename']))
                    # setup different size params
                    filesize = self.mIOs[-1].getFileSize()
                    blksize = self.mIOs[-1].getBlockSize()
                    if (self.mParam['src_total_sectors'] == -1) or ('src_total_sectors' not in self.mParam):
                        self.mParam['src_total_sectors'] = int(filesize/blksize) + 0 if (filesize % blksize) else 1
                    self.mIOs.append(BlockInputOutput(chunksize, self.mParam['tgt_filename'], 'wb+'))
            except Exception as ex:
                _logger.error('Cannot create block inputoutput: {}'.format(ex))
                raise
#             mode = 'rb+'
#             while True:
#                 try:
#                     # default mode is rb+, if failed, retry to open with 'wb+' mode
#                     self.mIOs.append(BlockInputOutput(chunksize, self.mParam['tgt_filename'], mode))
#                 except FileNotFoundError as err:
#                     # retry with wb+ mode to create the file and write to
#                     # offset in the file, append mode only append at the end
#                     _logger.error('Target file does not exist, re-try with \'wb+\' mode: {}'.format(err))
#                     mode = 'wb+'
#                     continue
#                 except PermissionError as err:
#                     _logger.error('No permission to access target file: {}'.format(err))
#                     raise
#                 except Exception as ex:
#                     _logger.error('pre-action exception: {}'.format(ex))
#                     raise
#                 else:
#                     break
        else:
            raise ArgumentTypeError('No src or tgt file specified')

        if len(self.mIOs) > 0 and all(isinstance(ioobj, BaseInputOutput) for ioobj in self.mIOs):
            return True
        return False

    def _mainAction(self):
        # TODO: copy specified address range from src file to target file
        try:
            if all(s in self.mParam for s in ['src_start_sector', 'src_total_sectors', 'tgt_start_sector']):
                chunksize = self.mParam['chunk_size'] if ('chunk_size' in self.mParam) else 1048576
                blksize = self.mIOs[0].getBlockSize()
                srcstart = self.mParam['src_start_sector'] * blksize
                tgtstart = self.mParam['tgt_start_sector'] * blksize
                totalbytes = self.mParam['src_total_sectors'] * blksize
                self.mResult['total_size'] = totalbytes
                # sector addresses of a very large file for looping
                address = self.__chunks(srcstart, tgtstart, totalbytes, chunksize)
                _logger.debug('list of addresses to copy: {}'.format(address))
                if len(address) > 1:
                    for (srcaddr, tgtaddr) in address:
                        self.__copyChunk(srcaddr, tgtaddr, 1)
                else:
                    self.__copyChunk(srcstart, \
                                     tgtstart, \
                                     totalbytes)
                return True
            else:
                raise ArgumentTypeError('Not specified source/target start sector, or total sectors')
        except Exception as ex:
            _logger.error('main-action exception: {}'.format(ex))
            raise
        return False
    
    def _postAction(self):
        for ioobj in self.mIOs:
            ioobj._close()
        del self.mOrigData
        return True

    def __copyChunk(self, srcaddr, tgtaddr, numChunks):
        try:
            # read from target first
            #origdata, origsize = self.mIOs[1].Read(tgtaddr, chunksize)
            #self.mOrigData.update(origdata)
            # if read something back, then set recoverable
            #self.mRecoverable = True if len(self.mOrigData) > 0 else False
            # read src and write to the target
            data = self.mIOs[0].Read(srcaddr, numChunks)
            self.mResult['bytes_read'] += len(data)
            written = self.mIOs[1].Write(data, self.mResult['bytes_written'])
            _logger.debug('read: @{} size:{}, written: @{} size:{}'.format(hex(srcaddr), len(data), hex(tgtaddr), written))
            # write should return number of bytes written
            if (written > 0):
                self.mResult['bytes_written'] += written
            del data # hopefully this would clear the write data buffer
        except:
            raise

    def __chunks(self, srcstart, tgtstart, totalbytes, chunksize):
        # breaks up data into blocks, with source/target sector addresses
        parts = int(totalbytes / chunksize) + (1 if (totalbytes % chunksize) else 0)
        return [(srcstart+i*chunksize, tgtstart + i*chunksize) for i in range(parts)]



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
        if self.mIO is None and 'src_filename' in self.mParam:
            try:
                self.mIO = FileInputOutput(self.mParam['src_filename'], 'rt')
                return True
            except Exception:
                raise
        else:
            if isinstance(self.mIO, FileInputOutput):
                return True
            raise ReferenceError('No File Input Output')
        return False
    
    def _mainAction(self):
        # read the file, and return read lines
        # TODO: should implement writing files in the future
        try:
            if all(s in self.mParam for s in ['src_start_line', 'src_totallines']):
                data = self.mIO.Read(self.mParam['src_start_line'], self.mParam['src_totallines'])
            elif 'src_start_line' in self.mParam and not 'src_totallines' in self.mParam:
                # only src_start_line, start from start line and read rest
                data = self.mIO.Read(self.mParam['src_start_line'])
            elif 'src_total_lines' in self.mParam:
                # only src_total_lines, read from start with total lines
                data = self.mIO.Read(0, self.mParam['src_total_lines'])
            else:
                # no src_start_line and no src_totallines, start from beginning and read all
                data = self.mIO.Read(0)
            _logger.debug('read data: {}'.format(data))
            self.mResult['lines_read'] += len(data)
            self.mResult.update({'file_content': data})
            return True
        except Exception:
            raise
        return False
    
    def _postAction(self):
        if 're_pattern' in self.mParam:
            # if there is a regular express pattern passed in, return the
            # found regular express pattern
            p = re.compile(self.mParam['re_pattern'], re.IGNORECASE)
            for line in self.mResult['file_content']:
                m = p.match(line)
                if m:
                    _logger.debug('from pattern {} found_match: {}'.format(self.mParam['re_pattern'], m.groups()))
                    self.mResult['found_match'] = ','.join([g for g in m.groups()])
        # clear the mIO
        del self.mIO
        return True



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
            _logger.debug('controllers: {}\ndisks: {}\npartitions: {}'.format(self.mCtrls, self.mDisks, self.mPartitions))
            if len(self.mPartitions) > 0 and len(self.mDisks) > 0 and len(self.mCtrls) > 0:
                return True
        else:
            return False

    def _mainAction(self):
        # check the actparams against the udev info
        # find self.mParam['tgt_type'] from ctrller's attributes('type') or driver()
        for o in self.mCtrls:
            _logger.debug('tgt_type: {}, attributes: {}, driver: {}'.format(self.mParam['tgt_type'], self.__getDevAttributes(o).values(), o.driver))
            if (self.mParam['tgt_type'] in self.__getDevAttributes(o).values() \
                or self.mParam['tgt_type'] == o.driver):
                _logger.debug('found controller: {}'.format(o))
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
                                               'id_serial': d.get('ID_SERIAL'), \
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
        # setup options, chunk_size in bytes default 64KB, i.e. 65535
        chunksize = self.mParam['chunk_size'] if ('chunk_size' in self.mParam) else 65535
        srcPath = '/rescue/' + self.mParam['src_directory'].strip('/') + '/' + self.mParam['src_filename'].lstrip('/')
        host = self.mParam['host_name'] if ('host_name' in self.mParam) else 'rescue.technexion.net'
        protocol = self.mParam['host_protocol'] if ('host_protocol' in self.mParam) else 'http'
        dlhost = protocol.rstrip('://') + '://' + host.rstrip('/')
        _logger.debug('chunksize: {}, srcPath: {}, host: {}'.format(chunksize, srcPath, dlhost))

        # setup the input/output objects
        if 'tgt_filename' in self.mParam:
            try:
                self.mIOs.append(WebInputOutput(chunksize, srcPath, host=dlhost))
                self.mIOs.append(BlockInputOutput(chunksize, self.mParam['tgt_filename'], 'wb+'))
            except Exception as ex:
                _logger.error('Cannot create web inputoutput: {}'.format(ex))
                raise
        else:
            raise ArgumentTypeError('No tgt file specified')

        if len(self.mIOs) > 0 and all(isinstance(ioobj, BaseInputOutput) for ioobj in self.mIOs):
            return True
        return False

    def _mainAction(self):
        # copy specified address range from downloaded src file to target file
        try:
            chunksize = self.mParam['chunk_size'] if ('chunk_size' in self.mParam) else 65535
            totalbytes = self.mIOs[0].getFileSize()
            self.mResult['total_uncompressed'] = self.mIOs[0].getUncompressedSize()
            srcstart = 0
            tgtstart = self.mParam['tgt_start_sector']

            # sector addresses of a very large file for looping
            if totalbytes > 0:
                address = self.__chunks(srcstart, tgtstart, totalbytes, chunksize)
            else:
                raise IOError('There is 0 Total Bytes to download')
            _logger.debug('list of addresses to copy: {}'.format(address))
            if len(address) > 1:
                for (srcaddr, tgtaddr) in address:
                    self.__copyChunk(srcaddr, tgtaddr, 1)
            else:
                self.__copyChunk(srcstart, tgtstart, totalbytes)
            return True
        except Exception as ex:
            _logger.error('main-action exception: {}'.format(ex))
            raise
        return False

    def _postAction(self):
        for ioobj in self.mIOs:
            ioobj._close()
#        del self.mOrigData
        return True

    def __copyChunk(self, srcaddr, tgtaddr, numChunks):
        try:
            # read from target first
            #origdata, origsize = self.mIOs[1].Read(tgtaddr, numChunks)
            #self.mOrigData.update(origdata)
            # if read something back, then set recoverable
            #self.mRecoverable = True if len(self.mOrigData) > 0 else False
            # read src and write to the target
            data = self.mIOs[0].Read(srcaddr, numChunks)
            self.mResult['bytes_read'] += len(data)
            written = self.mIOs[1].Write(data, self.mResult['bytes_written'])
            _logger.debug('read: @{} size:{}, written: @{} size:{}'.format(hex(srcaddr), len(data), hex(self.mResult['bytes_written']), written))
            # write should return number of bytes written
            if (written > 0):
                self.mResult['bytes_written'] += written
            del data # hopefully this would clear the write data buffer
        except Exception:
            raise

    def __chunks(self, srcstart, tgtstart, totalbytes, chunksize):
        # breaks up data into blocks, with source/target sector addresses
        parts = int(totalbytes / chunksize) + (1 if (totalbytes % chunksize) else 0)
        return [(srcstart+i*chunksize, tgtstart + i*chunksize) for i in range(parts)]

class QueryWebFileActionModeller(BaseActionModeller):
    """
    Query Action Model to query file information on a website
    """

    def __init__(self):
        super().__init__()
        self.mIO = None

    def _preAction(self):
        self.mResult['lines_read'] = 0
        self.mResult['lines_written'] = 0
        if all(s in self.mParam for s in ['host_name', 'src_directory']):
            if ('host_name' in self.mParam) and self.mParam['host_name'].lower().startswith('http'):
                self.mWebHost = self.mParam['host_name']
            else:
                self.mWebHost = 'http://rescue.technexion.net'
            if ('src_directory' in self.mParam):
                if self.mParam['src_directory'] == '/':
                    self.mSrcPath = '/rescue/'
                else:
                    if self.mParam['src_directory'].endswith('/'):
                        self.mSrcPath = '/rescue/' + self.mParam['src_directory'].strip('/') + '/'
                    else:
                        self.mSrcPath = '/rescue/' + self.mParam['src_directory'].lstrip('/')
            # setup the web input output
            if self.mIO is None:
                try:
                    self.mIO = WebInputOutput(0, self.mSrcPath, host=self.mWebHost)
                except Exception:
                    _logger.error('Cannot create WebInputOutput with {}, {}'.format(self.mSrcPath, self.mWebHost))
                    raise
            return True if isinstance(self.mIO, WebInputOutput) else False
        else:
            return False

    def _mainAction(self):
        # read the file, and return read lines
        # TODO: should implement writing files in the future
        try:
            _logger.debug('File Type: {}'.format(self.mIO.getFileType()))
            if 'html' in self.mIO.getFileType():
                webpage = self.mIO.Read(0, 0)
                # parse the web pages
                dctFiles = self.__parseWebPage(webpage)
                if len(dctFiles) > 0:
                    self.mResult['file_list'] = dctFiles
                    self.mResult['lines_read'] += len(webpage)
                    return True
            elif 'xz' in self.mIO.getFileType():
                self.mResult['header_info'] = self.mIO.getHeaderInfo()
                self.mResult['file_type'] = self.mIO.getFileType()
                self.mResult['total_size'] = self.mIO.getFileSize()
                self.mResult['total_uncompressed'] = self.mIO.getUncompressedSize()
                return True
            else:
                raise IOError('Cannot read none text base web files')
        except Exception as ex:
            _logger.error('Exception: {}'.format(ex))
            raise
        return False

    def _postAction(self):
        # clear the mIO
        del self.mIO
        return True

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
            _logger.debug('QueryLocalFile: self.mSrcPath: {}'.format(self.mSrcPath))
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
                                    del self.mIO
                                    self.mIO = None
                                else:
                                    self.mResult['file_list'].update({file: {'file_name': file, \
                                                                             'file_path': os.path.join(dirpath, file)}})
                            except Exception:
                                _logger.error('Cannot create BlockInputOutput with {}'.format(self.mSrcPath))
                                raise
                        _logger.debug('QueryLocalFile: {}: {}'.format(file, os.path.join(dirpath, file)))
            return True
        except Exception as ex:
            _logger.error('Exception: {}'.format(ex))
            raise
        return False



class ConfigMmcActionModeller(BaseActionModeller):
    """
    # Check for emmc boot sequence
    if 'androidthings' in self.mPick['os']:
        subprocess.check_call(['mmc', 'bootpart', 'enable', '1', '1', '/dev/mmcblk2'])
    else:
        subprocess.check_call(['mmc', 'bootpart', 'enable', '0', '1', '/dev/mmcblk2'])
     or subprocess.check_call(['mmc', 'bootpart', 'disable', '1', '1', '/dev/mmcblk2'])
    """
    def __init__(self):
        super().__init__()
        self.mIO = None
        self.mResult['retcode'] = 0
        self.mSubProcCmd = []

    def _preAction(self):
        if all(s in self.mParam for s in ['subcmd', 'target', 'config_id', 'config_action']):
            # subprocess.check_call(['mmc', 'bootpart', 'enable', '0', '1', '/dev/mmcblk2'])
            if self.mParam['subcmd'] == 'mmc' and any(value in self.mParam['config_id'] \
                                                      for value in ['bootpart', 'bootbus', 'bkops', 'cache', 'csd', 'cid', 'extcsd', \
                                                                    'enh_area', 'hwreset', 'rpmb', 'scr', 'ffu', 'sanitize', 'status', \
                                                                    'write_reliability', 'writeprotect']):
                self.mSubProcCmd.append('mmc')
            else:
                self.mSubProcCmd.append('echo')

            if stat.S_ISBLK(os.stat(self.mParam['target']).st_mode):
                if self.mParam['config_id'] == 'bootpart':
                    self.mSubProcCmd.extend([self.mParam['config_id'], self.mParam['config_action'], \
                                             self.mParam['boot_part_no'], self.mParam['send_ack'], self.mParam['target']])
                elif self.mParam['config_id'] == 'readonly':
                    if 'boot' in self.mParam['target']:
                        tgtfile = self.mParam['target'][:self.mParam['target'].find('boot')].replace('/dev/', '')
                    else:
                        tgtfile = self.mParam['target'].replace('/dev/', '')

                    self.mSubProcCmd.extend(['0' if self.mParam['config_action'] == 'disable' else '1',
                                             '>', '/sys/block/' + tgtfile + 'boot' + str(int(self.mParam['boot_part_no']) - 1) + '/force_ro'])
                _logger.info('_preAction: subprocess cmd: {}'.format(self.mSubProcCmd))
                return True
        return False

    def _mainAction(self):
        try:
            # do something to query mmc
            if len(self.mSubProcCmd):
                if self.mSubProcCmd[0] == 'mmc':
                    self.mResult['retcode'] = subprocess.check_call(self.mSubProcCmd)
                else:
                    self.mResult['retcode'] = subprocess.check_call(' '.join(self.mSubProcCmd), shell=True)
                _logger.info('_mainAction: retcode: {}'.format(self.mResult['retcode']))
                return True
        except Exception as ex:
            _logger.error('Exception: {}'.format(ex))
            raise
        return False



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
        elif sys.argv[1] == 'mmcreadonly':
            cfgmodel = ConfigMmcActionModeller()
            cfgparam = {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', 'config_action': 'disable', 'boot_part_no': '1', 'target': '/dev/mmcblk2'}
            cfgmodel.setActionParam(cfgparam)
            cfgmodel.performAction()
            print(cfgmodel.getResult())
    exit()
