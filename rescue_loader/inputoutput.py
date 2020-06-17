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

# inputoutput:
# The python object specializes in input/output of different types of files
# e.g. regular file, block device, char device, web files, compressed file
# with embeded functionality to compress/decompress while read/write operation
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import stat
import fcntl
import mimetypes
import urllib.request
import urllib.response
import urllib.error
import socket
import logging
from io import IOBase

_logger = logging.getLogger(__name__)

# ============================================================
# Support for Compressed Files
# ============================================================
class CompressedFile (object):
    magic = None
    file_type = None
    mime_type = None

    def __init__(self, fname, mode):
        super().__init__()
        # mFile is an open file or file like object
        if 'r' in mode :
            rwMode = 'r' + 'b' if ('b' in mode) else 't'
        elif 'w' in mode:
            rwMode = 'w' + 'b' if ('b' in mode) else 't'
        self.mFilename = fname
        self.mMode = rwMode

    @classmethod
    def isMagic(cls, fname):
        try:
            with open(fname, 'rb') as f:
                f.seek(0)
                return f.read(1024).startswith((cls.magic,))
        except Exception:
            raise

    @classmethod
    def isFileType(cls, ftype):
        try:
            if cls.file_type in ftype:
                return True
        except Exception:
            raise
        return False

    def getFileHandle(self):
        pass

    def getOriginalSize(self):
        pass

    def comp(self, data):
        pass

    def decomp(self, data):
        pass

    def flush(self):
        pass

import tarfile
class TARFile (CompressedFile):
    """
    Working with tar archive files, supports gzip, bz2, and lzma compression
    no read/write but add/extract files into the tar file
    """
    magic = b'\x75\x73\x74\x61\x72'
    file_type = 'tar'
    mine_type = 'compressed/tar'

    @classmethod
    def isMagic(cls, fname):
        ret = False
        try:
            ret = tarfile.is_tarfile(fname)
        except Exception:
            return False
        return ret

    def getFileHandle(self):
        return tarfile.TarFile(self.mFilename, self.mMode)

import zipfile
class ZIPFile (CompressedFile):
    """
    Working with zip archive files, supports zlib, bz2, and lzma compression
    read/write files into the zip file
    """
    magic = b'\x50\x4b\x03\x04'
    file_type = 'zip'
    mime_type = 'compressed/zip'

    @classmethod
    def isMagic(cls, fname):
        ret = False
        try:
            ret = zipfile.is_zipfile(fname)
        except Exception:
            return False
        return ret

    def getFileHandle(self):
        return zipfile.ZipFile(self.mFilename, self.mMode)

