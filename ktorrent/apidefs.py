class TorrentDef(object):
    coldefs = [
            { 'name': 'hash' },
            { 'name': 'status', 'type': 'int' , 'bits': ['started', 'checking', 'start after check', 'checked', 'error', 'paused', 'queued', 'loaded'] },
            { 'name': 'name' },
            { 'name': 'size', 'type': 'int' },
            { 'name': 'progress', 'type': 'int' },
            { 'name': 'downloaded', 'type': 'int' },
            { 'name': 'uploaded', 'type': 'int' },
            { 'name': 'ratio', 'type': 'int' },
            { 'name': 'up_speed', 'type': 'int' },
            { 'name': 'down_speed', 'type': 'int' },
            { 'name': 'eta', 'type': 'int' },
            { 'name': 'label' },
            { 'name': 'peers_connected', 'type': 'int' },
            { 'name': 'peers_swarm', 'type': 'int', 'alias': 'peers_in_swarm' },
            { 'name': 'seed_connected', 'type': 'int', 'alias': 'seeds_connected' },
            { 'name': 'seed_swarm', 'type': 'int', 'alias': 'seeds_in_swarm' },
            { 'name': 'availability', 'type': 'int' },
            { 'name': 'queue_position', 'type': 'int', 'alias': 'queue_order' },
            { 'name': 'remaining', 'type': 'int' },
            { 'name': 'download_url' },
            { 'name': 'rss_feed_url' },
            { 'name': 'message' },
            { 'name': 'stream_id' },
            { 'name': 'added_on', 'type': 'int' },
            { 'name': 'completed_on', 'type': 'int' },
            { 'name': 'app_update_url' },
            { 'name': 'directory' },
            { 'name': 'webseed_enabled' }
            ]
    coldefnames = {}
    for i,v in enumerate(coldefs):
        coldefnames[v['name']] = i
