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

# messenger:
# This library wraps dbus messaging into a python object
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# for SerialMessenger
import base64
import queue
import serial
import json
import pickle
import traceback
from threading import Thread, Event, ThreadError
from serial.threaded import LineReader, ReaderThread

# for DBusMessenger
import logging
_logger = logging.getLogger(__name__)

import dbus
from dbus.service import Object as DBusSrvObject
from dbus.mainloop.glib import DBusGMainLoop as DBusMainLoop
# For gobject:
#     from dbus.mainloop.glib import threads_init as lib_threads_init
# For gi.repository:
#     from dbus.mainloop.glib import Glib_threads_init as lib_thread_init
try:
    import gobject
except ImportError:
    _logger.error('Error Import gobject')
    try:
        from gi.repository import GLib
    except ImportError:
        _logger.error('Error Import GLib from gi.repository')
    else:
        dbus_main_loop = GLib.MainLoop
        loop_threads_init = GLib.threads_init
else:
    dbus_main_loop = gobject.MainLoop
    loop_threads_init = gobject.threads_init



#
# Serialization tools to serialize dictionaries to bytes and vice-versa
#
def binToDict(binCmd, serializer=pickle):
    dictCmd = None
    if isinstance(binCmd, bytes):
        if serializer == json:
            binCmd = ''.join(chr(int(x, 2)) for x in binCmd.split())
        dictCmd = serializer.loads(binCmd)
    return dictCmd

def dictToBin(dictCmd, serializer=pickle):
    binCmd = None
    if isinstance(dictCmd, dict):
        binCmd = serializer.dumps(dictCmd)
        if serializer == json:
            binCmd = ' '.join(format(ord(letter), 'b') for letter in binCmd)
    return binCmd



# ============================================================
#
# BaseMessenger
#
# base messenger class for communications between different
# installer software components
#
# ============================================================
class BaseMessenger(object):
    """
    BaseMessenger
    """
    def __init__(self, config):
        super().__init__()
        self.mConfig = {}
        self.mConfig.update(config)

    def sendMsg(self, msg):
        """
        To be overridden
        """
        pass

    def receiveMsg(self):
        """
        To be overridden
        """
        pass

    def hasValidConn(self):
        """
        To be overridden
        """
        pass

    def stop(self):
        """
        To be overridden
        """
        pass


