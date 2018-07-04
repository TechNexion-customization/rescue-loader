#!/usr/bin/env python3

import socket
import abc
import logging
from threading import Thread, Event

from model import CopyBlockActionModeller, \
                  QueryFileActionModeller, \
                  QueryBlockDevActionModeller, \
                  WebDownloadActionModeller, \
                  QueryWebFileActionModeller, \
                  QueryLocalFileActionModeller, \
                  ConfigMmcActionModeller, \
                  ConfigNicActionModeller, \
                  QRCodeActionModeller, \
                  BaseActionModeller
import urllib.parse

_logger = logging.getLogger(__name__)

class BaseOperationHandler(object):
    """
    Base Operation Handler that handles the Action Models and further IO actions
    """

    def __init__(self, cbUserRequest):
        super().__init__()
        self.mUseThread = False
        self.mThread = None
        self.mResult = {}
        self.mStatus = {}
        self.mActionModellers = []
        self.mRecoverModellers = []
        # setup the callback function for further user decisions
        self.mUserRequestHandler = cbUserRequest if callable(cbUserRequest) else None
        self.mUserInputs = {}
        self.mActionParam = {}
        self.mRunningModeller = None
        self.mSuccessModeller = None
        self.mInteractive = False

    def getStatus(self):
        _logger.info('return current status')
        return self.mStatus

    def getResult(self):
        if self.mSuccessModeller and callable(self.mSuccessModeller.getResult):
            _logger.info('return success result from {}'.format(self.mSuccessModeller))
            return self.mSuccessModeller.getResult()
        elif self.mRunningModeller and callable(self.mRunningModeller.getResult):
            _logger.info('return running result from {}'.format(self.mRunningModeller))
            return self.mRunningModeller.getResult()
        else:
            _logger.info('return performed result')
            return self.mResult

    def __run(self):
        # clear RunModel and RecoverModel references
        self.mRunningModeller = None
        self.mSuccessModeller = None
        self.mRecoverModellers = []
        # set the status to failure first, it will be overridden if success
        self.mStatus.update({'status': 'failure'})

        for model in self.mActionModellers:
            # the running model
            self.mRunningModeller = model

            # append the executed action models to the recover list
            self.mRecoverModellers.append(model)
            if (model.performAction()):
                # update successful result
                self.mResult.update(model.getResult())
                self.mStatus.update({'status': 'success'})
                _logger.info('call performAction success: {}'.format(self.mStatus))
                self.mSuccessModeller = model
#                 # FIXME: Do we really need to call user request to pass the current Status?
#                 if callable(self.mUserRequestHandler):
#                     # sent success status
#                     _logger.debug("Call User Request Handler to send success status")
#                     self.mUserRequestHandler(self.mStatus, self)
            else:
                self.mResult.update(model.getResult())
                _logger.info('call performAction failed: {}'.format(self.mStatus))
                self.__handleRecoverable(model)
        return

    def performOperation(self, OpParams):
        try:
            self.mActionParam.clear()
            self.mResult.clear()
            self.mStatus.clear()
            self.mStatus.update(OpParams)
            # clear old action models for next command
            if len(self.mActionModellers): del self.mActionModellers[:] #self.mActionModellers = []
            # if successfully setup an action model, do the work
            if self._setupActions(OpParams):
                if all(isinstance(model, BaseActionModeller) for model in self.mActionModellers):
