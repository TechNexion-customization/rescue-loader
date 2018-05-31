#!/usr/bin/env python3

# ============================================================
# installer operation controller daemon
#
# To start your installer environment, type:
#
# systemctl start installer.service
#
# ============================================================

import logging

from queue import Queue
from threading import Thread, Event, Lock
from defconfig import DefConfig, SetupLogging
from ophandle import FlashOperationHandler, \
                     InfoOperationHandler, \
                     DownloadOperationHandler, \
                     ConfigOperationHandler, \
                     QRCodeOperationHandler, \
                     InteractiveOperationHandler

from messenger import DbusMessenger, SocketMessenger

SetupLogging('/tmp/installer_srv.log')
# get the handler to the current module
_logger = logging.getLogger(__name__)



class Worker(object):

    def __init__(self, cmd, handle, cbSetResult):
        super().__init__()
        self.mCmd = {}
        self.mCmd.update(cmd)
        self.mHandle = handle
        self.mCbSetResult = cbSetResult

    def doWork(self, workEvt):
        _logger.info("worker: perform command: {}".format(self.mCmd))

        result = {}
        result.update(self.mCmd)
        result.update({'status': 'processing'})
        _logger.debug('worker: return status=processing as result: {}'.format(result))
        self.mCbSetResult(result)

        if callable(self.mHandle.performOperation):
            self.mHandle.performOperation(self.mCmd)

        if callable(self.mCbSetResult) and callable(self.mHandle.getStatus) and callable(self.mHandle.getResult):
            result = {}
            result.update(self.mCmd)
            result.update(self.mHandle.getStatus())
            result.update(self.mHandle.getResult())
            _logger.debug('worker: return result: {}'.format(result))
            self.mCbSetResult(result)

        # set the work event
        _logger.debug('worker: set Work Event to indicate work complete and return out')
        workEvt.set()



class WorkerThread(Thread):
    def __init__(self, q):
        super().__init__()
        self.mQueue = q
        self.mWorkEvent = Event()
        self.mQuitFlag = False

    def run(self):
        while True:
            try:
                worker = self.mQueue.get()
                self.mWorkEvent.clear()
                worker.doWork(self.mWorkEvent)
                while True:
                    # wait for work complete
                    if self.mWorkEvent.is_set():
                        self.mQueue.task_done()
                        break
                    else:
                        self.mWorkEvent.wait(1)
                if self.mQuitFlag:
                    raise Exception('Quit Gracefully')
            except Exception as ex:
                print(ex)
                pass



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
                                    self.__handleQuit)
        # initialize an array to hold BaseOpHandlers
        self.mOpHandlers = []
        self.mUserReqEvent = Event()
        self.mQueue = Queue()
        self.mThread = WorkerThread(self.mQueue)
        self.mThread.daemon = True # thread dies when main thread exits
        self.mThread.start()

    def run(self):
        # setup Operation Handlers from the defconfig
        self.mOpHandlers.append(FlashOperationHandler(self.__handleUserRequest))
        self.mOpHandlers.append(InfoOperationHandler(self.__handleUserRequest))
        self.mOpHandlers.append(DownloadOperationHandler(self.__handleUserRequest))
        self.mOpHandlers.append(ConfigOperationHandler(self.__handleUserRequest))
        self.mOpHandlers.append(QRCodeOperationHandler(self.__handleUserRequest))
        self.mOpHandlers.append(InteractiveOperationHandler(self.__handleUserRequest))

        # finally run the dbusmessenger server, and dbus run is blocking
        self.mMsger.run()

    def __findOpHandle(self, cmds):
        # find the OpHandle for executing command
        for ophdle in self.mOpHandlers:
            if ophdle.isOpSupported(cmds):
                return ophdle

    def __handleDBusMessage(self, msg):
        if isinstance(msg, dict):
            # manage user commands from client/viewer
            if 'user_response' in msg.keys():
                _logger.info("handle dbus msg: user_response: {}".format(msg))
                if callable(self.mCurrentHandler.updateUserResponse):
                    self.mCurrentHandler.updateUserResponse(msg)
                    self.__setEvent(self.mUserReqEvent)
            else:
                # find the correct OpHandler
                ophandle = self.__findOpHandle(msg)
                if ophandle is not None:
                    _logger.info("handle dbus msg: else queue the execute operation")
                    self.mQueue.put(Worker(msg, ophandle, self.setRetResult))
                    self.mCurrentHandler = ophandle
                    status = {}
                    status.update(msg)
                    status.update({'status': 'pending'})
                    self.mMsger.setStatus(self.__flatten(status))
            return True
        return False

    def __handleGetResult(self):
        _logger.debug('callback to get result from {}'.format(self.mCurrentHandler))
        if self.mCurrentHandler and callable(self.mCurrentHandler.getResult):
            return self.__flatten(self.mCurrentHandler.getResult())

    def __handleGetStatus(self):
        _logger.debug('callback to get status from {}'.format(self.mCurrentHandler))
        if self.mCurrentHandler and callable(self.mCurrentHandler.getStatus):
            return self.__flatten(self.mCurrentHandler.getStatus())

    def __handleQuit(self):
        _logger.debug('callback to quit gracefully...')
        # stop / break out the thread.run()
        self.mThread.mQuitFlag = True
        # join the thread in 10 seconds
        if self.mThread.join(10):
            # clear up the queue
            self.mQueue.clean()
            return self.__flatten({'quit': 'success'})
        else:
            return self.__flatten({'quit': 'failure'})

    def __handleUserRequest(self, status, handler):
        """
        Handles requesting for more user inputs for the operations
        This function has to be blocking so the ophandler can continue afterwards.
        Here, the request for user input has to wait for DBusMessage from client
        """
        userReq = {}
        self.__clearEvent(self.mUserReqEvent)
        if self.mCurrentHandler != handler:
            self.mCurrentHandler = handler
        if isinstance(status, dict):
            userReq.update(status)
            if 'user_request' in userReq.keys():
                # call appropriate client/viewer to signal execution result or get user input
                self.mMsger.sendMsg(self.__flatten(userReq))
                # wait user response for 25 seconds, same as DBus timeout
                self.__waitForEventTimeout(self.mUserReqEvent, 25)

    def setRetResult(self, result):
        if isinstance(result, dict):
            self.mMsger.setResult(self.__flatten(result))

    def __waitForEventTimeout(self, ev, t):
        _logger.debug('Wait for event {} with timeout: {}s'.format(ev, t))
        isSet = False
        while not ev.isSet():
            isSet = ev.wait(t)
            if isSet:
                _logger.debug('Event:{} isSet={}'.format(ev, isSet))
            else:
                _logger.debug('Timed Out: isSet={}'.format(isSet))
                break
        return isSet

    def __setEvent(self, ev):
        _logger.debug('Set Event: {}'.format(ev))
        ev.set()

    def __clearEvent(self, ev):
        _logger.debug('Clear Event: {}'.format(ev))
        ev.clear()

    def __flatten(self, value, key=''):
        ret = {}
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, dict):
                    ret.update(self.__flatten(v, k if len(key) == 0 else key+'|'+k))
                else:
                    ret[k if len(key) == 0 else key+'|'+k] = str(v)
        return ret



if __name__ == "__main__":
    conf = DefConfig()
    conf.loadConfig("/etc/installer.xml")
    srv = OpController(conf)
    exit(srv.run())
