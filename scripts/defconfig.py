#!/usr/bin/env python3

import logging
from lxml import etree
from lxml.etree import ElementTree
from os.path import isfile

# get the handler to the current module
_logger = logging.getLogger(__name__)

def SetupLogging(logfname):
    # set up logging to file - see previous section for more details
    logging.basicConfig(level=logging.DEBUG, \
                        format='%(asctime)s %(name)-12s (%(threadName)-10s):%(levelname)-8s %(message)s', \
                        datefmt='%m-%d %H:%M', \
                        filename=logfname, \
                        filemode='a')
    # define a Handler which writes INFO messages or higher to the sys.stderr
    consolefmtr = logging.Formatter('%(name)-12s: (%(threadName)-10s):%(levelname)-8s %(message)s')
    console = logging.StreamHandler()
    console.setFormatter(consolefmtr)
    console.setLevel(logging.WARNING)
    # add the console handler to the root logger
    logging.getLogger().addHandler(console)

#
# XmlDict object allow dict items to be act like Xml object
#
class XmlDictObject(dict):
    """
    Adds object like functionality to the standard dictionary.
    """
    def __init__(self, initdict=None):
        if initdict is None:
            initdict = {}
        super(XmlDictObject, self).__init__(initdict)
    
    def __getattr__(self, item):
        return self.__getitem__(item)
    
    def __setattr__(self, item, value):
        self.__setitem__(item, value)
    
    def __str__(self):
        if '_text' in self:
            return self.__getitem__('_text')
        else:
            return ''

    @staticmethod
    def Wrap(x):
        """
        Static method to wrap a dictionary recursively as an XmlDictObject
        """
        if isinstance(x, dict):
            return XmlDictObject((k, XmlDictObject.Wrap(v)) for (k, v) in x.items())
        elif isinstance(x, list):
            return [XmlDictObject.Wrap(v) for v in x]
        else:
            return x

    @staticmethod
    def __UnWrap(x):
        if isinstance(x, dict):
            return dict((k, XmlDictObject.__UnWrap(v)) for (k, v) in x.items())
        elif isinstance(x, list):
            return [XmlDictObject.__UnWrap(v) for v in x]
        else:
            return x
        
    def UnWrap(self):
        """
        Recursively converts an XmlDictObject to a standard dictionary and returns the result.
        """
        return XmlDictObject.__UnWrap(self)

#
# Define a 'SingletonMetaClass' type
#
class SingletonMetaClass(type):
    def __init__(cls, name, bases, dicts):
        # call class object's parent(i.e. type)'s __init__()  
        super(SingletonMetaClass, cls).__init__(name, bases, dicts)
        # assign orig_new_method to reference the class's original __new__()
        orig_new_method = cls.__new__
        # declare a local function to replace __new__()
        def replace_new_method(cls, *args, **kwds):
            # if class's variable __instance is None, i.e. nothing
            if cls.__instance == None:
                # call the original new method to create an instance
                cls.__instance = orig_new_method(cls, *args, **kwds)
            return cls.__instance
        # declare class variable
        cls.__instance = None
        # assign class method to new def method, which is decorated as static
        # therefore any interehited class calling __new__() woudl call to
        # replace_new_method() function
        cls.__new__ = staticmethod(replace_new_method)

