import os
import bencode
import logging
from tornado.options import options

class Settings(object):
    # todo -- fix so get/set don't write, but separate flush function
    _data = {}

    @classmethod
    def flush(cls):
        pass

    @classmethod
    def get(cls, key=None):
        if os.path.exists( options.resume_file ):
            fo = open(options.resume_file)
            resume_data = bencode.bdecode( fo.read() )
            if key is None:
                return resume_data
            elif key in resume_data:
                return resume_data[key]

    @classmethod
    def set(cls, key, value):
        if os.path.exists( options.resume_file ):
            fo = open(options.resume_file)
            resume_data = bencode.bdecode( fo.read() )
            fo.close()

            resume_data[str(key)] = value

            fo = open( options.resume_file, 'w' )
            #logging.info('writing settings %s' % resume_data)
            fo.write( bencode.bencode(resume_data) )
            fo.close()

