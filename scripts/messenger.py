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

import logging
import dbus
import gobject
#from gi.repository import GLib
from dbus.service import Object as DBusSrvObject

from dbus.mainloop.glib import DBusGMainLoop as DBusMainLoop
#from dbus.mainloop.qt import DBusQtMainLoop as DBusMainLoop
#from dbus.mainloop.glib import threads_init as GLib_threads_init

_logger = logging.getLogger(__name__)

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



class DbusMessenger(BaseMessenger, DBusSrvObject):
    """
    The DbusMessenger class that handles the DBus IPC messages
    """

    def __init__(self, config, cbExecHdl=None, cbStatusHdl=None, cbResultHdl=None, cbInterruptHdl=None):
        super().__init__(config)
        # set the dbus.mainloop.glib.DBusGMainLoop() as default event loop mechanism
        gobject.threads_init() # Must Do this first if use gobject.MainLoop()
        #GLib_threads_init() # Must Do this first if use GLib.MainLoop()
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
        # both client and server require an actual loop to handle events,
        # so, create a MainLoop() from PyGObject's GLib binding
        self.mDBusLoop = gobject.MainLoop()
        #self.mDBusLoop = GLib.MainLoop()
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
        # both server and client that uses a DBus Loop
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
                # call receive() to signal DBus client with param
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



class SocketMessenger(BaseMessenger):
    """
    SocketMessenger(BaseMessenger)
    """
    def __init__(self, config, cbhandle):
        super().__init__(config, cbhandle)

    def sendMsg(self, msg):
        pass

    def receiveMsg(self):
        return {}
