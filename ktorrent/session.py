import random
import logging
from tornado.options import options
import re
fnre = re.compile('btapp/torrent/all/([A-Fa-f0-9]{40})/([^/.]*)')
def create_update_add_remove_trees(changes, add, remove, key=None):
    # creates or updates add/remove trees
    if type(changes) == type({}):
        
        for k in changes:
            if k not in add:
                add[k] = {}
            if k not in remove:
                remove[k] = {}

            create_update_add_remove_trees(changes[k], add[k], remove[k], k)

    elif type(changes) == type([]): # leaf changes node
        add[key] = changes[1]
        remove[key] = changes[0]
    else:
        logging.error('hmmmmmm')
    

class Session(object):
    instances = {}

    def __init__(self, client):
        self.id = str(random.randrange(0,200))
        self.client = client
        self._seq = 0
        self.state = None
        self.state_add = {}
        self.state_remove = {}

    def compute_changes(self):
        add = {}
        remove = {}
        for hash, torrent in self.client.torrents.iteritems():

            if hash not in self.state['btapp']['torrent']['all']:
                dump = torrent.dump_state()
                if 'btapp' in add:
                    add['btapp']['torrent']['all'][hash] = dump
                else:
                    add['btapp'] = {'torrent':{'all':{hash:dump}}}
                self.state['btapp']['torrent']['all'][hash] = dump
            else:
                a, r = torrent.update_attributes(self.state['btapp']['torrent']['all'][hash])
                if a and r:
                    if options.verbose > 2:
                        logging.info('tor update attr ret %s %s' % (a,r))
                    if 'btapp' not in add:
                        add['btapp'] = {'torrent':{'all':{}}}
                        remove['btapp'] = {'torrent':{'all':{}}}

                    add['btapp']['torrent']['all'][hash] = a
                    remove['btapp']['torrent']['all'][hash] = r

        toremove = []
        for hash in self.state['btapp']['torrent']['all']:
            if hash not in self.client.torrents:
                if 'btapp' not in remove:
                    remove['btapp'] = {'torrent':{'all':{}}}

                # torrent was removed
                remove['btapp']['torrent']['all'][hash] = self.state['btapp']['torrent']['all'][hash]
                toremove.append(hash)
        for hash in toremove:
            del self.state['btapp']['torrent']['all'][hash]

        return add, remove

    def populate(self):
        self.state = {'btapp':{'torrent':{'all':{}},
                               'add':{'torrent':"[nf](string)(string,string)"}
                               }}
        for hash,torrent in self.client.torrents.iteritems():
            self.state['btapp']['torrent']['all'][hash] = torrent.dump_state()
        return self.state

    def process_changes(self, changes):
        logging.info('process changes %s' % changes)
        create_update_add_remove_trees(changes, self.state_add, self.state_remove)
        print self.state_add
        print self.state_remove
    
    def handle_add(self):
        #self.state['btapp']
        pass
            
    @classmethod
    def get(cls, id):
        if id in cls.instances:
            return cls.instances[id]
        
    @classmethod
    def create(cls, client):
        sess = cls(client)

        client.sessions[sess.id] = sess
        cls.instances[sess.id] = sess

        logging.info('created btapp session with id %s' % sess.id)
        return sess

    def handle_function(self, data):
        logging.info('handle function %s' % data)
        path = data['path']
        args = data['args']

        res = fnre.match(path)

        if path == 'btapp/add/torrent':
            self.client.add_torrent_any(args[0])
        elif res:
            hash, command = res.groups()
            torrent = self.client.torrents[hash]
            if torrent:
                if command == 'remove':
                    self.client.remove_torrent( hash )
                elif command == 'stop':
                    torrent.set_attribute('status', 0)
                elif command == 'start':
                    torrent.set_attribute('status', 1)
                else:
                    logging.error('unhandled torrent command %s' % command)
                    return {'error':'unhandled torrent function'}
            else:
                return {'error':'torrent not in client'}
        else:
            logging.error('unrecognized function')
            return {'error':'unrecognized function'}

            
        return {'ok':'thanks'}

    @classmethod
    def notify(self, client=None, added=None):
        logging.warn('notify sessions! %s %s' % (client, added))
        
    def get_update(self):
        if self._seq == 0:
            data = self.populate()
            data = [ {'add': data } ]
        else:
            add, remove = self.compute_changes()
            data = {}
            if add:
                data['add'] = add
            if remove:
                data['remove'] = remove
            if data:
                if options.verbose > 3:
                    logging.info('change data %s' % data)
                data = [data]
        self._seq += 1
        return data
