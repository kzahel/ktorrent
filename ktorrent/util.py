import logging
import os
from tornado.options import options
from hashlib import sha1
import bencode
import pdb
import binascii

def decode_peer(bytes):
    assert len(bytes) == 6
    ip = '.'.join( map(str, ( map(ord, bytes[:4]) ) ) )
    port = ord(bytes[4]) * 256 + ord(bytes[5])
    return ip, port

def hexlify(s):
    return binascii.hexlify(s).upper()

def debugmethod(func):
    '''Decorator to print function call details - parameters names and effective values'''
    def wrapper(*func_args, **func_kwargs):
        #print 'func_code.co_varnames =', func.func_code.co_varnames
        #print 'func_code.co_argcount =', func.func_code.co_argcount
        #print 'func_args =', func_args
        #print 'func_kwargs =', func_kwargs
        params = []
        for argNo in range(func.func_code.co_argcount):
            argName = func.func_code.co_varnames[argNo]
            argValue = func_args[argNo] if argNo < len(func_args) else func.func_defaults[argNo - func.func_code.co_argcount]
            params.append((argName, argValue))
        for argName, argValue in func_kwargs.items():
            params.append((argName, argValue))
        params = [ argName + ' = ' + repr(argValue) for argName, argValue in params]
        logging.info(' DEBUGMETHOD: %s' % func.__name__ + ' ( ' +  ', '.join(params) + ' )' )
        return func(*func_args, **func_kwargs)
    return wrapper

def parse_bitmask(torrent, data):
    pieces = []
    for byte in data:
        l = map(int, list(bin(ord(byte))[2:]))
        p = [0] * (8 - len(l))
        if p:
            l = p + l
        pieces += l

    extra_pad = len(pieces) - torrent.get_num_pieces()
    for _ in range(extra_pad):
        pieces.pop()

    return pieces

class MetaStorage(object):
    ''' stores filenames for infohashes '''

    data = None
    @classmethod
    def sync(cls):
        logging.warn('metastorage sync!')
        if cls.data is None:
            if os.path.exists( options.resume_file ):
                fo = open( options.resume_file )
                cls.data = bencode.bdecode(fo.read())
                fo.close()
            else:
                cls.data = {}
        else:
            fo = open( options.resume_file, 'w' )
            fo.write( bencode.bencode(cls.data) )
            fo.close()

    @classmethod
    def keys(cls):
        return cls.data.keys()

    @classmethod
    def get(cls, infohash):
        if infohash in cls.data:
            attributes = cls.data[infohash]
            filename = attributes['filename']
            if os.path.exists( os.path.join( options.datapath, filename ) ):
                return filename
            else:
                logging.error('could not locate torrent file on disk!')
                del cls.data[infohash]
                cls.sync()

    @classmethod
    def insert(cls, torrent):
        torrent_meta = torrent.meta
        filename = torrent_meta['info']['name'] + '.torrent'
        cls.data[ torrent.hash ] = { 'filename': filename }
        fo = open( os.path.join(options.datapath, filename), 'w')
        fo.write( bencode.bencode(torrent_meta) )
        fo.close()
        cls.sync()
