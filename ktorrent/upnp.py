# example of how to use miniupnp

import miniupnpc
u=miniupnpc.UPnP()
u.discoverdelay=2000
i = u.discover()
if i>0:
    print 'found',i
    import pdb; pdb.set_trace()
    url = u.selectigd()
    external = 31226
    internal = 22
    result=u.addportmapping(external, 'TCP', u.lanaddr, internal)
else:
    print 'no devices discovered'