class DbusMessenger(BaseMessenger, DBusSrvObject):
    """
    The DbusMessenger class that handles the DBus IPC messages
    """

    def __init__(self, config, cbExecHdl=None, cbStatusHdl=None, cbResultHdl=None, cbInterruptHdl=None):
        super().__init__(config)
        # set the dbus.mainloop.glib.DBusGMainLoop() as default event loop mechanism, but must threads_init() first
        loop_threads_init()
        # gobject.threads_init() # Must Do this first if use gobject.MainLoop()
        # GLib_threads_init() # Must Do this first if use GLib.MainLoop()
        DBusMainLoop(set_as_default=True)

        self.mCbExecHandler = cbExecHdl
        self.mCbStatusHandler = cbStatusHdl
        self.mCbResultHandler = cbResultHdl
        self.mCbInterruptHandler = cbInterruptHdl
        self.mIsServer = self.mConfig['IS_SERVER'] if ('IS_SERVER' in self.mConfig.keys()) else False
        self.__initialize()

    def __initialize(self):
        """
        initialize this object to the DBUS connection
        """
        # setup seesion bus
        self.mSessDBus = dbus.SessionBus()
        # get the dbus name for our app, and setup session bus name
        self.mBusName = dbus.service.BusName(self.mConfig['busname'], self.mSessDBus)
        # setup Dbus Server's obj path
        self.mObjPath = self.mConfig['srv_path']
        # both client and server require an actual loop to handle events, so, create a MainLoop() from PyGObject's GLib binding
        #self.mDBusLoop = gobject.MainLoop()
        #self.mDBusLoop = GLib.MainLoop()
        self.mDBusLoop = dbus_main_loop()
        if self.mIsServer:
            # call dbus.service.Object constructor with sessbus and obj path
            dbus.service.Object.__init__(self, self.mBusName, self.mObjPath)
        else:
            # get the server proxy object
            self.mServerObj = self.mSessDBus.get_object(self.mConfig['busname'], self.mObjPath)
            self.mSignal = self.mSessDBus.add_signal_receiver(handler_function=self.receiveMsg, \
                                                              signal_name='receive', \
                                                              path=self.mObjPath, \
                                                              dbus_interface=self.mConfig['ifacename'])

    def hasValidConn(self):
        if self.mIsServer:
            if self.connection:
                return True
        else:
            if self.mServerObj and self.mSignal:
                return True
        return False

    @dbus.service.method(dbus_interface="com.technexion.dbus.interface", in_signature='a{sv}', out_signature='b')
    def send(self, request):
        """
        provide sent(request) RPC call_method on the DBus server
        """
        _logger.debug('dbus i/f send method: callback to {} with {}'.format(self.mCbExecHandler.__name__, request['cmd'] if 'cmd' in request else request))
        return self.receiveMsg(request)

    @dbus.service.method(dbus_interface="com.technexion.dbus.interface", in_signature='', out_signature='a{sv}')
    def status(self):
        """
        provide status() RPC call_method on the DBus server
        """
        return self.getStatus()

    @dbus.service.method(dbus_interface="com.technexion.dbus.interface", in_signature='', out_signature='a{sv}')
    def result(self):
        """
        provide result() RPC call_method on the DBus server
        """
        return self.getResult()

    @dbus.service.method(dbus_interface="com.technexion.dbus.interface", in_signature='a{sv}', out_signature='b')
    def interrupt(self, param):
        """
        provide interrupt() RPC call_method on the DBus server
        """
        return self.setInterrupt(param)

    @dbus.service.signal(dbus_interface="com.technexion.dbus.interface", signature='a{sv}')
    def receive(self, response):
        """
        provide receive(response) RPC notify_signal on the DBus server
        """
        _logger.debug('dbus i/f trigger receive signal: {}'.format(response['cmd'] if 'cmd' in response else response))
        pass

    def run(self):
        # both client and server run the dbus with GLib.MainLoop()
        if self.mDBusLoop:
            self.mDBusLoop.run()

    def stop(self):
        # overridden: stop both server and client that uses a DBus Loop
        if self.mDBusLoop:
            self.mDBusLoop.quit()
        if not self.mIsServer and self.mSignal:
            self.mSignal.remove()

    def sendMsg(self, msg):
        """
        override sendMsg()
        API function to send message via DBus client
        """
        if isinstance(msg, dict):
            if self.mIsServer:
                # callback to receive() to signal DBus client with param
                self.receive(msg)
            else:
                # called to send param to DBus server
                if self.mServerObj:
                    self.mServerObj.send(msg)
                else:
                    raise ReferenceError('Unable to access DBUS exported object')
        else:
            raise TypeError('Message has to be packaged in a dictionary.')

    def receiveMsg(self, response):
        """
        override receiveMsg()
        - handles message received by DBus server's I/F send method,
          which also callback the self.mCbExecHandler(params)
        - callback signal handler fn for receiving DBus server's receive(response) signal
        """
        params = {}
        if callable(self.mCbExecHandler):
            # parse the serialized second string back to dict
            params.update(response)
            return self.mCbExecHandler(params)
        return False

    def setInterrupt(self, param):
        if isinstance(param, dict):
            if self.mIsServer:
                # called by dbus I/F interrupt method
                _logger.debug('dbus server i/f interrupt method: callback to {} with {}'.format(self.mCbInterruptHandler.__name__, param))
                if callable(self.mCbInterruptHandler):
                    return self.mCbInterruptHandler(param)
            else:
                # called by the CLI/WEB/GUI viewer to interrupt server jobs
                _logger.debug('dbus client calls to dbus i/f interrupt method: with {}'.format(param))
                if self.mServerObj:
                    return self.mServerObj.interrupt(param)
                else:
                    raise ReferenceError('Unable to access DBUS exported object')
        else:
            raise TypeError('Interrupt Param has to be packaged in a dictionary')

    def setStatus(self, status):
        if self.mIsServer:
            # called by the installer server to pass status to return to client
            # by triggering the receive(response) signal
            if isinstance(status, dict):
                retstatus = {}
                retstatus.update(status)
                self.sendMsg(retstatus)
            else:
                raise TypeError('Setting status must pass in a dictionary format')
        else:
            raise IOError("This method call is for dbus server only!")

    def getStatus(self):
        retStatus = {}
        if self.mIsServer:
            # called by dbus I/F status method
            _logger.debug('dbus server i/f status method: callback to {}'.format(self.mCbStatusHandler.__name__))
            if callable(self.mCbStatusHandler):
                retStatus.update(self.mCbStatusHandler())
                return retStatus
        else:
            # called by the CLI/WEB/GUI viewer to ask status from installer server
            _logger.debug('dbus client calls to dbus i/f status() method')
            if self.mServerObj:
                retStatus.update(self.mServerObj.status())
                return retStatus
            else:
                raise ReferenceError('Unable to access DBUS exported object')

    def setResult(self, result):
        if self.mIsServer:
            # called by the installer server to pass result to return to client
            # by triggering the receive(response) signal
            if isinstance(result, dict):
                retResult = {}
                retResult.update(result)
                self.sendMsg(retResult)
            else:
                raise TypeError('Setting result must pass in a dictionary format')
        else:
            raise IOError("This method call is for dbus server only!")

    def getResult(self):
        retResult = {}
        if self.mIsServer:
            # called by dbus I/F result method
            _logger.debug('dbus server i/f result method: callback to {}'.format(self.mCbResultHandler.__name__))
            if callable(self.mCbResultHandler):
                retResult.update(self.mCbResultHandler())
                return retResult
        else:
            # called by the CLI/WEB/GUI viewer to ask status from installer server
            _logger.debug('dbus client calls to dbus i/f result() method')
            if self.mServerObj:
                retResult.update(self.mServerObj.result())
                return retResult
            else:
                raise ReferenceError('Unable to access DBUS exported object')



