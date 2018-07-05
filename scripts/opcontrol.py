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

import logging
import time
import queue
from threading import Thread, Event, Lock
from defconfig import DefConfig, SetupLogging
from ophandle import FlashOperationHandler, \
                     InfoOperationHandler, \
                     DownloadOperationHandler, \
                     ConfigOperationHandler, \
                     QRCodeOperationHandler

from messenger import DbusMessenger, SocketMessenger

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
        self.mMsger = DbusMessenger(setting, \
                                    self.__handleDBusMessage, \
                                    self.__handleGetStatus, \
                                    self.__handleGetResult, \
                                    self.__handleUserInterrupt)
        # initialize an array to hold BaseOpHandlers
        self.mOpHandlers = []
        # initialize a queue to hold all the worker to perform the command job
        self.mQueue = queue.Queue()
        # using 2+ threads to handle the worker queue
        self.mThreads = [WorkerThread(self.mQueue), WorkerThread(self.mQueue)]
        for thrd in self.mThreads: thrd.start()

    def run(self):
        # setup Operation Handlers from the defconfig
        self.mOpHandlers.append(FlashOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(InfoOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(DownloadOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(ConfigOperationHandler(self.__sendUserRequest))
        self.mOpHandlers.append(QRCodeOperationHandler(self.__sendUserRequest))
        # finally run the dbusmessenger server, and dbus run is blocking
        self.mMsger.run()

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
                _logger.info("found a handler: {} and queue a worker with dbus msg/cmd to perform operation later".format(ophandler))
                self.mQueue.put(Worker(msg, ophandler, self.setRetResult))
                status = {}
                status.update(msg)
                status.update({'status': 'pending'})
                self.mMsger.setStatus(self.__flatten(status))
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
        # manage user interrupt from client/viewer
        for thrd in self.mThreads:
            thWkrHdlr = thrd.getWorkerHandler()
            if thWkrHdlr and callable(thWkrHdlr.updateUserResponse):
                _logger.info("found handler: {} of {} to handle user_response/interrupt: {}".format(thWkrHdlr, thrd.name, param))
                # call handler's updateUserResponse() api with param, and wait for handler to quit itself
                thWkrHdlr.updateUserResponse(param)

    def __sendUserRequest(self, req):
        """
        Handles requesting for more user inputs for the operations
        send the req by triggering receive signal, then user should interrupt
        by calling the DBus interrupt i/f method
        """
        userReq = {}
        if isinstance(req, dict):
            userReq.update(req)
            # signal client/viewer with receive signal with request to get user input
            self.mMsger.sendMsg(self.__flatten(userReq))

    def setRetResult(self, result):
        if isinstance(result, dict):
            self.mMsger.setResult(self.__flatten(result))

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

if __name__ == "__main__":
    opcontrol()