#
# DefConfig class for loading, saving, getting, setting installer configurations
#
class DefConfig(object):
    """
        DefConfig(object)
        __metaclass__ = SingletonMetaClass
        
        loadsConfig(filename) - loads from xml configuration file
        saveConfig(filename) - saves to xml configuration file
        getConfig() - gets the configuration in a python dictionary, e.g. {}
        setConfig(changed) - sets the changed configurations (dict)
    """
    
    __metaclass__ = SingletonMetaClass
    
    def __init__(self):
        super(DefConfig, self).__init__() # older python style
        # super().__init__()
        self.mSettings = None

    def loadConfig(self, filename):
        _logger.debug('load configurations from file: {}'.format(filename))
        try:
            if self.mSettings == None:
                self.mSettings = self.__ConvertXmlToDict(filename)
            else:
                self.mSettings.update(self.__ConvertXmlToDict(filename))
            return True
        except TypeError as err:
            return err
    
    def saveConfig(self, filename):
        _logger.debug('save configurations to file: {}'.format(filename))
        root = self.__ConvertDictToXml(self.mSettings)
        tree = ElementTree(root)
        tree.write(open(filename, 'w'), encoding='uft-8')
    
    def __ConvertXmlToDict(self, root, dictclass=XmlDictObject):
        """
        Converts an XML file or ElementTree Element to a dictionary
        """
        def __ConvertXmlToDictRecurse(node, dictclass):
            nodedict = dictclass()
            if len(node.items()) > 0:
                # if we have attributes, set them
                nodedict.update(dict(node.items()))
            for child in node:
                # recursively add the element's children
                newitem = __ConvertXmlToDictRecurse(child, dictclass)
                if child.tag in nodedict:
                    # found duplicate tag, force a list
                    if type(nodedict[child.tag]) is type([]):
                        # append to existing list
                        nodedict[child.tag].append(newitem)
                    else:
                        # convert to list
                        nodedict[child.tag] = [nodedict[child.tag], newitem]
                else:
                    # only one, directly set the dictionary
                    nodedict[child.tag] = newitem
            if node.text is None: 
                text = ''
            else: 
                text = node.text.strip()
            if len(nodedict) > 0:            
                # if we have a dictionary add the text as a dictionary value (if there is any)
                if len(text) > 0:
                    nodedict['_text'] = text
            else:
                # if we don't have child nodes or attributes, just set the text
                nodedict = text
            return nodedict
    
        # If a string is passed in, try to open it as a file
        # isinstance(root, basestring) # old python style
        if isinstance(root, str): # or isinstance(root, unicode): # python3 are all unicodes
            if not isfile(root):
                raise IOError('Configuration File Does Not Exist!')
            # use element tree to parse the filename, and assigned the root
            tree = etree.parse(root)
            root = tree.getroot()
        elif not isinstance(root, ElementTree.Element):
            raise TypeError('Expected ElementTree.Element or file path string')
        return dictclass({root.tag: __ConvertXmlToDictRecurse(root, dictclass)})

    def __ConvertDictToXml(self, xmldict):
        """
        Converts a dictionary to an XML ElementTree Element 
        """
        def __ConvertDictToXmlRecurse(parent, dictitem):
            assert type(dictitem) is not type([])
            if isinstance(dictitem, dict):
                for (tag, child) in dictitem.items():
                    if str(tag) == '_text':
                        parent.text = str(child)
                    elif type(child) is type([]):
                        # iterate through the array and convert
                        for listchild in child:
                            elem = ElementTree.Element(tag)
                            parent.append(elem)
                            __ConvertDictToXmlRecurse(elem, listchild)
                    else:                
                        elem = etree.Element(tag)
                        parent.append(elem)
                        __ConvertDictToXmlRecurse(elem, child)
            else:
                parent.text = str(dictitem)
    
        roottag = xmldict.keys()[0]
        root = etree.Element(roottag)
        __ConvertDictToXmlRecurse(root, xmldict[roottag])
        return root

    def getSettings(self, key=None, flatten=False):
        ret = {}
        ret.update(self.mSettings)
        if isinstance(key, str):
            return self.__find(key, ret)
        if flatten:
            return self.__flatten(ret)
        return ret
    
    def setSetting(self, changed):
        # check validify of changed dictionary
        try:
            if (self.__checkSetting(changed)):
                self.mSettings.update(changed)
                return True
        except TypeError as err:
            return err

    def __checkSetting(self, changed):
        if isinstance(changed, dict):
            # TODO:
            # you can access the data as a dictionary
            # print changed['settings']['color']
            # changed['settings']['color'] = 'red'
            # TODO: Write checking logics here
            
            return True
        elif isinstance(changed, XmlDictObject):
            # TODO:
            # or you can access it like object attributes
            # print configdict.settings.color
            # configdict.settings.color = 'red'
            # TODO: Write checking logics here
            
            return True
        else:
            raise TypeError('Expected Dictionary or XmlDictObject')

    def __find(self, key, value):
        ret = {}
        if isinstance(value, dict):
            for k, v in value.items():
                if k == key:
                    ret[k] = v
                elif isinstance(v, dict):
                    ret.update(self.__find(key, v))
                elif isinstance(v, list):
                    for d in v:
                        if isinstance(d, dict):
                            more = self.__find(key, d)
                            for r in more:
                                ret.update(self.__find(key,r))
        return ret

    def __flatten(self, value):
        ret = {}
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, dict):
                    ret.update(self.__flatten(v))
                else:
                    ret[k] = v
        return ret

if __name__ == "__main__":
    defconf = DefConfig()
    defconf.loadConfig("/etc/installer.xml")
    settings = defconf.getSettings()
    print(settings)
    settings.update({'MESSENGER_CLIENT': True})
    defconf.setSetting(settings)
    settings = defconf.getSettings('server_busname')
    print(settings)
    settings = defconf.getSettings('server_name')
    print(settings)
    settings = defconf.getSettings(flatten=True)
    print(settings)
    defconf.saveConfig("./installer.xml")
    exit()