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

# operation control:
# This library contains the main mechanism that queue client's request
# into a job queue, and ensure mutual exclusive execution of each job
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================
# installer operation controller daemon
#
# To start your installer environment, type:
#
# systemctl start installer.service
#
# ============================================================

import resource
import logging
import time
import queue
from threading import Thread
from defconfig import DefConfig, SetupLogging, IsATargetBoard
from ophandle import FlashOperationHandler, \
                     InfoOperationHandler, \
                     DownloadOperationHandler, \
                     ConfigOperationHandler, \
                     QRCodeOperationHandler

from messenger import DbusMessenger, WebMessenger

SetupLogging('/tmp/installer_srv.log')
# get the handler to the current module
_logger = logging.getLogger(__name__)



class Worker(object):

    def __init__(self, cmd, handler, cbSetResult):
        super().__init__()
        self.mCmd = {}
        self.mCmd.update(cmd)
        self.mHandler = handler
        self.mCbSetResult = cbSetResult

    def doWork(self):
        _logger.debug("worker: perform command: {}".format(self.mCmd))
        # wait for the handler's event to be set
        if callable(self.mHandler.waitEvent):
            self.mHandler.waitEvent()
        # return {'status':'processing', ...} before performOperation
        result = {}
        result.update(self.mCmd)
        result.update({'status': 'processing'})
        self.mCbSetResult(result)
        # perform handler's operation
        if callable(self.mHandler.performOperation):
            self.mHandler.performOperation(self.mCmd)
        # gets the results no matter if succeeded or failed
        if callable(self.mCbSetResult) and callable(self.mHandler.getStatus) and callable(self.mHandler.getResult):
            result.update(self.mHandler.getStatus())
            result.update(self.mHandler.getResult())
            _logger.debug('worker: return result: {}'.format(result))
            self.mCbSetResult(result)
        # set the handler's event no matter what result is produced
        if callable(self.mHandler.setEvent):
            self.mHandler.setEvent()



class WorkerThread(Thread):
    def __init__(self, q):
        super().__init__()
        self.mQueue = q
        self.mWorker = None

    def getWorkerHandler(self):
        if self.mWorker and self.mWorker.mHandler:
            return self.mWorker.mHandler
        return None

    def run(self):
        while True:
            try:
                # get and do the work
                self.mWorker = self.mQueue.get_nowait()
                self.mWorker.doWork()
                self.mQueue.task_done()
            except queue.Empty:
                time.sleep(1)
            finally:
                self.mWorker = None