import lzma
class XZFile (CompressedFile):
    """
    Working directly with xz files
    lzma.LZMAFile() supports io.BufferedIOBase interface
    """
    magic = b'\xFD\x37\x7A\x58\x5A\x00'
    file_type = 'xz'
    mine_type = 'compressed/xz'

    def __init__(self, fname, mode):
        super().__init__(fname, mode)
        self.xz_filters = [{'id': lzma.FILTER_DELTA, 'dist': 5}, \
                      {'id': lzma.FILTER_LZMA2, 'preset': 9 | lzma.PRESET_EXTREME},]
        self.mDecompR = None
        self.mCompR = None

    def getFileHandle(self):
        return lzma.LZMAFile(self.mFilename, self.mMode)

    def getOriginalSize(self):
        try:
            with open(self.mFilename, 'rb', 0) as f:
                # get end matter for uncompressed size parsing
                f.seek(-1024, 2)
                enddata = f.read(1024)
                return self.calcRec(enddata)
        except Exception as ex:
            _logger.error('{} (XZFile) calsize exception: {}'.format(type(self).__name__, ex))
            return 0

    def calcRec(self, endmatter):
        # get backsize from stream footer without crc
        backsize = int.from_bytes(endmatter[-8:-4], byteorder='little')
        if backsize == 0:
            raise BufferError('backsize should refer to index fields of at least 4 bytes')
        # get crc type and set number of crc bytes
        crctype = int.from_bytes(endmatter[-3:-2], byteorder='little')
        if crctype == 0x01: # CRC32
            crcsize = 4
        elif crctype == 0x04: # CRC64
            crcsize = 8
        elif crctype == 0x0A: # SHA256
            crcsize = 32
        # start counting backwards from the end of file to get index field
        # f.seek(-(8 + crcsize + (backsize*4)), 2);  f.read(backsize*4)
        indexdata = endmatter[-(8 + crcsize + (backsize*4)):-(8 + crcsize)]
        if (indexdata[0] == 0):
            return self.__decodeRec(int(indexdata[1]), indexdata[2:])

    def __decodeRec(self, numrec, records):
        ret = 0
        indexes = [0]
        uncmpsizes = []
        # find all index pointing to bytes less than 128, i.e. 0x80
        for i, b in enumerate(records):
            if not (b & 0x80):
                indexes.append(i+1)
        # split up all the numbers from records
        for start, stop in zip(indexes[:-1], indexes[1:]):
            uncmpsizes.append(records[start:stop])
        for num in uncmpsizes[1::2]: # loop even records
            for i, b in enumerate(num):
                ret += (b & 0x7f) << (i*7);
        return ret

    def comp(self, data):
        # incremental XZ/LMZA compression
        try:
            if self.mCompR is None:
                self.mCompR = lzma.LZMACompressor(format=lzma.FORMAT_XZ, filters=self.xz_filters) # dict_size=67108864,
            return self.mCompR.compress(data)
        except Exception as ex:
            _logger.error('{} (XZFile) lzma compress exception: {}'.format(type(self).__name__, ex))
            raise

    def decomp(self, data):
        # incremental XZ/LMZA decompression
        # read raw compressed data from filename given
        try:
            if self.mDecompR is None:
                self.mDecompR = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=100663296) # 111982830(103MB) 134217728(128MB)
            # decompress the read data and return uncompressed data
            return self.mDecompR.decompress(data)
        except lzma.LZMAError as err:
            _logger.error('{} (XZFile) lzma fail decompress within given memory limit: {}'.format(type(self).__name__, err))
            raise
        except Exception as ex:
            _logger.error('{} (XZFile) lzma decompress exception: {}'.format(type(self).__name__, ex))
            raise
        return 0

    def flush(self):
        try:
            if self.mCompR is None:
                self.mCompR = lzma.LZMACompressor(format=lzma.FORMAT_XZ, dict_size=67108864, filters=cls.xz_filters)
            return self.mCompR.flush()
        except Exception as ex:
            _logger.error('{} XZFile lzma compress flush exception: {}'.format(type(self).__name__, ex))
            raise
        return 0

import bz2
class BZ2File (CompressedFile):
    """
    Working directly with bz2 files
    bz2.BZ2File() supports io.BufferedIOBase interface
    """
    magic = b'\x42\x5a\x68'
    file_type = 'bz2'
    mime_type = 'compressed/bz2'

    def getFileHandle(self):
        return bz2.BZ2File(self.mFilename, self.mMode)

import gzip
class GZFile (CompressedFile):
    """
    Working directly with gzip files
    gzip.GzipFile() supports io.BufferedIOBase interface
    """
    magic = b'\x1f\x8b\x08'
    file_type = 'gz'
    mime_type = 'compressed/gz'

    def getFileHandle(self):
        return gzip.GzipFile(self.mFilename, self.mMode)