#                     if self.mUseThread:
#                         # use thread
#                         _logger.info('thread run')
#                         # join the previous finished thread first
#                         if isinstance(self.mThread, Thread) and not self.mThread.isAlive():
#                             self.mThread.join()
#                             del self.mThread
#                             self.mThread = None
#                         # start the thread to do work and continue
#                         if self.mThread == None:
#                             self.mThread = Thread(name='WorkThread', target=self.__run, args=(workEvt,))
#                             self.mThread.start()
#                         # set the status to processing
#                         self.mStatus.update({'status': 'processing'})
#                     else:
#                         # normal run
                    _logger.info('normal run')
                    self.__run()
                    return True
                else:
                    raise ReferenceError('Cannot reference all Action Models')
            else:
                raise ValueError('Invalid Parameters')

        except Exception as ex:
            _logger.error('performOperation exception: {}'.format(ex))
            # should handle all lower level exceptions here.
            self.mStatus.update({'status': 'failure', 'error': str(ex)})
        return False

    def __handleRecoverable(self, model):
        if model.isRecoverable():
            # recoverable
            # when there is a need for user request to get user inputs, send request
            if callable(self.mUserRequestHandler):
                # NOTE: blocking until a user response is returned from client/viewer
                # we sent both success status and user_request status through here
                _logger.debug("Call User Request Handler")
                prompt = {}
                prompt.update(self.mStatus)
                prompt.update({'is_recoverable': 'yes' if model.isRecoverable() else 'no'});
                prompt.update({'user_request': 'Recover from failed operation? Y/N: '});
                self.mUserRequestHandler(prompt, self)
                # after the user request returns, check the user input
                if self._hasValidUserResponse(self.mUserInputs):
                    _logger.debug("Has valid user inputs, so recover operation")
                    # FIXME: Retry or Recover
                    if self.__recoverOperation():
                        self.mStatus.update({'status': 'success'})
                    else:
                        self.mStatus.update({'status': 'failure', 'error': 'Recover failed'})
                else:
                    # no or not valid User Input Response, continue for now
                    self.mStatus.update({'status': 'failure', 'error': 'Invalid user input'})
    
    def __recoverOperation(self):
        try:
            for model in self.mRecoverModellers.reverse():
                if isinstance(model, BaseActionModeller):
                    return model.recoverAction()
                else:
                    raise ReferenceError('Cannot reference a ActionModel')
        except Exception as ex:
            # handle all lower level exceptions here.
            # even when recover failed
            self.mStatus.update({'error': str(ex)})
        finally:
            self.mStatus.update({'recover': 'False'})
            return False

    def updateUserResponse(self, inputs):
        if isinstance(inputs, dict):
            self.mUserInputs.update(inputs)
            return True
        else:
            _logger.error('User inputs must be in a dictionary form')
        return False

    def isOpSupported(self, OpParams):
        """
        To be overridden
        """
        return False

    def _hasValidUserResponse(self, inputs):
        """
        To be overridden
        """
        return False

    def _setupActions(self, OpParams):
        """
        To be overridden
        """
        return False



class FlashOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB, use_thread=True):
        super().__init__(UserRequestCB)
        self.mUseThread = use_thread
        self.mSrcFileOps = ['src_filename', 'tgt_filename']

    def isOpSupported(self, OpParams):
        if isinstance(OpParams, dict) and 'cmd' in OpParams.keys():
            if OpParams['cmd'] == 'flash':
                return True
        return False

    def _setupActions(self, OpParams):
        # setup "flash" cmd operations
        if (self.__parseParam(OpParams)):
            self.mActionModellers.append(CopyBlockActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        else:
            raise SyntaxError('Invalid Operation Parameters: {}'.format(OpParams))

    def __parseParam(self, OpParams):
        _logger.debug('__parseParam: OpParams: {}'.format(OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            if all(s in OpParams.keys() for s in self.mSrcFileOps):
                # check for copy from source file to target file
                self.mActionParam['src_filename'] = str(OpParams['src_filename'])
                self.mActionParam['tgt_filename'] = str(OpParams['tgt_filename'])
                if 'src_start_sector' in OpParams.keys():
                    self.mActionParam['src_start_sector'] = int(OpParams['src_start_sector'])
                else:
                    self.mActionParam['src_start_sector'] = 0
                if 'tgt_start_sector' in OpParams.keys():
                    self.mActionParam['tgt_start_sector'] = int(OpParams['tgt_start_sector'])
                else:
                    self.mActionParam['tgt_start_sector'] = 0
                if 'src_total_sectors' in OpParams.keys():
                    self.mActionParam['src_total_sectors'] = int(OpParams['src_total_sectors'])
                else:
                    self.mActionParam['src_total_sectors'] = -1
                if 'chunk_size' in OpParams.keys():
                    self.mActionParam['chunk_size'] = int(OpParams['chunk_size'])
                else:
                    self.mActionParam['chunk_size'] = -1
                return True
        else:
            return False



class QRCodeOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB, use_thread=True):
        super().__init__(UserRequestCB)
        self.mUseThread = use_thread
        self.mSrcFileOps = ['dl_url', 'tgt_filename']

    def isOpSupported(self, OpParams):
        if isinstance(OpParams, dict) and 'cmd' in OpParams.keys():
            if OpParams['cmd'] == 'qrcode':
                return True
        return False

    def _setupActions(self, OpParams):
        # setup "flash" cmd operations
        if (self.__parseParam(OpParams)):
            self.mActionModellers.append(QRCodeActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        else:
            raise SyntaxError('Invalid Operation Parameters: {}'.format(OpParams))

    def __parseParam(self, OpParams):
        _logger.debug('__parseParam: OpParams: {}'.format(OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            if all(s in OpParams.keys() for s in self.mSrcFileOps):
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
                return True
        else:
            return False



class InfoOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)
        self.mOptions = ['target', 'location']

    def isOpSupported(self, OpParams):
        # Check if User Response is valid
        if isinstance(OpParams, dict) and 'cmd' in OpParams.keys():
            if OpParams['cmd'] == 'info':
                return True
        return False

    def _setupActions(self, OpParams):
        # setup "info" cmd operations
        if (self.__parseParam(OpParams)):
            self.mActionModellers.append(QueryBlockDevActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(QueryWebFileActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(QueryFileActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(QueryLocalFileActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        else:
            raise SyntaxError('Invalid Operation Parameters: {}'.format(OpParams))

    def __parseParam(self, OpParams):
        _logger.debug('__parseParam: OpParams: {}'.format(OpParams))
        self.mActionParam.clear()
#         # default values for type and for all locations
#         self.mActionParam['tgt_type'] = 'mmc'
#         self.mActionParam['dst_pos'] = -1
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            for i in self.mOptions:
                for k, v in OpParams.items():
                    if k==i and v=='emmc':
                        # check for the correct /dev/mmcblk[x]p[x] path and set it
                        self.mActionParam['tgt_type'] = 'mmc'
                    elif k==i and v=='sdcard':
                        # check for the correct /dev/mmcblk[x]p[x] path and set it
                        self.mActionParam['tgt_type'] = 'sd'
                    elif k==i and v=='hd':
                        # check for the correct /dev/sd[x] path and set it
                        self.mActionParam['tgt_type'] = 'sd'
                    elif k==i and v.startswith('http'):
                        self.mActionParam['host_name'] = v # web host address
                    elif k==i and v == socket.gethostname():
                        self.mActionParam['local_fs'] = v # local file system
                    elif k==i and v=='spl':
                        self.mActionModellers['dst_pos'] = 2 # sector 2 for spl
                    elif k==i and v=='bootloader':
                        self.mActionParam['dst_pos'] = 2 # image for android uboot.imx
                    elif k==i and v=='controller':
                        self.mActionParam['dst_pos'] = 'c' # controller
                    elif k==i and v=='disk':
                        self.mActionParam['dst_pos'] = 'd' # disk
                    elif k==i and v=='partition':
                        self.mActionParam['dst_pos'] = 'p' # partition
                    elif k=='location' and v.startswith('/') and v.endswith('/'):
                        self.mActionParam['src_directory'] = v # directory/folder
                    elif k=='location' and v.startswith('/') and v.endswith('xz'):
                        self.mActionParam['src_directory'] = v # directory/folder
                    elif k==i and v=='som':
                        self.mActionParam['src_filename'] = '/proc/device-tree/model'
                        self.mActionParam['re_pattern'] = '\w+\ (\w+)-(imx\w+|IMX\w+).+\ (\w+)\ baseboard'
                    elif k==i and v=='cpu':
                        self.mActionParam['re_pattern'] = '.*-(imx\w+|IMX\w+).*'
                    elif k==i and v=='form':
                        self.mActionParam['re_pattern'] = '\w+\ (\w+)-\w+'
                    elif k==i and v=='baseboard':
                        self.mActionParam['re_pattern'] = '.*\ (\w+)\ baseboard'

            if 'tgt_type' in self.mActionParam and not 'dst_pos' in self.mActionParam:
                self.mActionParam['dst_pos'] = -1
        if all(s in self.mActionParam.keys() for s in ['tgt_type', 'dst_pos']):
            _logger.debug('__parseParam: mActionParam:{}'.format(self.mActionParam))
            return True
        elif all(s in self.mActionParam.keys() for s in ['host_name', 'src_directory']):
            _logger.debug('__parseParam: mActionParam:{}'.format(self.mActionParam))
            return True
        elif all(s in self.mActionParam.keys() for s in ['local_fs', 'src_directory']):
            _logger.debug('__parseParam: mActionParam:{}'.format(self.mActionParam))
            return True
        elif all(s in self.mActionParam.keys() for s in ['src_filename', 're_pattern']):
            _logger.debug('__parseParam: mActionParam:{}'.format(self.mActionParam))
            return True
        else:
            return False



class DownloadOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB, use_thread=True):
        super().__init__(UserRequestCB)
        self.mUseThread = use_thread
        self.mDlFileOps = ['dl_module',  'dl_baseboard', 'dl_os', 'dl_version', \
                           'dl_display', 'dl_filetype', 'dl_host', 'dl_protocol']

    def isOpSupported(self, OpParams):
        if isinstance(OpParams, dict) and 'cmd' in OpParams.keys():
            if OpParams['cmd'] == 'download':
                return True
        return False

    def _setupActions(self, OpParams):
        # setup "download" cmd operations
        if (self.__parseParam(OpParams)):
            self.mActionModellers.append(WebDownloadActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        else:
            raise SyntaxError('Invalid Operation Parameters: {}'.format(OpParams))

    def __parseParam(self, OpParams):
        _logger.debug('__parseParam: OpParams: {}'.format(OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict):
            if 'tgt_filename' in OpParams.keys():
                self.mActionParam['tgt_filename'] = str(OpParams['tgt_filename'])
            else:
                self.mActionParam['tgr_filename'] = '/tmp/download.tmp'
            if 'tgt_start_sector' in OpParams.keys():
                self.mActionParam['tgt_start_sector'] = int(OpParams['tgt_start_sector'])
            else:
                self.mActionParam['tgt_start_sector'] = 0
            if 'src_total_sectors' in OpParams.keys():
                self.mActionParam['src_total_sectors'] = int(OpParams['src_total_sectors'])
            else:
                self.mActionParam['src_total_sectors'] = -1
            if 'chunk_size' in OpParams.keys():
                self.mActionParam['chunk_size'] = int(OpParams['chunk_size'])

            if all(s in OpParams.keys() for s in self.mDlFileOps):
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
                _logger.debug('mActionParam: {}'.format(self.mActionParam))
                return True
            elif 'dl_url' in OpParams.keys():
                urlobj = urllib.parse.urlparse(OpParams['dl_url'])
                self.mActionParam['host_protocol'] = urlobj.scheme
                self.mActionParam['host_name'] = urlobj.hostname
                self.mActionParam['src_filename'] = urlobj.path.split('/')[-1]
                self.mActionParam['src_directory'] = '/'.join(urlobj.path.split('/')[2:-1])
                _logger.debug('mActionParam: {}'.format(self.mActionParam))
                return True
        else:
            return False



class ConfigOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB):
        super().__init__(UserRequestCB)

    def isOpSupported(self, OpParams):
        # Check if User Response is valid
        if isinstance(OpParams, dict) and 'cmd' in OpParams.keys() and 'subcmd' in OpParams.keys():
            if OpParams['cmd'] == 'config':
                if any(k in OpParams['subcmd'] for k in ['mmc', 'nic']):
                    return True
        return False

    def _setupActions(self, OpParams):
        # setup "config" cmd operation:
        # {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', 'config_setting': 'enable', 'boot_part_no': 1, 'send_ack': '1', 'target': '/dev/mmcblk2'}
        if (self.__parseParam(OpParams)):
            self.mActionModellers.append(ConfigMmcActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            self.mActionModellers.append(ConfigNicActionModeller())
            self.mActionModellers[-1].setActionParam(self.mActionParam)
            return True
        else:
            raise SyntaxError('Invalid Operation Parameters: {}'.format(OpParams))

    def __parseParam(self, OpParams):
        _logger.debug('__parseParam: OpParams: {}'.format(OpParams))
        self.mActionParam.clear()
        # Parse the OpParams and Setup mActionParams
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
        if all(s in self.mActionParam.keys() for s in ['subcmd', 'target', 'config_id', 'config_action']):
            _logger.debug('__parseParam: mActionParam:{}'.format(self.mActionParam))
            return True
        else:
            return False



class InteractiveOperationHandler(BaseOperationHandler):
    def __init__(self, UserRequestCB, use_thread=True):
        super().__init__(UserRequestCB)
        self.mUseThread = use_thread

    def __interactiveMode(self, ActParams, StatusEvt):
        try:
            while True:
                # clear old action models for next command
                if len(self.mActionModellers):
                    self.mActionModellers = []
                    # del self.mActionModellers

                # if successfully setup an action model, do the work
                if self._setupActions(ActParams):
                    if all(isinstance(model, BaseActionModeller) for model in self.mActionModellers):
                        _logger.info('interactive run')
                        self._BaseOperationHandler__run(StatusEvt)

                if not self.mInteractive:
                    _logger.info('Quit interactive mode')
                    # break out of loop when self.mInteractive is set to false
                    self.mStatus.clear()
                    self.mStatus.update({'error': 'Quit interactive mode'})
                    self.mStatus.update({'status': 'success'})
                    break

        except Exception as ex:
            # handle all lower level exceptions here.
            self.mStatus.clear()
            self.mStatus.update({'error': str(ex)})
            self.mStatus.update({'status': 'failure'})

        # send last message before return out of InteractiveThread
        if self.mUserRequestHandler:
            self.mUserRequestHandler(self.mStatus, self)
        return

    def performOperation(self, OpParams, WorkEvt = Event()):
        """
        Override performOperation for interactive operations
        """
        self.__parseParam(OpParams)
        # Use thread to handle setup action as well as running operations
        if self.mUseThread:
            # join the previous finished thread first
            if isinstance(self.mThread, Thread) and not self.mThread.isAlive():
                self.mThread.join()
                del self.mThread
                self.mThread = None
            # use a thread to run interactive mode
            if self.mThread == None:
                self.mThread = Thread(name='InteractiveThread', \
                                      target=self.__interactiveMode, \
                                      args=(self.mActionParam, WorkEvt,))
                self.mThread.start()
                # set the status to processing
                self.mStatus.update({'status': 'processing'})
        else:
            self.mStatus.update({'error': 'Cannot start interactive mode without using thread'})
            self.mStatus.update({'status': 'failure'})
        return False

    def isOpSupported(self, OpParams):
        if isinstance(OpParams, dict):
            if ('interactive' in OpParams.keys()):
                self.mInteractive = True
                return True
        return False

    def _hasValidUserResponse(self, inputs):
        # Check if User Response is valid
        _logger.debug('_hasValidUserResponse: {}'.format(inputs))
        if isinstance(inputs, dict) and 'user_response' in inputs.keys():
            return self.__parseInput(inputs['user_response'])
        return False

    def _setupActions(self, ActParams):
        _logger.warning('_setupActions: {}'.format(ActParams))
        # setup "interactive" cmd operations
        # if parse operation succuessful, ask for what to do next
        if callable(self.mUserRequestHandler):
            # NOTE: blocking until a user response is returned from client/viewer
            # we sent both success status and user_request status through here
            _logger.warning("Call User Request Handler to ask for what to do next")
            self.mStatus.update({'user_request': 'What do you want to do next?'});
            self.mUserRequestHandler(self.mStatus, self)
            # after the handler returns, check the user input after user
            # responded from client/viewer, handle a valid user response
            # if we have one
            if self._hasValidUserResponse(self.mUserInputs):
                _logger.warning("Has valid user inputs")
                # FIXME: Retry or Recover
                self.mStatus.update({'status': 'success'})
                # if still in interactive mode, set up action models
                if self.mInteractive:
                    # setup cmd operations from new user input
                    self.mActionModellers.append(WebDownloadActionModeller())
                    self.mActionModellers[-1].setActionParam(self.mActionParam)
                    return True
            else:
                # no or not valid User Input Response, what to do next?
                self.mStatus.update({'error': 'Not valid user input'})
                self.mStatus.update({'status': 'failure'})
        return False

    def __parseParam(self, OpParams):
        _logger.debug('__parseParam: OpParams: {}'.format(OpParams))
        # Parse the OpParams and Setup mActionParams
        if isinstance(OpParams, dict) and 'cmd' in OpParams.keys():
            OpParams.pop('interactive')
            self.mActionParam.update(OpParams)

    def __parseInput(self, UserResponse):
        """
        Check additional user inputs, if valid return True else False
        """
        _logger.debug('__parseInput: {}'.format(UserResponse))
        if UserResponse.upper() == 'Q' or UserResponse.upper() == 'QUIT':
            # quit the interactive mode
            self.mInteractive = False
            return True
        return False



if __name__ == "__main__":
    def opcb(Status, Hdl):
        print ('called back:\n{}'.format(Status))

    import sys

    if sys.argv[1] == 'local':
        hdlr = FlashOperationHandler(opcb, use_thread=True)
        param = {'cmd': 'flash', 'src_filename': './test.bin', 'src_start_sector': 0, 'src_total_sectors': 64, 'tgt_filename': './target.bin', 'tgt_start_sector': 32}
    elif sys.argv[1] == 'som':
        hdlr = InfoOperationHandler(opcb)
        param = {'cmd': 'info', 'target': 'som', 'location': 'baseboard'}
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
