import logging

class Peer(object):
    instances_compact = {}
    instances_peerid = {}

    pex_flags = ['default', 'prefer_encrypt', 'is_seeder']

    def __init__(self, data):
        self.data = data
        self.flags = None

    def add_flags(self, flags):
        self.flags = flags

    @classmethod
    def instantiate(cls, data):
        if 'compact' in data:
            key = data['compact']
            if key in cls.instances_compact:
                instance = cls.instances_compact[key]
            else:
                instance = cls(data)
                cls.instances_compact[key] = instance
            return instance
        elif 'peerid' in data:
            key = data['peerid']
            if key in cls.instances_peerid:
                instance = cls.instances_peerid[key]
            else:
                instance = cls(data)
                cls.instances_peerid[key] = instance
            return instance
        else:
            logging.error('error instantiating peer')
            if options.asserts:
                import pdb; pdb.set_trace()
