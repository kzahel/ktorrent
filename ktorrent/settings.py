import os
import bencode
import logging
from tornado.options import options

def get_deep(keys, d):
    if len(keys) == 0:
        return d
    else:
        if keys[0] in d:
            return get_deep( keys[1:], d[keys[0]] )
        else:
            raise KeyError

assert get_deep(['foo'],{'foo':99}) == 99
assert get_deep(['foo','bar'],{'foo':{'bar':23}}) == 23
assert get_deep(['foo'],{'foo':{'bar':23}}) == {'bar':23}

def set_deep(keys, value, d):
    # i.e. if d = {}, keys = ['hello','foo'], val = 3
    # then updates d to {'hello': {'foo': 3 }}

    for i in range(len(keys)):
        l = keys[:i+1]
        try:
            val = get_deep(l, d)
            if i == len(keys)-1:
                # final thing!
                get_deep(keys[:-1], d)[keys[-1]] = value
            elif type(val) == type({}):
                pass
            else:
                raise KeyError
        except KeyError:
            if i == len(keys)-1:
                get_deep(keys[:i], d)[keys[i]] = value
            else:
                get_deep(keys[:i], d)[keys[i]] = {}

d = {}        
set_deep(['foo'], 3, d)
assert d == {'foo':3}

d = {'foo':3}
set_deep(['foo','bar'], 99, d)
assert d == {'foo':{'bar':99}}

d = {}
set_deep(['foo','bar','bob','baz'], 23, d)
assert d == {'foo': {'bar': {'bob': {'baz': 23}}}}

set_deep(['foo','bar','woooooooo','hooo'],44, d)
assert d == {'foo': {'bar': {'bob': {'baz': 23}, 'woooooooo': {'hooo': 44}}}}

d = {}
set_deep(['torrents','aa','attributes'],{'bob':1}, d)
assert d == {'torrents':{'aa':{'attributes':{'bob':1}}}}
set_deep(['torrents','aa','attributes'],{'bob':0}, d)
assert d == {'torrents':{'aa':{'attributes':{'bob':0}}}}

class Settings(object):
    # todo -- fix so get/set don't write, but separate flush function
    _data = {}

    @classmethod
    def load(cls):
        if os.path.exists( options.resume_file ):
            fo = open(options.resume_file)
            try:
                raw = fo.read()
                resume_data = bencode.bdecode( raw )
                cls._data = resume_data
            except:
                logging.error('error loading resume data %s' % raw)
                cls._data = {}
        else:
            cls._data = {}

    @classmethod
    def flush(cls):
        fo = open( options.resume_file, 'w' )
        #logging.info('writing settings %s' % cls._data)
        fo.write( bencode.bencode(cls._data) )
        fo.close()

    @classmethod
    def get(cls, key=None):
        if key is None:
            return cls._data
        elif type(key) == type([]):
            return get_deep(key, cls._data)
        elif key in cls._data:
            return cls._data[key]

    @classmethod
    def set(cls, key, value):
        if type(key) == type([]):
            set_deep(key, value, cls._data)
        else:
            cls._data[key] = value