# ============================================================
#
# Operation Controller
#
# The default daemon running as a system service,
# controls the flow of the Model View Control for the installer.
#
# ============================================================
class OpController(object):
    """
    OpController

    """
    def __init__(self, conf):
        super().__init__()
        # initialize a DbusMessenger for sending and receiving messages
        setting = conf.getSettings(flatten=True)
        setting.update({'IS_SERVER': True})
        self.mMsger = []
        self.mMsger.append(DbusMessenger(setting, \
                                         self.__handleDBusMessage, \
                                         self.__handleGetStatus, \
                                         self.__handleGetResult, \
                                         self.__handleUserInterrupt))

        # initialize an array to hold BaseOpHandlers
        self.mOpHandlers = []
        # initialize a queue to hold all the worker to perform the command job
        self.mQueue = queue.Queue()
        # using 2+ threads to handle the worker queue
        self.mThreads = [WorkerThread(self.mQueue), WorkerThread(self.mQueue)]
        for thrd in self.mThreads:
            thrd.start()

    def run(self):
        # setup Operation Handlers from the defconfig
        self.mOpHandlers.append(FlashOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(InfoOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(DownloadOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(ConfigOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(QRCodeOperationHandler(self.__sendUserRequest))
        # finally run the dbusmessenger server, because dbus's run is blocking
        for mgr in self.mMsger:
            if isinstance(mgr, DbusMessenger):
                mgr.run()

    def __findOpHandler(self, cmds):
        # find the OpHandle for executing command
        for ophdler in self.mOpHandlers:
            if ophdler.isOpSupported(cmds):
                return ophdler
        return None

    def __handleDBusMessage(self, msg):
        if isinstance(msg, dict):
            # find the correct OpHandler
            ophandler = self.__findOpHandler(msg)
            if ophandler:
                _logger.info("found a handler: {} and queue a worker with msg/cmd to perform operation later".format(type(ophandler).__name__))
                self.mQueue.put(Worker(msg, ophandler, self.setRetResult))
                status = {}
                status.update(msg)
                status.update({'status': 'pending'})
                for msger in self.mMsger:
                    msger.setStatus(self.__flatten(status))
                return True
        return False

    def __handleGetResult(self):
        # find the WorkerThread which has taken worker from the queue and called doWork().
        result = {}
        for thrd in self.mThreads:
            thWkrHdlr = thrd.getWorkerHandler()
            if thWkrHdlr and callable(thWkrHdlr.getResult):
                _logger.debug('callback to get result from handler: {} of {} result: {}'.format(thWkrHdlr, thrd.name, thWkrHdlr.getResult()))
                result.update(self.__flatten(thWkrHdlr.getResult()))
        return result

    def __handleGetStatus(self):
        # find the WorkerThread that has taken worker from the queue and called doWork().
        status = {'status': 'idle'}
        for thrd in self.mThreads:
            thWkrHdlr = thrd.getWorkerHandler()
            if thWkrHdlr and callable(thWkrHdlr.getStatus):
                _logger.debug('callback to get status from handler: {} of {} status:{}'.format(thWkrHdlr, thrd.name, thWkrHdlr.getStatus()))
                status.update(self.__flatten(thWkrHdlr.getStatus()))
        return self.__flatten(status)

    def __handleUserInterrupt(self, param):
        """
        Manage user interrupt from client/viewer
        - loop through worker threads to find all the ophandlers and
          if ophandler has updateUserResponse and if callable, call it
        """
        for thrd in self.mThreads:
            thWkrHdlr = thrd.getWorkerHandler()
            if thWkrHdlr and callable(thWkrHdlr.updateUserResponse):
                _logger.info("found handler: {} of {} to handle user_response/interrupt: {}".format(thWkrHdlr, thrd.name, param))
                # call handler's updateUserResponse() api with param, and wait for handler to quit itself
                thWkrHdlr.updateUserResponse(param)

    def __sendUserRequest(self, req):
        """
        Callback Handles for requesting more user inputs from the opOperationHandler
        - send the user req by triggering receive signal, then user should interrupt
          by calling the DBus interrupt i/f method
        """
        userReq = {}
        if isinstance(req, dict):
            userReq.update(req)
            # signal client/viewer with receive signal with request to get user input
            for msger in self.mMsger:
                msger.sendMsg(self.__flatten(userReq))

    def setRetResult(self, result):
        if isinstance(result, dict):
            for msger in self.mMsger:
                msger.setResult(self.__flatten(result))

    def __flatten(self, value, key=''):
        ret = {}
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, dict):
                    ret.update(self.__flatten(v, k if len(key) == 0 else key+'|'+k))
                else:
                    ret[k if len(key) == 0 else key+'|'+k] = str(v)
        return ret



def opcontrol():
    conf = DefConfig()
    conf.loadConfig("/etc/installer.xml")
    srv = OpController(conf)
    exit(srv.run())

def memory_limit():
    soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
    resource.setrlimit(resource.RLIMIT_DATA, (get_memory() * 1024 / 2, hard))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (get_memory() * 1024 / 2, hard))

def get_memory():
    with open('/proc/meminfo', 'r') as mem:
        free_memory = 0
        for i in mem:
            sline = i.split()
            if str(sline[0]) in ('MemFree:', 'Buffers:', 'Cached:'):
                free_memory += int(sline[1])
    return free_memory

if __name__ == "__main__":
    memory_limit() # limits the maximum memory usage
    try:
        opcontrol()
    except MemoryError:
        _logger.error('\n\n\ERROR: Memory Exception\n')
        exit(1)