# ============================================================
# Queue Thread
# ============================================================
class QueueThread(Thread):
    def __init__(self, q, mgr, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mQueue = q
        self.mMsger = mgr
        self._stopped = Event()
        self._stopped.clear()

    def run(self):
        """
        overridden - thread fn() to extract command dictionary from queue
        and send to receiveMsg() to be processed
        """
        while not self._stopped.is_set():
            try:
                dictCmd = self.mQueue.get_nowait()
                _logger.debug('get dictCmd from queue: {}'.format(dictCmd))
                self.mMsger.receiveMsg(dictCmd)
                self.mQueue.task_done()
            except queue.Empty:
                self._stopped.wait(1.0)

    def close(self):
        """ Stop the thread. """
        self._stopped.set()



class SerialLineReader(LineReader):

    def setQueue(self, q):
        self.mQ = q

    def connection_made(self, transport):
        super().connection_made(transport)
        _logger.info('serial: port opened')

    def handle_line(self, data):
        """Override Process one line here"""
        try:
            # read from the serial inputs, which was base64 decoded
            # parse the serial inputs from serial server
            response = binToDict(base64.urlsafe_b64decode(data))
            # put in message queue
            if isinstance(response, dict):
                if self.mQ:
                    _logger.debug('serial: read and add to queue: {}'.format({k: v for k, v in response.items() if k not in ('tgt_data', 'verbose')}))
                    self.mQ.put(response)
                else:
                    raise IOError('Error No Queue to store serial read')
            else:
                raise IOError('Error reading dictionary from SerialLineReader')
        except:
            raise

    def write_line(self, data):
        """
        Override write data to the transport. ``data`` is a dictionary of Unicode strings
        so the data dictionary is turned into bytes first and then base64 coded, finally
        the newline is applied before sending.
        """
        coded = dictToBin(data)
        if isinstance(coded, str):
            coded.encode(self.ENCODING, self.UNICODE_HANDLING)
        b64code = base64.urlsafe_b64encode(coded)
        _logger.debug('serial: write data: {}, base64: {}...'.format(data, b64code[:80].decode() if len(b64code) > 80 else b64code.decode()))
        # use of '+' is not the best choice but bytes does not support % or .format in py3 and we want a single write call
        self.transport.write(b64code + self.TERMINATOR)

    def connection_lost(self, exc):
        """Override Forget transport"""
        if exc:
            traceback.print_exc(exc)
        _logger.info('serial: port closed')



class SerialMessenger(BaseMessenger):
    """
    Mimic DBusMessenger
    For implementing a PC-Host version of rescue loader
    need guiclientd on the PC-host to connect with SerialMessenger to installerd here (on target board)
    """

    def __init__(self, config, cbExecHdl=None, cbStatusHdl=None, cbResultHdl=None, cbInterruptHdl=None):
        super().__init__(config)
        self.mIsServer = self.mConfig['IS_SERVER'] if ('IS_SERVER' in self.mConfig.keys()) else False
        self.mCbExecHandler = cbExecHdl
        self.mCbStatusHandler = cbStatusHdl
        self.mCbResultHandler = cbResultHdl
        self.mCbInterruptHandler = cbInterruptHdl
        self.mTransport = None
        self.mSerialLineReader = None
        self.mReaderThread = None
        self.mRetStatus = {}
        self.mRetResult = {}
        self.mRetStatusEvent = Event()
        self.mRetResultEvent = Event()
        self.mRetStatusEvent.clear()
        self.mRetResultEvent.clear()

        # Setup serial communication with queue to receive inputs commands from remote rescue loader
        #self.mSerial = serial.Serial()
        if self.mIsServer:
            serport = self.mConfig['srv_serial'] if 'srv_serial' in self.mConfig.keys() else '/dev/ttyGS0'
        else:
            serport = self.mConfig['cli_serial'] if 'cli_serial' in self.mConfig.keys() else '/dev/ttyACM0'
        serbaudrate = int(self.mConfig['baudrate']) if 'baudrate' in self.mConfig.keys() else 115200
        bytesize = int(self.mConfig['bytesize']) if 'bytesize' in self.mConfig.keys() else serial.EIGHTBITS # 5, 6, 7, 8
        parity = self.mConfig['partity'] if 'partity' in self.mConfig.keys() else serial.PARITY_NONE # 'N'one, 'E'ven, 'O'dd, 'M'ark, 'S'pace
        stopbits = float(self.mConfig['stopbit']) if 'stopbit' in self.mConfig.keys() else serial.STOPBITS_ONE # 1, 1.5, 2
        rtimeout = float(self.mConfig['timeout']) if 'timeout' in self.mConfig.keys() else 0 # None: block-read, 0: non-block read, xxx: timeout block read
        xonxoff = self.mConfig['xonxoff'] == 'True' if 'xonxoff' in self.mConfig.keys() else False # disable software flow control
        rtscts = self.mConfig['rtscts'] == 'True' if 'rtscts' in self.mConfig.keys() else False # disable hardware (RTS/CTS) flow control
        dsrdtr = self.mConfig['dsrdtr'] == 'True' if 'dsrdtr' in self.mConfig.keys() else False # disable hardware (DSR/DTR) flow control
        wtimeout = float(self.mConfig['write_timeout']) if 'write_timeout' in self.mConfig.keys() else 0 # None: block, 0: non-block, xxx: timeout block
        try:
            self.mQueue = queue.Queue()
            self.mQueueThread = QueueThread(self.mQueue, self, name='SerialQueueThread')
            # URL Handlers: rfc2217, socket, loop, hwgrep, spy, alt
            _logger.info('serial: port: {} baudrate: {}'.format(serport, serbaudrate))
            #self.mSerial = serial.Serial(port=serport, baudrate=serbaudrate, timeout=rtimeout, write_timeout=wtimeout)
            self.mSerial = serial.serial_for_url('spy://{}?file=/tmp/serial.log'.format(serport), \
                                                baudrate=serbaudrate, \
                                                bytesize=bytesize, \
                                                parity=parity, \
                                                stopbits=stopbits, \
                                                timeout=rtimeout, \
                                                xonxoff=xonxoff, \
                                                rtscts=rtscts, \
                                                dsrdtr=dsrdtr, \
                                                write_timeout=wtimeout)
        except (ValueError, serial.SerialException) as e:
            _logger.error('serial: constructor: {}'.format(e))
            raise e

    def run(self):
        # both client and server open the /dev/ttyXXX serial interface for communication
        if self.mReaderThread is None:
            try:
                # start a thread to read incoming serial communication and parse them into a queue item
                _logger.info('serial: start ReaderThread')
                self.mReaderThread = ReaderThread(self.mSerial, SerialLineReader)
                self.mReaderThread.setName('SerialLineReaderThread')
                self.mReaderThread.start()
                # Wait until connection/thread is set up and return the transport and protocol instances.
                # note: transport is ReaderThread() itself
                self.mTransport, self.mSerialLineReader = self.mReaderThread.connect()
                if self.mTransport != self.mReaderThread:
                    raise IOError('ReaderThread does not match returned Transport')
                self.mSerialLineReader.setQueue(self.mQueue)
                # start a thread to read from queue and process the command dictionary
                _logger.info('serial: start QueueThread')
                self.mQueueThread.start()
            except (IOError, RuntimeError, AssertionError, ThreadError) as e:
                _logger.error("Error open serial port: {}, e: {}".format(self.mReaderThread.getName(), e))
                raise
            except:
                raise

    def stop(self):
        # overridden - close the /dev/ttyXXX serial interface for both server and client
        if self.mQueueThread:
            _logger.info('serial: stop QueueThread')
            self.mQueueThread.close()
            self.mQueueThread.join()
        if self.mReaderThread:
            _logger.info('serial: stop ReaderThread')
            self.mReaderThread.close()
            self.mReaderThread.join()

    def sendMsg(self, msg):
        """
        override sendMsg()
        API function to send message via Serial communication
        """
        ret = False
        if self.mSerialLineReader:
            if isinstance(msg, dict):
                # call protocol's write_line() to send message to serial client
                self.mSerialLineReader.write_line(msg)
                ret = True
            else:
                raise TypeError('Message has to be packaged in a dictionary.')
        else:
            raise IOError('No Serial Line Reader')
        return ret

    def receiveMsg(self, response):
        """
        override receiveMsg()
        - called back by the QueueThread which constantly monitors message queue
        - handles message received from serial communication and put on the message queue,
        - if SerialMessenger server in installerd:
            calls back to self.mCbStatusHandler() if response is a simple {'status': 'query'} dictionary
                    and send status via self.sendMsg() back to client
            calls back to self.mCbResultHandler() if response is a simple {'result': 'query'} dictionary
                    and send status via self.sendMsg() back to client
            otherwise
            calls back to the self.mCbExecHandler(params) cbfn, i.e. opcontrol.__handleDBusMessage()
        - if SerialMessenger client in guiclientd:
            update the member self.mRetStatus and clear event so self.getStatus() can continue
            update the member self.mRetResult and clear event so self.getResult() can continue
        """
        if self.mIsServer:
            msg = {}
            msg.update(response)
            if 'status' in response and response['status'] == 'query':
                msg.update(self.getStatus())
                self.sendMsg(msg)
                return True
            if 'result' in response and response['result'] == 'query':
                msg.update(self.getResult())
                self.sendMsg(msg)
                return True
            if 'cmd' in response and (response['cmd'] == 'stop' or response['cmd'] == 'disconnect'):
                self.setInterrupt(response)
                return True
        else:
            if 'status' in response:
                self.setStatus(response)
            if 'result' in response:
                self.setResult(response)

        if callable(self.mCbExecHandler):
            # parse the serialized second string back to dict
            return self.mCbExecHandler(response)
        return False

    def setInterrupt(self, param):
        if isinstance(param, dict):
            if self.mIsServer:
                # called by dbus I/F interrupt method
                if callable(self.mCbInterruptHandler):
                    self.mCbInterruptHandler(param)
            else:
                # called by the CLI/WEB/GUI viewer to interrupt server jobs
                if self.mReaderThread:
                    self.sendMsg(param)
                    # no need to wait until serial server respond?
                else:
                    raise ReferenceError('Unable to access serial messenger to set interrupt')
        else:
            raise TypeError('Interrupt Param has to be packaged in a dictionary')

    def setStatus(self, status):
        """
        Called by opcontrol to set the status of worker's exectution status
        """
        if self.mIsServer:
            # called by the installerd to return status to client
            # by triggering the receive(response) signal
            if isinstance(status, dict):
                retstatus = {}
                retstatus.update(status)
                self.sendMsg(retstatus)
            else:
                raise TypeError('Setting status must pass in a dictionary format')
        else:
            self.mRetStatus.update(status)
            self.mRetStatusEvent.set()

    def getStatus(self):
        """
        For client side:
            Called by CLI/WEB/GUI viewer to getStatus from serial server
        For server side:
            Called by opcontrol's QueueThread to recvMsg() to get status
        """
        retStatus = {}
        if self.mIsServer:
            # called by dbus I/F status method
            _logger.debug('serial: getStatus method: callback to {}'.format(self.mCbStatusHandler.__name__))
            if callable(self.mCbStatusHandler):
                retStatus.update(self.mCbStatusHandler())
                return retStatus
        else:
            # called by the CLI/WEB/GUI viewer to ask status from installer server
            if self.mReaderThread:
                _logger.debug('serial: calls to serial server to getStatus via standard sendMsg(), wait until mStatusEvent is set()')
                self.sendMsg({'status': 'query'})
                # wait until status comes back from serial server
                self.mRetStatusEvent.wait()
                self.mRetStatusEvent.clear()
                return self.mRetStatus
            else:
                raise ReferenceError('Unable to access serial messenger to get status')

    def setResult(self, result):
        """ Called by opcontrol to set the status of worker's exectution result
        """
        if self.mIsServer:
            # called by the installer server to pass result to return to client
            # by triggering the receive(response) signal
            if isinstance(result, dict):
                retResult = {}
                retResult.update(result)
                self.sendMsg(retResult)
            else:
                raise TypeError('Setting result must pass in a dictionary format')
        else:
            self.mRetResult.update(result)
            self.mRetResultEvent.set()

    def getResult(self):
        retResult = {}
        if self.mIsServer:
            # called by dbus I/F result method
            if callable(self.mCbResultHandler):
                retResult.update(self.mCbResultHandler())
                return retResult
        else:
            # called by the CLI/WEB/GUI viewer to ask result from installer server
            if self.mReaderThread:
                self.sendMsg({'result': 'query'})
                # wait until status comes back from serial server
                self.mRetResultEvent.wait()
                self.mRetResultEvent.clear()
                return self.mRetResult
            else:
                raise ReferenceError('Unable to access serial messenger to get result')



class WebMessenger(BaseMessenger):
    """
    WebMessenger(BaseMessenger)
    """
    def __init__(self, config, cbExecHdl=None, cbStatusHdl=None, cbResultHdl=None, cbInterruptHdl=None):
        super().__init__(config)
        self.mCbExecHandler = cbExecHdl

    def run(self):
        pass

    def sendMsg(self, msg):
        pass

    def receiveMsg(self):
        return {}
