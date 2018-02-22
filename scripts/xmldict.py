#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from lxml import etree
from lxml.etree import ElementTree
from os.path import isfile


class XmlDict(dict):
    """
    XmlDict object allow dict items to act like Xml object
    Also add Object like functionality to dict for handling XML attributes.
    """
    def __init__(self, initdict=None):
        if initdict is None:
            initdict = {}
        super().__init__(initdict)

    def __getattr__(self, key):
        """
        override fallback __getattr__ to get XML tag's attributes
        by calling dict's magic __getitem__ method
        Examples:
            >>> a = XmlDict()
            >>> a.fish = 'fish'
            >>> a['fish']
            'fish'
            >>> a['water'] = 'water'
            >>> a.water
            'water'
            >>> a.test = {'value': 1}
            >>> a.test2 = XmlDict({'name': 'test2', 'value': 2})
            >>> a.test, a.test2.name, a.test2.value
            (1, 'test2', 2)
        """
        value = self.__getitem__(key)
        # if value is the only key in object, it can be omited
        if isinstance(value, dict) and value.keys() == ['value']:
            return value['value']
        else:
            return value
    
    def __setattr__(self, item, value):
        """
        override the magic __setattr__ to set XML tag's attributes
        to the dict by calling dict's magic __setitem__ method
        """
        self.__setitem__(item, value)
    
    def __str__(self):
        """
        get the output for print
        - for XmlNode it means extracting the _text node's value
        """
        if '_text' in self:
            return self.__getitem__('_text')
        else:
            return ''

    @staticmethod
    def __Wrap(x):
        """
        Static method to wrap a XmlDict
        """
        if isinstance(x, dict):
            return XmlDict((k, XmlDict.__Wrap(v)) for (k, v) in x.items())
        elif isinstance(x, list):
            return [XmlDict.__Wrap(v) for v in x]
        else:
            return x

    @staticmethod
    def __UnWrap(x):
        """
        Static method to unwrap a XmlDict
        """
        if isinstance(x, dict):
            return dict((k, XmlDict.__UnWrap(v)) for (k, v) in x.items())
        elif isinstance(x, list):
            return [XmlDict.__UnWrap(v) for v in x]
        else:
            return x

def ConvertXmlToDict(root, dictclass=XmlDict):
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
                # found existing duplicate tag which is of type list, force append to the list
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

def ConvertDictToXml(xmldict):
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