# ============================================================
# inputoutput base class for installer
# ============================================================
class BaseInputOutput(object):
    """
    BaseInputOutput
    """
    def __init__(self, filename, mode='rb+'):
        super().__init__()
        self.mHandle = None
        self.mFilename = filename
        self.mMode = mode
        self.mBuffer = 0 if 'b' in self.mMode else 1
        self._open()

    def _write(self, data, start):
        # should try python3 -u flag to get unbuffered writes for all file I/O
        try:
            if (self._open()):
                if 'b' in self.mMode:
                    # NOTE: we always seek from start of file
                    self.mHandle.seek(start, 0)
                    ret = self.mHandle.write(data)
                else:
                    # read up to start lines
                    self.mHandle.readlines(start)
                    self.mHandle.truncate()
                    ret = self.mHandle.writelines(data)
                # flush to disk straight away
                self.mHandle.flush()
                # data sync
                os.fdatasync(self.mHandle)
                return ret
        except Exception as ex:
            _logger.error('{} (Base) write exception: {}'.format(type(self).__name__, ex))
            raise
        return 0

    def _read(self, start, size):
        try:
            if (self._open()):
                if 'b' in self.mMode:
                    # # NOTE: we always seek from start of file
                    self.mHandle.seek(start, 0)
                    return self.mHandle.read(size) if (size > 0) else self.mHandle.read()
                else:
                    # change the behaviour to read from start line, and number of lines
                    self.mHandle.seek(0)
                    data = self.mHandle.readlines()
                    return data[start:start+size]  if (size > 0) else data[start:]
        except Exception as ex:
            _logger.error('{} (Base) read exception: {}'.format(type(self).__name__, ex))
            raise
        return 0

    def _open(self):
        if (self.mHandle is None) or (isinstance(self.mHandle, IOBase) and self.mHandle.closed):
            # if filehandle already exist, or mode is write or append
            try:
                if os.path.isdir(self.mFilename):
                    raise IOError('{} is a directory folder'.format(self.mFilename))
                # default buffering, 1 for text file, 0 for direct access
                self.mHandle = open(self.mFilename, mode=self.mMode, buffering=self.mBuffer)
                if any(s in self.mMode for s in ['w', 'a', '+']) and self.mHandle:
                    fcntl.flock(self.mHandle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _logger.debug('{} (Base) _open: {} mode:{} buffering:{}'.format(type(self).__name__, self.mFilename, self.mMode, self.mBuffer))
                return True
            except Exception as ex:
                _logger.error('{} (Base) open exception: {}'.format(type(self).__name__, ex))
                raise
        else:
            # already opened
            return True

    def _close(self):
        if (self.mHandle and (isinstance(self.mHandle, IOBase) and not self.mHandle.closed)):
            if any(s in self.mMode for s in ['w', 'a', '+']):
                fcntl.flock(self.mHandle, fcntl.LOCK_UN)
                # only flush and fsync files with write mode
                # metadata (owner, size, mtime, etc) sync
                self.mHandle.flush()
                os.fsync(self.mHandle)
            self.mHandle.close()
            _logger.debug('{} (Base) _close: {}'.format(type(self).__name__, self.mFilename))

    def isBinFile(self):
        try:
            # try open file in text mode
            with open(self.mFilename, 'tr') as self.mHandle:
                self.mHandle.readline()
                return False
        except:  # if fail then file is non-text (binary)
            return True

    def isHexData(self, data):
        try:
            int(data, 16)
        except:
            return False
        return True

    def getFileSize(self):
        """
        returns file size in bytes
        """
        statinfo = os.stat(self.mFilename)
        if int(statinfo.st_size) > 0:
            _logger.debug('{} (Base) {} - getFileSize: {}'.format(type(self).__name__, self.mFilename, statinfo.st_size))
            return int(statinfo.st_size)
        else:
            if self.mHandle:
                _logger.debug('{} (Base) {} - getFileSize: {}'.format(type(self).__name__, self.mFilename, os.lseek(self.mHandle.fileno(), os.SEEK_SET, os.SEEK_END)))
                return int(os.lseek(self.mHandle.fileno(), os.SEEK_SET, os.SEEK_END))
        return 0

    def getBlockSize(self):
        """
        returns block size in bytes
        """
        if self.mFilename:
            statinfo = os.stat(self.mFilename)
            _logger.debug('{} (Base) {} - getBlockSize: {}'.format(type(self).__name__, self.mFilename, statinfo.st_blksize))
            return int(statinfo.st_blksize)
        return 0

    def getFileType(self):
        return mimetypes.guess_type(self.mFilename)

    def getStat(self):
        if self.mFilename:
            statinfo = os.stat(self.mFilename)
            _logger.debug('{} (Base) {} - getStatInfo: {}'.format(type(self).__name__, self.mFilename, statinfo))
            return dict(zip('mode ino dev nlink uid gid size atime mtime ctime'.split(), statinfo))

    def Write(self, data, start):
        pass

    def Read(self, start, size):
        pass



class CompressInputOutput(BaseInputOutput):
    """
    CompressInputOutput
    """
    def __init__(self, filename, mode='ab+'):
        super().__init__(filename, mode)
        self.mCFHandle = None
        if stat.S_ISREG(os.stat(filename).st_mode):
            self.mCFHandle = self.__getCompressedFile()

    # factory function to create a suitable instance for accessing files
    def __getCompressedFile(self):
        for cls in (BZ2File, GZFile, XZFile, ZIPFile, TARFile):
            if cls.isMagic(self.mFilename):
                return cls(self.mFilename, self.mMode)
        return None

    def _write(self, data, start):
        """
        Overrides BaseInputOutput _write()
        """
        try:
            # compress first
            if self.mCFHandle:
                # compress the data first then write to target file
                compdata = self.mCFHandle.comp(data)
                return super()._write(compdata, start+len(compdata))
            else:
                return super()._write(data, start)
        except Exception as ex:
            _logger.error('{} (Comp) _write exception: {}'.format(type(self).__name__, ex))
        return 0

    def _read(self, start, size):
        """
        Overrides BaseInputOutput _read()
        """
        try:
            # read file blocks from source file first
            if self.mCFHandle:
                # then decompress
                return self.mCFHandle.decomp(super()._read(start, size))
            else:
                return super()._read(start, size)
        except Exception as ex:
            _logger.error('{} (Comp) _read exception: {}'.format(type(self).__name__, ex))
        return 0

    def _close(self):
        """
        Overrides _close()
        """
        try:
            if self.mCFHandle:
                _logger.debug('{} (Comp) _close: {}'.format(type(self).__name__, self.mCFHandle))
                if any(s in self.mMode for s in ['w', 'a']) and self.mHandle:
                    # FIXME: Check how to write meta data for all compress file types
                    # for XZFile, need to flush the compress file metadata at the end
                    super()._write(self.mCFHandle.flush(), self.getFileSize())
                del self.mCFHandle
            super()._close()
        except Exception:
            raise

    def getUncompressedSize(self):
        """
        returns uncompressed size in bytes
        """
        if self.mCFHandle:
            return self.mCFHandle.getOriginalSize()
        return 0

    def Write(self, data, start):
        try:
            return self._write(data, start)
        except Exception as ex:
            _logger.error('{} (Comp) Write() exception: {}'.format(type(self).__name__, ex))
            raise

    def Read(self, start, size):
        try:
            return self._read(start, size)
        except Exception as ex:
            _logger.error('{} (Comp) Read() exception: {}'.format(type(self).__name__, ex))
            raise



class BlockInputOutput(CompressInputOutput):
    """
    BlockInputOutput

    """
    def __init__(self, chunksize, filename, mode='rb+'):
        super().__init__(filename, mode)
        self.mChunkSize = chunksize
        _logger.debug('{} init() - chunksize:{}'.format(type(self).__name__, self.mChunkSize))

    def Write(self, chunkdata, byteoffset):
        """
        Overrides CompressInputOutput Write()
        writing raw binary chunkdata, (which is a string of bytes), also support
        a dictionary of { sector_num, binary_data } too.
        """
        try:
            return super().Write(chunkdata, byteoffset)
        except Exception as ex:
            _logger.error('{} Write() exception: {}'.format(type(self).__name__, ex))
            raise

    def Read(self, byteoffset, totalchunks):
        """
        Overrides CompressInputOutput Read()
        returning dictionary, but list of binary blocks is also as good
        """
        try:
            # convert byteoffset to byte byteoffset address, and size in bytes
            return super().Read(byteoffset, totalchunks * self.mChunkSize)
        except Exception as ex:
            _logger.error('{} Read() exception: {}'.format(type(self).__name__, ex))
            raise



class FileInputOutput(BaseInputOutput):
    """
    FileInputOutput

    """
    def __init__(self, filename, mode='rt+'):
        super().__init__(filename, mode)

    def Write(self, lines, startline=0):
        try:
            return self._write(lines, startline)
        except Exception:
            raise

    def Read(self, startline, numlines=0):
        try:
            # read only the lines of a file content
            return self._read(startline, numlines)
        except Exception:
            raise



class WebInputOutput(BaseInputOutput):
    """
    WebInputOutput
    """
    def __init__(self, chunksize, filename, mode='dl', host='http://rescue.technexion.net/'):
        self.mChunkSize = chunksize if (chunksize > 0) else 65536
        self.mHost = host
        self.mUrl = self.mHost.rstrip('/') + '/' + filename.lstrip('/')
        # will call to the overridden _open() which
        # handles our own web input(download, 'dl') output(upload, 'ul')
        super().__init__(filename, mode)
        # and the overridden _open() will be called first for WebInputOutput
        self.mCFHandle = self.__getCompressedFile()
        _logger.debug('{} open_url:{} handle:{} CFhandle:{}'.format(type(self).__name__, self.mUrl, self.mHandle, self.mCFHandle))

    # factory function to create a suitable instance for accessing files
    def __getCompressedFile(self):
        #self.mCFHandle = XZFile(filename, 'rb+')
        for cls in (BZ2File, GZFile, XZFile, ZIPFile, TARFile):
            if cls.isFileType(self.mFileType):
                return cls(self.mFilename, 'rb+')
        return None

    def _write(self, data, start):
        """
        Overrides _write() => Compress and upload
        """
        try:
            # FIXME: Upload to remote request
            pass
        except TypeError as err:
            _logger.error('{} _open ignore type error: {}'.format(type(self).__name__, err))
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as err:
            _logger.error('{} upload exception: {}'.format(type(self).__name__, err))
            raise
        return 0

    def _read(self, start, size):
        """
        Overrides _read() => Download from host and uncompress
        """
        retry = 3
        while retry:
            try:
                if self.mHandle:
                    # download from urllib.response
                    return self.mHandle.read(size) if (size > 0) else self.mHandle.read()
            except TypeError as err:
                _logger.error('{} _open ignore type error: {}'.format(self.__class__, err))
                break
            except (urllib.error.URLError, urllib.error.HTTPError):
                _logger.error('{} download exception: {}'.format(self.__class__, err))
                raise
            except (socket.timeout) as err:
                _logger.error('{} download time out exception: {}'.format(self.__class__, err))
                if retry > 1:
                    retry -= 1
                else:
                    raise
        return 0

    def _open(self):
        """
        Overrides _open()
        """
        try:
            if 'dl' in self.mMode:
                # For HTTP and HTTPS URLs, setup request
                # req = urllib.request.Request(self.mUrl) # no cgi data, no timeout
                # self.mHandle = urllib.request.urlopen(req)
                self.mHandle = urllib.request.urlopen(self.mUrl, None, 30) # timeout 30s
                if self.mHandle:
                    self.mWebHdrInfo = self.mHandle.info()
                    _logger.debug('{} Hdr Info: {}'.format(type(self).__name__, self.mWebHdrInfo))
                    if 'content-length' in self.mWebHdrInfo:
                        self.mFileSize = int(self.mWebHdrInfo['content-length'])
                    else:
                        self.mFileSize = 0
                    if 'content-type' in self.mWebHdrInfo:
                        self.mFileType = self.mWebHdrInfo['content-type']
            else:
                # For HTTP and HTTPS URLs, setup response to remote requester
                raise ConnectionError('Upload not supported yet')
#             if self.mCFHandle is None:
#                 raise IOError('Cannot open compressed file')
        except TypeError as err:
            _logger.error('{} _open ignore type error: {}'.format(type(self).__name__, err))
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as err:
            _logger.error('{} _open error: {}'.format(type(self).__name__, err))
            raise

    def _close(self):
        """
        Overrides _close()
        """
        try:
            if self.mCFHandle:
                if any(s in self.mMode for s in ['w', 'a']):
                    self.mCFHandle.flush()
                del self.mCFHandle
            if self.mHandle:
                self.mHandle.close()
            _logger.debug('{} _close: {}'.format(type(self).__name__, self.mUrl))
        except TypeError as err:
            _logger.error('{} _open ignore type error: {}'.format(type(self).__name__, err))
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as err:
            _logger.error('{} _close error: {}'.format(type(self).__name__, err))
            raise

    def Write(self, data, start):
        """
        uploading compressed data from raw data
        """
        try:
            if self.mCFHandle:
                # compress data and write/upload it
                return self._write(self.mCFHandle.comp(data), start)
            else:
                return self._write(data, start)
        except Exception as ex:
            _logger.error('{} Write() exception: {}'.format(type(self).__name__, ex))
            raise

    def Read(self, start, size):
        """
        return uncompressed download data
        """
        try:
            # read/download web file then decompress data
            if self.mCFHandle:
                return self.mCFHandle.decomp(self._read(start, size * self.mChunkSize))
            else:
                return self._read(start, size * self.mChunkSize)
        except Exception as ex:
            _logger.error('{} Read() exception: {}'.format(type(self).__name__, ex))
            raise

    def getHeaderInfo(self):
        """
        additional function to return header from webpage
        """
        return '\n'.join(str(i+': '+self.mWebHdrInfo[i]) for i in self.mWebHdrInfo)

    def getFileSize(self):
        """
        Overrides getFileSize
        """
        return self.mFileSize

    def getFileType(self):
        """
        Overrides getFileType
        """
        return self.mFileType

    def getUncompressedSize(self):
        """
        returns uncompressed size in bytes
        """
        # ask for end range of the xz file over the network
        # Create a request for the given URL.
        request = urllib.request.Request(self.mUrl)

        # Add the header to specify the range to download.
        start = self.getFileSize() - 512
        request.add_header('range', 'bytes={}-'.format(start))
        response = urllib.request.urlopen(request)

        # If a content-range header is present, partial retrieval worked.
        if 'content-range' in response.headers:
            # The header contains the string 'bytes', followed by a space, then the
            # range in the format 'start-end', followed by a slash and then the total
            # size of the page (or an asterix if the total size is unknown). Lets get
            # the range and total size from this.
            range, total = response.headers['content-range'].split(' ')[-1].split('/')

            # Print a message giving the range information.
            if total == '*':
                _logger.debug("{} Bytes {} of an unknown total were retrieved.".format(type(self).__name__, range))
            else:
                _logger.debug("{} Bytes {} of a total of {} were retrieved.".format(type(self).__name__, range, total))

            # And for good measure, lets check how much data we downloaded.
            endmatter = response.read()
            _logger.debug("{} Retrieved from {} data size: {} bytes in range {}".format(type(self).__name__, self.mUrl, len(endmatter), range))

            if self.mCFHandle:
                return self.mCFHandle.calcRec(endmatter)
        return 0



if __name__ == "__main__":
    def chunks(srcStart, tgtStart, totalBytes, chunkSize):
        # breaks up data into chunks
        parts = int(totalBytes / chunkSize) + (1 if (totalBytes % chunkSize) else 0)
        return [(srcStart + i * chunkSize, tgtStart + i) for i in range(parts)]

    import argparse
    parser = argparse.ArgumentParser(description='Process Arguments.')
    parser.add_argument('-c', '--config-file', dest='configfile', help='Specify the configuration file to load', metavar='FILE')
    parser.add_argument('-s', '--source', dest='sourcefile', help='Specify the source file to read', metavar='FILE')
    parser.add_argument('-t', '--target', dest='targetfile', help='Specify the target file to write', metavar='FILE')
    parser.add_argument('-u', '--url', dest='srcurl', help='Specify the target url to download', metavar='FILE')
    parser.add_argument('-r', '--readonly', dest='readonly', action='store_true', default=False, help='Specify read compress file only')
    parser.add_argument('-v', '--verbose', dest='verbose', default=False, help='Show more information')
    args = parser.parse_args()
    print(args)

    total = 0
    try:
        if args.sourcefile and args.targetfile:
            srcstat = os.stat(args.sourcefile)
            tgtstat = os.stat(args.targetfile)
            chunksize = 1048576

            print (srcstat.st_size, srcstat.st_blksize)
            # get files handle
            sio = BlockInputOutput(chunksize, args.sourcefile)
            print('calculated uncompressed size: {}'.format(sio.getUncompressedSize()))
#             tio = BlockInputOutput(args.targetfile)
#
            address = chunks(0, 0, int(srcstat.st_size), chunksize)
            print(len(address), address)
#
#             for (srcChunkNum, tgtChunkNum) in address:
#                 data = sio._read(srcChunkNum, chunksize)
#                 size = len(data)
#                 total += size
#                 written = tio._write(data, total)
#                 print('read: @{} size:{}, written: @{} size:{}'.format(hex(srcChunkNum), size, hex(tgtChunkNum), written))

#             #tio = os.open(args.targetfile, os.O_RDWR | os.O_DIRECT | os.O_SYNC | os.O_LARGEFILE)
            with open(args.targetfile, 'wb+', 0) as tfile:
                for (srcChunkNum, tgtChunkNum) in address:
                    if not args.readonly:
                        written = tfile.write(sio.Read(srcChunkNum, 1))
                        tfile.flush()
                        os.fsync(tfile.fileno())
                    else:
                        written = len(sio.Read(srcChunkNum, 1))
                    total += written
                    print('src addr: {} read bytes: {} written bytes: {}'.format(srcChunkNum, chunksize, written))

    except Exception as ex:
        print('Exception: {}'.format(ex))

    print('total uncompressed: {}'.format(total))

    if args.configfile:
        print (os.stat(args.configfile))
        fio = FileInputOutput(args.configfile)
        fdata = fio.Read(0)
        print (fdata)
        fio.Write(fdata, len(fdata))
        del fio

    total = 0
    if args.srcurl and args.targetfile:
        print(args.srcurl)
        chunksize = 65536
        wio = WebInputOutput(chunksize, args.srcurl)
        print(wio.getUncompressedSize())
        address = chunks(0, 0, wio.getFileSize(), chunksize)
        print(len(address), address)
        with open(args.targetfile, 'wb+', 0) as tfile:
                for (srcChunkNum, tgtChunkNum) in address:
                    if not args.readonly:
                        written = tfile.write(wio.Read(srcChunkNum, 1))
                        tfile.flush()
                        os.fsync(tfile.fileno())
                    else:
                        written = len(wio.Read(srcChunkNum, 1))
                    total += written
                    print('src addr: {} read bytes: {} written bytes: {}'.format(srcChunkNum, chunksize, written))

    print('total uncompressed: {}'.format(total))

    exit()
