#!/usr/bin/env python3

import abc
import logging
from urllib.parse import urlparse

from os.path import isfile
from threading import Thread, Event
#from ConfigParser import ConfigParser # read/write config files

from defconfig import DefConfig
from messenger import DbusMessenger, SocketMessenger

# get the handler to the current module, and setup logging options
_logger = logging.getLogger(__name__)



class BaseViewer(object):
    """
    Base Viewer Class
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, confname = ''):
        super().__init__()
        self.mResponseEvent = Event()
        self.mDefConfig = DefConfig()
        self.__initialize(confname)

    def __initialize(self, confname):
        # standard initialization for all Viewers
        if isinstance(confname, str) and isfile(confname):
            self.mDefConfig.loadConfig(confname)
        else:
            self.mDefConfig.loadConfig('/etc/installer.xml')

    @abc.abstractmethod
    def _mainExec(self):
        pass

    @abc.abstractmethod
    def _preExec(self):
        pass

    @abc.abstractmethod
    def _postExec(self):
        pass

    @abc.abstractmethod
    def _parseResult(self):
        pass

    @abc.abstractmethod
    def _parseCmd(self, params):
        pass

    def _waitForEventTimeout(self, t):
        _logger.debug('Client Wait for Response Event Timeout {}s'.format(t))
        isSet = False
        while not self.mResponseEvent.isSet():
            isSet = self.mResponseEvent.wait(t)
            if isSet:
                _logger.debug('Client Processing event')
            else:
                _logger.debug('Timed Out: Client Doing other things')
                break
        return isSet

    def _setEvent(self):
        self.mResponseEvent.set()
        _logger.debug('Set Response Event')

    def _clearEvent(self):
        self.mResponseEvent.clear()
        _logger.debug('Clear Response Event')

    def _unflatten(self, value):
        ret = {}
        for k, v in value.items():
            keys = k.split('|')
            d = ret
            for key in keys[:-1]:
                if key not in d:
                    d[str(key)] = dict()
                d = d[str(key)]
            d[str(keys[-1])] = str(v)
        return ret


class CliViewer(BaseViewer):
    def __init__(self, confname=''):
        super().__init__(confname)
        self.mThread = None
        self.mCmd = {}
        self.mInputs = {}
        self.mResponse = {}
        self.__setupMsger()

    def __setupMsger(self):
        # check the DefConfig, and create mMsger as the dbus client
        conf = self.mDefConfig.getSettings(flatten=True)
        self.mMsger = DbusMessenger(conf, self.response)

    def __run(self):
        self.mThread = Thread(name='DBusThread', target=self.mMsger.run)
        self.mThread.start()

    def _parseCmd(self, params):
        # do the user commands checking here, and convert it into proper
        # recognizable dictionary to send to the dbus server
        self.mCmd.clear()

        if 'cmd' in params.keys():
            # FORMAT for server parsing dictionary
            # {cmd: {options}}
            if 'verbose' in params and params.pop('verbose'):
                params.update({'verbose': 'True'})
            else:
                params.update({'verbose': 'False'})

            if 'interactive' in params:
                params.pop('interactive')
                params.update({'interactive': 'True'})

            if params['cmd'] is None:
                params.pop('cmd')

            #self.mCmd.update({params.pop('cmd'): params})
            self.mCmd.update(params)
        if len(self.mCmd) > 0:
            return True
        else:
            return False

    def _isStatusProcessing(self):
        status ={}
        status.update(self._unflatten(self.mMsger.getStatus()))
        if status['status'] == 'processing':
            return True
        return False

    def _parseResult(self, result = None):
        if result:
            self.__dump(result)
        else:
            self.__dump(self.mResponse)

    def _preExec(self):
        return True

    def _mainExec(self):
        try:
            if isinstance(self.mCmd, dict):
                # clear the event before sending message over to dbus
                self._clearEvent()
                _logger.debug('send cmd via DBus')
                self.mMsger.sendMsg(self.mCmd)
                return True
            else:
                raise TypeError('cmd must be in a dictionary format')
        except Exception as ex:
            _logger.info('Error: {}'.format(ex))
        return False

    def _postExec(self):
        while True:
            # loop to wait for dbus response
            # wait for dbus server response for 25 seconds, same as DBus timeout
            self._waitForEventTimeout(1)
            if self.mResponseEvent.is_set():
                # handle what is received from the (dbus) server after Response Event is set
                # The server will signal a 'pending' response first.
                # Then a 'processing' response
                # and finally a 'success' or a 'failure' response
                if 'user_request' in self.mResponse.keys():
                    # if it is a user_request, then get user inputs,
                    # pass them to the server again and return false
                    self.mInputs.update({'user_response': self.__getUserInput(self.mResponse['user_request'])})
                    self.mInput.update(self.mCmd)
                    if len(self.mInputs) > 0:
                        _logger.info('get more user inputs: {}'.format(self.mInputs))
                        self.mMsger.sendMsg(self.mInputs)
                    self._clearEvent()
                    continue
                elif 'status' in self.mResponse.keys():
                    if self.mResponse['status'] == 'pending':
                        # clear the event and wait until server send another response with status==processing
                        self._clearEvent()
                        continue
                    elif self.mResponse['status'] == 'processing':
                        # keep getting results after it becomes 'processing'
                        # and until status in success or failure, so don't clear the event
                        # but continue the loop to come back here again
                        _logger.debug('event set, status just becomes processing')
                        self._clearEvent()
                        continue
                    else:
                        if self._isStatusProcessing():
                            _logger.debug("event set but still processing")
                            self._parseResult(self._unflatten(self.mMsger.getResult()))
                            self._clearEvent()
                            continue
                        else:
                            # get and parse the result, and break out of loop
                            if self.mResponse['status'] == 'success':
                                self._parseResult()
                            else:
                                self._parseResult(self._unflatten(self.mMsger.getResult()))
                            break
            else:
                _logger.debug("Wait Timed Out")
                if self.mResponse['status'] == 'processing':
                    self._parseResult(self._unflatten(self.mMsger.getResult()))
                self._clearEvent()
                continue

    def __dump(self, value):
        for k in value.keys():
            if isinstance(value[k], dict):
                self.__dump(value[k])
            else:
                _logger.info('{:>24.24} {}'.format(k.strip(), value[k].strip().replace('\n', ' ')))

    def __getUserInput(self, prompt):
        return input(prompt)

    def getResult(self):
        return self.mResponse

    def queryResult(self):
        return self.mMsger.getResult()

    def request(self, arguments):
        """
        Handles command requests from the different viewers
        """
        params = {}
        params.update(arguments)
        # run the client signal handler, i.e. dbus response, on a separate thread
        self.__run()
        # execute parsed commands
        if self._parseCmd(params):
            if (self._preExec()):
                if (self._mainExec()):
                    self._postExec()
        # stop the messenger thread loop, and join the thread
        self.mMsger.stop()
        self.mThread.join()

    def response(self, response):
        """
        Callback to be called from the DBus Client's signal handler
        update the server response and set the response event before return out
        """
        self.mResponse.clear()
        self.mResponse.update(self._unflatten(response))
        self._setEvent()



class WebViewer(BaseViewer):
    def __init__(self, confname=''):
        super().__init__(confname)
        self.mPageTemplates = []

    def _parseCmd(self, params):
        pass

    def _parseResult(self):
        pass

    def _preExec(self):
        pass

    def _postExec(self):
        pass

    def __getUserInput(self, prompt):
        pass



if __name__ == "__main__":
    fmtr = logging.Formatter('%(asctime)s %(name)-12s (%(threadName)-10s):%(levelname)-8s %(message)s', datefmt='%m-%d %H:%M')
    hdlr = logging.FileHandler('/tmp/installer_cli.log')
    hdlr.setFormatter(fmtr)
    hdlr.setLevel(logging.DEBUG)
    _logger.addHandler(hdlr)
    # define a console handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    consolefmtr = logging.Formatter('%(name)-12s: (%(threadName)-10s):%(levelname)-8s %(message)s')
    console.setFormatter(consolefmtr)
    _logger.addHandler(console)

    def QueryTargetType(tgtstr):
        def CheckUrl(url):
            try:
                result = urlparse(url)
                return True if all([result.scheme, result.netloc]) else False
            except:
                return False

        supported_targets = ['emmc', 'sdcard', 'hd', 'som']
        if any(s == tgtstr for s in supported_targets):
            return tgtstr
        else:
            if CheckUrl(tgtstr):
                return tgtstr
            else:
                raise argparse.ArgumentTypeError('Invalid Host URL')

    def QueryLocationType(locstr):
        supported_locs = ['all', 'spl', 'bootloader', \
                          'controller', 'disk', 'partition', \
                          'bus', 'device', 'sensor', 'connection', \
                          'kernel', 'dtb', 'rootfs', 'os', 'cpu', 'form', 'baseboard']
        if any(s == locstr for s in supported_locs):
            return locstr
        else:
            if locstr.startswith('/') and locstr.endswith('/'):
                return locstr
            elif locstr.startswith('/') and locstr.endswith('xz'):
                return locstr
            else:
                raise argparse.ArgumentTypeError('Invalid Location Directory')

    import argparse
    parser = argparse.ArgumentParser(description='Technexion Installer Program: CLI')
    subparsers = parser.add_subparsers(dest='cmd', help='commands')

    # info commands
    # 'target', 'location'
    info_parser = subparsers.add_parser('info', help='information queries')
    info_parser.add_argument('-t', '--target', type=QueryTargetType, \
                             action='store', dest='target', default='emmc', \
                             help='Specify target storage media, choices are: [emmc, sdcard, hd, or a valid web host URL]')
    info_parser.add_argument('-l', '--location', type=QueryLocationType, \
                             action='store', dest='location', default='all', \
                             help='Information of target storage media, choices are: [all, spl, bootloader, \
                                    controller, disk, partition, bus, device, \
                                    sensor, connection, kernel, dtb, rootfs, os, or \
                                    a valid URL directory]')

    # flash commands
    # 'src_filename', 'tgt_filename', src_start_sector, tgt_start_sector, src_total_sectors
    flash_parser = subparsers.add_parser('flash', help='flash local file to local storage media')
    flash_parser.add_argument('-t', '--target-filename', dest='tgt_filename', \
                              action='store', metavar='FILENAME', help='Specify target storage media')
    flash_parser.add_argument('-b', '--target-start-sector', dest='tgt_start_sector', \
                              action='store', default='0', help='Specify starting locations on the target storage media')
    flash_parser.add_argument('-s', '--source-filename', dest='src_filename', \
                              action='store', metavar='FILENAME', help='Specify source storage media')
    flash_parser.add_argument('-f', '--src-start-sector', dest='src_start_sector', \
                              action='store', default='0', help='Specify starting locations on the source storage media')
    flash_parser.add_argument('-n', '--total-sectors', dest='src_total_sectors', \
                              action='store', default='-1', help='Specify total number of sectors to copy')

    # config commands
    # 'configfile'
    config_parser = subparsers.add_parser('config', help='configurations')
    config_parser.add_argument('subcmd', choices=('load', 'save'), default='load', \
                               action='store', help='Load/Save the configuration')
    config_parser.add_argument('-c', '--config-file', dest='configfile', \
                               action='store', metavar='FILENAME', help='Specify the configuration file')

    # verify commands


    # connect commands
    

    # disconnect commands
    

#     # start commands
#     start_parser = subparsers.add_parser('start', help='start client/server')
#     start_parser.add_argument('-t', dest='type', choices=('srv', 'cli'), \
#                               action='store', default='cli', help='start the server or client')
#     
#     # stop commands
#     stop_parser = subparsers.add_parser('stop', help='stop client/server')
#     stop_parser.add_argument('-t', dest='type', choices=('srv', 'cli'), \
#                              action='store', default='cli', help='start the server or client')

    # upload commands
    
    # download commands
    # 'dl_module',  'dl_baseboard', 'dl_os', 'dl_version', 'dl_display', \
    # 'dl_filetype', 'dl_host', 'dl_protocol', 'tgt_filename'
    dl_parser = subparsers.add_parser('download', help='download rescue files and flash to local storage media')
    dl_parser.add_argument('-t', '--target-filename', dest='tgt_filename', \
                           action='store', metavar='FILENAME', help='Specify target storage media')
    dl_parser.add_argument('-b', '--target-start-sector', dest='tgt_start_sector', type=str, \
                           action='store', default='0', help='Specify starting sector on the target storage media')
    dl_parser.add_argument('-p', '--host-protocol', dest='dl_protocol', choices=('http', 'ftp'), \
                           action='store', default='http', help='Specify host protocol to use for downloads')
    dl_parser.add_argument('-s', '--host-name', dest='dl_host', \
                           action='store', metavar='HOST', default='rescue.technexion.net', help='Specify host/URL to download from')
    dl_parser.add_argument('-m', '--module', dest='dl_module', type=str, \
                           choices=('edm1_cf_imx6all', 'pico-imx6', 'pico-imx6ul', 'pico-imx7', 'pico_imx6', 'tek3_imx6', 'tep5-imx6', 'tep5_imx6'), \
                           action='store', default=argparse.SUPPRESS, help='Specify the module of target device')
    dl_parser.add_argument('-d', '--baseboard', dest='dl_baseboard', \
                           choices=('dwarf', 'hobbit', 'nymph', 'fairy', 'pi', 'toucan', 'tek3', 'tep5'), \
                           action='store', default=argparse.SUPPRESS, help='Specify the baseboard of target device')
    dl_parser.add_argument('-o', '--operating-system', dest='dl_os', \
                           choices=('ubuntu', 'android', 'yocto'),\
                           action='store', default=argparse.SUPPRESS, help='Specify the operating system to download for target device')
    dl_parser.add_argument('-v', '--os-version', dest='dl_version', type=str, \
                           action='store', default=argparse.SUPPRESS, metavar='OS_VERSION', help='Specify the version of operating system to download')
    dl_parser.add_argument('-y', '--display', dest='dl_display', \
                           choices=('lcd800x480', 'lvds1024x600', '070', '050', 'vga', 'hdmi'), \
                           action='store', default=argparse.SUPPRESS, help='Specify the display version of target device')
    dl_parser.add_argument('-e', '--file-extension', dest='dl_filetype', \
                           choices=('xz', 'imx', 'img', 'bin'), \
                           action='store', default=argparse.SUPPRESS, help='Specify the file extension of the download file')
    dl_parser.add_argument('-f', '--src-start-sector', dest='src_start_sector', type=str, \
                           action='store', default='0', help='Specify starting locations on the source storage media')
    dl_parser.add_argument('-n', '--src-total-sectors', dest='src_total_sectors', type=str, \
                           action='store', default='-1', help='Specify total number of sectors to download')
    dl_parser.add_argument('-c', '--chunk-size', dest='chunk_size', type=str, \
                           action='store', default='65536', help='Specify the block size to read/write per I/O')
    dl_parser.add_argument('-u', '--url', dest='dl_url', default=argparse.SUPPRESS, \
                           action='store', metavar='DOWNLOAD_URL', help='Specify the proper URL of the download file')

    # install commands
    
    # rescue commands

    # Global Options
#     parser.add_argument('-i', '--interactive', dest='interactive', \
#                         action='store_true', default=argparse.SUPPRESS, help='Interactive mode')
    parser.add_argument('--verbose', dest='verbose', \
                        action='store_true', default=False, help='Show more information')
    parser.add_argument('--version', action='version', version='%(prog)s 0.1.0')
    args = parser.parse_args() # by default, arguments taken from sys.argv[1:]
    if args.verbose:
        _logger.setLevel(logging.DEBUG)
    else:
        _logger.setLevel(logging.INFO)

    cli = CliViewer()
    _logger.info('Parsed arguments: {}'.format(args))
    cli.request(args.__dict__)
    exit(0)
