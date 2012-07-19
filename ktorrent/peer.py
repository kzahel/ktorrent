import logging

class Peer(object):
    instances = {}

    def __init__(self, peerid):
        self.id = peerid

    @classmethod
    def instantiate(cls, peerid):
        logging.warn('instantiate peer with id %s' % [peerid])
        if peerid in cls.instances:
            instance = cls.instances[peerid]
        else:
            instance = cls(peerid)
            cls.instances[peerid] = instance
        return instance
