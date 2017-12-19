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
from threading import Event
from defconfig import DefConfig, SetupLogging
from ophandle import FlashOperationHandler, \
                     InfoOperationHandler, \
                     DownloadOperationHandler, \
                     InteractiveOperationHandler
from messenger import DbusMessenger, SocketMessenger

SetupLogging('/tmp/installer_srv.log')
# get the handler to the current module
_logger = logging.getLogger(__name__)



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
        # super(OpController, self).__init__() # older python style
        super().__init__()
        # initialize a DbusMessenger for sending and receiving messages
        setting = conf.getSettings(flatten=True)
        setting.update({'IS_SERVER': True})
        self.mMsger = DbusMessenger(setting, self.__handleDBusMessage) 
        # initialize an array to hold BaseOpHandlers
        self.mOpHandlers = []
        self.mRetStatus = {}
        self.mUserReqEvent = Event()
        self.mStatusEvent = Event()
        
    def run(self):
        # setup Operation Handlers from the defconfig
        self.mOpHandlers.append(FlashOperationHandler(self.__handleOpCallback))
        self.mOpHandlers.append(InfoOperationHandler(self.__handleOpCallback))
        self.mOpHandlers.append(DownloadOperationHandler(self.__handleOpCallback))
        self.mOpHandlers.append(InteractiveOperationHandler(self.__handleOpCallback))

        # finally run the dbusmessenger server, and dbus run is blocking
        self.mMsger.run()
    
    def __executeOperation(self, params):
        self.mRetStatus.clear()
        for hdle in self.mOpHandlers:
            self.mCurrentHandler = hdle
            if hdle.isOpSupported(params):
                if (hdle.performOperation(params, self.mStatusEvent)):
                    self.mRetStatus.update(hdle.getStatus())
                    _logger.debug('handle.performOperation: {}'.format(self.mRetStatus))
                    return True
                # FIXME: if the ophandler is running with the thread
                #        we need to wait for the thread to finish before
                #        handling another command
        return False
    
    def __handleDBusMessage(self, msg):
        if isinstance(msg, dict):
            # manage user commands from client/viewer
            if 'user_response' in msg.keys():
                # need to find the correct OpHandler to update user response
                _logger.info("handle dbus msg: user_response")
                if self.mCurrentHandler:
                    self.mCurrentHandler.updateUserResponse(msg)
                    #self.mCurrentHandler = None
                self.__setEvent(self.mUserReqEvent)
                return False
            elif 'query_status' in msg.keys():
                _logger.info("handle dbus msg: query_status")
                self.mRetStatus.clear()
                self.__clearEvent(self.mStatusEvent)
                # wait for a status event timeout
                if not self.__waitForEventTimeout(self.mStatusEvent, 1):
                    # if it is timed out, get the current status
                    self.mRetStatus.update(self.mCurrentHandler.getStatus())
                    _logger.debug('Waiting for Status Event Timed Out, status={}'.format(self.mRetStatus))
                # else need to get the latest mRetStatus from the Op. callback
                self.mMsger.sendMsg(self.__flatten(self.mRetStatus))
                return False
            else:
                _logger.info("handle dbus msg: else execute operation")
                self.__clearEvent(self.mStatusEvent)
                # FIXME: Should queue the DBusMessage commands here into a queue
                # Otherwise second op job will override the first op job.
                if not self.__executeOperation(msg):
                    _logger.warning('Execute not finished or failed')
                    self.mRetStatus.update(self.mCurrentHandler.getStatus())
                    self.mMsger.sendMsg(self.__flatten(self.mRetStatus))
                    return False
        # execution success falls through here
        self.mRetStatus.update(self.mCurrentHandler.getStatus())
        self.mMsger.sendMsg(self.__flatten(self.mRetStatus))
        return True
    
    def __handleOpCallback(self, status, handler):
        """
        Handles requesting for more user inputs for the operations
        This function has to be blocking so the ophandler can continue afterwards.
        Here, the request for user input has to wait for DBusMessage from client
        """
        self.mRetStatus.clear()
        self.__clearEvent(self.mUserReqEvent)
        if handler:
            self.mCurrentHandler = handler
        if isinstance(status, dict):
            self.mRetStatus.update(status)
            # call appropriate client/viewer to signal execution result or get user input
            self.mMsger.sendMsg(self.__flatten(self.mRetStatus))
            if 'user_request' in self.mRetStatus.keys():
                # wait user response for 25 seconds, same as DBus timeout
                self.__waitForEventTimeout(self.mUserReqEvent, 25)

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
    srv.run()
    exit()
